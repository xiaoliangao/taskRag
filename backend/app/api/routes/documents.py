from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from app.api.deps import OwnedTopicDep, SessionDep
from app.core.errors import NotFoundError
from app.db.repositories.document_repo import (
    ChunkRepository,
    DocumentRepository,
    TopicDocumentRepository,
)
from app.schemas.document import (
    DocumentChunkPublic,
    DocumentDetail,
    DocumentListResponse,
    DocumentSummary,
    UploadResponse,
)

router = APIRouter()


@router.get("/topics/{topic_id}/documents", response_model=DocumentListResponse)
async def list_documents(
    topic: OwnedTopicDep,
    db: SessionDep,
    source: str | None = None,
    q: str | None = None,
    date_from: datetime | None = Query(default=None, alias="from"),
    date_to: datetime | None = Query(default=None, alias="to"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> DocumentListResponse:
    offset = (page - 1) * page_size
    items, total = await TopicDocumentRepository(db).list_documents_for_topic(
        topic.id,
        source=source,
        q=q,
        date_from=date_from,
        date_to=date_to,
        offset=offset,
        limit=page_size,
    )
    # Bulk-load topic insights so we can show priority/relevance per doc
    from sqlalchemy import select as _sel
    from app.db.models.intel import TopicDocumentInsight

    doc_ids = [d.id for d, _ in items]
    insight_by_doc: dict[int, TopicDocumentInsight] = {}
    if doc_ids:
        rr = await db.execute(
            _sel(TopicDocumentInsight).where(
                TopicDocumentInsight.topic_id == topic.id,
                TopicDocumentInsight.document_id.in_(doc_ids),
            )
        )
        for ins in rr.scalars().all():
            insight_by_doc[ins.document_id] = ins

    summaries: list[DocumentSummary] = []
    for doc, link in items:
        ins = insight_by_doc.get(doc.id)
        summaries.append(
            DocumentSummary(
                id=doc.id,
                source=doc.source,
                title=doc.title,
                authors=list(doc.authors or []),
                published_at=doc.published_at,
                url=doc.url,
                abstract=doc.abstract,
                matched_keyword=link.matched_keyword,
                added_at=link.added_at,
                reading_priority=(ins.reading_priority if ins else None),
                relevance_score=(ins.relevance_score if ins else None),
            )
        )
    return DocumentListResponse(items=summaries, page=page, page_size=page_size, total=total)


@router.get("/topics/{topic_id}/documents/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: int, topic: OwnedTopicDep, db: SessionDep
) -> DocumentDetail:
    assoc = await TopicDocumentRepository(db).get_association(topic.id, document_id)
    if not assoc:
        raise NotFoundError("Document not found in this topic")
    doc = await DocumentRepository(db).get_by_id(document_id)
    if not doc:
        raise NotFoundError("Document not found")
    chunks = await ChunkRepository(db).list_for_document(document_id)
    full_text: str | None = None
    if doc.full_text_path:
        try:
            p = Path(doc.full_text_path)
            if p.exists():
                full_text = p.read_text(encoding="utf-8", errors="ignore")[:200_000]
        except Exception:
            full_text = None
    return DocumentDetail(
        id=doc.id,
        source=doc.source,
        title=doc.title,
        authors=list(doc.authors or []),
        published_at=doc.published_at,
        url=doc.url,
        abstract=doc.abstract,
        full_text=full_text,
        chunks=[
            DocumentChunkPublic(
                id=c.id,
                chunk_index=c.chunk_index,
                section_title=c.section_title,
                page_start=c.page_start,
                page_end=c.page_end,
                text=c.text,
            )
            for c in chunks
        ],
    )


@router.get("/topics/{topic_id}/documents/{document_id}/pdf")
async def get_document_pdf(
    document_id: int, topic: OwnedTopicDep, db: SessionDep
) -> FileResponse:
    assoc = await TopicDocumentRepository(db).get_association(topic.id, document_id)
    if not assoc:
        raise NotFoundError("Document not found in this topic")
    doc = await DocumentRepository(db).get_by_id(document_id)
    if not doc or not doc.pdf_path:
        raise NotFoundError("No PDF available for this document")
    p = Path(doc.pdf_path)
    if not p.exists():
        raise NotFoundError("PDF file missing on disk")
    filename = f"{doc.source}_{doc.external_id.replace('/', '_')}.pdf"
    return FileResponse(
        path=str(p),
        media_type="application/pdf",
        filename=filename,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post("/topics/{topic_id}/documents/upload", response_model=UploadResponse)
async def upload_document(topic: OwnedTopicDep) -> UploadResponse:
    # v1 stub — upload pipeline not implemented in initial demo.
    return UploadResponse(task_id=None, status="not_implemented", message="Upload coming soon")
