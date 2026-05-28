"""Semantic Scholar API fallback collector.

Used when arXiv direct API rate-limits us. Semantic Scholar indexes most arXiv
papers, plus other sources, and has a different rate-limit pool.

Endpoint: https://api.semanticscholar.org/graph/v1/paper/search
Auth: optional API key via SEMANTIC_SCHOLAR_API_KEY for higher quota
"""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.collectors.base import BaseCollector, CollectorRateLimitedError, RawDocument
from app.core.config import get_settings
from app.core.constants import SourceType

log = logging.getLogger(__name__)


SS_BASE = "https://api.semanticscholar.org/graph/v1"
FIELDS = (
    "title,authors,year,abstract,openAccessPdf,externalIds,url,publicationDate"
)


class SemanticScholarCollector(BaseCollector):
    """Returns RawDocument with source='arxiv' when possible (keeps storage dedup
    aligned with the arxiv collector), or source='semantic_scholar' as last resort."""

    source = SourceType.SEMANTIC_SCHOLAR.value

    def __init__(self) -> None:
        s = get_settings()
        self._api_key = s.semantic_scholar_api_key or None
        self._timeout = 20.0

    def search(self, keywords: list[str], since: datetime, max_results: int) -> list[RawDocument]:
        if not keywords:
            return []
        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": "TaskRAG/0.1 (mailto:dev@example.com)",
        }
        if self._api_key:
            headers["x-api-key"] = self._api_key

        out: list[RawDocument] = []
        rate_limited = False
        last_detail = ""
        year_floor = since.year if since else None

        with httpx.Client(timeout=self._timeout, headers=headers) as client:
            for kw in keywords:
                params = {
                    "query": kw,
                    "limit": min(max_results, 25),
                    "fields": FIELDS,
                    "sort": "publicationDate:desc",
                }
                if year_floor:
                    params["year"] = f"{year_floor}-"

                # Polite delay between keyword queries
                try:
                    resp = client.get(f"{SS_BASE}/paper/search", params=params)
                except Exception as exc:
                    log.warning("Semantic Scholar HTTP error for '%s': %s", kw, exc)
                    continue

                if resp.status_code == 429:
                    rate_limited = True
                    last_detail = f"HTTP 429 on keyword '{kw}'"
                    # Without an API key SS rate-limits almost immediately and
                    # won't recover within a user request. Bail the entire
                    # search rather than wasting 5s per remaining keyword.
                    if not self._api_key:
                        log.warning(
                            "Semantic Scholar 429 for '%s' (no API key) — aborting", kw
                        )
                        break
                    log.warning(
                        "Semantic Scholar 429 for '%s'; pausing 5s before next keyword", kw
                    )
                    time.sleep(5)
                    continue
                if resp.status_code >= 400:
                    log.warning(
                        "Semantic Scholar %d for '%s': %s",
                        resp.status_code, kw, resp.text[:200],
                    )
                    continue

                payload = resp.json()
                for paper in payload.get("data", []) or []:
                    raw = self._paper_to_raw(paper, matched_keyword=kw)
                    if raw and (since is None or self._after_since(raw, since)):
                        out.append(raw)
                # be polite — SS recommends ~1 req/sec without API key
                time.sleep(1.1 if not self._api_key else 0.2)

        if rate_limited and not out:
            raise CollectorRateLimitedError(self.source, last_detail)
        return out

    @staticmethod
    def _after_since(raw: RawDocument, since: datetime) -> bool:
        if not raw.published_at:
            return True
        if raw.published_at.tzinfo is None:
            return raw.published_at.replace(tzinfo=UTC) >= since
        return raw.published_at >= since

    def fetch_by_doi(self, doi: str) -> RawDocument | None:
        """Lookup by DOI via /paper/DOI:{doi}. No-op if no API key (avoid 429 cycle)."""
        norm = doi.strip()
        norm = norm.removeprefix("https://doi.org/").removeprefix("http://doi.org/").removeprefix("doi:")
        if not norm:
            return None
        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": "TaskRAG/0.1 (mailto:dev@example.com)",
        }
        if self._api_key:
            headers["x-api-key"] = self._api_key
        try:
            with httpx.Client(timeout=self._timeout, headers=headers) as client:
                resp = client.get(
                    f"{SS_BASE}/paper/DOI:{norm}",
                    params={"fields": FIELDS},
                )
                if resp.status_code == 404:
                    return None
                if resp.status_code == 429 and not self._api_key:
                    return None
                if resp.status_code >= 400:
                    log.warning("SS DOI lookup %d for '%s': %s", resp.status_code, norm, resp.text[:200])
                    return None
                return self._paper_to_raw(resp.json(), matched_keyword=f"doi:{norm}")
        except Exception as exc:
            log.warning("SS DOI lookup exception for '%s': %s", norm, exc)
            return None

    def _paper_to_raw(self, paper: dict, matched_keyword: str) -> RawDocument | None:
        external_ids = paper.get("externalIds") or {}
        arxiv_id = external_ids.get("ArXiv")
        title = (paper.get("title") or "").strip()
        if not title:
            return None
        authors = [a.get("name", "") for a in (paper.get("authors") or []) if a.get("name")]
        abstract = (paper.get("abstract") or "").strip() or None
        pub_date = self._parse_date(
            paper.get("publicationDate") or (str(paper.get("year")) if paper.get("year") else None)
        )
        open_pdf = (paper.get("openAccessPdf") or {}).get("url") if paper.get("openAccessPdf") else None

        if arxiv_id:
            # Treat as an arXiv document so it dedupes against direct-arXiv ingests
            return RawDocument(
                source=SourceType.ARXIV.value,
                external_id=str(arxiv_id),
                title=title,
                authors=authors,
                published_at=pub_date,
                url=f"https://arxiv.org/abs/{arxiv_id}",
                abstract=abstract,
                raw_content_url=f"https://arxiv.org/pdf/{arxiv_id}",
                matched_keyword=matched_keyword,
                metadata={
                    "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
                    "via": "semantic_scholar",
                    "ss_paper_id": paper.get("paperId"),
                },
            )

        paper_id = paper.get("paperId")
        if not paper_id:
            return None
        return RawDocument(
            source=SourceType.SEMANTIC_SCHOLAR.value,
            external_id=str(paper_id),
            title=title,
            authors=authors,
            published_at=pub_date,
            url=paper.get("url") or f"https://www.semanticscholar.org/paper/{paper_id}",
            abstract=abstract,
            raw_content_url=open_pdf,
            matched_keyword=matched_keyword,
            metadata={
                "pdf_url": open_pdf,
                "via": "semantic_scholar",
                "ss_paper_id": paper_id,
            },
        )

    @staticmethod
    def _parse_date(value) -> datetime | None:
        if not value:
            return None
        s = str(value).strip()
        for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
            try:
                return datetime.strptime(s, fmt).replace(tzinfo=UTC)
            except ValueError:
                continue
        return None

    def download_pdf(self, raw_doc: RawDocument) -> Path | None:
        """Download via metadata.pdf_url (arxiv.org/pdf or openAccessPdf)."""
        settings = get_settings()
        pdf_url = raw_doc.metadata.get("pdf_url") or raw_doc.raw_content_url
        if not pdf_url:
            return None
        target_dir = settings.pdf_storage_dir / raw_doc.source
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{raw_doc.external_id.replace('/', '_')}.pdf"
        if target.exists() and target.stat().st_size > 0:
            return target
        try:
            with httpx.Client(
                timeout=60.0,
                follow_redirects=True,
                headers={
                    "User-Agent": "TaskRAG/0.1 (mailto:dev@example.com)",
                },
            ) as c:
                resp = c.get(pdf_url)
                if resp.status_code >= 400:
                    log.warning("PDF download via SS failed %s: %d", pdf_url, resp.status_code)
                    return None
                target.write_bytes(resp.content)
            return target
        except Exception as exc:
            log.warning("PDF download via SS exception %s: %s", pdf_url, exc)
            return None
