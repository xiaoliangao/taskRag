"""Repositories for v1.3+ research extension tables (Trend Radar)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Sequence

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.models.research_ext import (
    ClaimRelation,
    DocumentSignal,
    PaperClaim,
    TermOccurrence,
    TopicTerm,
    TopicTrendItem,
    TopicTrendRun,
)


# --- Sync repositories (Celery tasks) ---


class TopicTermRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert_term(
        self,
        topic_id: int,
        term: str,
        normalized_term: str,
        term_type: str = "keyword",
        source: str = "auto",
    ) -> TopicTerm:
        existing = (
            self.db.query(TopicTerm)
            .filter(TopicTerm.topic_id == topic_id, TopicTerm.normalized_term == normalized_term)
            .first()
        )
        if existing is not None:
            if term_type and term_type != "keyword":
                existing.term_type = term_type
            existing.updated_at = datetime.now(tz=timezone.utc)
            return existing
        row = TopicTerm(
            topic_id=topic_id,
            term=term,
            normalized_term=normalized_term,
            term_type=term_type,
            source=source,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def recompute_stats(self, topic_id: int) -> None:
        """Refresh first_seen/last_seen/document_count/occurrence_count for all terms in the topic."""
        from sqlalchemy import func as sa_func

        stats = (
            self.db.query(
                TermOccurrence.term_id,
                sa_func.min(TermOccurrence.occurred_at).label("first_seen"),
                sa_func.max(TermOccurrence.occurred_at).label("last_seen"),
                sa_func.count(sa_func.distinct(TermOccurrence.document_id)).label("doc_count"),
                sa_func.count(TermOccurrence.id).label("occ_count"),
            )
            .filter(TermOccurrence.topic_id == topic_id)
            .group_by(TermOccurrence.term_id)
            .all()
        )
        stats_map = {row.term_id: row for row in stats}
        terms = self.db.query(TopicTerm).filter(TopicTerm.topic_id == topic_id).all()
        for term in terms:
            row = stats_map.get(term.id)
            if row is None:
                term.document_count = 0
                term.occurrence_count = 0
                continue
            term.first_seen_at = row.first_seen
            term.last_seen_at = row.last_seen
            term.document_count = row.doc_count or 0
            term.occurrence_count = row.occ_count or 0
        self.db.flush()


class TermOccurrenceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert_many(self, rows: Iterable[dict]) -> int:
        """Bulk insert with conflict-do-nothing on the unique tuple."""
        items = [dict(r) for r in rows]
        if not items:
            return 0
        stmt = pg_insert(TermOccurrence).values(items)
        stmt = stmt.on_conflict_do_nothing(
            constraint="uq_term_occ_topic_term_doc_field",
        )
        result = self.db.execute(stmt)
        self.db.flush()
        return result.rowcount or 0

    def clear_for_document(self, topic_id: int, document_id: int) -> None:
        self.db.execute(
            delete(TermOccurrence).where(
                TermOccurrence.topic_id == topic_id,
                TermOccurrence.document_id == document_id,
            )
        )
        self.db.flush()


class TopicTrendRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_run(self, topic_id: int, window_days: int, bucket: str = "week") -> TopicTrendRun:
        run = TopicTrendRun(
            topic_id=topic_id,
            window_days=window_days,
            bucket=bucket,
            status="running",
            started_at=datetime.now(tz=timezone.utc),
        )
        self.db.add(run)
        self.db.flush()
        return run

    def finish_run(
        self,
        run: TopicTrendRun,
        summary_md: str | None,
        heatmap_json: dict,
    ) -> None:
        now = datetime.now(tz=timezone.utc)
        run.status = "success"
        run.summary_md = summary_md
        run.heatmap_json = heatmap_json or {}
        run.finished_at = now
        run.generated_at = now
        self.db.flush()

    def fail_run(self, run: TopicTrendRun, error: str) -> None:
        run.status = "failed"
        run.error_message = error[:2000]
        run.finished_at = datetime.now(tz=timezone.utc)
        self.db.flush()

    def add_items(self, items: Iterable[dict]) -> int:
        rows = [TopicTrendItem(**row) for row in items]
        if not rows:
            return 0
        self.db.add_all(rows)
        self.db.flush()
        return len(rows)


# --- Async repositories (API) ---


class TopicTrendAsyncRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_runs(self, topic_id: int, limit: int = 20) -> Sequence[TopicTrendRun]:
        result = await self.db.execute(
            select(TopicTrendRun)
            .where(TopicTrendRun.topic_id == topic_id)
            .order_by(TopicTrendRun.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_run(self, run_id: int) -> TopicTrendRun | None:
        return await self.db.get(TopicTrendRun, run_id)

    async def get_latest_run(
        self, topic_id: int, window_days: int | None = None
    ) -> TopicTrendRun | None:
        stmt = (
            select(TopicTrendRun)
            .where(
                TopicTrendRun.topic_id == topic_id,
                TopicTrendRun.status == "success",
            )
            .order_by(TopicTrendRun.generated_at.desc())
            .limit(1)
        )
        if window_days is not None:
            stmt = stmt.where(TopicTrendRun.window_days == window_days)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_items(self, run_id: int) -> Sequence[TopicTrendItem]:
        result = await self.db.execute(
            select(TopicTrendItem)
            .where(TopicTrendItem.trend_run_id == run_id)
            .order_by(TopicTrendItem.frequency_recent.desc())
        )
        return result.scalars().all()


class PaperClaimRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def replace_for_document(
        self,
        topic_id: int,
        document_id: int,
        rows: Iterable[dict],
    ) -> int:
        # Replace claims for one document (idempotent re-extraction)
        self.db.execute(
            delete(PaperClaim).where(
                PaperClaim.topic_id == topic_id,
                PaperClaim.document_id == document_id,
            )
        )
        objs = [PaperClaim(**r) for r in rows]
        if not objs:
            self.db.flush()
            return 0
        self.db.add_all(objs)
        self.db.flush()
        return len(objs)

    def list_for_topic(self, topic_id: int) -> Sequence[PaperClaim]:
        return (
            self.db.query(PaperClaim)
            .filter(PaperClaim.topic_id == topic_id)
            .all()
        )


class ClaimRelationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert(
        self,
        topic_id: int,
        claim_a_id: int,
        claim_b_id: int,
        relation_type: str,
        confidence: float,
        reason_md: str | None,
        evidence_json: dict,
    ) -> None:
        # Sort to ensure (a < b) canonical ordering
        a, b = sorted([claim_a_id, claim_b_id])
        existing = (
            self.db.query(ClaimRelation)
            .filter(
                ClaimRelation.topic_id == topic_id,
                ClaimRelation.claim_a_id == a,
                ClaimRelation.claim_b_id == b,
            )
            .first()
        )
        if existing:
            existing.relation_type = relation_type
            existing.confidence = confidence
            existing.reason_md = reason_md
            existing.evidence_json = evidence_json
            existing.updated_at = datetime.now(tz=timezone.utc)
            return
        self.db.add(
            ClaimRelation(
                topic_id=topic_id,
                claim_a_id=a,
                claim_b_id=b,
                relation_type=relation_type,
                confidence=confidence,
                reason_md=reason_md,
                evidence_json=evidence_json,
            )
        )

    def clear_for_topic(self, topic_id: int) -> None:
        self.db.execute(
            delete(ClaimRelation).where(ClaimRelation.topic_id == topic_id)
        )


class DocumentSignalRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert(
        self,
        topic_id: int,
        document_id: int,
        signal_type: str,
        score: float,
        reason_md: str | None,
        evidence_json: dict,
        source: str = "local",
    ) -> None:
        existing = (
            self.db.query(DocumentSignal)
            .filter(
                DocumentSignal.topic_id == topic_id,
                DocumentSignal.document_id == document_id,
                DocumentSignal.signal_type == signal_type,
            )
            .first()
        )
        if existing:
            existing.score = score
            existing.reason_md = reason_md
            existing.evidence_json = evidence_json
            existing.source = source
            existing.detected_at = datetime.now(tz=timezone.utc)
            return
        self.db.add(
            DocumentSignal(
                topic_id=topic_id,
                document_id=document_id,
                signal_type=signal_type,
                score=score,
                reason_md=reason_md,
                evidence_json=evidence_json,
                source=source,
            )
        )


# --- Async repositories ---


class PaperClaimAsyncRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_topic(
        self,
        topic_id: int,
        claim_type: str | None = None,
        document_id: int | None = None,
        limit: int = 200,
    ) -> Sequence[PaperClaim]:
        stmt = select(PaperClaim).where(PaperClaim.topic_id == topic_id)
        if claim_type:
            stmt = stmt.where(PaperClaim.claim_type == claim_type)
        if document_id:
            stmt = stmt.where(PaperClaim.document_id == document_id)
        stmt = stmt.order_by(PaperClaim.confidence.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_by_id(self, claim_id: int) -> PaperClaim | None:
        return await self.db.get(PaperClaim, claim_id)


class ClaimRelationAsyncRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_topic(
        self,
        topic_id: int,
        relation_type: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 200,
    ) -> Sequence[ClaimRelation]:
        stmt = (
            select(ClaimRelation)
            .where(
                ClaimRelation.topic_id == topic_id,
                ClaimRelation.confidence >= min_confidence,
            )
            .order_by(ClaimRelation.confidence.desc())
            .limit(limit)
        )
        if relation_type:
            stmt = stmt.where(ClaimRelation.relation_type == relation_type)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_by_id(self, relation_id: int) -> ClaimRelation | None:
        return await self.db.get(ClaimRelation, relation_id)


class DocumentSignalAsyncRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_topic(
        self,
        topic_id: int,
        signal_type: str | None = None,
        limit: int = 50,
    ) -> Sequence[DocumentSignal]:
        stmt = (
            select(DocumentSignal)
            .where(DocumentSignal.topic_id == topic_id)
            .order_by(DocumentSignal.score.desc())
            .limit(limit)
        )
        if signal_type:
            stmt = stmt.where(DocumentSignal.signal_type == signal_type)
        result = await self.db.execute(stmt)
        return result.scalars().all()


class TopicTermAsyncRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_topic(
        self,
        topic_id: int,
        term_type: str | None = None,
        limit: int = 50,
    ) -> Sequence[TopicTerm]:
        stmt = (
            select(TopicTerm)
            .where(TopicTerm.topic_id == topic_id)
            .order_by(TopicTerm.occurrence_count.desc())
            .limit(limit)
        )
        if term_type:
            stmt = stmt.where(TopicTerm.term_type == term_type)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_by_id(self, term_id: int) -> TopicTerm | None:
        return await self.db.get(TopicTerm, term_id)

    async def list_documents_for_term(self, term_id: int) -> Sequence[int]:
        result = await self.db.execute(
            select(TermOccurrence.document_id)
            .where(TermOccurrence.term_id == term_id)
            .distinct()
        )
        return [row[0] for row in result.all()]
