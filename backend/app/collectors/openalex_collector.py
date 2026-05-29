"""OpenAlex collector — free, no API key required.

Docs: https://docs.openalex.org/

We use polite identification via `mailto=...` query param (recommended). When a
result has an arXiv ID, we emit RawDocument(source='arxiv', external_id=arxivId)
so it dedupes naturally with the direct arXiv collector.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.collectors.base import BaseCollector, CollectorRateLimitedError, RawDocument
from app.core.config import get_settings
from app.core.constants import SourceType

log = logging.getLogger(__name__)


OA_BASE = "https://api.openalex.org"
POLITE_MAILTO = "dev@example.com"  # also surfaces in User-Agent
FIELDS = (
    "id,doi,ids,title,publication_date,abstract_inverted_index,authorships,"
    "open_access,primary_location,locations,type,"
    "referenced_works,cited_by_count,counts_by_year"
)


def _short_wid(s: str | None) -> str | None:
    """Trailing 'W123…' id from an OpenAlex work URL/id."""
    if not s:
        return None
    s = str(s).strip()
    if "/" in s:
        s = s.rsplit("/", 1)[-1]
    return s or None


def _abstract_from_inverted(idx: dict | None) -> str | None:
    if not idx or not isinstance(idx, dict):
        return None
    positions: list[tuple[int, str]] = []
    for word, posns in idx.items():
        if not isinstance(posns, list):
            continue
        for p in posns:
            if isinstance(p, int):
                positions.append((p, word))
    if not positions:
        return None
    positions.sort()
    return " ".join(w for _, w in positions)


def _arxiv_id_from(work: dict) -> str | None:
    """Extract a plain arXiv id (e.g. '2104.06678') from an OpenAlex work."""
    ids = work.get("ids") or {}
    arxiv_field = ids.get("arxiv")
    if arxiv_field:
        s = str(arxiv_field).strip()
        if "arxiv.org/abs/" in s:
            s = s.split("arxiv.org/abs/", 1)[1]
        s = s.rstrip("/")
        s = re.sub(r"v\d+$", "", s)
        return s or None
    # Fallback: scan locations for an arxiv.org URL
    for loc in work.get("locations") or []:
        url = loc.get("landing_page_url") or loc.get("pdf_url") or ""
        if "arxiv.org/abs/" in url:
            tail = url.split("arxiv.org/abs/", 1)[1].rstrip("/")
            tail = re.sub(r"v\d+$", "", tail)
            return tail or None
    return None


def _openalex_work_id(work: dict) -> str:
    """Use the trailing 'W123456789' portion as external_id."""
    full = str(work.get("id") or "")
    if "/" in full:
        return full.rsplit("/", 1)[-1]
    return full


def _parse_pub_date(work: dict) -> datetime | None:
    s = work.get("publication_date")
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)
    except Exception:
        return None


def _best_pdf_url(work: dict) -> str | None:
    """Pick a direct PDF URL. We prefer `*.pdf_url` fields (genuine PDF
    streams) over `open_access.oa_url`, which is often a publisher landing
    page that the download path would then reject. landing → PDF redirect
    chains exist but burn an extra request; prefer direct first."""
    primary = work.get("primary_location") or {}
    if primary.get("pdf_url"):
        return primary["pdf_url"]
    for loc in work.get("locations") or []:
        if loc.get("pdf_url"):
            return loc["pdf_url"]
    oa = work.get("open_access") or {}
    if oa.get("oa_url"):
        return oa["oa_url"]
    return None


def _resolve_via_unpaywall(doi: str) -> str | None:
    """Last-resort PDF lookup for paywalled OpenAlex works.

    Unpaywall aggregates open-access copies of papers (preprints, repository
    deposits) indexed by DOI. Free, no key required, ~100k/day per email.
    Returns a direct PDF URL when one exists, otherwise None.
    """
    if not doi:
        return None
    # Normalize DOI: strip the "https://doi.org/" prefix Unpaywall doesn't want.
    norm = doi.removeprefix("https://doi.org/").removeprefix("http://doi.org/").strip()
    if not norm:
        return None
    try:
        with httpx.Client(timeout=8.0) as c:
            resp = c.get(
                f"https://api.unpaywall.org/v2/{norm}",
                params={"email": POLITE_MAILTO},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            best = data.get("best_oa_location") or {}
            return best.get("url_for_pdf") or None
    except Exception as exc:
        log.debug("unpaywall lookup failed for %s: %s", norm, exc)
        return None


class OpenAlexCollector(BaseCollector):
    source = SourceType.OPENALEX.value

    def __init__(self) -> None:
        self._timeout = 25.0

    def search(self, keywords: list[str], since: datetime, max_results: int) -> list[RawDocument]:
        if not keywords:
            return []
        headers = {
            "Accept": "application/json",
            "User-Agent": f"TaskRAG/0.1 (mailto:{POLITE_MAILTO})",
        }
        out: list[RawDocument] = []
        rate_limited = False
        last_detail = ""
        from_date = since.date().isoformat() if since else None

        with httpx.Client(timeout=self._timeout, headers=headers) as client:
            for kw in keywords:
                # Use OpenAlex's top-level `search` param — it runs a real
                # TF-IDF over title/abstract/keywords and supports
                # `sort=relevance_score:desc`. The previous filter-based
                # approach (`title_and_abstract.search:term`) only did fuzzy
                # boolean matching with no relevance ranking, so combined with
                # `sort=publication_date:desc` it surfaced "newest paper that
                # happens to mention one of these words" — i.e. noise.
                params: dict[str, Any] = {
                    "search": kw,
                    "per-page": min(max_results, 25),
                    "sort": "relevance_score:desc",
                    "select": FIELDS,
                    "mailto": POLITE_MAILTO,
                }
                if from_date:
                    params["filter"] = f"from_publication_date:{from_date}"

                try:
                    resp = client.get(f"{OA_BASE}/works", params=params)
                except Exception as exc:
                    log.warning("OpenAlex HTTP error for '%s': %s", kw, exc)
                    continue

                if resp.status_code == 429:
                    log.warning("OpenAlex 429 for '%s'", kw)
                    rate_limited = True
                    last_detail = f"HTTP 429 on keyword '{kw}'"
                    time.sleep(5)
                    continue
                if resp.status_code >= 400:
                    log.warning(
                        "OpenAlex %d for '%s': %s",
                        resp.status_code,
                        kw,
                        resp.text[:200],
                    )
                    continue

                payload = resp.json()
                for work in payload.get("results", []) or []:
                    raw = self._work_to_raw(work, matched_keyword=kw)
                    if raw:
                        out.append(raw)
                # 100k/day budget → polite ~100ms between requests is plenty
                time.sleep(0.15)

        if rate_limited and not out:
            raise CollectorRateLimitedError(self.source, last_detail)
        return out

    def fetch_by_doi(self, doi: str) -> RawDocument | None:
        """Lookup a single work by DOI via OpenAlex's /works/doi:{doi} route."""
        norm = doi.strip()
        norm = norm.removeprefix("https://doi.org/").removeprefix("http://doi.org/").removeprefix("doi:")
        if not norm:
            return None
        headers = {
            "Accept": "application/json",
            "User-Agent": f"TaskRAG/0.1 (mailto:{POLITE_MAILTO})",
        }
        try:
            with httpx.Client(timeout=self._timeout, headers=headers) as client:
                resp = client.get(
                    f"{OA_BASE}/works/doi:{norm}",
                    params={"select": FIELDS, "mailto": POLITE_MAILTO},
                )
                if resp.status_code == 404:
                    return None
                if resp.status_code >= 400:
                    log.warning("OpenAlex DOI lookup %d for '%s': %s", resp.status_code, norm, resp.text[:200])
                    return None
                return self._work_to_raw(resp.json(), matched_keyword=f"doi:{norm}")
        except Exception as exc:
            log.warning("OpenAlex DOI lookup exception for '%s': %s", norm, exc)
            return None

    def fetch_by_openalex_id(self, work_id: str) -> RawDocument | None:
        """Lookup a single work by its OpenAlex id (W…) — used to enrich an
        already-ingested document with citation metadata."""
        wid = _short_wid(work_id)
        if not wid:
            return None
        headers = {
            "Accept": "application/json",
            "User-Agent": f"TaskRAG/0.1 (mailto:{POLITE_MAILTO})",
        }
        try:
            with httpx.Client(timeout=self._timeout, headers=headers) as client:
                resp = client.get(
                    f"{OA_BASE}/works/{wid}",
                    params={"select": FIELDS, "mailto": POLITE_MAILTO},
                )
                if resp.status_code == 404:
                    return None
                if resp.status_code >= 400:
                    log.warning("OpenAlex id lookup %d for '%s': %s", resp.status_code, wid, resp.text[:200])
                    return None
                return self._work_to_raw(resp.json(), matched_keyword=f"oaid:{wid}")
        except Exception as exc:
            log.warning("OpenAlex id lookup exception for '%s': %s", wid, exc)
            return None

    def search_by_title(self, title: str, limit: int = 5) -> list[RawDocument]:
        """Title-targeted fuzzy search using OpenAlex `title.search:` filter."""
        q = title.strip()
        if not q:
            return []
        headers = {
            "Accept": "application/json",
            "User-Agent": f"TaskRAG/0.1 (mailto:{POLITE_MAILTO})",
        }
        out: list[RawDocument] = []
        try:
            with httpx.Client(timeout=self._timeout, headers=headers) as client:
                resp = client.get(
                    f"{OA_BASE}/works",
                    params={
                        "filter": f"title.search:{q}",
                        "per-page": min(limit, 25),
                        "sort": "relevance_score:desc",
                        "select": FIELDS,
                        "mailto": POLITE_MAILTO,
                    },
                )
                if resp.status_code >= 400:
                    log.warning("OpenAlex title search %d: %s", resp.status_code, resp.text[:200])
                    return []
                for work in resp.json().get("results", []) or []:
                    raw = self._work_to_raw(work, matched_keyword=f"title:{q[:40]}")
                    if raw:
                        out.append(raw)
        except Exception as exc:
            log.warning("OpenAlex title search exception: %s", exc)
        return out

    def _work_to_raw(self, work: dict, matched_keyword: str) -> RawDocument | None:
        title = (work.get("title") or "").strip()
        if not title:
            return None
        authors = [
            (a.get("author") or {}).get("display_name", "")
            for a in (work.get("authorships") or [])
        ]
        authors = [a for a in authors if a]
        pub_date = _parse_pub_date(work)
        abstract = _abstract_from_inverted(work.get("abstract_inverted_index"))
        pdf_url = _best_pdf_url(work)
        arxiv_id = _arxiv_id_from(work)
        work_id = _openalex_work_id(work)

        # Citation metadata — carried on every work so the citation-graph module
        # can build real "A cites B" edges and citation-velocity signals without
        # a second fetch. referenced_works can be long; cap to keep JSONB lean.
        cite_meta = {
            "openalex_id": work_id or None,
            "cited_by_count": work.get("cited_by_count"),
            "counts_by_year": work.get("counts_by_year") or [],
            "referenced_works": [
                w for w in (_short_wid(r) for r in (work.get("referenced_works") or [])) if w
            ][:200],
        }

        if arxiv_id:
            # Treat as arxiv document to dedupe across collectors
            return RawDocument(
                source=SourceType.ARXIV.value,
                external_id=arxiv_id,
                title=title,
                authors=authors,
                published_at=pub_date,
                url=f"https://arxiv.org/abs/{arxiv_id}",
                abstract=abstract,
                raw_content_url=f"https://arxiv.org/pdf/{arxiv_id}",
                matched_keyword=matched_keyword,
                metadata={
                    "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
                    "via": "openalex",
                    "doi": (work.get("ids") or {}).get("doi"),
                    **cite_meta,
                },
            )

        if not work_id:
            return None
        landing = (work.get("primary_location") or {}).get("landing_page_url")
        return RawDocument(
            source=SourceType.OPENALEX.value,
            external_id=work_id,
            title=title,
            authors=authors,
            published_at=pub_date,
            url=landing or f"https://openalex.org/{work_id}",
            abstract=abstract,
            raw_content_url=pdf_url,
            matched_keyword=matched_keyword,
            metadata={
                "pdf_url": pdf_url,
                "via": "openalex",
                "doi": (work.get("ids") or {}).get("doi"),
                "type": work.get("type"),
                **cite_meta,
            },
        )

    def download_pdf(self, raw_doc: RawDocument) -> Path | None:
        settings = get_settings()
        target_dir = settings.pdf_storage_dir / raw_doc.source
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_id = raw_doc.external_id.replace("/", "_")
        target = target_dir / f"{safe_id}.pdf"
        if target.exists() and target.stat().st_size > 0:
            return target

        # Candidate URLs in order: the one OpenAlex itself chose, then a DOI →
        # Unpaywall lookup. Tried sequentially because Unpaywall costs a network
        # round-trip; only worth paying when OpenAlex came up empty or returned
        # a landing page.
        candidates: list[str] = []
        primary = raw_doc.metadata.get("pdf_url") or raw_doc.raw_content_url
        if primary:
            candidates.append(primary)

        for pdf_url in candidates + [None]:  # extra None slot triggers Unpaywall
            if pdf_url is None:
                # Already tried direct candidates above; try Unpaywall.
                doi = raw_doc.metadata.get("doi")
                pdf_url = _resolve_via_unpaywall(doi) if doi else None
                if not pdf_url:
                    break
                log.info("OpenAlex Unpaywall recovery for %s → %s", raw_doc.external_id, pdf_url)
            try:
                with httpx.Client(
                    timeout=60.0,
                    follow_redirects=True,
                    headers={"User-Agent": f"TaskRAG/0.1 (mailto:{POLITE_MAILTO})"},
                ) as c:
                    resp = c.get(pdf_url)
                    if resp.status_code >= 400:
                        log.info(
                            "OpenAlex PDF candidate %s failed: HTTP %d", pdf_url, resp.status_code
                        )
                        continue
                    ct = resp.headers.get("content-type", "")
                    if "pdf" not in ct.lower() and not resp.content.startswith(b"%PDF"):
                        log.info("OpenAlex URL not a PDF (%s); skipping: %s", ct, pdf_url)
                        continue
                    target.write_bytes(resp.content)
                return target
            except Exception as exc:
                log.warning("OpenAlex PDF download exception %s: %s", pdf_url, exc)
                continue
        return None
