"""Knowledge graph (weak-relations) service (Sprint 5 MVP)."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.document import Document, TopicDocument
from app.db.models.intel import DocumentBriefing
from app.db.models.research_ext import (
    DocumentRelation,
    TermOccurrence,
    TopicTerm,
)

log = logging.getLogger(__name__)

_MAX_NODES = 80
_MAX_EDGES = 240

_WEIGHT_BY_TYPE = {
    "same_method": 0.75,
    "same_dataset": 0.6,
    "same_metric": 0.5,
    "same_term": 0.4,
    "same_author": 0.4,
}


def _normalize(s: str | None) -> str:
    if not s:
        return ""
    return " ".join(s.strip().lower().split())


async def rebuild_document_relations(db: AsyncSession, topic_id: int) -> dict[str, int]:
    """Rebuild lightweight document_relations for a topic."""
    # Clear existing local relations
    await db.execute(
        delete(DocumentRelation).where(
            DocumentRelation.topic_id == topic_id,
            DocumentRelation.source == "local",
        )
    )

    # Pull topic documents + briefings
    rows = (
        await db.execute(
            select(Document, DocumentBriefing)
            .join(TopicDocument, TopicDocument.document_id == Document.id)
            .outerjoin(DocumentBriefing, DocumentBriefing.document_id == Document.id)
            .where(TopicDocument.topic_id == topic_id)
        )
    ).all()
    docs = [(doc, briefing) for doc, briefing in rows]
    if not docs:
        return {"edges": 0, "nodes": 0}

    # Index by dataset / metric / method / author
    by_dataset: dict[str, list[int]] = defaultdict(list)
    by_metric: dict[str, list[int]] = defaultdict(list)
    by_method: dict[str, list[int]] = defaultdict(list)
    by_author: dict[str, list[int]] = defaultdict(list)

    for doc, briefing in docs:
        if briefing:
            for d in briefing.datasets or []:
                name = _normalize(d if isinstance(d, str) else (d.get("name") if isinstance(d, dict) else ""))
                if name:
                    by_dataset[name].append(doc.id)
            for m in briefing.metrics or []:
                name = _normalize(m if isinstance(m, str) else (m.get("name") if isinstance(m, dict) else ""))
                if name:
                    by_metric[name].append(doc.id)
            method = _normalize(briefing.method)
            if method:
                # only first 4 words as a coarse key
                key = " ".join(method.split()[:4])
                by_method[key].append(doc.id)
        for a in doc.authors or []:
            a_norm = _normalize(a if isinstance(a, str) else (a.get("name") if isinstance(a, dict) else ""))
            if a_norm and len(a_norm) >= 3:
                by_author[a_norm].append(doc.id)

    # Build edges
    edges: list[tuple[int, int, str, float, dict]] = []

    def _emit(rel_type: str, groups: dict[str, list[int]], weight: float, label_key: str) -> None:
        for key, ids in groups.items():
            unique = list({i for i in ids})
            if len(unique) < 2:
                continue
            for i in range(len(unique)):
                for j in range(i + 1, len(unique)):
                    a, b = sorted([unique[i], unique[j]])
                    edges.append((a, b, rel_type, weight, {label_key: key}))

    _emit("same_dataset", by_dataset, _WEIGHT_BY_TYPE["same_dataset"], "dataset")
    _emit("same_metric", by_metric, _WEIGHT_BY_TYPE["same_metric"], "metric")
    _emit("same_method", by_method, _WEIGHT_BY_TYPE["same_method"], "method")
    _emit("same_author", by_author, _WEIGHT_BY_TYPE["same_author"], "author")

    # Same shared-term: build from top-N TopicTerms occurrences
    term_rows = (
        await db.execute(
            select(TopicTerm.id, TopicTerm.term)
            .where(TopicTerm.topic_id == topic_id)
            .order_by(TopicTerm.occurrence_count.desc())
            .limit(40)
        )
    ).all()
    top_term_ids = [r.id for r in term_rows]
    term_name = {r.id: r.term for r in term_rows}
    if top_term_ids:
        occ_rows = (
            await db.execute(
                select(TermOccurrence.term_id, TermOccurrence.document_id).where(
                    TermOccurrence.topic_id == topic_id,
                    TermOccurrence.term_id.in_(top_term_ids),
                )
            )
        ).all()
        by_term: dict[int, list[int]] = defaultdict(list)
        for r in occ_rows:
            by_term[r.term_id].append(r.document_id)
        for tid, ids in by_term.items():
            uniq = list(set(ids))
            if len(uniq) < 2:
                continue
            for i in range(len(uniq)):
                for j in range(i + 1, len(uniq)):
                    a, b = sorted([uniq[i], uniq[j]])
                    edges.append(
                        (a, b, "same_term", _WEIGHT_BY_TYPE["same_term"], {"term": term_name.get(tid, "")})
                    )

    # Dedup by (a, b, rel_type) keeping highest weight & merge evidence
    deduped: dict[tuple[int, int, str], tuple[float, dict]] = {}
    for a, b, rt, w, ev in edges:
        key = (a, b, rt)
        cur = deduped.get(key)
        if not cur or w > cur[0]:
            deduped[key] = (w, ev)
    inserted_pairs = sorted(deduped.items(), key=lambda kv: kv[1][0], reverse=True)[:_MAX_EDGES]

    datetime.now(tz=UTC)
    for (a, b, rt), (w, ev) in inserted_pairs:
        db.add(
            DocumentRelation(
                topic_id=topic_id,
                source_document_id=a,
                target_document_id=b,
                relation_type=rt,
                confidence=w,
                evidence_json=ev,
                source="local",
            )
        )
    await db.flush()
    return {"edges": len(inserted_pairs), "nodes": len(docs)}


async def list_graph(
    db: AsyncSession,
    topic_id: int,
    relation_types: list[str] | None = None,
    limit_nodes: int = _MAX_NODES,
) -> dict:
    """Return graph nodes + edges for the front end."""
    stmt = select(DocumentRelation).where(DocumentRelation.topic_id == topic_id)
    if relation_types:
        stmt = stmt.where(DocumentRelation.relation_type.in_(relation_types))
    stmt = stmt.order_by(DocumentRelation.confidence.desc()).limit(_MAX_EDGES)
    rels = (await db.execute(stmt)).scalars().all()

    node_ids: set[int] = set()
    for r in rels:
        node_ids.add(r.source_document_id)
        node_ids.add(r.target_document_id)
    node_ids = set(list(node_ids)[:limit_nodes])

    if not node_ids:
        return {"nodes": [], "edges": []}

    docs = (
        await db.execute(
            select(Document)
            .join(TopicDocument, TopicDocument.document_id == Document.id)
            .where(
                TopicDocument.topic_id == topic_id,
                Document.id.in_(node_ids),
            )
        )
    ).scalars().all()

    nodes = [
        {
            "id": d.id,
            "title": d.title,
            "year": d.published_at.year if d.published_at else None,
            "source": d.source,
        }
        for d in docs
    ]
    edges = [
        {
            "source": r.source_document_id,
            "target": r.target_document_id,
            "type": r.relation_type,
            "weight": r.confidence,
            "evidence": r.evidence_json or {},
        }
        for r in rels
        if r.source_document_id in node_ids and r.target_document_id in node_ids
    ]
    return {"nodes": nodes, "edges": edges}


__all__ = ["rebuild_document_relations", "list_graph"]
