"""Search-preview + collect-selected service.

Used by the manual-collect UI to let the user see candidate papers from the
collectors before deciding which ones to ingest.
"""
from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import CollectorRateLimitedError, RawDocument, dedupe_raw_docs
from app.collectors.registry import get_collector, get_fallback_sources
from app.core.config import get_settings
from app.db.models.document import Document, TopicDocument
from app.schemas.picker import PreviewItem, PreviewResponse

log = logging.getLogger(__name__)

# Reused across calls so we don't pay thread-startup cost on every search-preview.
_search_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="picker-search")


def _redis_client():
    try:
        import redis

        return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    except Exception:
        return None


def _preview_cache_key(
    topic_id: int, sources: list[str], keywords: list[str], limit: int
) -> str:
    payload = json.dumps(
        {"s": sorted(sources), "k": sorted(keywords), "n": limit},
        ensure_ascii=False,
    )
    digest = hashlib.md5(payload.encode("utf-8")).hexdigest()
    return f"sp:v1:{topic_id}:{digest}"


def invalidate_preview_cache(topic_id: int) -> None:
    """Best-effort: drop all cached previews for a topic. Called after ingestion."""
    cli = _redis_client()
    if cli is None:
        return
    try:
        for key in cli.scan_iter(match=f"sp:v1:{topic_id}:*", count=100):
            cli.delete(key)
    except Exception as exc:
        log.warning("invalidate_preview_cache failed for topic %s: %s", topic_id, exc)


def _search_with_timeout(
    collector, keywords: list[str], since: datetime, max_results: int, timeout_s: float
) -> list[RawDocument]:
    """Run collector.search in a worker thread; raise TimeoutError on overrun.

    The thread keeps running in the background after a timeout — we just stop
    waiting on it. That's fine: arxiv/openalex calls are I/O bound and will
    finish on their own without holding the request hostage.
    """
    fut = _search_executor.submit(collector.search, keywords, since, max_results)
    try:
        return fut.result(timeout=timeout_s)
    except FutureTimeoutError:
        raise TimeoutError(f"collector {getattr(collector, 'source', '?')} exceeded {timeout_s}s")


def _search_preview_for_source(
    primary_source: str,
    keywords: list[str],
    since: datetime,
    max_results: int,
    timeout_s: float,
) -> tuple[list[RawDocument], bool]:
    """Try primary source, fall back the same way as collect_topic_source_task.
    Returns (raw_docs, rate_limited).

    Fallback triggers on: CollectorRateLimitedError, our own TimeoutError, or
    any other exception. If primary returns docs we stop; if primary returns
    empty we also try fallbacks so the user sees something.
    """
    rate_limited = False
    chain = [primary_source] + get_fallback_sources(primary_source)
    aggregate: list[RawDocument] = []
    for src in chain:
        collector = get_collector(src)
        try:
            docs = _search_with_timeout(collector, keywords, since, max_results, timeout_s)
            if docs:
                aggregate.extend(docs)
                if src == primary_source:
                    break
        except CollectorRateLimitedError as exc:
            log.warning("preview %s rate-limited: %s", src, exc.detail)
            rate_limited = True
            continue
        except TimeoutError as exc:
            log.warning("preview %s timeout: %s — falling back", src, exc)
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

    # Cache hit → return early. We re-check already_in_topic against current DB
    # state instead of caching that flag, so users see fresh ingestion status.
    cli = _redis_client()
    cache_key = _preview_cache_key(topic_id, sources, topic_keywords, limit)
    cached_docs: list[RawDocument] | None = None
    cached_rate_limited: list[str] = []
    cached_sources: list[str] = sources
    if cli is not None:
        try:
            hit = cli.get(cache_key)
            if hit:
                blob = json.loads(hit)
                cached_docs = [RawDocument.model_validate(d) for d in blob.get("docs", [])]
                cached_rate_limited = list(blob.get("rate_limited", []))
                cached_sources = list(blob.get("sources", sources))
        except Exception as exc:
            log.warning("preview cache read failed: %s", exc)

    if cached_docs is None:
        since = datetime.now(tz=UTC) - timedelta(days=settings.backfill_days)
        all_docs: list[RawDocument] = []
        rate_limited: list[str] = []
        for src in sources:
            docs, rl = _search_preview_for_source(
                primary_source=src,
                keywords=topic_keywords,
                since=since,
                max_results=limit,
                timeout_s=settings.manual_preview_source_timeout_s,
            )
            all_docs.extend(docs)
            if rl and not docs:
                rate_limited.append(src)
        deduped = dedupe_raw_docs(all_docs)[:limit]

        if cli is not None:
            try:
                cli.setex(
                    cache_key,
                    settings.manual_preview_cache_ttl_s,
                    json.dumps(
                        {
                            "docs": [d.model_dump(mode="json") for d in deduped],
                            "rate_limited": rate_limited,
                            "sources": sources,
                        },
                        ensure_ascii=False,
                    ),
                )
            except Exception as exc:
                log.warning("preview cache write failed: %s", exc)
    else:
        deduped = cached_docs
        rate_limited = cached_rate_limited
        sources = cached_sources

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
