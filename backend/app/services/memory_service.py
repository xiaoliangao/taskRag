"""Conversation Memory (v1.4 Sprint 7).

Summarizes long chat sessions into structured memory items that get injected
into future QA prompts as USER_RESEARCH_CONTEXT.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import ChatMessage, ChatSession, ChatSessionSummary
from app.rag.llm_client import get_llm_client
from app.services.json_llm import safe_parse_json_object, truncate_for_llm

log = logging.getLogger(__name__)

_MIN_MESSAGES_FOR_SUMMARY = 6
_NEW_SUMMARY_THRESHOLD = 5  # +N messages since last summary triggers regen
_MAX_HISTORY_TURNS_IN_PROMPT = 16
_SUMMARY_CONTEXT_LIMIT = 1200  # max chars to keep when injecting into QA


_SUMMARY_SYSTEM = """你是对话总结助手。给定一段研究助手聊天历史，输出 JSON：

{
  "summary_md": "用户在 ... 的研究讨论。聚焦了 ... 关键点。",
  "memory_items": [
    {
      "memory_type": "user_goal | excluded_direction | finding | open_question | preference",
      "content": "...",
      "confidence": 0.7
    }
  ]
}

硬性规则：
1. summary_md 限制 ≤ 600 字。
2. memory_items ≤ 6 条；每条 confidence ∈ [0.4, 1.0]。
3. 不要复述每一条消息；提炼模式与结论。
4. 严格输出 JSON。
"""


async def list_session_summaries(
    db: AsyncSession,
    *,
    user_id: int,
    topic_id: int,
    limit: int = 3,
) -> Sequence[ChatSessionSummary]:
    """Recent summaries to inject as long-term memory."""
    stmt = (
        select(ChatSessionSummary)
        .where(
            ChatSessionSummary.user_id == user_id,
            ChatSessionSummary.topic_id == topic_id,
        )
        .order_by(ChatSessionSummary.generated_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return rows


def build_memory_block(summaries: Sequence[ChatSessionSummary]) -> str:
    """Render summaries as a single block <= _SUMMARY_CONTEXT_LIMIT chars."""
    if not summaries:
        return ""
    parts: list[str] = []
    used = 0
    for s in summaries:
        chunk = f"- (summary {s.generated_at.date()}) {s.summary_md.strip()}"
        for item in (s.memory_items_json or [])[:3]:
            if isinstance(item, dict) and item.get("content"):
                chunk += f"\n  · [{item.get('memory_type', 'note')}] {str(item.get('content'))[:200]}"
        if used + len(chunk) > _SUMMARY_CONTEXT_LIMIT:
            break
        parts.append(chunk)
        used += len(chunk)
    return "\n".join(parts)


async def needs_resummary(
    db: AsyncSession,
    session_id: int,
) -> bool:
    """Return True if the session has enough new messages to warrant (re)summarizing."""
    msg_count = (
        await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
        )
    ).scalars().all()
    total = len(msg_count)
    if total < _MIN_MESSAGES_FOR_SUMMARY:
        return False
    existing = (
        await db.execute(
            select(ChatSessionSummary).where(
                ChatSessionSummary.chat_session_id == session_id
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        return True
    return total - (existing.message_count_at_gen or 0) >= _NEW_SUMMARY_THRESHOLD


async def summarize_session(db: AsyncSession, session_id: int) -> ChatSessionSummary | None:
    """Generate (or refresh) a session summary. Sync-compatible via run_async."""
    chat = await db.get(ChatSession, session_id)
    if chat is None:
        return None

    msgs = (
        await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .limit(_MAX_HISTORY_TURNS_IN_PROMPT * 2)
        )
    ).scalars().all()
    if len(msgs) < _MIN_MESSAGES_FOR_SUMMARY:
        return None

    transcript = "\n".join(
        f"{'用户' if m.role == 'user' else '助手'}: {m.content[:400]}"
        for m in msgs
    )
    client = get_llm_client()
    try:
        raw = client.complete(
            [
                {"role": "system", "content": _SUMMARY_SYSTEM},
                {
                    "role": "user",
                    "content": f"对话历史:\n{truncate_for_llm(transcript, 4500)}\n\n请输出 JSON。",
                },
            ],
            temperature=0.2,
            max_tokens=700,
            feature="chat_session_summary",
        )
    except Exception as exc:
        log.warning("summarize_session_llm_failed: %s", exc)
        return None

    data = safe_parse_json_object(raw, fallback={})
    summary_md = (data.get("summary_md") or "").strip()
    if not summary_md:
        return None
    items = data.get("memory_items") or []
    items_clean: list[dict[str, Any]] = []
    if isinstance(items, list):
        for it in items[:6]:
            if not isinstance(it, dict):
                continue
            mt = (it.get("memory_type") or "note").strip().lower()
            content = (it.get("content") or "").strip()
            if not content:
                continue
            conf = float(it.get("confidence", 0.7) or 0.7)
            items_clean.append({"memory_type": mt, "content": content[:400], "confidence": max(0.0, min(1.0, conf))})

    # Upsert (one summary per session)
    existing = (
        await db.execute(
            select(ChatSessionSummary).where(
                ChatSessionSummary.chat_session_id == session_id
            )
        )
    ).scalar_one_or_none()
    now = datetime.now(tz=UTC)
    if existing is None:
        existing = ChatSessionSummary(
            user_id=chat.user_id,
            topic_id=chat.topic_id,
            chat_session_id=chat.id,
            summary_md=summary_md[:2000],
            memory_items_json=items_clean,
            message_count_at_gen=len(msgs),
            generated_at=now,
        )
        db.add(existing)
    else:
        existing.summary_md = summary_md[:2000]
        existing.memory_items_json = items_clean
        existing.message_count_at_gen = len(msgs)
        existing.generated_at = now
    await db.flush()
    return existing


__all__ = [
    "build_memory_block",
    "list_session_summaries",
    "needs_resummary",
    "summarize_session",
]
