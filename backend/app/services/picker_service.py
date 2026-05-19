"""Search-preview + collect-selected service.

Used by the manual-collect UI to let the user see candidate papers from the
collectors before deciding which ones to ingest.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import CollectorRateLimitedError, RawDocument, dedupe_raw_docs
from app.collectors.registry import get_collector, get_fallback_sources
from app.core.config import get_settings
from app.db.models.document import Document, TopicDocument
from app.schemas.picker import PreviewItem, PreviewResponse

log = logging.getLogger(__name__)


def _search_preview_for_source(
    primary_source: str, keywords: list[str], since: datetime, max_results: int
) -> tuple[list[RawDocument], bool]:
    """Try primary source, fall back the same way as collect_topic_source_task.
    Returns (raw_docs, rate_limited)."""
    rate_limited = False
    chain = [primary_source] + get_fallback_sources(primary_source)
    aggregate: list[RawDocument] = []
    for src in chain:
        collector = get_collector(src)
        try:
            docs = collector.search(keywords, since, max_results)
            if docs:
                aggregate.extend(docs)
                if src == primary_source:
                    break
        except CollectorRateLimitedError as exc:
            log.warning("preview %s rate-limited: %s", src, exc.detail)
            rate_limited = True
            continue
        except Exception as exc:
            log.warning("preview %s error: %s", src, exc)
            continue
    return dedupe_raw_docs(aggregate), rate_limited


async def search_preview(
    *,
    db: AsyncSession,
    topic_id: int,
    topic_keywords: list[str],
    topic_sources: list[str],
    chosen_sources: list[str] | None,
    limit: int,
) -> PreviewResponse:
    """Run search across one-or-more sources, return combined deduped preview."""
    settings = get_settings()
    sources = chosen_sources or topic_sources
    sources = [s for s in sources if s in topic_sources]
    if not sources:
        sources = topic_sources
    since = datetime.now(tz=UTC) - timedelta(days=settings.backfill_days)

    all_docs: list[RawDocument] = []
    rate_limited: list[str] = []
    for src in sources:
        docs, rl = _search_preview_for_source(
            primary_source=src, keywords=topic_keywords, since=since, max_results=limit
        )
        all_docs.extend(docs)
        if rl and not docs:
            rate_limited.append(src)
    deduped = dedupe_raw_docs(all_docs)[:limit]

    # Mark which ones are already in this topic
    existing_keys: set[tuple[str, str]] = set()
    if deduped:
        keys = [(d.source, d.external_id) for d in deduped]
        r = await db.execute(
            select(Document.source, Document.external_id, Document.id)
            .where(
                Document.source.in_([k[0] for k in keys]),
                Document.external_id.in_([k[1] for k in keys]),
            )
        )
        doc_id_by_key: dict[tuple[str, str], int] = {}
        for src, ext, did in r.all():
            doc_id_by_key[(src, ext)] = did
        if doc_id_by_key:
            r2 = await db.execute(
                select(TopicDocument.document_id).where(
                    TopicDocument.topic_id == topic_id,
                    TopicDocument.document_id.in_(list(doc_id_by_key.values())),
                )
            )
            linked = {int(x) for x in r2.scalars().all()}
            for k, did in doc_id_by_key.items():
                if did in linked:
                    existing_keys.add(k)

    items = [
        PreviewItem(
            source=d.source,
            external_id=d.external_id,
            title=d.title,
            authors=d.authors,
            published_at=d.published_at,
            url=d.url,
            abstract=d.abstract,
            raw_content_url=d.raw_content_url,
            matched_keyword=d.matched_keyword,
            metadata=d.metadata,
            already_in_topic=(d.source, d.external_id) in existing_keys,
        )
        for d in deduped
    ]
    return PreviewResponse(
        sources_queried=sources, rate_limited_sources=rate_limited, items=items
    )
