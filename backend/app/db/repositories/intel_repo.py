"""Repositories for v1.1+ intelligence tables (sync + async helpers)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.models.intel import (
    DocumentBriefing,
    ReadingPath,
    ReadingPathItem,
    ResearchInsight,
    ResearchNote,
    TopicDocumentInsight,
    TopicPulse,
    UserDocumentState,
)


# --- Briefing ---

class BriefingRepository:
    """Sync-only repository (used from Celery tasks). Async access goes via the API service layer."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, document_id: int, language: str = "zh-CN") -> DocumentBriefing | None:
        return (
            self.db.query(DocumentBriefing)
            .filter(DocumentBriefing.document_id == document_id, DocumentBriefing.language == language)
            .first()
        )

    def upsert_pending(self, document_id: int, language: str = "zh-CN") -> DocumentBriefing:
        b = self.get(document_id, language)
        if b is None:
            b = DocumentBriefing(document_id=document_id, language=language, status="pending")
            self.db.add(b)
            self.db.flush()
        else:
            b.status = "pending"
            b.error_msg = None
        return b

    def save_success(self, b: DocumentBriefing, data: dict, model_provider: str, model_name: str) -> DocumentBriefing:
        b.status = "success"
        b.one_sentence_summary = data.get("one_sentence_summary")
        b.problem = data.get("problem")
        b.method = data.get("method")
        b.contributions = data.get("contributions") or []
        b.experiments = data.get("experiments") or []
        b.limitations = data.get("limitations") or []
        b.datasets = data.get("datasets") or []
        b.metrics = data.get("metrics") or []
        b.code_available = data.get("code_available")
        b.code_url = data.get("code_url")
        b.reading_time_minutes = data.get("reading_time_minutes")
        b.evidence_chunk_ids = data.get("evidence_chunk_ids") or []
        b.model_provider = model_provider
        b.model_name = model_name
        b.generated_at = datetime.now(tz=timezone.utc)
        b.error_msg = None
        self.db.flush()
        return b

    def save_failure(self, b: DocumentBriefing, err: str) -> None:
        b.status = "failed"
        b.error_msg = err[:2000]
        self.db.flush()


class BriefingAsyncRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, document_id: int, language: str = "zh-CN") -> DocumentBriefing | None:
        r = await self.db.execute(
            select(DocumentBriefing).where(
                DocumentBriefing.document_id == document_id, DocumentBriefing.language == language
            )
        )
        return r.scalar_one_or_none()


# --- Topic Document Insight ---

class TopicInsightRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, topic_id: int, document_id: int) -> TopicDocumentInsight | None:
        return (
            self.db.query(TopicDocumentInsight)
            .filter(TopicDocumentInsight.topic_id == topic_id, TopicDocumentInsight.document_id == document_id)
            .first()
        )

    def upsert(self, topic_id: int, document_id: int, data: dict) -> TopicDocumentInsight:
        i = self.get(topic_id, document_id)
        if i is None:
            i = TopicDocumentInsight(topic_id=topic_id, document_id=document_id)
            self.db.add(i)
        i.relevance_score = data.get("relevance_score")
        i.relevance_reason = data.get("relevance_reason")
        i.reading_priority = data.get("reading_priority")
        i.tags = data.get("tags") or []
        i.why_read = data.get("why_read")
        i.generated_at = datetime.now(tz=timezone.utc)
        self.db.flush()
        return i


class TopicInsightAsyncRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, topic_id: int, document_id: int) -> TopicDocumentInsight | None:
        r = await self.db.execute(
            select(TopicDocumentInsight).where(
                TopicDocumentInsight.topic_id == topic_id,
                TopicDocumentInsight.document_id == document_id,
            )
        )
        return r.scalar_one_or_none()

    async def list_for_topic(self, topic_id: int, limit: int = 50) -> Sequence[TopicDocumentInsight]:
        r = await self.db.execute(
            select(TopicDocumentInsight)
            .where(TopicDocumentInsight.topic_id == topic_id)
            .order_by(TopicDocumentInsight.relevance_score.desc().nullslast())
            .limit(limit)
        )
        return r.scalars().all()


