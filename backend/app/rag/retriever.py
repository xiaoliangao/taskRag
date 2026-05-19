from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.document import Chunk
from app.indexer.embedder import get_embedder
from app.indexer.qdrant_client import search_for_topic
from app.rag.reranker import get_reranker

log = logging.getLogger(__name__)

# Retrieval config (v1.4)
_BM25_TOP_K = 50
_VECTOR_TOP_K_DEFAULT = 50
_RRF_K = 60  # RRF dampening constant (60 is the classic value)


@dataclass
class Citation:
    document_id: int
    chunk_id: int | None
    title: str
    url: str
    source: str
    published_at: datetime | None
    section_title: str | None
    page_start: int | None
    page_end: int | None
    score: float
    text: str

    def to_dict(self, *, drop_text: bool = False) -> dict[str, Any]:
        d: dict[str, Any] = {
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "section_title": self.section_title,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "score": round(self.score, 4),
        }
        if not drop_text:
            d["text"] = self.text
        return d


def _freshness(published_at: datetime | None, now: datetime) -> float:
    if published_at is None:
        return 0.5
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    days = max(0.0, (now - published_at).total_seconds() / 86400.0)
    return math.exp(-days / 365.0)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


async def _vector_search_chunks(
    *,
    topic_id: int,
    query: str,
    top_k: int,
) -> list[tuple[str, float, dict[str, Any]]]:
    """Run Qdrant vector search. Returns list of (vector_id_str, score, payload).

    Failures are logged and downgraded to an empty list — callers fall back to BM25.
    """
    embedder = get_embedder()
    try:
        query_vec = embedder.embed_query(query)
    except Exception as exc:
        log.error("Embedding query failed: %s", exc)
        return []
    try:
        results = search_for_topic(topic_id=topic_id, query_vector=query_vec, top_k=top_k)
    except Exception as exc:
        log.error("Qdrant search failed: %s", exc)
        return []
    return [(str(r.id), float(r.score), r.payload or {}) for r in results]


async def _bm25_search_chunks(
    *,
    db: AsyncSession,
    topic_id: int,
    query: str,
    top_k: int,
) -> list[tuple[int, float]]:
    """Run PostgreSQL full-text BM25 search scoped to the topic.

    Uses the v1.4 `chunks.text_tsv` generated column + GIN index. Returns list of
    (chunk_id, ts_rank_cd_score). Silently returns [] if the column is missing
    (e.g. migration 0009 not yet applied).
    """
    if not (query or "").strip():
        return []
    stmt = text(
        """
        SELECT c.id, ts_rank_cd(c.text_tsv, q) AS rank
          FROM chunks c
          JOIN topic_documents td ON td.document_id = c.document_id,
               plainto_tsquery('english', :query) AS q
         WHERE td.topic_id = :topic_id
           AND c.text_tsv @@ q
         ORDER BY rank DESC
         LIMIT :limit
        """
    )
    try:
        res = await db.execute(stmt, {"query": query, "topic_id": topic_id, "limit": top_k})
    except Exception as exc:
        log.warning("BM25 search failed (column missing or PG error): %s", exc)
        return []
    return [(int(row.id), float(row.rank)) for row in res.all()]


def _rrf_fuse(
    rankings: list[list[tuple[Any, float]]],
    *,
    k: int = _RRF_K,
) -> dict[Any, float]:
    """Reciprocal Rank Fusion across N rankings.

    For each item, RRF score = sum over rankings of 1/(k + rank). Items absent
    from a ranking contribute 0.
    """
    scores: dict[Any, float] = {}
    for ranking in rankings:
        for rank, (item_id, _raw_score) in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return scores


