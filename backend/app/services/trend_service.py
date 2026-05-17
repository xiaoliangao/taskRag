"""Trend Radar service (Sprint 1)."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db.models.document import Document, TopicDocument
from app.db.models.intel import DocumentBriefing, TopicDocumentInsight
from app.db.models.research_ext import (
    TermOccurrence,
    TopicTerm,
    TopicTrendRun,
)
from app.db.repositories.research_ext_repo import (
    TermOccurrenceRepository,
    TopicTermRepository,
    TopicTrendRepository,
)
from app.services.term_extraction import (
    CandidateTerm,
    extract_candidates_for_document,
)

log = logging.getLogger(__name__)

_TOP_N_FOR_HEATMAP = 25


class TrendService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.term_repo = TopicTermRepository(db)
        self.occ_repo = TermOccurrenceRepository(db)
        self.run_repo = TopicTrendRepository(db)

    # --- Term extraction & ingestion ---

    def rebuild_terms_for_topic(self, topic_id: int) -> int:
        """Walk all documents in the topic, extract candidate terms,
        and upsert topic_terms / term_occurrences.
        Returns number of distinct (term, doc, field) occurrences upserted.
        """
        rows = (
            self.db.query(Document, DocumentBriefing, TopicDocumentInsight, TopicDocument)
            .join(TopicDocument, TopicDocument.document_id == Document.id)
            .outerjoin(DocumentBriefing, DocumentBriefing.document_id == Document.id)
            .outerjoin(
                TopicDocumentInsight,
                (TopicDocumentInsight.document_id == Document.id)
                & (TopicDocumentInsight.topic_id == topic_id),
            )
            .filter(TopicDocument.topic_id == topic_id)
            .all()
        )

        total = 0
        for doc, briefing, insight, _td in rows:
            cands = extract_candidates_for_document(
                title=doc.title,
                abstract=doc.abstract,
                briefing_method=briefing.method if briefing else None,
                briefing_contributions=briefing.contributions if briefing else None,
                briefing_datasets=briefing.datasets if briefing else None,
                briefing_metrics=briefing.metrics if briefing else None,
                insight_why_read=insight.why_read if insight else None,
            )
            if not cands:
                continue
            total += self._ingest_for_document(topic_id, doc, cands)
        self.term_repo.recompute_stats(topic_id)
        return total

    def _ingest_for_document(
        self,
        topic_id: int,
        doc: Document,
        cands: list[CandidateTerm],
    ) -> int:
        # group candidates by normalized term; the first wins for raw casing/type
        by_norm: dict[str, CandidateTerm] = {}
        per_field: list[tuple[CandidateTerm, str]] = []
        for c in cands:
            by_norm.setdefault(c.normalized, c)
            per_field.append((c, c.source_field))

        term_id_by_norm: dict[str, int] = {}
        for norm, cand in by_norm.items():
            term_row = self.term_repo.upsert_term(
                topic_id=topic_id,
                term=cand.term,
                normalized_term=norm,
                term_type=cand.term_type,
                source="auto",
            )
            term_id_by_norm[norm] = term_row.id

        occ_rows = []
        seen: set[tuple[int, str]] = set()
        for cand, field in per_field:
            term_id = term_id_by_norm[cand.normalized]
            key = (term_id, field)
            if key in seen:
                continue
            seen.add(key)
            occ_rows.append(
                dict(
                    topic_id=topic_id,
                    term_id=term_id,
                    document_id=doc.id,
                    chunk_id=None,
                    source_field=field,
                    context_text=cand.context_text,
                    occurred_at=doc.published_at,
                )
            )
        return self.occ_repo.upsert_many(occ_rows)

    # --- Trend computation ---

    def generate_trend_run(
        self,
        topic_id: int,
        window_days: int = 60,
        bucket: str = "week",
    ) -> int:
        run = self.run_repo.create_run(topic_id, window_days, bucket)
        try:
            self._fill_run(run, topic_id, window_days, bucket)
            return run.id
        except Exception as exc:
            log.exception("trend_run_failed", extra={"topic_id": topic_id})
            self.run_repo.fail_run(run, str(exc))
            raise

    def _fill_run(
        self,
        run: TopicTrendRun,
        topic_id: int,
        window_days: int,
        bucket: str,
    ) -> None:
        now = datetime.now(tz=timezone.utc)
        recent_start = now - timedelta(days=window_days)
        baseline_start = recent_start - timedelta(days=window_days)

        all_terms = self.db.query(TopicTerm).filter(TopicTerm.topic_id == topic_id).all()
        term_map = {t.id: t for t in all_terms}

        occurrences = (
            self.db.query(TermOccurrence)
            .filter(TermOccurrence.topic_id == topic_id)
            .all()
        )

        recent: dict[int, int] = defaultdict(int)
        baseline: dict[int, int] = defaultdict(int)
        first_seen_in_recent: set[int] = set()
        evidence_docs: dict[int, set[int]] = defaultdict(set)

        for occ in occurrences:
            ts = occ.occurred_at
            if ts is None:
                # Treat undated occurrences as baseline so they don't fake recency.
                baseline[occ.term_id] += 1
                evidence_docs[occ.term_id].add(occ.document_id)
                continue
            if ts >= recent_start:
                recent[occ.term_id] += 1
                evidence_docs[occ.term_id].add(occ.document_id)
            elif ts >= baseline_start:
                baseline[occ.term_id] += 1

        for term_id, term in term_map.items():
            fs = term.first_seen_at
            if fs is not None and fs >= recent_start:
                first_seen_in_recent.add(term_id)

        items_payload: list[dict[str, Any]] = []
        emerging = 0
        rising = 0
        declining = 0
        for term_id, term in term_map.items():
            r = recent.get(term_id, 0)
            b = baseline.get(term_id, 0)
            if r == 0 and b == 0:
                continue
            growth = (r - b) / max(b, 1)
            if term_id in first_seen_in_recent and r >= 2:
                status = "emerging"
                emerging += 1
            elif growth >= 1.0 and r >= 2:
                status = "rising"
                rising += 1
            elif growth <= -0.5 and b >= 3:
                status = "declining"
                declining += 1
            else:
                status = "stable"
            evidence = sorted(evidence_docs.get(term_id, set()))[:5]
            confidence = min(1.0, 0.2 + 0.15 * r + 0.1 * len(evidence))
            explanation = (
                f"近 {run.window_days} 天出现 {r} 次，基线窗口出现 {b} 次。"
            )
            items_payload.append(
                dict(
                    trend_run_id=run.id,
                    topic_id=topic_id,
                    term_id=term_id,
                    term=term.term,
                    term_type=term.term_type,
                    status=status,
                    frequency_recent=r,
                    frequency_baseline=b,
                    growth_rate=round(growth, 3),
                    confidence=round(confidence, 3),
                    evidence_document_ids=evidence,
                    explanation=explanation,
                )
            )
            term.trend_score = max(0.0, r * 1.0 + max(growth, 0.0) * 2.0)

        items_payload.sort(
            key=lambda d: (d["frequency_recent"], d["growth_rate"]), reverse=True
        )
        self.run_repo.add_items(items_payload)

        heatmap = self._build_heatmap(topic_id, items_payload, window_days, bucket)
        summary_md = self._build_summary_md(
            window_days, emerging, rising, declining, items_payload
        )
        self.run_repo.finish_run(run, summary_md, heatmap)

    def _build_heatmap(
        self,
        topic_id: int,
        items: list[dict[str, Any]],
        window_days: int,
        bucket: str,
    ) -> dict[str, Any]:
        # Heatmap shows top-N terms across the recent window using monthly buckets.
        top = items[:_TOP_N_FOR_HEATMAP]
        if not top:
            return {"buckets": [], "terms": [], "values": []}

        now = datetime.now(tz=timezone.utc)
        start = now - timedelta(days=window_days)
        # Always use month buckets for readability. (bucket arg reserved for future.)
        bucket_keys: list[str] = []
        cursor = datetime(start.year, start.month, 1, tzinfo=timezone.utc)
        end = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        while cursor <= end:
            bucket_keys.append(cursor.strftime("%Y-%m"))
            year = cursor.year + (1 if cursor.month == 12 else 0)
            month = 1 if cursor.month == 12 else cursor.month + 1
            cursor = datetime(year, month, 1, tzinfo=timezone.utc)

        term_ids = [d["term_id"] for d in top]
        labels = [d["term"] for d in top]

        occs = (
            self.db.query(TermOccurrence)
            .filter(
                TermOccurrence.topic_id == topic_id,
                TermOccurrence.term_id.in_(term_ids),
                TermOccurrence.occurred_at.isnot(None),
                TermOccurrence.occurred_at >= start,
            )
            .all()
        )
        grid: dict[int, dict[str, int]] = {tid: defaultdict(int) for tid in term_ids}
        for occ in occs:
            if occ.occurred_at is None:
                continue
            key = occ.occurred_at.strftime("%Y-%m")
            if key in bucket_keys:
                grid[occ.term_id][key] += 1

        values = [[grid[tid].get(b, 0) for b in bucket_keys] for tid in term_ids]
        return {"buckets": bucket_keys, "terms": labels, "values": values}

    def _build_summary_md(
        self,
        window_days: int,
        emerging: int,
        rising: int,
        declining: int,
        items: list[dict[str, Any]],
    ) -> str:
        top_rising = [d["term"] for d in items if d["status"] in ("emerging", "rising")][:5]
        top_declining = [d["term"] for d in items if d["status"] == "declining"][:5]
        lines = [
            f"过去 {window_days} 天共识别 {len(items)} 个有效术语，"
            f"其中新兴 {emerging}、升温 {rising}、降温 {declining}。",
        ]
        if top_rising:
            lines.append("升温/新兴方向：" + "、".join(top_rising))
        if top_declining:
            lines.append("降温方向：" + "、".join(top_declining))
        if len(lines) == 1:
            lines.append("数据较少时趋势信号可能不显著，建议等更多文献入库后再次生成。")
        return "\n\n".join(lines)
