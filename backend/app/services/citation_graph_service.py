"""Citation-graph module.

Builds a real "A cites B" graph for a topic from OpenAlex citation metadata,
on top of the existing `document_relations` table (relation_type='cites',
source='openalex'), plus per-paper citation counts and a recent-velocity proxy.

Three steps:
  1. enrich_topic_citations — fetch referenced_works / cited_by_count /
     counts_by_year from OpenAlex for each topic doc, stored in metadata_json.
  2. rebuild_citation_edges — map referenced OpenAlex ids → in-topic documents
     and persist directed 'cites' edges.
  3. get_citation_graph — nodes (with counts + degrees + velocity) + edges.

No migration: reuses Document.metadata_json (JSONB) and DocumentRelation.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.openalex_collector import OpenAlexCollector, _short_wid
from app.core.constants import SourceType
from app.db.models.document import Document, TopicDocument
from app.db.models.research_ext import DocumentRelation

log = logging.getLogger(__name__)

CITES = "cites"
CITE_SOURCE = "openalex"
# Cap OpenAlex calls per rebuild so the request can't run unbounded; leftover
# docs are reported as `remaining` and picked up on the next rebuild click.
_ENRICH_CAP = 50


async def _topic_documents(db: AsyncSession, topic_id: int) -> list[Document]:
    rows = (
        await db.execute(
            select(Document)
            .join(TopicDocument, TopicDocument.document_id == Document.id)
            .where(TopicDocument.topic_id == topic_id)
        )
    ).scalars().all()
    return list(rows)


def _doc_wid(source: str, external_id: str, metadata: dict | None) -> str | None:
    """The OpenAlex work id for a local document, if known."""
    md = metadata or {}
    if md.get("openalex_id"):
        return _short_wid(md["openalex_id"])
    if source == SourceType.OPENALEX.value:
        return _short_wid(external_id)
    return None


def _recent_citations(counts_by_year: list | None) -> int:
    """Velocity proxy: citations accrued in the two most recent reported years."""
    try:
        items = sorted(
            (
                (int(c["year"]), int(c.get("cited_by_count") or 0))
                for c in (counts_by_year or [])
                if isinstance(c, dict) and c.get("year") is not None
            ),
            reverse=True,
        )
        return sum(v for _, v in items[:2])
    except Exception:
        return 0


def compute_citation_pairs(nodes: list[dict]) -> list[tuple[int, int]]:
    """Pure edge builder. `nodes`: [{id, wid, refs:[wid,…]}]. Returns directed
    (citing_id, cited_id) pairs for references that resolve to an in-set doc."""
    wid_to_id: dict[str, int] = {}
    for n in nodes:
        w = _short_wid(n.get("wid"))
        if w:
            wid_to_id[w] = n["id"]
    pairs: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for n in nodes:
        for ref in n.get("refs") or []:
            tgt = wid_to_id.get(_short_wid(ref) or "")
            if tgt and tgt != n["id"] and (n["id"], tgt) not in seen:
                seen.add((n["id"], tgt))
                pairs.append((n["id"], tgt))
    return pairs


async def _fetch_meta(collector: OpenAlexCollector, doc: Document, md: dict):
    """Resolve a document on OpenAlex (by id → DOI → title) off the event loop."""
    wid = _doc_wid(doc.source, doc.external_id, md)
    if wid:
        return await asyncio.to_thread(collector.fetch_by_openalex_id, wid)
    doi = md.get("doi")
    if doi:
        r = await asyncio.to_thread(collector.fetch_by_doi, doi)
        if r:
            return r
    if doc.title:
        results = await asyncio.to_thread(collector.search_by_title, doc.title, 1)
        if results:
            return results[0]
    return None


async def enrich_topic_citations(db: AsyncSession, topic_id: int) -> dict[str, int]:
    """Fill citation metadata for topic docs that don't have it yet (idempotent;
    capped per call). Returns {enriched, remaining, total}."""
    docs = await _topic_documents(db, topic_id)
    collector = OpenAlexCollector()
    enriched = 0
    attempted = 0
    remaining = 0
    for doc in docs:
        md = dict(doc.metadata_json or {})
        if md.get("citations_enriched"):
            continue
        attempted += 1
        if attempted > _ENRICH_CAP:
            remaining += 1
            continue
        raw = await _fetch_meta(collector, doc, md)
        if raw is not None:
            rmd = raw.metadata or {}
            md["referenced_works"] = rmd.get("referenced_works") or []
            md["cited_by_count"] = rmd.get("cited_by_count")
            md["counts_by_year"] = rmd.get("counts_by_year") or []
            if rmd.get("openalex_id"):
                md["openalex_id"] = rmd["openalex_id"]
            md["citations_enriched"] = True
            enriched += 1
        else:
            # Mark as resolved-with-no-data so we don't re-hit OpenAlex forever.
            md["citations_enriched"] = True
            md["citations_no_data"] = True
        doc.metadata_json = md
    await db.flush()
    return {"enriched": enriched, "remaining": remaining, "total": len(docs)}


async def rebuild_citation_edges(db: AsyncSession, topic_id: int) -> dict[str, int]:
    """Recompute directed 'cites' edges among the topic's documents."""
    await db.execute(
        delete(DocumentRelation).where(
            DocumentRelation.topic_id == topic_id,
            DocumentRelation.relation_type == CITES,
            DocumentRelation.source == CITE_SOURCE,
        )
    )
    docs = await _topic_documents(db, topic_id)
    nodes = [
        {
            "id": d.id,
            "wid": _doc_wid(d.source, d.external_id, d.metadata_json),
            "refs": (d.metadata_json or {}).get("referenced_works") or [],
        }
        for d in docs
    ]
    pairs = compute_citation_pairs(nodes)
    for src, tgt in pairs:
        db.add(
            DocumentRelation(
                topic_id=topic_id,
                source_document_id=src,
                target_document_id=tgt,
                relation_type=CITES,
                confidence=1.0,
                evidence_json={},
                source=CITE_SOURCE,
            )
        )
    await db.flush()
    return {"edges": len(pairs), "nodes": len(docs)}


