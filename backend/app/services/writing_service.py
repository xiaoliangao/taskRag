"""Related Work Studio service (Sprint 4 MVP)."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.document import Document, TopicDocument
from app.db.models.intel import DocumentBriefing
from app.db.models.research_ext import WritingProject, WritingProjectSource
from app.rag.llm_client import get_llm_client
from app.services.json_llm import (
    safe_parse_json_object,
    truncate_for_llm,
)

log = logging.getLogger(__name__)


_OUTLINE_SYSTEM = """你是 Related Work 大纲生成助手。给定用户研究问题 + Topic 内已选择的论文 briefing，
生成一个结构化的章节大纲。

硬性规则：
1. 每个 section 内只允许 1-3 个 paragraph_intent。
2. 每个 paragraph_intent 必须绑定 ≥ 1 个 document_id（来自给定 sources）。
3. 不允许引入未给定的论文。
4. 大纲使用与 user_intent 相同的语言（默认中文）。
5. 严格输出 JSON object。
"""

_OUTLINE_USER_TMPL = """user_intent: {intent}

sources:
{sources}

输出 JSON：
{{
  "sections": [
    {{
      "section_title": "...",
      "paragraphs": [
        {{
          "intent": "概述 ... 的方法路线",
          "document_ids": [101, 122]
        }}
      ]
    }}
  ]
}}
"""

_DRAFT_SYSTEM = """你是 Related Work 段落写作助手。基于已确认的 outline + 已选 sources，
为每个 paragraph_intent 写出一段连贯的学术段落。

硬性规则：
1. 每个具体 claim 后必须带 citation label，如 [1]。
2. citation label 必须能与 citation_json 中的条目一一对应。
3. 不允许编造作者、年份、数据集、指标。
4. 任何 outline 未提供证据的论点不要写；改写为"当前 Topic 中未找到充分证据"。
5. 段落语气保持中性学术风格。
6. 输出 JSON object：包含 draft_md (markdown) 与 citation_json (与 draft 内编号一致)。
"""

_DRAFT_USER_TMPL = """user_intent: {intent}

outline_json:
{outline}

sources:
{sources}

