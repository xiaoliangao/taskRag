"""Re-ingest all (or one topic's) documents under the Wave-3 RAG pipeline.

For each existing Document this script:
  1. Reconstructs a `RawDocument` from the persisted row + pdf_path.
  2. Wipes the doc's existing chunks (PG) and Qdrant points.
  3. Calls `ingest_raw_document` with one of the doc's topic_ids, which
     runs the new Pkg-PC chunker (parent-child) + Pkg-CR contextual
     summarization + embedder, and pushes the new vectors to Qdrant.
  4. For any *additional* topic_ids the doc belongs to, patches the
     Qdrant payload's `topic_ids` list so cross-topic search keeps working.

Usage (inside the backend container):
  python -m scripts.backfill_chunks            # all topics
  python -m scripts.backfill_chunks --topic 2  # one topic
  python -m scripts.backfill_chunks --dry-run  # print plan, don't touch DB

The script is idempotent: running it twice leaves the same end state.
"""
from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy import select

from app.collectors.base import RawDocument
from app.core.constants import DocumentParseStatus
from app.db.models.document import Chunk, Document, TopicDocument
from app.db.session import get_sync_sessionmaker
from app.indexer.ingest_service import ingest_raw_document
from app.indexer.qdrant_client import add_topic_id_to_documents, delete_points_for_documents

log = logging.getLogger(__name__)


def _raw_from_document(doc: Document) -> RawDocument:
    """Reconstruct a RawDocument for the ingest path. Pulls pdf_url + arxiv_id
    out of metadata_json so the parser path uses the existing PDF on disk."""
    meta = dict(doc.metadata_json or {})
    # If we previously stored an absolute pdf_path it'll be on the Document
    # row directly; the collector's download_pdf will short-circuit because
    # the file already exists. metadata.pdf_url drives the collector branch
    # selection in _parse_to_chunks.
    if doc.pdf_path:
        meta.setdefault("pdf_url", f"file://{doc.pdf_path}")
    return RawDocument(
        source=doc.source,
        external_id=doc.external_id,
        title=doc.title or "(untitled)",
        authors=list(doc.authors or []),
        published_at=doc.published_at,
        url=doc.url or "",
        abstract=doc.abstract,
        raw_content_url=meta.get("pdf_url"),
        matched_keyword=None,
        metadata=meta,
    )


def _backfill_one(db, doc: Document, all_topic_ids: list[int], *, dry_run: bool) -> dict:
    """Process a single document. Returns a small status dict for logging."""
    if not all_topic_ids:
        return {"doc_id": doc.id, "status": "skipped", "reason": "no topic associations"}

    primary_topic = all_topic_ids[0]
    extra_topics = all_topic_ids[1:]

    if dry_run:
        return {
            "doc_id": doc.id,
            "status": "would-process",
            "topics": all_topic_ids,
            "pdf_on_disk": bool(doc.pdf_path),
        }

    # 1) wipe chunks for this doc (PG) — cascades nothing else since parent_id
    # is self-referential within the same set. Use sync delete on children first
    # to avoid FK SET NULL noise on already-doomed parent rows.
    child_q = db.query(Chunk).filter(Chunk.document_id == doc.id, Chunk.is_parent.is_(False))
    parent_q = db.query(Chunk).filter(Chunk.document_id == doc.id, Chunk.is_parent.is_(True))
    n_children = child_q.count()
    n_parents = parent_q.count()
    child_q.delete(synchronize_session=False)
    parent_q.delete(synchronize_session=False)
    # legacy: any chunks where is_parent is null
    db.query(Chunk).filter(Chunk.document_id == doc.id).delete(synchronize_session=False)
    db.commit()

    # 2) wipe Qdrant points for this doc
    try:
        delete_points_for_documents([doc.id])
    except Exception as exc:
        log.warning("qdrant delete failed for doc %s: %s — continuing", doc.id, exc)

    # 3) reset parse_status so the ingest path doesn't skip
    doc.parse_status = DocumentParseStatus.PENDING.value
    db.commit()

    # 4) re-ingest. ingest_raw_document upserts on (source, external_id) — the
    # existing Document row is reused since the keys match.
    raw = _raw_from_document(doc)
    result = ingest_raw_document(
        db=db, topic_id=primary_topic, raw=raw, collection_task_id=None
    )
    # ingest_raw_document only flushes — explicit commit so the chunks survive
    # the session close. (Original caller `ingest_picked_documents_task`
    # commits between every pick; we need the same behaviour here.)
    db.commit()

    # 5) patch Qdrant payload for the other topics the doc was linked to
    if extra_topics and result.document_id:
        for tid in extra_topics:
            try:
                add_topic_id_to_documents([doc.id], tid)
            except Exception as exc:
                log.warning("qdrant topic patch failed doc=%s topic=%s: %s", doc.id, tid, exc)

    return {
        "doc_id": doc.id,
        "status": "ok",
        "old_chunks": n_children + n_parents,
        "ingest_result": "new" if result.new else "reused" if result.reused else "skipped",
        "topics": all_topic_ids,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Wave-3 RAG backfill — re-chunk + re-embed every doc.")
    parser.add_argument("--topic", type=int, default=None, help="restrict to this topic_id")
    parser.add_argument("--dry-run", action="store_true", help="print plan, no writes")
    parser.add_argument("--limit", type=int, default=None, help="cap number of docs (for testing)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )

    Session = get_sync_sessionmaker()
    with Session() as db:
        # Pull docs + the topics they belong to so we can patch payloads later.
        if args.topic is not None:
            doc_ids = [
                tid for (tid,) in db.execute(
                    select(TopicDocument.document_id).where(TopicDocument.topic_id == args.topic)
                ).all()
            ]
            docs = (
                db.execute(select(Document).where(Document.id.in_(doc_ids)).order_by(Document.id))
            ).scalars().all() if doc_ids else []
        else:
            docs = db.execute(select(Document).order_by(Document.id)).scalars().all()

        if args.limit:
            docs = docs[: args.limit]

        log.info("backfill start: %d documents", len(docs))
        ok = err = skipped = 0
        for i, doc in enumerate(docs, 1):
            topic_ids = [
                tid for (tid,) in db.execute(
                    select(TopicDocument.topic_id).where(TopicDocument.document_id == doc.id)
                ).all()
            ]
            try:
                status = _backfill_one(db, doc, topic_ids, dry_run=args.dry_run)
            except Exception as exc:
                err += 1
                log.exception("doc %s failed: %s", doc.id, exc)
                db.rollback()
                continue

            if status["status"] == "ok":
                ok += 1
            elif status["status"] == "skipped":
                skipped += 1
            log.info("[%d/%d] %s", i, len(docs), status)

        log.info("backfill done: ok=%d err=%d skipped=%d", ok, err, skipped)
        return 0 if err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
