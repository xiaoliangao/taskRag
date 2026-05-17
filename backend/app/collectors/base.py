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


def dedupe_raw_docs(items: list[RawDocument]) -> list[RawDocument]:
    """Dedup by (source, external_id), keeping the first occurrence's matched_keyword
    and collecting all matched keywords in metadata.all_matched_keywords."""
    seen: dict[tuple[str, str], RawDocument] = {}
    for d in items:
        key = (d.source, d.external_id)
        if key not in seen:
            d.metadata["all_matched_keywords"] = [d.matched_keyword] if d.matched_keyword else []
            seen[key] = d
        else:
            existing = seen[key]
            if d.matched_keyword and d.matched_keyword not in existing.metadata.get("all_matched_keywords", []):
                existing.metadata.setdefault("all_matched_keywords", []).append(d.matched_keyword)
    return list(seen.values())