# --- User Document State ---

class UserDocStateAsyncRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, user_id: int, document_id: int) -> UserDocumentState | None:
        r = await self.db.execute(
            select(UserDocumentState).where(
                UserDocumentState.user_id == user_id, UserDocumentState.document_id == document_id
            )
        )
        return r.scalar_one_or_none()

    async def get_many(self, user_id: int, document_ids: Sequence[int]) -> dict[int, UserDocumentState]:
        if not document_ids:
            return {}
        r = await self.db.execute(
            select(UserDocumentState).where(
                UserDocumentState.user_id == user_id,
                UserDocumentState.document_id.in_(list(document_ids)),
            )
        )
        return {s.document_id: s for s in r.scalars().all()}

    async def upsert(self, user_id: int, document_id: int, fields: dict) -> UserDocumentState:
        s = await self.get(user_id, document_id)
        if s is None:
            s = UserDocumentState(user_id=user_id, document_id=document_id)
            self.db.add(s)
        for k, v in fields.items():
            if hasattr(s, k):
                setattr(s, k, v)
        await self.db.flush()
        return s


# --- Topic Pulse ---

class PulseRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_date(self, topic_id: int, date_iso: datetime) -> TopicPulse | None:
        return (
            self.db.query(TopicPulse)
            .filter(TopicPulse.topic_id == topic_id, TopicPulse.pulse_date == date_iso)
            .first()
        )

    def upsert_pending(self, topic_id: int, date_iso: datetime) -> TopicPulse:
        p = self.get_by_date(topic_id, date_iso)
        if p is None:
            p = TopicPulse(topic_id=topic_id, pulse_date=date_iso, status="pending")
            self.db.add(p)
        else:
            p.status = "pending"
        self.db.flush()
        return p

    def save_success(self, p: TopicPulse, data: dict, model_provider: str, model_name: str) -> TopicPulse:
        p.status = "success"
        p.title = data.get("title")
        p.summary_md = data.get("summary_md")
        p.highlights = data.get("highlights") or []
        p.new_documents = data.get("new_documents") or []
        p.important_documents = data.get("important_documents") or []
        p.emerging_keywords = data.get("emerging_keywords") or []
        p.suggested_actions = data.get("suggested_actions") or []
        p.citations_json = data.get("citations") or []
        p.model_provider = model_provider
        p.model_name = model_name
        p.generated_at = datetime.now(tz=timezone.utc)
        p.error_msg = None
        self.db.flush()
        return p

    def save_failure(self, p: TopicPulse, err: str) -> None:
        p.status = "failed"
        p.error_msg = err[:2000]
        self.db.flush()


class PulseAsyncRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_topic(self, topic_id: int, limit: int = 30) -> Sequence[TopicPulse]:
        r = await self.db.execute(
            select(TopicPulse)
            .where(TopicPulse.topic_id == topic_id)
            .order_by(TopicPulse.pulse_date.desc())
            .limit(limit)
        )
        return r.scalars().all()

    async def get_latest(self, topic_id: int) -> TopicPulse | None:
        r = await self.db.execute(
            select(TopicPulse)
            .where(TopicPulse.topic_id == topic_id, TopicPulse.status == "success")
            .order_by(TopicPulse.pulse_date.desc())
            .limit(1)
        )
        return r.scalar_one_or_none()

    async def get_by_id(self, pulse_id: int) -> TopicPulse | None:
        return await self.db.get(TopicPulse, pulse_id)


# --- Reading Path ---