输出 JSON：
{{
  "draft_md": "...",
  "citation_json": [
    {{"label": "[1]", "document_id": 101, "title": "...", "url": "..."}}
  ]
}}
"""


def _fmt_list(values: list | None, limit: int = 5) -> str:
    if not values:
        return "—"
    out = []
    for v in values[:limit]:
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            out.append(v.get("name") or v.get("title") or str(v))
        else:
            out.append(str(v))
    return "; ".join(out)


def _format_sources(
    docs: list[tuple[Document, DocumentBriefing | None]],
    max_chars: int = 8000,
) -> str:
    lines: list[str] = []
    used = 0
    for doc, briefing in docs:
        block = (
            f"- document_id: {doc.id}\n"
            f"  title: {doc.title}\n"
            f"  url: {doc.url}\n"
            f"  published_at: {doc.published_at.isoformat() if doc.published_at else 'unknown'}\n"
            f"  summary: {(briefing.one_sentence_summary if briefing else (doc.abstract or ''))[:300]}\n"
            f"  method: {(briefing.method if briefing else '') or 'N/A'}\n"
            f"  datasets: {_fmt_list(briefing.datasets if briefing else [], 3)}\n"
            f"  metrics: {_fmt_list(briefing.metrics if briefing else [], 3)}\n"
            f"  limitations: {_fmt_list(briefing.limitations if briefing else [], 3)}\n"
        )
        if used + len(block) > max_chars:
            break
        lines.append(block)
        used += len(block)
    return "\n".join(lines) or "(no sources)"


CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def validate_citations(draft_md: str, citation_json: list, allowed_doc_ids: set[int]) -> list[str]:
    """Return list of validation errors; empty list = OK."""
    errors: list[str] = []
    label_to_entry: dict[str, dict] = {}
    for entry in citation_json or []:
        if not isinstance(entry, dict):
            continue
        label = entry.get("label")
        if isinstance(label, str):
            label_to_entry[label] = entry
    used_labels = set(f"[{m.group(1)}]" for m in CITATION_PATTERN.finditer(draft_md or ""))
    for label in used_labels:
        if label not in label_to_entry:
            errors.append(f"draft 引用 {label} 在 citation_json 中找不到")
            continue
        did = label_to_entry[label].get("document_id")
        if not isinstance(did, int) or did not in allowed_doc_ids:
            errors.append(f"citation {label} 指向的 document_id={did} 不属于已选源")
    return errors


async def _fetch_documents(
    db: AsyncSession, topic_id: int, document_ids: list[int]
) -> list[tuple[Document, DocumentBriefing | None]]:
    if not document_ids:
        return []
    rows = (
        await db.execute(
            select(Document, DocumentBriefing)
            .join(TopicDocument, TopicDocument.document_id == Document.id)
            .outerjoin(DocumentBriefing, DocumentBriefing.document_id == Document.id)
            .where(
                TopicDocument.topic_id == topic_id,
                Document.id.in_(document_ids),
            )
        )
    ).all()
    pairs: dict[int, tuple[Document, DocumentBriefing | None]] = {}
    for doc, briefing in rows:
        pairs.setdefault(doc.id, (doc, briefing))
    return [pairs[did] for did in document_ids if did in pairs]


class WritingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_project(
        self,
        *,
        user_id: int,
        topic_id: int,
        title: str,
        user_intent: str,
        document_ids: list[int],
    ) -> WritingProject:
        if not document_ids:
            raise ValueError("at least 1 source document required")
        # Validate documents belong to topic
        valid = (
            await self.db.execute(
                select(TopicDocument.document_id).where(
                    TopicDocument.topic_id == topic_id,
                    TopicDocument.document_id.in_(document_ids),
                )
            )
        ).all()
        valid_ids = {r[0] for r in valid}
        if valid_ids != set(document_ids):
            raise ValueError("some documents are not in this topic")

        project = WritingProject(
            user_id=user_id,
            topic_id=topic_id,
            title=title[:200],
            writing_type="related_work",
            user_intent=user_intent[:2000],
            scope_json={"source_scope": "selected_documents", "document_ids": document_ids},
            status="draft",
        )
        self.db.add(project)
        await self.db.flush()
        for did in document_ids:
            self.db.add(
                WritingProjectSource(
                    writing_project_id=project.id,
                    document_id=did,
                    role="primary",
                )
            )
        await self.db.flush()
        return project

    async def generate_outline(self, project: WritingProject) -> WritingProject:
        document_ids = (project.scope_json or {}).get("document_ids") or []
        docs = await _fetch_documents(self.db, project.topic_id, document_ids)
        if not docs:
            project.status = "failed"
            project.error_message = "没有可用的 source documents"
            await self.db.flush()
            return project
        client = get_llm_client()
        user_msg = _OUTLINE_USER_TMPL.format(
            intent=truncate_for_llm(project.user_intent or "", 800),
            sources=_format_sources(docs, max_chars=4000),
        )
        try:
            raw = client.complete(
                [
                    {"role": "system", "content": _OUTLINE_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.2,
                max_tokens=800,
            )
        except Exception as exc:
            project.status = "failed"
            project.error_message = f"outline_llm_failed: {exc}"[:500]
            await self.db.flush()
            return project
        data = safe_parse_json_object(raw, fallback={"sections": []})
        project.outline_json = data
        project.status = "outline_ready"
        await self.db.flush()
        return project

    async def generate_draft(self, project: WritingProject) -> WritingProject:
        if not project.outline_json or not project.outline_json.get("sections"):
            await self.generate_outline(project)
        if project.status == "failed":
            return project
        document_ids = (project.scope_json or {}).get("document_ids") or []
        docs = await _fetch_documents(self.db, project.topic_id, document_ids)
        allowed = {d.id for d, _ in docs}
        client = get_llm_client()
        user_msg = _DRAFT_USER_TMPL.format(
            intent=truncate_for_llm(project.user_intent or "", 800),
            outline=truncate_for_llm(str(project.outline_json), 2000),
            sources=_format_sources(docs, max_chars=5000),
        )
        try:
            raw = client.complete(
                [
                    {"role": "system", "content": _DRAFT_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.3,
                max_tokens=1600,
            )
        except Exception as exc:
            project.status = "failed"
            project.error_message = f"draft_llm_failed: {exc}"[:500]
            await self.db.flush()
            return project
        data = safe_parse_json_object(raw, fallback={})
        draft_md = (data.get("draft_md") or "").strip()
        citations = data.get("citation_json") or []
        if not isinstance(citations, list):
            citations = []
        # Inject minimal fallback metadata into citation entries (title/url from sources)
        doc_meta = {d.id: {"title": d.title, "url": d.url} for d, _ in docs}
        for c in citations:
            if isinstance(c, dict):
                did = c.get("document_id")
                if isinstance(did, int) and did in doc_meta:
                    c.setdefault("title", doc_meta[did]["title"])
                    c.setdefault("url", doc_meta[did]["url"])

        errors = validate_citations(draft_md, citations, allowed)
        if errors:
            project.status = "failed"
            project.error_message = "citation_validation_failed: " + " | ".join(errors[:3])
            project.draft_md = draft_md  # keep for inspection
            project.citation_json = citations
            await self.db.flush()
            return project

        project.draft_md = draft_md
        project.citation_json = citations
        project.status = "draft_ready"
        await self.db.flush()
        return project


async def list_projects(
    db: AsyncSession, user_id: int, topic_id: int, limit: int = 50
) -> Sequence[WritingProject]:
    return (
        await db.execute(
            select(WritingProject)
            .where(
                WritingProject.user_id == user_id,
                WritingProject.topic_id == topic_id,
            )
            .order_by(WritingProject.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()


async def get_project(db: AsyncSession, project_id: int) -> WritingProject | None:
    return await db.get(WritingProject, project_id)


__all__ = ["WritingService", "list_projects", "get_project", "validate_citations"]