async def retrieve_for_topic(
    *,
    db: AsyncSession,
    topic_id: int,
    query: str,
    top_k: int | None = None,
    top_n: int | None = None,
    dedup_by_document: bool = True,
) -> list[Citation]:
    """Hybrid retrieval: BM25 + vector → RRF → rerank → freshness fuse → optional dedup.

    `top_k` controls per-source candidate pool. `top_n` is the final cap.
    """
    s = get_settings()
    top_k = top_k or max(s.vector_top_k, _VECTOR_TOP_K_DEFAULT)
    top_n = top_n or s.rerank_top_n

    # 1) parallel BM25 + vector search
    vector_hits, bm25_hits = await asyncio.gather(
        _vector_search_chunks(topic_id=topic_id, query=query, top_k=top_k),
        _bm25_search_chunks(db=db, topic_id=topic_id, query=query, top_k=_BM25_TOP_K),
    )

    if not vector_hits and not bm25_hits:
        return []

    # 2) Hydrate Chunk rows for all candidate ids.
    #    Vector hits use vector_id (UUID); BM25 uses chunk.id directly.
    from uuid import UUID

    vector_uuids: list[UUID] = []
    payload_by_vid: dict[str, dict[str, Any]] = {}
    score_by_vid: dict[str, float] = {}
    for vid, sc, payload in vector_hits:
        try:
            vector_uuids.append(UUID(vid))
            score_by_vid[vid] = sc
            payload_by_vid[vid] = payload
        except Exception:
            continue

    bm25_chunk_ids = [cid for cid, _ in bm25_hits]
    bm25_score_by_id = {cid: sc for cid, sc in bm25_hits}

    # Single query: pull all chunks needed (union of vector + bm25 ids).
    chunks_by_vid: dict[str, Chunk] = {}
    chunks_by_id: dict[int, Chunk] = {}
    if vector_uuids:
        r1 = await db.execute(select(Chunk).where(Chunk.vector_id.in_(vector_uuids)))
        for c in r1.scalars().all():
            chunks_by_vid[str(c.vector_id)] = c
            chunks_by_id[c.id] = c
    if bm25_chunk_ids:
        missing_ids = [cid for cid in bm25_chunk_ids if cid not in chunks_by_id]
        if missing_ids:
            r2 = await db.execute(select(Chunk).where(Chunk.id.in_(missing_ids)))
            for c in r2.scalars().all():
                chunks_by_id[c.id] = c
                chunks_by_vid[str(c.vector_id)] = c

    # 3) RRF fuse on chunk.id
    vec_ranking_by_id: list[tuple[int, float]] = []
    for vid, sc, _ in vector_hits:
        chunk = chunks_by_vid.get(vid)
        if chunk is not None:
            vec_ranking_by_id.append((chunk.id, sc))
    fused = _rrf_fuse([vec_ranking_by_id, bm25_hits])
    if not fused:
        return []

    # 4) Build Citation objects for top fused candidates (a generous pool for rerank).
    rerank_pool = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[: max(top_k, top_n * 4)]
    citations: list[Citation] = []
    now = datetime.now(tz=UTC)
    for chunk_id, fused_score in rerank_pool:
        chunk = chunks_by_id.get(chunk_id)
        if chunk is None:
            continue
        # Find the matching qdrant payload (preferred) or fallback to chunk fields.
        vid = str(chunk.vector_id)
        payload = payload_by_vid.get(vid, {})
        citations.append(
            Citation(
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
        )

    if not citations:
        return []

    # 5) Cross-encoder rerank on the pool.
    reranker = get_reranker()
    rerank_scores = reranker.rerank(query, [c.text for c in citations]) if citations else None

    # 6) Final score: rerank * 0.8 + freshness * 0.2
    for i, cit in enumerate(citations):
        base = rerank_scores[i] if rerank_scores else cit.score
        freshness = _freshness(cit.published_at, now)
        cit.score = float(base) * 0.8 + freshness * 0.2

    citations.sort(key=lambda c: c.score, reverse=True)

    # 7) Optional document-level dedup: keep highest-scoring chunk per document.
    if dedup_by_document:
        seen_docs: set[int] = set()
        deduped: list[Citation] = []
        for c in citations:
            if c.document_id in seen_docs:
                continue
            seen_docs.add(c.document_id)
            deduped.append(c)
        citations = deduped

    return citations[:top_n]
