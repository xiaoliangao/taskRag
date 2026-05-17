from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DocumentParseStatus
from app.db.models.document import Chunk, Document, TopicDocument


class DocumentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, document_id: int) -> Document | None:
        return await self.db.get(Document, document_id)

    async def get_by_source_external(self, source: str, external_id: str) -> Document | None:
        result = await self.db.execute(
            select(Document).where(Document.source == source, Document.external_id == external_id)
        )
        return result.scalar_one_or_none()

    async def upsert(self, *, source: str, external_id: str, defaults: dict) -> tuple[Document, bool]:
        existing = await self.get_by_source_external(source, external_id)
        if existing:
            return existing, False
        doc = Document(source=source, external_id=external_id, **defaults)
        self.db.add(doc)
        await self.db.flush()
        return doc, True

    async def mark_parsed(self, document_id: int, full_text_path: str | None) -> None:
        doc = await self.get_by_id(document_id)
        if not doc:
            return
        doc.parse_status = DocumentParseStatus.PARSED.value
        if full_text_path:
            doc.full_text_path = full_text_path
        await self.db.flush()

    async def mark_skipped(self, document_id: int, reason: str) -> None:
        doc = await self.get_by_id(document_id)
        if not doc:
            return
        doc.parse_status = DocumentParseStatus.SKIPPED.value
        meta = dict(doc.metadata_json or {})
        meta["skip_reason"] = reason
        doc.metadata_json = meta
        await self.db.flush()


class ChunkRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def exists_for_document(self, document_id: int) -> bool:
        result = await self.db.execute(
            select(func.count(Chunk.id)).where(Chunk.document_id == document_id)
        )
        return (result.scalar_one() or 0) > 0

    async def list_for_document(self, document_id: int) -> Sequence[Chunk]:
        result = await self.db.execute(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.chunk_index)
        )
        return result.scalars().all()

    async def list_vector_ids(self, document_id: int) -> Sequence[str]:
        result = await self.db.execute(
            select(Chunk.vector_id).where(Chunk.document_id == document_id)
        )
        return [str(v) for v in result.scalars().all()]

    async def list_vector_ids_for_documents(self, document_ids: Sequence[int]) -> Sequence[str]:
        if not document_ids:
            return []
        result = await self.db.execute(
            select(Chunk.vector_id).where(Chunk.document_id.in_(document_ids))
        )
        return [str(v) for v in result.scalars().all()]

    async def insert_many(self, document_id: int, rows: list[dict]) -> Sequence[Chunk]:
        chunks: list[Chunk] = []
        for r in rows:
            chunks.append(Chunk(document_id=document_id, **r))
        self.db.add_all(chunks)
        await self.db.flush()
        return chunks


class TopicDocumentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def insert_ignore(
        self,
        *,
        topic_id: int,
        document_id: int,
        matched_keyword: str | None,
        added_by_task_id: int | None = None,
    ) -> bool:
        """Returns True if newly inserted, False if already existed."""
        stmt = pg_insert(TopicDocument).values(
            topic_id=topic_id,
            document_id=document_id,
            matched_keyword=matched_keyword,
            added_by_task_id=added_by_task_id,
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["topic_id", "document_id"]).returning(
            TopicDocument.topic_id
        )
        result = await self.db.execute(stmt)
        return result.first() is not None

    async def list_document_ids_for_topic(self, topic_id: int) -> Sequence[int]:
        result = await self.db.execute(
            select(TopicDocument.document_id).where(TopicDocument.topic_id == topic_id)
        )
        return [int(x) for x in result.scalars().all()]

    async def count_for_topic(self, topic_id: int) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(TopicDocument)
            .where(TopicDocument.topic_id == topic_id)
        )
        return int(result.scalar_one() or 0)

    async def list_documents_for_topic(
        self,
        topic_id: int,
        *,
        source: str | None = None,
        q: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[Sequence[tuple[Document, TopicDocument]], int]:
        conds = [TopicDocument.topic_id == topic_id]
        join_clause = and_(TopicDocument.document_id == Document.id)
        if source:
            conds.append(Document.source == source)
        if q:
            ilike = f"%{q}%"
            conds.append(Document.title.ilike(ilike))
        if date_from:
            conds.append(Document.published_at >= date_from)
        if date_to:
            conds.append(Document.published_at <= date_to)

        base = (
            select(Document, TopicDocument)
            .join(TopicDocument, join_clause)
            .where(*conds)
        )
        total_q = select(func.count()).select_from(base.subquery())
        total = int((await self.db.execute(total_q)).scalar_one() or 0)

        items_q = base.order_by(TopicDocument.added_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(items_q)
        return result.all(), total

    async def get_association(self, topic_id: int, document_id: int) -> TopicDocument | None:
        return await self.db.get(TopicDocument, (topic_id, document_id))
