from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models.document import Chunk
from app.indexer.embedder import get_embedder
from app.indexer.qdrant_client import search_for_topic
from app.rag.reranker import get_reranker

log = logging.getLogger(__name__)


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
        published_at = published_at.replace(tzinfo=timezone.utc)
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


async def retrieve_for_topic(
    *,
    db: AsyncSession,
    topic_id: int,
    query: str,
    top_k: int | None = None,
    top_n: int | None = None,
) -> list[Citation]:
    s = get_settings()
    top_k = top_k or s.vector_top_k
    top_n = top_n or s.rerank_top_n

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

    if not results:
        return []

    # Hydrate chunk text from Postgres (chunks aren't stored in Qdrant payload).
    chunk_ids: list[int] = []
    payload_by_chunk: dict[int, dict[str, Any]] = {}
    # qdrant point id is the chunk vector_id (UUID); we need to look up by vector_id.
    vector_ids: list[str] = []
    for r in results:
        vid = str(r.id)
        vector_ids.append(vid)
        payload_by_chunk[len(vector_ids) - 1] = {"score": float(r.score), "payload": r.payload or {}}

    from uuid import UUID

    uuid_list = []
    for vid in vector_ids:
        try:
            uuid_list.append(UUID(vid))
        except Exception:
            continue

    rows = []
    if uuid_list:
        result = await db.execute(select(Chunk).where(Chunk.vector_id.in_(uuid_list)))
        rows = list(result.scalars().all())
    chunks_by_vid = {str(c.vector_id): c for c in rows}

    # Build initial citations preserving Qdrant order
    citations: list[Citation] = []
    now = datetime.now(tz=timezone.utc)
    for idx, vid in enumerate(vector_ids):
        chunk = chunks_by_vid.get(vid)
        info = payload_by_chunk[idx]
        payload = info["payload"]
        if chunk is None:
            text = ""
        else:
            text = chunk.text
        citations.append(
            Citation(
                document_id=int(payload.get("document_id") or (chunk.document_id if chunk else 0)),
                chunk_id=chunk.id if chunk else None,
                title=str(payload.get("title") or ""),
                url=str(payload.get("url") or ""),
                source=str(payload.get("source") or ""),
                published_at=_parse_dt(payload.get("published_at")),
                section_title=payload.get("section_title") or (chunk.section_title if chunk else None),
                page_start=payload.get("page_start") or (chunk.page_start if chunk else None),
                page_end=payload.get("page_end") or (chunk.page_end if chunk else None),
                score=info["score"],
                text=text,
            )
        )

    # Rerank (best-effort)
    reranker = get_reranker()
    rerank_scores = reranker.rerank(query, [c.text for c in citations]) if citations else None

    # Combine score: rerank * 0.8 + freshness * 0.2 (per dev doc §12.2)
    for i, cit in enumerate(citations):
        base = rerank_scores[i] if rerank_scores else cit.score
        freshness = _freshness(cit.published_at, now)
        cit.score = float(base) * 0.8 + freshness * 0.2

    citations.sort(key=lambda c: c.score, reverse=True)
    return citations[:top_n]
