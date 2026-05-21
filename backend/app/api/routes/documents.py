from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import OwnedTopicDep, SessionDep
from app.core.config import get_settings
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
log = logging.getLogger(__name__)


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
        meta = doc.metadata_json or {}
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
                abstract_only=meta.get("abstract_only"),
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
    meta = doc.metadata_json or {}
    return DocumentDetail(
        id=doc.id,
        source=doc.source,
        title=doc.title,
        authors=list(doc.authors or []),
        published_at=doc.published_at,
        url=doc.url,
        abstract=doc.abstract,
        full_text=full_text,
        abstract_only=meta.get("abstract_only"),
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
async def upload_document(
    topic: OwnedTopicDep,
    file: UploadFile = File(..., description="PDF file to ingest"),
) -> UploadResponse:
    """Upload a PDF and ingest it under the current topic.

    v1.4: magic-byte check + size cap + sync ingest. For large files we should
    defer to Celery but in v1.4 we keep it inline (typical PDF is <2 MB).
    """
    settings = get_settings()
    max_bytes = settings.upload_max_bytes

    # Read full payload (size-bounded).
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="empty file")
    if len(raw_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"file too large ({len(raw_bytes)} bytes > {max_bytes})",
        )

    # Magic-byte check: real PDFs start with '%PDF-' within the first 1024 bytes.
    head = raw_bytes[:1024]
    if not head.startswith(b"%PDF-") and b"%PDF-" not in head:
        raise HTTPException(status_code=415, detail="not a PDF (magic byte missing)")

    # Persist file to storage dir.
    settings.ensure_storage_dirs()
    file_hash = hashlib.sha256(raw_bytes).hexdigest()[:16]
    safe_name = (file.filename or "upload.pdf").replace("/", "_").replace("\\", "_")[:120]
    target_path = Path(settings.upload_storage_dir) / f"{file_hash}_{safe_name}"
    target_path.write_bytes(raw_bytes)

    # Build a RawDocument and run the existing ingest pipeline (sync).
    from app.collectors.base import RawDocument
    from app.db.session import get_sync_sessionmaker
    from app.indexer.ingest_service import ingest_raw_document

    external_id = f"upload-{file_hash}"
    raw = RawDocument(
        source="upload",
        external_id=external_id,
        title=Path(safe_name).stem[:200] or "Uploaded PDF",
        authors=[],
        published_at=datetime.now(tz=UTC),
        url=f"local://{target_path.name}",
        abstract=None,
        matched_keyword="upload",
        metadata={
            "original_filename": file.filename,
            "size_bytes": len(raw_bytes),
            "local_path": str(target_path),
        },
    )

    SessionLocal = get_sync_sessionmaker()
    try:
        with SessionLocal() as sdb:
            from app.db.models.document import Document

            result = ingest_raw_document(db=sdb, topic_id=topic.id, raw=raw)
            # Attach the local PDF path so /documents/{id}/pdf can serve it.
            if result.document_id:
                doc = sdb.get(Document, result.document_id)
                if doc is not None:
                    doc.pdf_path = str(target_path)
                    sdb.flush()
            sdb.commit()
    except Exception as exc:
        log.exception("upload_ingest_failed")
        raise HTTPException(status_code=500, detail=f"ingest failed: {exc}") from exc

    status = "ingested" if result.new else ("reused" if result.reused else "skipped")
    return UploadResponse(
        task_id=None,
        status=status,
        message=f"document_id={result.document_id} ({status})",
    )
