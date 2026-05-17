from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import arxiv

from app.collectors.base import BaseCollector, CollectorRateLimitedError, RawDocument
from app.core.config import get_settings
from app.core.constants import SourceType

log = logging.getLogger(__name__)


class ArxivCollector(BaseCollector):
    source = SourceType.ARXIV.value

    def __init__(self) -> None:
        # arXiv asks clients to wait 3s between requests; bump to 5s to be safe,
        # and only retry once to avoid burning the rate-limit budget on backoff.
        self._client = arxiv.Client(page_size=50, delay_seconds=5.0, num_retries=1)

    def search(self, keywords: list[str], since: datetime, max_results: int) -> list[RawDocument]:
        if not keywords:
            return []
        out: list[RawDocument] = []
        rate_limited = False
        last_detail = ""
        for kw in keywords:
            query = self._build_query(kw)
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending,
            )
            try:
                for r in self._client.results(search):
                    if r.published and r.published.replace(tzinfo=timezone.utc) < since:
                        break
                    out.append(self._to_raw(r, matched_keyword=kw))
            except arxiv.HTTPError as exc:
                log.warning(
                    "arXiv search failed for '%s' (%s); aborting remaining keywords", kw, exc
                )
                if "429" in str(exc):
                    rate_limited = True
                    last_detail = f"HTTP 429 on keyword '{kw}'"
                    break  # stop trying more keywords during cooldown
            except Exception as exc:
                log.warning("arXiv search failed for '%s': %s", kw, exc)

        if rate_limited and not out:
            # Nothing came back AND we know why. Signal to caller so it can try a fallback.
            raise CollectorRateLimitedError(self.source, last_detail)
        return out

    @staticmethod
    def _build_query(keyword: str) -> str:
        # Restrict the match to title or abstract so passing mentions in
        # references / appendix don't drag in unrelated papers.
        kw = keyword.replace('"', "")
        return f'(ti:"{kw}" OR abs:"{kw}")'

    @staticmethod
    def _to_raw(r: "arxiv.Result", matched_keyword: str) -> RawDocument:
        external_id = ArxivCollector._normalize_id(r.get_short_id() or r.entry_id)
        return RawDocument(
            source=SourceType.ARXIV.value,
            external_id=external_id,
            title=(r.title or "").strip().replace("\n", " "),
            authors=[a.name for a in (r.authors or [])],
            published_at=r.published.replace(tzinfo=timezone.utc) if r.published and r.published.tzinfo is None else r.published,
            url=r.entry_id,
            abstract=(r.summary or "").strip(),
            raw_content_url=r.pdf_url,
            matched_keyword=matched_keyword,
            metadata={
                "categories": list(r.categories or []),
                "primary_category": r.primary_category,
                "pdf_url": r.pdf_url,
            },
        )

    @staticmethod
    def _normalize_id(raw: str) -> str:
        # Strip URL prefix and version suffix
        s = raw
        if "arxiv.org/abs/" in s:
            s = s.split("arxiv.org/abs/", 1)[1]
        s = s.rstrip("/")
        # Remove trailing version e.g. 2401.12345v2 -> 2401.12345
        s = re.sub(r"v\d+$", "", s)
        return s

    def download_pdf(self, raw_doc: RawDocument) -> Path | None:
        settings = get_settings()
        pdf_url = raw_doc.metadata.get("pdf_url") or raw_doc.raw_content_url
        if not pdf_url:
            return None
        target_dir = settings.pdf_storage_dir / self.source
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{raw_doc.external_id.replace('/', '_')}.pdf"
        if target.exists() and target.stat().st_size > 0:
            return target

        import httpx

        # Identify ourselves politely so arXiv operators can contact us
        # if our access pattern is problematic.
        headers = {
            "User-Agent": "TaskRAG-Demo/0.1 (https://github.com/taskrag; mailto:dev@example.com)"
        }

        try:
            with httpx.Client(timeout=60.0, follow_redirects=True, headers=headers) as c:
                resp = c.get(pdf_url)
                if resp.status_code >= 400:
                    log.warning("PDF download failed %s: %s", pdf_url, resp.status_code)
                    return None
                target.write_bytes(resp.content)
            return target
        except Exception as exc:
            log.warning("PDF download exception %s: %s", pdf_url, exc)
            return None
