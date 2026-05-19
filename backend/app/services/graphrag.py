"""GraphRAG retrieval augmentation (v1.5 B-2).

Given an initial set of top documents retrieved via hybrid search, look up
their 1-hop neighbors in the `document_relations` table (built by graph_service
in Sprint 5) and merge the neighbors into the candidate pool before rerank.

Use case: a query that surfaces paper P will now also surface P's strong
neighbors (same_method / same_dataset / same_term edges with weight ≥ threshold),
even if those neighbors didn't match the query directly.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from sqlalchemy import or_, select

from app.db.models.document import Chunk, Document
from app.db.models.research_ext import DocumentRelation

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.rag.retriever import Citation

log = logging.getLogger(__name__)

# Tunables — kept conservative so the neighbor pool doesn't drown out the hybrid hits.
_NEIGHBOR_MIN_CONFIDENCE = 0.4
_NEIGHBORS_PER_SEED = 3
_TOTAL_NEIGHBOR_CAP = 12
_NEIGHBOR_SCORE_DAMPEN = 0.6  # neighbor scores are dampened so seeds still rank above


async def expand_with_neighbors(
    *,
    db: "AsyncSession",
    topic_id: int,
    citations: "list[Citation]",
    max_seeds: int = 5,
) -> "list[Citation]":
    """Return `citations` plus up to `_TOTAL_NEIGHBOR_CAP` neighbor citations
    (one chunk per neighbor document, picked deterministically).

    The new citations get score = seed.score * _NEIGHBOR_SCORE_DAMPEN * confidence
    so they slot in below the original seeds in most cases.
    """
    if not citations:
        return citations

    seeds = citations[:max_seeds]
    seed_doc_ids = {c.document_id for c in seeds}
    if not seed_doc_ids:
        return citations

    # Query both directions of edges (a→b and b→a).
    seed_list: Sequence[int] = list(seed_doc_ids)
    rel_rows = (
        await db.execute(
            select(DocumentRelation)
            .where(
                DocumentRelation.topic_id == topic_id,
                DocumentRelation.confidence >= _NEIGHBOR_MIN_CONFIDENCE,
                or_(
                    DocumentRelation.source_document_id.in_(seed_list),
                    DocumentRelation.target_document_id.in_(seed_list),
                ),
            )
            .order_by(DocumentRelation.confidence.desc())
        )
    ).scalars().all()

    # For each seed, pick top-K neighbor documents not already present.
    existing_docs = {c.document_id for c in citations}
    neighbor_meta: dict[int, tuple[float, str, int]] = {}  # nb_doc_id -> (best_conf, rel_type, seed_doc_id)
    per_seed_count: dict[int, int] = {sd: 0 for sd in seed_doc_ids}
    for r in rel_rows:
        if r.source_document_id in seed_doc_ids:
            seed, nb = r.source_document_id, r.target_document_id
        else:
            seed, nb = r.target_document_id, r.source_document_id
        if nb in existing_docs or nb in seed_doc_ids:
            continue
        if per_seed_count.get(seed, 0) >= _NEIGHBORS_PER_SEED:
            continue
        prev = neighbor_meta.get(nb)
        if prev is None or r.confidence > prev[0]:
            neighbor_meta[nb] = (float(r.confidence), r.relation_type, seed)
            per_seed_count[seed] = per_seed_count.get(seed, 0) + 1
        if len(neighbor_meta) >= _TOTAL_NEIGHBOR_CAP:
            break

    if not neighbor_meta:
        return citations

    nb_doc_ids = list(neighbor_meta.keys())
    # Pull one representative chunk per neighbor document (chunk_index = 0 is usually abstract/intro).
    chunk_rows = (
        await db.execute(
            select(Chunk, Document)
            .join(Document, Document.id == Chunk.document_id)
            .where(Chunk.document_id.in_(nb_doc_ids))
            .order_by(Chunk.document_id.asc(), Chunk.chunk_index.asc())
        )
    ).all()
    rep_chunk: dict[int, tuple[Chunk, Document]] = {}
    for chunk, doc in chunk_rows:
        rep_chunk.setdefault(chunk.document_id, (chunk, doc))

    # Build a quick seed-id → score map so neighbors inherit "their" seed's strength.
    seed_score: dict[int, float] = {c.document_id: c.score for c in seeds}

    from app.rag.retriever import Citation as Cit

    augmented: list = list(citations)
    for nb_id, (conf, rel_type, seed_id) in neighbor_meta.items():
        pair = rep_chunk.get(nb_id)
        if not pair:
            continue
        chunk, doc = pair
        base_score = seed_score.get(seed_id, 0.5)
        score = base_score * _NEIGHBOR_SCORE_DAMPEN * conf
        augmented.append(
            Cit(
                document_id=doc.id,
                chunk_id=chunk.id,
                title=doc.title or "",
                url=doc.url or "",
                source=doc.source or "",
                published_at=doc.published_at,
                section_title=chunk.section_title,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                score=score,
                text=chunk.text or "",
            )
        )

    augmented.sort(key=lambda c: c.score, reverse=True)
    log.info(
        "graphrag: expanded %d -> %d citations (added %d neighbors from %d seeds)",
        len(citations),
        len(augmented),
        len(neighbor_meta),
        len(seed_doc_ids),
    )
    return augmented


__all__ = ["expand_with_neighbors"]