async def get_citation_graph(db: AsyncSession, topic_id: int) -> dict[str, Any]:
    """Nodes (counts + in/out degree + velocity) and directed citation edges."""
    docs = await _topic_documents(db, topic_id)
    doc_ids = {d.id for d in docs}

    rels = (
        await db.execute(
            select(DocumentRelation).where(
                DocumentRelation.topic_id == topic_id,
                DocumentRelation.relation_type == CITES,
                DocumentRelation.source == CITE_SOURCE,
            )
        )
    ).scalars().all()

    in_deg: dict[int, int] = defaultdict(int)
    out_deg: dict[int, int] = defaultdict(int)
    edges: list[dict[str, int]] = []
    for r in rels:
        if r.source_document_id in doc_ids and r.target_document_id in doc_ids:
            out_deg[r.source_document_id] += 1
            in_deg[r.target_document_id] += 1
            edges.append({"source": r.source_document_id, "target": r.target_document_id})

    nodes: list[dict[str, Any]] = []
    enriched = 0
    for d in docs:
        md = d.metadata_json or {}
        if md.get("citations_enriched"):
            enriched += 1
        nodes.append(
            {
                "id": d.id,
                "title": d.title,
                "year": d.published_at.year if d.published_at else None,
                "source": d.source,
                "cited_by_count": md.get("cited_by_count"),
                "recent_citations": _recent_citations(md.get("counts_by_year")),
                "in_degree": in_deg.get(d.id, 0),
                "out_degree": out_deg.get(d.id, 0),
            }
        )

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {"total": len(docs), "enriched": enriched, "edges": len(edges)},
    }


__all__ = [
    "enrich_topic_citations",
    "rebuild_citation_edges",
    "get_citation_graph",
    "compute_citation_pairs",
]
