"""Method comparison matrix service (Sprint 4 MVP)."""
from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.document import Document, TopicDocument
from app.db.models.intel import DocumentBriefing
from app.db.models.research_ext import ComparisonItem, ComparisonSession
from app.rag.llm_client import get_llm_client
from app.services.json_llm import (
    safe_parse_json_object,
    truncate_for_llm,
)

log = logging.getLogger(__name__)


_DEFAULT_COLUMNS = [
    "paper",
    "problem",
    "method",
    "datasets",
    "metrics",
    "main_results",
    "strengths",
    "limitations",
    "code",
]

_FILL_SYSTEM = """你是论文方法对比助手。给定一篇论文的 briefing 与摘要，
针对以下对比维度，逐个填写该论文的对应内容。

硬性规则：
1. 每个字段输出 ≤ 80 字；不允许跨论文比较或推断。
2. datasets / metrics 字段直接复用 briefing 中的列表（取前 3 个）。
3. main_results 仅能写 briefing/abstract 中明确出现的数字或定性结论。
4. 缺失字段返回 "N/A"，不要编造。
5. code 字段：briefing.code_available 为 true 写 "Yes" + url；否则 "N/A"。
6. 严格输出 JSON object；键名与给定 dimensions 完全一致。
"""

_FILL_USER_TMPL = """document_title: {title}
abstract: {abstract}

briefing:
  one_sentence_summary: {summary}
  problem: {problem}
  method: {method}
  contributions: {contributions}
  experiments: {experiments}
  limitations: {limitations}
  datasets: {datasets}
  metrics: {metrics}
  code_available: {code_avail}
  code_url: {code_url}

dimensions: {dimensions}

输出 JSON：
{{
  "problem": "...",
  "method": "...",
  "datasets": "...",
  "metrics": "...",
  "main_results": "...",
  "strengths": "...",
  "limitations": "...",
  "code": "N/A"
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


async def _fetch_documents_with_briefing(
    db: AsyncSession, topic_id: int, document_ids: list[int]
) -> list[tuple[Document, DocumentBriefing | None]]:
    if not document_ids:
        return []
    # Ensure each document belongs to topic
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
    # Preserve user-requested order
    return [pairs[did] for did in document_ids if did in pairs]


class ComparisonService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        user_id: int,
        topic_id: int,
        title: str,
        document_ids: list[int],
    ) -> ComparisonSession:
        if len(document_ids) < 2:
            raise ValueError("comparison requires at least 2 documents")
        if len(document_ids) > 8:
            raise ValueError("comparison supports at most 8 documents")
        # Validate documents belong to topic
        rows = (
            await self.db.execute(
                select(TopicDocument.document_id).where(
                    TopicDocument.topic_id == topic_id,
                    TopicDocument.document_id.in_(document_ids),
                )
            )
        ).all()
        valid_ids = {r[0] for r in rows}
        if valid_ids != set(document_ids):
            raise ValueError("some documents are not in this topic")

        session = ComparisonSession(
            user_id=user_id, topic_id=topic_id, title=title[:200], status="pending"
        )
        self.db.add(session)
        await self.db.flush()
        for i, did in enumerate(document_ids):
            self.db.add(
                ComparisonItem(
                    comparison_session_id=session.id,
                    document_id=did,
                    role="target",
                    order_index=i,
                )
            )
        await self.db.flush()
        return session

    async def generate(self, session: ComparisonSession) -> ComparisonSession:
        session.status = "running"
        await self.db.flush()
        items = (
            await self.db.execute(
                select(ComparisonItem)
                .where(ComparisonItem.comparison_session_id == session.id)
                .order_by(ComparisonItem.order_index.asc())
            )
        ).scalars().all()
        document_ids = [it.document_id for it in items]
        doc_rows = await _fetch_documents_with_briefing(self.db, session.topic_id, document_ids)

        rows = []
        client = get_llm_client()
        for doc, briefing in doc_rows:
            cells = self._cells_from_briefing(doc, briefing)
            need_llm_fill = any(v == "N/A" for v in cells.values() if v) and (briefing is not None or doc.abstract)
            if need_llm_fill:
                cells = self._llm_fill(client, doc, briefing, cells)
            cells["paper"] = doc.title or f"Document #{doc.id}"
            cells["document_id"] = doc.id
            rows.append(cells)

        result_json = {
            "columns": _DEFAULT_COLUMNS,
            "rows": rows,
        }
        result_md = self._render_markdown(result_json)
        session.result_json = result_json
        session.result_md = result_md
        session.status = "success"
        session.finished_at = datetime.now(tz=UTC)
        await self.db.flush()
        return session

    def _cells_from_briefing(
        self, doc: Document, briefing: DocumentBriefing | None
    ) -> dict:
        if briefing is None:
            return {col: "N/A" for col in _DEFAULT_COLUMNS}
        return {
            "paper": doc.title or "(无标题)",
            "problem": (briefing.problem or "N/A")[:160],
            "method": (briefing.method or "N/A")[:160],
            "datasets": _fmt_list(briefing.datasets, 3),
            "metrics": _fmt_list(briefing.metrics, 3),
            "main_results": _fmt_list(briefing.experiments, 2),
            "strengths": _fmt_list(briefing.contributions, 2),
            "limitations": _fmt_list(briefing.limitations, 2),
            "code": (
                "Yes" if briefing.code_available else ("N/A" if briefing.code_available is None else "No")
            ) + (f" ({briefing.code_url})" if briefing.code_url else ""),
        }

    def _llm_fill(
        self,
        client,
        doc: Document,
        briefing: DocumentBriefing | None,
        cells: dict,
    ) -> dict:
        missing = [k for k, v in cells.items() if v == "N/A" and k != "paper"]
        if not missing:
            return cells
        try:
            user_msg = _FILL_USER_TMPL.format(
                title=truncate_for_llm(doc.title or "", 200),
                abstract=truncate_for_llm(doc.abstract or "", 1200),
                summary=(briefing.one_sentence_summary if briefing else "") or "",
                problem=(briefing.problem if briefing else "") or "",
                method=(briefing.method if briefing else "") or "",
                contributions=_fmt_list(briefing.contributions if briefing else [], 5),
                experiments=_fmt_list(briefing.experiments if briefing else [], 5),
                limitations=_fmt_list(briefing.limitations if briefing else [], 5),
                datasets=_fmt_list(briefing.datasets if briefing else [], 5),
                metrics=_fmt_list(briefing.metrics if briefing else [], 5),
                code_avail=(briefing.code_available if briefing else None),
                code_url=(briefing.code_url if briefing else "") or "",
                dimensions=missing,
            )
            raw = client.complete(
                [
                    {"role": "system", "content": _FILL_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.1,
                max_tokens=500,
            )
        except Exception as exc:
            log.warning("comparison_cell_fill_failed: %s", exc)
            return cells
        data = safe_parse_json_object(raw, fallback={})
        for k in missing:
            v = data.get(k)
            if isinstance(v, str) and v.strip():
                cells[k] = v.strip()[:200]
        return cells

    @staticmethod
    def _render_markdown(result_json: dict) -> str:
        cols = result_json.get("columns") or []
        rows = result_json.get("rows") or []
        if not cols or not rows:
            return "_无数据_"
        lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
        for r in rows:
            cells = []
            for c in cols:
                val = r.get(c, "")
                if not isinstance(val, str):
                    val = str(val)
                cells.append(val.replace("|", "/").replace("\n", " "))
            lines.append("| " + " | ".join(cells) + " |")
        return "\n".join(lines)


async def list_sessions(
    db: AsyncSession, user_id: int, topic_id: int, limit: int = 50
) -> Sequence[ComparisonSession]:
    return (
        await db.execute(
            select(ComparisonSession)
            .where(
                ComparisonSession.user_id == user_id,
                ComparisonSession.topic_id == topic_id,
            )
            .order_by(ComparisonSession.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()


async def get_session(db: AsyncSession, session_id: int) -> ComparisonSession | None:
    return await db.get(ComparisonSession, session_id)


__all__ = ["ComparisonService", "list_sessions", "get_session"]