class ReadingPathRepository:
    """Sync repo for use in Celery."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, topic_id: int, title: str, description: str | None = None) -> ReadingPath:
        p = ReadingPath(topic_id=topic_id, title=title, description=description, status="pending")
        self.db.add(p)
        self.db.flush()
        return p

    def save_success(self, p: ReadingPath, items: list[dict]) -> None:
        # wipe existing items for clean rewrite
        self.db.query(ReadingPathItem).filter(ReadingPathItem.reading_path_id == p.id).delete()
        for idx, item in enumerate(items):
            self.db.add(
                ReadingPathItem(
                    reading_path_id=p.id,
                    document_id=item["document_id"],
                    order_index=idx,
                    stage=item.get("stage"),
                    reason=item.get("reason"),
                    expected_minutes=item.get("expected_minutes"),
                    prerequisite_document_ids=item.get("prerequisite_document_ids") or [],
                )
            )
        p.status = "success"
        p.generated_at = datetime.now(tz=timezone.utc)
        self.db.flush()


class ReadingPathAsyncRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_latest(self, topic_id: int) -> ReadingPath | None:
        r = await self.db.execute(
            select(ReadingPath)
            .where(ReadingPath.topic_id == topic_id, ReadingPath.status == "success")
            .order_by(ReadingPath.generated_at.desc().nullslast(), ReadingPath.created_at.desc())
            .limit(1)
        )
        return r.scalar_one_or_none()

    async def items_for_path(self, path_id: int) -> Sequence[ReadingPathItem]:
        r = await self.db.execute(
            select(ReadingPathItem)
            .where(ReadingPathItem.reading_path_id == path_id)
            .order_by(ReadingPathItem.order_index.asc())
        )
        return r.scalars().all()


# --- Research Insight ---

class InsightRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, topic_id: int, insight_type: str, **fields) -> ResearchInsight:
        i = ResearchInsight(topic_id=topic_id, insight_type=insight_type, status="success", **fields)
        self.db.add(i)
        self.db.flush()
        return i


class InsightAsyncRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_topic(self, topic_id: int, insight_type: str | None = None) -> Sequence[ResearchInsight]:
        q = select(ResearchInsight).where(ResearchInsight.topic_id == topic_id)
        if insight_type:
            q = q.where(ResearchInsight.insight_type == insight_type)
        q = q.order_by(ResearchInsight.created_at.desc())
        r = await self.db.execute(q)
        return r.scalars().all()

    async def get_by_id(self, insight_id: int) -> ResearchInsight | None:
        return await self.db.get(ResearchInsight, insight_id)


# --- Research Notes ---

class NotesAsyncRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_topic(self, user_id: int, topic_id: int) -> Sequence[ResearchNote]:
        r = await self.db.execute(
            select(ResearchNote)
            .where(ResearchNote.user_id == user_id, ResearchNote.topic_id == topic_id)
            .order_by(ResearchNote.pinned.desc(), ResearchNote.created_at.desc())
        )
        return r.scalars().all()

    async def get(self, note_id: int) -> ResearchNote | None:
        return await self.db.get(ResearchNote, note_id)

    async def create(
        self,
        *,
        user_id: int,
        topic_id: int,
        source_type: str,
        source_id: int | None,
        title: str | None,
        content_md: str,
        tags: list | None = None,
        pinned: bool = False,
    ) -> ResearchNote:
        n = ResearchNote(
            user_id=user_id,
            topic_id=topic_id,
            source_type=source_type,
            source_id=source_id,
            title=title,
            content_md=content_md,
            tags=tags or [],
            pinned=pinned,
        )
        self.db.add(n)
        await self.db.flush()
        return n

    async def update(self, n: ResearchNote, fields: dict) -> ResearchNote:
        for k, v in fields.items():
            if hasattr(n, k):
                setattr(n, k, v)
        await self.db.flush()
        return n

    async def delete(self, n: ResearchNote) -> None:
        await self.db.delete(n)
        await self.db.flush()

    async def list_recent_pinned(self, user_id: int, topic_id: int, limit: int = 5) -> Sequence[ResearchNote]:
        r = await self.db.execute(
            select(ResearchNote)
            .where(
                ResearchNote.user_id == user_id,
                ResearchNote.topic_id == topic_id,
                ResearchNote.pinned.is_(True),
            )
            .order_by(ResearchNote.updated_at.desc())
            .limit(limit)
        )
        return r.scalars().all()
