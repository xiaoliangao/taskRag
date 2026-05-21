"""Cross-topic QA (v1.4 Sprint 7).

Lets a user ask one question across multiple of *their own* topics.
Security: caller MUST verify ownership upfront (see qa_cross route).
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.document import Chunk
from app.db.models.topic import Topic
from app.indexer.embedder import get_embedder
from app.indexer.qdrant_client import search_for_topics
from app.rag.reranker import get_reranker
from app.rag.retriever import Citation, _freshness, _parse_dt, _rrf_fuse

log = logging.getLogger(__name__)


async def _vector_search_cross(
    *,
    topic_ids: Sequence[int],
    query: str,
    top_k: int,
) -> list[tuple[str, float, dict[str, Any]]]:
    embedder = get_embedder()
    try:
        vec = embedder.embed_query(query)
    except Exception as exc:
        log.error("cross-topic embedding failed: %s", exc)
        return []
    try:
        hits = search_for_topics(topic_ids=list(topic_ids), query_vector=vec, top_k=top_k)
    except Exception as exc:
        log.error("cross-topic qdrant search failed: %s", exc)
        return []
    return [(str(h.id), float(h.score), h.payload or {}) for h in hits]


async def _bm25_search_cross(
    *,
    db: AsyncSession,
    topic_ids: Sequence[int],
    query: str,
    top_k: int,
) -> list[tuple[int, float]]:
    if not (query or "").strip() or not topic_ids:
        return []
    stmt = text(
        """
        SELECT c.id, ts_rank_cd(c.text_tsv, q) AS rank
          FROM chunks c
          JOIN topic_documents td ON td.document_id = c.document_id,
               plainto_tsquery('english', :query) AS q
         WHERE td.topic_id = ANY(:topic_ids)
           AND c.text_tsv @@ q
           AND c.is_parent = false
         ORDER BY rank DESC
         LIMIT :limit
        """
    )
    try:
        res = await db.execute(
            stmt, {"query": query, "topic_ids": list(topic_ids), "limit": top_k}
        )
    except Exception as exc:
        log.warning("cross-topic BM25 failed: %s", exc)
        return []
    return [(int(r.id), float(r.rank)) for r in res.all()]


async def retrieve_cross_topic(
    *,
    db: AsyncSession,
    topic_ids: Sequence[int],
    query: str,
    top_n: int | None = None,
) -> list[Citation]:
    """Hybrid retrieval across multiple owned topics."""
    if not topic_ids:
        return []
    s = get_settings()
    top_n = top_n or max(s.rerank_top_n, 8)
    top_k = max(s.vector_top_k, 50)

    vec_hits, bm25_hits = await asyncio.gather(
        _vector_search_cross(topic_ids=topic_ids, query=query, top_k=top_k),
        _bm25_search_cross(db=db, topic_ids=topic_ids, query=query, top_k=50),
    )
    if not vec_hits and not bm25_hits:
        return []

    # Hydrate chunks
    vec_uuids: list[UUID] = []
    payload_by_vid: dict[str, dict[str, Any]] = {}
    for vid, _sc, payload in vec_hits:
        try:
            vec_uuids.append(UUID(vid))
            payload_by_vid[vid] = payload
        except Exception:
            continue
    bm25_ids = [cid for cid, _ in bm25_hits]

    chunks_by_id: dict[int, Chunk] = {}
    chunks_by_vid: dict[str, Chunk] = {}
    if vec_uuids:
        rows = (await db.execute(select(Chunk).where(Chunk.vector_id.in_(vec_uuids)))).scalars().all()
        for c in rows:
            chunks_by_id[c.id] = c
            chunks_by_vid[str(c.vector_id)] = c
    if bm25_ids:
        missing = [cid for cid in bm25_ids if cid not in chunks_by_id]
        if missing:
            rows = (await db.execute(select(Chunk).where(Chunk.id.in_(missing)))).scalars().all()
            for c in rows:
                chunks_by_id[c.id] = c
                chunks_by_vid[str(c.vector_id)] = c

    # RRF fuse on chunk.id
    vec_ranking: list[tuple[int, float]] = []
    for vid, sc, _p in vec_hits:
        chunk = chunks_by_vid.get(vid)
        if chunk is not None:
            vec_ranking.append((chunk.id, sc))
    fused = _rrf_fuse([vec_ranking, bm25_hits])
    if not fused:
        return []

    rerank_pool = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[: max(top_k, top_n * 4)]

    # Pull topic name per chunk via topic_documents
    chunk_ids = [cid for cid, _ in rerank_pool]
    topic_by_chunk: dict[int, tuple[int, str]] = {}
    if chunk_ids:
        rows = await db.execute(
            text(
                """
                SELECT c.id AS chunk_id, td.topic_id, t.name AS topic_name
                  FROM chunks c
                  JOIN topic_documents td ON td.document_id = c.document_id
                  JOIN topics t ON t.id = td.topic_id
                 WHERE c.id = ANY(:chunk_ids) AND td.topic_id = ANY(:topic_ids)
                """
            ),
            {"chunk_ids": chunk_ids, "topic_ids": list(topic_ids)},
        )
        for row in rows.all():
            # If a chunk's document is linked to multiple of the user's topics,
            # we just keep the first (deterministic enough for UI).
            topic_by_chunk.setdefault(int(row.chunk_id), (int(row.topic_id), row.topic_name))

    citations: list[Citation] = []
    now = datetime.now(tz=UTC)
    for chunk_id, fused_score in rerank_pool:
        chunk = chunks_by_id.get(chunk_id)
        if chunk is None:
            continue
        vid = str(chunk.vector_id)
        payload = payload_by_vid.get(vid, {})
        topic_meta = topic_by_chunk.get(chunk_id)
        cit = Citation(
            document_id=int(payload.get("document_id") or chunk.document_id),
            chunk_id=chunk.id,
            title=str(payload.get("title") or ""),
            url=str(payload.get("url") or ""),
            source=str(payload.get("source") or ""),
            published_at=_parse_dt(payload.get("published_at")),
            section_title=payload.get("section_title") or chunk.section_title,
            page_start=payload.get("page_start") or chunk.page_start,
            page_end=payload.get("page_end") or chunk.page_end,
            score=fused_score,
            text=chunk.text,
        )
        # Stash topic info on the dict-form returned later
        if topic_meta is not None:
            cit_extra = {"topic_id": topic_meta[0], "topic_name": topic_meta[1]}
            setattr(cit, "_cross_topic", cit_extra)  # type: ignore[attr-defined]
        citations.append(cit)

    # Rerank
    reranker = get_reranker()
    scores = reranker.rerank(query, [c.text for c in citations]) if citations else None
    for i, c in enumerate(citations):
        base = scores[i] if scores else c.score
        c.score = float(base) * 0.8 + _freshness(c.published_at, now) * 0.2

    citations.sort(key=lambda c: c.score, reverse=True)

    # Dedup by document
    seen: set[int] = set()
    deduped: list[Citation] = []
    for c in citations:
        if c.document_id in seen:
            continue
        seen.add(c.document_id)
        deduped.append(c)
    return deduped[:top_n]


async def list_user_topic_ids(db: AsyncSession, user_id: int) -> list[int]:
    rows = await db.execute(select(Topic.id).where(Topic.user_id == user_id))
    return [r[0] for r in rows.all()]


__all__ = ["retrieve_cross_topic", "list_user_topic_ids"]
