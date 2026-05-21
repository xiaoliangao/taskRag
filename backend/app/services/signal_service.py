"""Breakthrough signal service (Sprint 2, local MVP)."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models.document import Document, TopicDocument
from app.db.models.intel import TopicDocumentInsight, UserDocumentState
from app.db.models.research_ext import (
    MethodEvolutionEdge,
    TopicTrendItem,
    TopicTrendRun,
)
from app.db.repositories.research_ext_repo import DocumentSignalRepository

log = logging.getLogger(__name__)

_BREAKTHROUGH_THRESHOLD = 0.65


class SignalService:
    """Compute local breakthrough / high-relevance signals without external citations API."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = DocumentSignalRepository(db)

    def refresh_for_topic(self, topic_id: int, max_docs: int = 80) -> dict[str, int]:
        # Pull recent documents + insight relevance + favorite state.
        now = datetime.now(tz=UTC)
        recent_cutoff = now - timedelta(days=180)

        rows = (
            self.db.query(Document, TopicDocumentInsight)
            .join(TopicDocument, TopicDocument.document_id == Document.id)
            .outerjoin(
                TopicDocumentInsight,
                (TopicDocumentInsight.document_id == Document.id)
                & (TopicDocumentInsight.topic_id == topic_id),
            )
            .filter(TopicDocument.topic_id == topic_id)
            .order_by(Document.published_at.desc().nullslast())
            .limit(max_docs)
            .all()
        )

        # Favorite counts per document (across users — favored = strong local signal)
        favorite_rows = (
            self.db.query(
                UserDocumentState.document_id,
                func.count(UserDocumentState.id).label("n"),
            )
            .filter(UserDocumentState.favorite.is_(True))
            .group_by(UserDocumentState.document_id)
            .all()
        )
        favorite_map = {r.document_id: int(r.n) for r in favorite_rows}

        # Trend term overlap: how many trend items (rising/emerging) cite each document
        trend_overlap_map: dict[int, int] = {}
        latest_run = (
            self.db.query(TopicTrendRun)
            .filter(
                TopicTrendRun.topic_id == topic_id,
                TopicTrendRun.status == "success",
            )
            .order_by(TopicTrendRun.generated_at.desc())
            .first()
        )
        if latest_run:
            items = (
                self.db.query(TopicTrendItem)
                .filter(
                    TopicTrendItem.trend_run_id == latest_run.id,
                    TopicTrendItem.status.in_(("emerging", "rising")),
                )
                .all()
            )
            for it in items:
                for doc_id in it.evidence_document_ids or []:
                    if isinstance(doc_id, int):
                        trend_overlap_map[doc_id] = trend_overlap_map.get(doc_id, 0) + 1

        # Method-pivot: documents cited as evidence on method evolution edges
        # are likely turning points; promote them. Counts unique edges, not
        # repeated mentions of the same edge.
        method_pivot_map: dict[int, int] = {}
        evolution_edges = (
            self.db.query(MethodEvolutionEdge)
            .filter(MethodEvolutionEdge.topic_id == topic_id)
            .all()
        )
        for edge in evolution_edges:
            for doc_id in edge.evidence_document_ids or []:
                if isinstance(doc_id, int):
                    method_pivot_map[doc_id] = method_pivot_map.get(doc_id, 0) + 1

        inserted = 0
        for doc, insight in rows:
            relevance = float(insight.relevance_score) if insight and insight.relevance_score else 0.4
            fav = favorite_map.get(doc.id, 0)
            overlap = trend_overlap_map.get(doc.id, 0)
            pivot = method_pivot_map.get(doc.id, 0)
            recency = 0.0
            if doc.published_at and doc.published_at >= recent_cutoff:
                age_days = max(1.0, (now - doc.published_at).days)
                recency = max(0.0, 1.0 - age_days / 180.0)

            score = round(
                0.40 * relevance
                + 0.20 * min(1.0, overlap / 3.0)
                + 0.15 * min(1.0, fav / 2.0)
                + 0.15 * min(1.0, pivot / 2.0)
                + 0.10 * recency,
                3,
            )
            reasons = []
            if overlap:
                reasons.append(f"与 {overlap} 个升温/新兴趋势词相关")
            if pivot:
                reasons.append(f"作为 {pivot} 条方法演化的证据 — 拐点候选")
            if fav:
                reasons.append(f"被收藏 {fav} 次")
            if recency > 0:
                reasons.append("近 180 天内发表")
            if relevance >= 0.7:
                reasons.append(f"Topic 相关度 {relevance:.2f}")
            reason_md = "；".join(reasons) if reasons else "基于本地相关性与近期度估算"

            evidence = {
                "relevance_score": relevance,
                "favorite_count": fav,
                "trend_overlap": overlap,
                "method_pivot_count": pivot,
                "recency": round(recency, 3),
            }

            self.repo.upsert(
                topic_id=topic_id,
                document_id=doc.id,
                signal_type=(
                    "breakthrough_candidate"
                    if score >= _BREAKTHROUGH_THRESHOLD
                    else "high_relevance"
                ),
                score=score,
                reason_md=reason_md,
                evidence_json=evidence,
                source="local",
            )
            inserted += 1
        return {"documents_seen": len(rows), "signals_upserted": inserted}


__all__ = ["SignalService"]
