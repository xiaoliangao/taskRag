from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path

from sqlalchemy.orm import Session

from app.collectors.base import RawDocument
from app.collectors.registry import get_collector
from app.core.config import get_settings
from app.core.constants import DocumentParseStatus, SourceType
from app.db.models.document import Document
from app.indexer.chunker import ChunkData, split_plain_text, split_sections
from app.indexer.cleaner import clean_text
from app.indexer.embedder import get_embedder
from app.indexer.parser_pdf import parse_pdf
from app.indexer.qdrant_client import (
    add_topic_id_to_documents,
    stable_vector_id,
    upsert_points,
)

log = logging.getLogger(__name__)


@dataclass
class IngestResult:
    new: bool = False
    reused: bool = False
    skipped: bool = False
    document_id: int | None = None
    newly_associated: bool = False  # topic_document association added in this call


def _content_hash(raw: RawDocument) -> str:
    base = "|".join([raw.source, raw.external_id, raw.title or "", raw.url or ""])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _parse_to_chunks(document: Document, raw: RawDocument) -> tuple[list[ChunkData], str | None]:
    """Return chunks and an optional full_text_path written to disk.

    Side effect: when we fall back to abstract because the PDF was unreachable
    or unparseable, stamps `document.metadata_json["abstract_only"] = True` so
    the UI can warn that this document's RAG coverage is shallow. When the
    full PDF parses cleanly the flag is set to False (rather than omitted) so
    callers can distinguish "known full-text" from "never tried".
    """
    settings = get_settings()
    fulltext_path: str | None = None

    def _stamp(abstract_only: bool) -> None:
        meta = dict(document.metadata_json or {})
        meta["abstract_only"] = abstract_only
        document.metadata_json = meta

    # arXiv (direct or via OpenAlex/SS fallback) + OpenAlex/SS with PDF url.
    if (
        document.source
        in (
            SourceType.ARXIV.value,
            SourceType.OPENALEX.value,
            SourceType.SEMANTIC_SCHOLAR.value,
        )
        and (raw.metadata.get("pdf_url") or raw.raw_content_url)
    ):
        # Each source has its own download_pdf implementation
        collector = get_collector(document.source)
        pdf_path: Path | None = None
        download = getattr(collector, "download_pdf", None)
        if callable(download):
            pdf_path = download(raw)
        if pdf_path:
            document.pdf_path = str(pdf_path)
            parsed = parse_pdf(pdf_path)
            if parsed:
                cleaned_full = clean_text(parsed.full_text)
                target_dir = settings.fulltext_storage_dir / document.source
                target_dir.mkdir(parents=True, exist_ok=True)
                target = target_dir / f"{document.external_id.replace('/', '_')}.txt"
                target.write_text(cleaned_full[: settings.fulltext_max_bytes], encoding="utf-8")
                fulltext_path = str(target)
                cleaned_sections = [
                    type(s)(
                        title=s.title,
                        text=clean_text(s.text),
                        page_start=s.page_start,
                        page_end=s.page_end,
                    )
                    for s in parsed.sections
                    if s.text and s.text.strip()
                ]
                _stamp(False)
                if cleaned_sections:
                    return split_sections(cleaned_sections), fulltext_path
                return split_plain_text(cleaned_full, section_title="Body"), fulltext_path
        # Fallback: abstract only
        if raw.abstract:
            _stamp(True)
            return split_plain_text(clean_text(raw.abstract), section_title="Abstract"), None
        _stamp(True)
        return [], None

    # Generic fallback for other sources: use abstract / metadata text if available
    body = raw.abstract or raw.metadata.get("body") or raw.metadata.get("readme") or ""
    body = clean_text(body)
    if not body:
        _stamp(True)
        return [], None
    _stamp(True)
    return split_plain_text(body, section_title="Body"), None


