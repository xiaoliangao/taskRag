from __future__ import annotations

from functools import lru_cache

from app.collectors.arxiv_collector import ArxivCollector
from app.collectors.base import BaseCollector
from app.collectors.openalex_collector import OpenAlexCollector
from app.collectors.semantic_scholar_collector import SemanticScholarCollector
from app.core.constants import SourceType


@lru_cache
def _build_registry() -> dict[str, BaseCollector]:
    return {
        SourceType.ARXIV.value: ArxivCollector(),
        SourceType.OPENALEX.value: OpenAlexCollector(),
        SourceType.SEMANTIC_SCHOLAR.value: SemanticScholarCollector(),
    }


class _NoopCollector:
    def __init__(self, source: str) -> None:
        self.source = source

    def search(self, keywords, since, max_results):  # type: ignore[override]
        return []


def get_collector(source: str) -> BaseCollector:
    reg = _build_registry()
    if source in reg:
        return reg[source]
    return _NoopCollector(source)


# Per-source fallback chain. When the primary collector raises
# CollectorRateLimitedError (and ingested zero docs), the task layer walks this
# list and tries the next one. OpenAlex sits before Semantic Scholar because
# its limits are far more generous and it has near-complete arXiv coverage.
FALLBACK_CHAIN: dict[str, list[str]] = {
    SourceType.ARXIV.value: [
        SourceType.OPENALEX.value,
        SourceType.SEMANTIC_SCHOLAR.value,
    ],
    SourceType.OPENALEX.value: [SourceType.SEMANTIC_SCHOLAR.value],
    SourceType.SEMANTIC_SCHOLAR.value: [SourceType.OPENALEX.value],
}


def get_fallback_sources(source: str) -> list[str]:
    return FALLBACK_CHAIN.get(source, [])


collector_registry = _build_registry
