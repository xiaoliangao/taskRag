"""Export Hub service (Sprint 5 MVP) - BibTeX + Markdown vault inline strings."""
from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.document import Document, TopicDocument
from app.db.models.intel import DocumentBriefing


def _slug(value: str | None) -> str:
    if not value:
        return "item"
    s = re.sub(r"[^A-Za-z0-9]+", "-", value.lower()).strip("-")
    return (s or "item")[:60]


def _year(d: Document) -> str:
    return str(d.published_at.year) if d.published_at else "n.d."


def _authors_str(d: Document) -> str:
    authors = []
    for a in d.authors or []:
        if isinstance(a, str):
            authors.append(a)
        elif isinstance(a, dict):
            authors.append(a.get("name") or "")
    return " and ".join(a for a in authors if a) or "Unknown"


def _fmt_list(values: list | None, limit: int = 5) -> str:
    if not values:
        return ""
    out: list[str] = []
    for v in values[:limit]:
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            out.append(v.get("name") or v.get("title") or str(v))
        else:
            out.append(str(v))
    return ", ".join(out)


def _bibtex_one(doc: Document) -> str:
    key = f"{_slug(_first_author_last(doc))}{_year(doc)}{_slug(doc.title)[:20]}"
    entry_type = "@article" if doc.source in {"arxiv", "openalex", "semantic_scholar"} else "@misc"
    fields = [
        f"  title = {{{(doc.title or '').strip()}}}",
        f"  author = {{{_authors_str(doc)}}}",
        f"  year = {{{_year(doc)}}}",
        f"  url = {{{doc.url or ''}}}",
    ]
    if doc.source == "arxiv":
        fields.append("  archivePrefix = {arXiv}")
        fields.append(f"  eprint = {{{doc.external_id or ''}}}")
    body = ",\n".join(fields)
    return f"{entry_type}{{{key},\n{body}\n}}\n"


def _first_author_last(doc: Document) -> str:
    for a in doc.authors or []:
        s = a if isinstance(a, str) else (a.get("name") if isinstance(a, dict) else "")
        if s:
            parts = s.split()
            return parts[-1] if parts else s
    return "anon"


async def _topic_documents_with_briefing(
    db: AsyncSession, topic_id: int
) -> list[tuple[Document, DocumentBriefing | None]]:
    rows = (
        await db.execute(
            select(Document, DocumentBriefing)
            .join(TopicDocument, TopicDocument.document_id == Document.id)
            .outerjoin(DocumentBriefing, DocumentBriefing.document_id == Document.id)
            .where(TopicDocument.topic_id == topic_id)
            .order_by(Document.published_at.desc().nullslast())
        )
    ).all()
    return [(doc, briefing) for doc, briefing in rows]


async def export_bibtex(db: AsyncSession, topic_id: int) -> str:
    docs = await _topic_documents_with_briefing(db, topic_id)
    if not docs:
        return "% no documents in topic\n"
    out = [
        f"% TaskRAG export — topic {topic_id} — {len(docs)} entries — "
        f"{datetime.now(tz=UTC).isoformat()}\n"
    ]
    for doc, _ in docs:
        out.append(_bibtex_one(doc))
    return "\n".join(out)


def _md_one(doc: Document, briefing: DocumentBriefing | None) -> str:
    tags = []
    if briefing:
        for d in briefing.datasets or []:
            name = d if isinstance(d, str) else (d.get("name") if isinstance(d, dict) else "")
            if name:
                tags.append("#" + _slug(name))
    raw_title = (doc.title or "").strip()
    title_escaped = raw_title.replace('"', '\\"')
    published_str = doc.published_at.isoformat() if doc.published_at else "n.d."
    lines = [
        "---",
        f'title: "{title_escaped}"',
        f'source: "{doc.source}"',
        f'published_at: "{published_str}"',
        f'url: "{doc.url or ""}"',
        f"tags: [{', '.join(tags)}]",
        "---",
        "",
        f"# {(doc.title or '').strip()}",
        "",
        f"- Authors: {_authors_str(doc)}",
        f"- URL: {doc.url or ''}",
    ]
    if briefing:
        if briefing.one_sentence_summary:
            lines += ["", "## One sentence", briefing.one_sentence_summary]
        if briefing.problem:
            lines += ["", "## Problem", briefing.problem]
        if briefing.method:
            lines += ["", "## Method", briefing.method]
        if briefing.contributions:
            lines += ["", "## Contributions"] + [
                f"- {x}" for x in (briefing.contributions or [])[:8]
            ]
        if briefing.limitations:
            lines += ["", "## Limitations"] + [
                f"- {x}" for x in (briefing.limitations or [])[:5]
            ]
        if briefing.datasets:
            lines += ["", "## Datasets", _fmt_list(briefing.datasets, 6)]
        if briefing.metrics:
            lines += ["", "## Metrics", _fmt_list(briefing.metrics, 6)]
    elif doc.abstract:
        lines += ["", "## Abstract", doc.abstract]
    return "\n".join(lines) + "\n"


async def export_markdown_bundle(db: AsyncSession, topic_id: int) -> str:
    """Return a single markdown bundle with sections per paper."""
    docs = await _topic_documents_with_briefing(db, topic_id)
    if not docs:
        return "# (empty topic)\n"
    parts: list[str] = [
        f"# TaskRAG Export — Topic {topic_id}",
        "",
        f"Generated: {datetime.now(tz=UTC).isoformat()}",
        f"Total documents: {len(docs)}",
        "",
        "---",
        "",
    ]
    for doc, briefing in docs:
        parts.append(_md_one(doc, briefing))
        parts.append("\n---\n")
    return "\n".join(parts)


__all__ = ["export_bibtex", "export_markdown_bundle"]