def ingest_raw_document(
    *,
    db: Session,
    topic_id: int,
    raw: RawDocument,
    collection_task_id: int | None = None,
) -> IngestResult:
    """Sync ingest function — used from Celery workers (sync SQLAlchemy session)."""
    from app.db.models.document import Chunk, TopicDocument

    # 1) upsert document by (source, external_id)
    existing: Document | None = (
        db.query(Document)
        .filter(Document.source == raw.source, Document.external_id == raw.external_id)
        .first()
    )
    if existing:
        document = existing
    else:
        document = Document(
            source=raw.source,
            external_id=raw.external_id,
            title=raw.title,
            authors=raw.authors or [],
            published_at=raw.published_at,
            url=raw.url,
            abstract=raw.abstract,
            content_hash=_content_hash(raw),
            metadata_json=dict(raw.metadata or {}),
            parse_status=DocumentParseStatus.PENDING.value,
        )
        db.add(document)
        db.flush()

    # 2) insert topic_documents association (ignore if exists)
    assoc_existing = (
        db.query(TopicDocument)
        .filter(TopicDocument.topic_id == topic_id, TopicDocument.document_id == document.id)
        .first()
    )
    newly_associated = False
    if not assoc_existing:
        db.add(
            TopicDocument(
                topic_id=topic_id,
                document_id=document.id,
                matched_keyword=raw.matched_keyword,
                added_by_task_id=collection_task_id,
            )
        )
        db.flush()
        newly_associated = True

    # 3) if chunks already exist for the document, just patch topic_ids in Qdrant
    has_chunks = (
        db.query(Chunk.id).filter(Chunk.document_id == document.id).limit(1).first() is not None
    )
    if has_chunks:
        if newly_associated:
            try:
                add_topic_id_to_documents([document.id], topic_id)
            except Exception as exc:
                log.warning("Qdrant topic_ids update failed for doc %s: %s", document.id, exc)
        return IngestResult(reused=True, document_id=document.id, newly_associated=newly_associated)

    # 4) otherwise: parse, chunk, embed, write
    chunks, fulltext_path = _parse_to_chunks(document, raw)
    if not chunks:
        document.parse_status = DocumentParseStatus.SKIPPED.value
        meta = dict(document.metadata_json or {})
        meta["skip_reason"] = "no parseable text"
        document.metadata_json = meta
        db.flush()
        return IngestResult(skipped=True, document_id=document.id, newly_associated=newly_associated)

    embedder = get_embedder()
    vectors = embedder.embed_texts([c.text for c in chunks])

    # Insert chunks
    chunk_rows: list[Chunk] = []
    points: list[dict] = []
    for c, vec in zip(chunks, vectors, strict=False):
        vid = stable_vector_id(document.source, document.external_id, c.chunk_index, document.doc_version)
        chunk_row = Chunk(
            document_id=document.id,
            chunk_index=c.chunk_index,
            text=c.text,
            token_count=c.token_count,
            section_title=c.section_title,
            page_start=c.page_start,
            page_end=c.page_end,
            vector_id=vid,
        )
        db.add(chunk_row)
        chunk_rows.append(chunk_row)
        points.append(
            {
                "id": str(vid),
                "vector": vec,
                "payload": {
                    "document_id": document.id,
                    "topic_ids": [topic_id],
                    "source": document.source,
                    "published_at": (
                        document.published_at.astimezone(UTC).isoformat()
                        if document.published_at
                        else None
                    ),
                    "title": document.title,
                    "url": document.url,
                    "section_title": c.section_title,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                },
            }
        )
    db.flush()

    try:
        upsert_points(points=points)
    except Exception as exc:
        log.error("Qdrant upsert failed: %s", exc)
        # mark parse_status failed so it can be retried later
        document.parse_status = DocumentParseStatus.FAILED.value
        meta = dict(document.metadata_json or {})
        meta["qdrant_error"] = str(exc)[:300]
        document.metadata_json = meta
        db.flush()
        raise

    document.parse_status = DocumentParseStatus.PARSED.value
    if fulltext_path:
        document.full_text_path = fulltext_path
    db.flush()
    return IngestResult(new=True, document_id=document.id, newly_associated=newly_associated)
