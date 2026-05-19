"""CRAG-style retrieval reflection (v1.5 B-1).

Given a query and the initial retrieval, ask the LLM to score whether the
context is *sufficient* to answer. On "low" verdict, ask for a rewritten query
and retry once, then merge with the original hits (dedup by document_id).
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.rag.llm_client import get_llm_client
from app.services.json_llm import (
    normalize_confidence,
    safe_parse_json_object,
    truncate_for_llm,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.rag.retriever import Citation

log = logging.getLogger(__name__)

_GRADE_SYSTEM = """你是检索质量评估器。给定用户问题 + 检索到的若干候选片段标题/摘要，
判断这些候选**整体上**是否足以回答用户问题。

verdict 取值且只能取一个：
  high     候选高度相关，可以直接回答
  medium   有相关但缺一些角度，建议补充检索
  low      关联度低或视角偏离，必须重新检索

并且必须给出一个 rewritten_query（即使 verdict=high 也给一个备用 query）：
  - 如果 high：保留原问题或微调
  - 如果 medium/low：写一个角度不同的等效查询，可以同义词替换 / 拆解子问题 / 加领域术语

硬性规则：
1. 仅基于给定标题/摘要判断，不要补外部知识。
2. confidence ∈ [0,1]：high 给 ≥ 0.75；medium ≈ 0.5；low ≤ 0.4。
3. 严格输出 JSON。
"""

_GRADE_USER_TMPL = """问题: {question}

候选片段:
{candidates}

输出 JSON：
{{
  "verdict": "medium",
  "confidence": 0.55,
  "reason": "...",
  "rewritten_query": "..."
}}
"""


def _format_candidates(citations: "list[Citation]", limit: int = 8) -> str:
    lines = []
    for i, c in enumerate(citations[:limit], start=1):
        snippet = (c.text or "")[:160].replace("\n", " ").strip()
        lines.append(f"[{i}] {c.title or '(无标题)'}  — {snippet}")
    return "\n".join(lines) or "(no candidates)"


def grade_retrieval(question: str, citations: "list[Citation]") -> dict:
    """Synchronous grade call. Returns a dict with verdict/confidence/rewritten_query."""
    if not citations:
        return {
            "verdict": "low",
            "confidence": 0.2,
            "reason": "no candidates",
            "rewritten_query": question,
        }
    client = get_llm_client()
    try:
        raw = client.complete(
            [
                {"role": "system", "content": _GRADE_SYSTEM},
                {
                    "role": "user",
                    "content": _GRADE_USER_TMPL.format(
                        question=truncate_for_llm(question, 600),
                        candidates=truncate_for_llm(_format_candidates(citations), 1800),
                    ),
                },
            ],
            temperature=0.1,
            max_tokens=300,
            feature="crag_grade",
        )
    except Exception as exc:
        log.warning("crag_grade_llm_failed: %s", exc)
        return {
            "verdict": "medium",
            "confidence": 0.5,
            "reason": "grader_unavailable",
            "rewritten_query": question,
        }
    data = safe_parse_json_object(raw, fallback={})
    verdict = (data.get("verdict") or "").strip().lower()
    if verdict not in ("high", "medium", "low"):
        verdict = "medium"
    return {
        "verdict": verdict,
        "confidence": normalize_confidence(data.get("confidence"), default=0.5),
        "reason": (data.get("reason") or "")[:300],
        "rewritten_query": (data.get("rewritten_query") or question).strip() or question,
    }


async def reflective_retrieve(
    *,
    db: "AsyncSession",
    topic_id: int,
    question: str,
    initial: "list[Citation]",
) -> tuple["list[Citation]", dict]:
    """If initial retrieval is graded low/medium, retry once with rewritten query and merge.

    Returns (final_citations, audit) where audit captures the grader's verdict.
    """
    from app.rag.retriever import retrieve_for_topic  # local import to avoid cycle

    grade = await asyncio.to_thread(grade_retrieval, question, initial)
    audit = {
        "verdict": grade["verdict"],
        "confidence": grade["confidence"],
        "rewrote": False,
        "rewritten_query": None,
    }
    if grade["verdict"] == "high":
        return initial, audit

    new_q = grade["rewritten_query"]
    if not new_q or new_q.strip().lower() == question.strip().lower():
        return initial, audit

    audit["rewrote"] = True
    audit["rewritten_query"] = new_q
    try:
        retry = await retrieve_for_topic(
            db=db, topic_id=topic_id, query=new_q, dedup_by_document=True
        )
    except Exception as exc:
        log.warning("crag_retry_failed: %s", exc)
        return initial, audit

    # Merge by document_id; keep max score
    by_doc: dict[int, "Citation"] = {}
    for c in [*initial, *retry]:
        prev = by_doc.get(c.document_id)
        if prev is None or c.score > prev.score:
            by_doc[c.document_id] = c
    merged = sorted(by_doc.values(), key=lambda c: c.score, reverse=True)
    return merged, audit


__all__ = ["grade_retrieval", "reflective_retrieve"]
