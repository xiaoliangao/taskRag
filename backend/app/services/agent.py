"""Lightweight Agent loop (v1.5 B-3).

Implements a plan→tool→observe→answer cycle without LangGraph dependency.
The agent can call a small fixed registry of read-only tools scoped to the
user's owned topics. All tools return JSON-serializable observations.

Design:
  1. Planner LLM call: emit JSON `{thought, tool, args}` or `{final}`.
  2. Execute tool, capture observation (short string).
  3. Append to transcript and loop.
  4. Max steps cap; on overflow, force a final answer.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.document import Document, TopicDocument
from app.db.models.research_ext import MethodEntity
from app.rag.llm_client import get_llm_client
from app.services.json_llm import safe_parse_json_object

log = logging.getLogger(__name__)

_MAX_STEPS = 5
_FEATURE = "agent_loop"


_SYSTEM_PROMPT = """你是一个研究助手 Agent。可以通过工具调用 + 多步推理，从用户的课题语料中获取证据，
最后给出基于证据的回答。

可用工具：
1. topic_search(topic_id: int, query: str) → 在某个课题里做混合检索，返回 top 5 个 chunk 的标题 + 简短摘录。
2. paper_lookup(document_id: int) → 返回某篇论文的元数据（标题 / 作者 / 年份 / 摘要 / 是否有 briefing）。
3. list_methods(topic_id: int) → 返回该课题已识别的 top 方法实体清单（按 first_seen 排序）。

每一步输出 JSON object，格式之一：
  {"thought": "...", "tool": "topic_search", "args": {...}}     # 调用工具
  {"thought": "...", "final": "你的最终回答（markdown）"}        # 结束并回答

