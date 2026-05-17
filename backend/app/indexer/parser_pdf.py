from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings

log = logging.getLogger(__name__)


@dataclass
class ParsedSection:
    title: str | None
    text: str
    page_start: int
    page_end: int


@dataclass
class ParsedPdf:
    full_text: str
    sections: list[ParsedSection]


_SECTION_RE = re.compile(
    r"^\s*(?:\d+\.?\s+|[IVX]+\.?\s+|[A-Z]\.\s+)?"
    r"(Abstract|Introduction|Related Work|Background|Method|Methods|Methodology|"
    r"Approach|Experiments?|Results?|Evaluation|Discussion|Conclusions?|References)"
    r"\s*:?\s*$",
    re.IGNORECASE,
)


_PARSE_TIMEOUT_S = 60
_MAX_PAGES = 80


def parse_pdf(pdf_path: Path) -> ParsedPdf | None:
    """Parse a PDF with a hard timeout. Returns None on failure or timeout
    so the caller can fall back to abstract-only indexing."""
    import concurrent.futures

    if not pdf_path.exists():
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_parse_pdf_impl, pdf_path)
        try:
            return future.result(timeout=_PARSE_TIMEOUT_S)
        except concurrent.futures.TimeoutError:
            log.warning("PDF parse timed out after %ds for %s — falling back to abstract", _PARSE_TIMEOUT_S, pdf_path)
            return None
        except Exception as exc:
            log.warning("PDF parse failed for %s: %s", pdf_path, exc)
            return None


def _parse_pdf_impl(pdf_path: Path) -> ParsedPdf | None:
    try:
        import fitz  # type: ignore
    except Exception as exc:
        log.error("PyMuPDF not installed: %s", exc)
        return None

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        log.warning("PyMuPDF failed to open %s: %s", pdf_path, exc)
        return None

    if doc.page_count > _MAX_PAGES:
        log.info("PDF has %d pages (> %d cap); skipping parse for %s", doc.page_count, _MAX_PAGES, pdf_path)
        doc.close()
        return None

    settings = get_settings()
    max_bytes = settings.fulltext_max_bytes

    full_parts: list[str] = []
    sections: list[ParsedSection] = []
    current_title: str | None = None
    current_lines: list[str] = []
    current_start_page = 1
    current_end_page = 1
    total_len = 0

    def _flush_section(end_page: int) -> None:
        nonlocal current_title, current_lines, current_start_page
        text = "\n".join(current_lines).strip()
        if text:
            sections.append(
                ParsedSection(
                    title=current_title,
                    text=text,
                    page_start=current_start_page,
                    page_end=end_page,
                )
            )
        current_title = None
        current_lines = []

    try:
        for page_idx in range(doc.page_count):
            page = doc.load_page(page_idx)
            text = page.get_text("text") or ""
            full_parts.append(text)
            total_len += len(text.encode("utf-8", errors="ignore"))

            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if _SECTION_RE.match(line) and len(line) < 80:
                    _flush_section(page_idx + 1)
                    current_title = line
                    current_start_page = page_idx + 1
                    current_end_page = page_idx + 1
                else:
                    current_lines.append(line)
                    current_end_page = page_idx + 1

            if total_len > max_bytes:
                log.info("Truncating PDF parse at page %d (over %d bytes)", page_idx + 1, max_bytes)
                break

        _flush_section(current_end_page)
    finally:
        doc.close()

    full_text = "\n".join(full_parts).strip()
    if not full_text:
        return None
    return ParsedPdf(full_text=full_text, sections=sections)
