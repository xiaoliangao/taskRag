from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class RawDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source: str
    external_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    published_at: datetime | None = None
    url: str
    abstract: str | None = None
    raw_content_url: str | None = None
    matched_keyword: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CollectorRateLimitedError(Exception):
    """Raised when a collector hit a hard rate limit AND produced no docs.
    Triggers fallback in the task layer."""

    def __init__(self, source: str, detail: str = "") -> None:
        super().__init__(f"{source} rate limited: {detail}")
        self.source = source
        self.detail = detail


class BaseCollector(Protocol):
    source: str

    def search(
        self,
        keywords: list[str],
        since: datetime,
        max_results: int,
    ) -> list[RawDocument]:
        ...


def _normalize_title(title: str) -> str:
    """Title key for cross-source dedup: lowercase, strip punctuation/whitespace.

    Catches the same paper showing up via two upstream APIs with mildly
    different external_ids (eg OpenAlex returning a work twice across pages,
    or arxiv+openalex mirroring the same item) when the per-source primary key
    misses."""
    import re

    if not title:
        return ""
    t = title.lower().strip()
    t = re.sub(r"[\s\-–—:;,.，。：；·_/\\()\[\]{}\"'’“”]+", "", t)
    return t


def dedupe_raw_docs(items: list[RawDocument]) -> list[RawDocument]:
    """Dedup with two passes: (source, external_id) for exact matches, then
    normalized title for cross-source / API-jitter duplicates."""
    seen_keys: dict[tuple[str, str], RawDocument] = {}
    seen_titles: dict[str, RawDocument] = {}
    for d in items:
        key = (d.source, d.external_id)
        title_key = _normalize_title(d.title) if d.title else ""

        existing = seen_keys.get(key)
        if existing is None and title_key:
            existing = seen_titles.get(title_key)

        if existing is None:
            d.metadata["all_matched_keywords"] = [d.matched_keyword] if d.matched_keyword else []
            seen_keys[key] = d
            if title_key:
                seen_titles[title_key] = d
        else:
            if d.matched_keyword and d.matched_keyword not in existing.metadata.get("all_matched_keywords", []):
                existing.metadata.setdefault("all_matched_keywords", []).append(d.matched_keyword)
    return list(seen_keys.values())