硬性规则：
1. tool 名必须严格匹配上面的工具列表。
2. args 必须是合法 JSON object。
3. 同一个工具不要重复用相同参数调用（已观察过的不要再调）。
4. 最终回答必须基于工具返回的观察。无证据时明确说"未找到"。
5. 严格输出 JSON object（不要 markdown 包裹、不要解释）。
"""


@dataclass
class AgentStep:
    role: str  # "thought" | "tool_call" | "observation" | "final"
    content: str = ""
    tool: str | None = None
    args: dict[str, Any] | None = None


@dataclass
class AgentTrace:
    steps: list[AgentStep] = field(default_factory=list)
    final_answer: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": [
                {
                    "role": s.role,
                    "content": s.content,
                    "tool": s.tool,
                    "args": s.args,
                }
                for s in self.steps
            ],
            "final_answer": self.final_answer,
            "error": self.error,
        }


# ---- Tool implementations ----


async def _tool_topic_search(
    db: AsyncSession,
    *,
    topic_id: int,
    query: str,
    owned_topic_ids: Sequence[int],
) -> dict[str, Any]:
    if int(topic_id) not in set(owned_topic_ids):
        return {"error": f"topic {topic_id} not owned"}
    from app.rag.retriever import retrieve_for_topic

    hits = await retrieve_for_topic(
        db=db, topic_id=int(topic_id), query=str(query), top_n=5, dedup_by_document=True
    )
    return {
        "topic_id": topic_id,
        "hits": [
            {
                "document_id": h.document_id,
                "title": h.title,
                "snippet": (h.text or "")[:200],
                "score": round(h.score, 3),
            }
            for h in hits
        ],
    }


async def _tool_paper_lookup(
    db: AsyncSession,
    *,
    document_id: int,
    owned_topic_ids: Sequence[int],
) -> dict[str, Any]:
    # Verify the document is reachable in *some* owned topic
    owned = (
        await db.execute(
            select(TopicDocument.topic_id)
            .where(
                TopicDocument.document_id == int(document_id),
                TopicDocument.topic_id.in_(list(owned_topic_ids)),
            )
            .limit(1)
        )
    ).first()
    if not owned:
        return {"error": f"document {document_id} not reachable for this user"}
    doc = await db.get(Document, int(document_id))
    if not doc:
        return {"error": "document not found"}
    return {
        "document_id": doc.id,
        "title": doc.title,
        "authors": doc.authors or [],
        "year": doc.published_at.year if doc.published_at else None,
        "source": doc.source,
        "abstract": (doc.abstract or "")[:600],
        "url": doc.url,
    }


async def _tool_list_methods(
    db: AsyncSession,
    *,
    topic_id: int,
    owned_topic_ids: Sequence[int],
) -> dict[str, Any]:
    if int(topic_id) not in set(owned_topic_ids):
        return {"error": f"topic {topic_id} not owned"}
    rows = (
        await db.execute(
            select(MethodEntity)
            .where(MethodEntity.topic_id == int(topic_id))
            .order_by(
                MethodEntity.document_count.desc(),
                MethodEntity.first_seen_at.asc().nullslast(),
            )
            .limit(30)
        )
    ).scalars().all()
    return {
        "topic_id": topic_id,
        "methods": [
            {
                "name": m.name,
                "first_seen": m.first_seen_at.isoformat() if m.first_seen_at else None,
                "documents": m.document_count,
            }
            for m in rows
        ],
    }


async def _dispatch_tool(
    db: AsyncSession,
    *,
    tool: str,
    args: dict[str, Any],
    owned_topic_ids: Sequence[int],
) -> dict[str, Any]:
    try:
        if tool == "topic_search":
            return await _tool_topic_search(
                db,
                topic_id=int(args.get("topic_id", 0)),
                query=str(args.get("query", "")),
                owned_topic_ids=owned_topic_ids,
            )
        if tool == "paper_lookup":
            return await _tool_paper_lookup(
                db,
                document_id=int(args.get("document_id", 0)),
                owned_topic_ids=owned_topic_ids,
            )
        if tool == "list_methods":
            return await _tool_list_methods(
                db,
                topic_id=int(args.get("topic_id", 0)),
                owned_topic_ids=owned_topic_ids,
            )
        return {"error": f"unknown tool: {tool}"}
    except Exception as exc:  # pragma: no cover - tools must never crash the loop
        return {"error": f"tool_failed: {exc!s}"[:300]}


# ---- Main loop ----


def _truncate_observation(obs: dict[str, Any], limit: int = 800) -> str:
    s = json.dumps(obs, ensure_ascii=False, default=str)
    if len(s) > limit:
        return s[:limit] + "…[truncated]"
    return s


async def run_agent(
    *,
    db: AsyncSession,
    question: str,
    owned_topic_ids: Sequence[int],
    max_steps: int = _MAX_STEPS,
) -> AgentTrace:
    trace = AgentTrace()
    transcript: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"用户问题: {question}\n\n用户当前拥有的 topic_id 列表: {list(owned_topic_ids)}",
        },
    ]
    client = get_llm_client()

    for step_idx in range(max_steps):
        try:
            raw = client.complete(
                transcript, temperature=0.1, max_tokens=600, feature=_FEATURE
            )
        except Exception as exc:
            trace.error = f"planner_failed: {exc!s}"[:300]
            break

        action = safe_parse_json_object(raw, fallback={})
        if not action:
            trace.steps.append(AgentStep(role="thought", content=raw[:300]))
            trace.error = "planner_returned_non_json"
            break

        thought = (action.get("thought") or "").strip()
        if thought:
            trace.steps.append(AgentStep(role="thought", content=thought[:500]))

        # Final answer branch
        if "final" in action:
            trace.final_answer = str(action.get("final") or "").strip()
            trace.steps.append(AgentStep(role="final", content=trace.final_answer))
            break

        tool = (action.get("tool") or "").strip()
        args = action.get("args") if isinstance(action.get("args"), dict) else {}
        if not tool:
            trace.error = "missing_tool"
            break

        trace.steps.append(AgentStep(role="tool_call", tool=tool, args=args))
        observation = await _dispatch_tool(
            db, tool=tool, args=args or {}, owned_topic_ids=owned_topic_ids
        )
        obs_str = _truncate_observation(observation)
        trace.steps.append(AgentStep(role="observation", content=obs_str))

        # Feed back into the next planner call
        transcript.append({"role": "assistant", "content": json.dumps(action, ensure_ascii=False)})
        transcript.append(
            {"role": "user", "content": f"工具 {tool} 返回:\n{obs_str}\n\n请继续，输出 JSON。"}
        )

        # Stop early if we already used too much context
        if sum(len(m["content"]) for m in transcript) > 18_000:
            break

    if not trace.final_answer:
        # Force a final answer if the loop exhausted
        try:
            transcript.append(
                {
                    "role": "user",
                    "content": "已达到最大步数。请基于已有观察直接输出最终回答 JSON {\"final\": \"...\"}。",
                }
            )
            raw = client.complete(
                transcript, temperature=0.2, max_tokens=600, feature=_FEATURE
            )
            data = safe_parse_json_object(raw, fallback={})
            trace.final_answer = str(data.get("final") or raw)[:4000]
            trace.steps.append(AgentStep(role="final", content=trace.final_answer))
        except Exception as exc:
            trace.error = trace.error or f"forced_final_failed: {exc!s}"[:300]

    return trace


