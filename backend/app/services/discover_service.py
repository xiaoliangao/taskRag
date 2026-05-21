"""Topic-less paper discovery.

Same multi-source fallback chain as `picker_service`, but driven by an ad-hoc
user query rather than a saved topic's keywords. Results are cached in Redis
keyed by (sorted sources, sorted keywords, limit) — independent of any topic.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta

from app.collectors.base import RawDocument, dedupe_raw_docs
from app.core.config import get_settings
from app.services.picker_service import _redis_client, _search_preview_for_source

log = logging.getLogger(__name__)

_DEFAULT_SOURCES = ["arxiv", "openalex", "semantic_scholar"]


def _discover_cache_key(sources: list[str], keywords: list[str], limit: int) -> str:
    payload = json.dumps(
        {"s": sorted(sources), "k": sorted(keywords), "n": limit},
        ensure_ascii=False,
    )
    digest = hashlib.md5(payload.encode("utf-8")).hexdigest()
    return f"discover:v1:{digest}"


def discover_search(
    *,
    keywords: list[str],
    sources: list[str] | None,
    limit: int,
    days: int | None = None,
) -> tuple[list[RawDocument], list[str]]:
    """Run the picker fallback chain without any topic context.

    Returns (deduped docs, rate_limited_sources).
    """
    settings = get_settings()
    src_list = [s for s in (sources or _DEFAULT_SOURCES) if s in _DEFAULT_SOURCES]
    if not src_list:
        src_list = list(_DEFAULT_SOURCES)
    kws = [k.strip() for k in keywords if k and k.strip()]
    if not kws:
        return [], []

    cli = _redis_client()
    cache_key = _discover_cache_key(src_list, kws, limit)
    if cli is not None:
        try:
            hit = cli.get(cache_key)
            if hit:
                blob = json.loads(hit)
                docs = [RawDocument.model_validate(d) for d in blob.get("docs", [])]
                return docs, list(blob.get("rate_limited", []))
        except Exception as exc:
            log.warning("discover cache read failed: %s", exc)

    since = datetime.now(tz=UTC) - timedelta(days=days or settings.backfill_days)
    all_docs: list[RawDocument] = []
    rate_limited: list[str] = []
    for src in src_list:
        docs, rl = _search_preview_for_source(
            primary_source=src,
            keywords=kws,
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
                    },
                    ensure_ascii=False,
                ),
            )
        except Exception as exc:
            log.warning("discover cache write failed: %s", exc)

    return deduped, rate_limited
