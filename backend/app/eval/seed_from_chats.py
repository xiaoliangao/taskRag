"""Seed golden-set questions from past chat conversations (semi-automated).

The eval pipeline needs (question, expected_chunk_ids[]) pairs. The richest
source of these is the user's own past chat: pick assistant replies that
already carry citations to specific chunks, and treat (prior user question,
citation chunk_ids) as a golden entry.

Usage (inside the backend container):

  # Preview what would be inserted — no DB writes
  python -m app.eval.seed_from_chats --topic 2 --limit 30 --dry-run

  # Actually persist
  python -m app.eval.seed_from_chats --topic 2 --limit 30

The script:
  1. Loads up to `--limit` recent assistant messages in the topic that
     have at least one citation with a chunk_id.
  2. Pairs each with the immediately preceding user message (the question).
  3. Skips entries where the question is too short (<8 chars) or where
     citations point to chunks that no longer exist (Wave-3 backfill
     replaced all chunk ids — old citations would all be invalid; we
     filter to ones whose chunk_id still resolves).
  4. Inserts into rag_eval_questions with tag derived from the chat
     session's mode (factual/synthesis/...), best-effort.

This is semi-automated: review what gets seeded, then iterate.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from sqlalchemy import select

from app.db.models.chat import ChatMessage, ChatSession
from app.db.models.document import Chunk
from app.db.models.eval import RagEvalQuestion
from app.db.session import get_async_sessionmaker


_MODE_TO_TAG: dict[str, str] = {
    "default": "synthesis",
    "mentor": "synthesis",
    "beginner": "factual",
    "debate": "comparison",
    "reviewer": "synthesis",
    "what_if": "multi_step",
}


async def _build_candidates(db, topic_id: int, limit: int) -> list[dict[str, Any]]:
    # Pull recent (session, message) pairs in the topic, newest first.
    rows = (
        await db.execute(
            select(ChatMessage, ChatSession)
            .join(ChatSession, ChatSession.id == ChatMessage.session_id)
            .where(ChatSession.topic_id == topic_id, ChatMessage.role == "assistant")
            .order_by(ChatMessage.id.desc())
            .limit(limit * 3)  # over-fetch; we'll filter
        )
    ).all()

    candidates: list[dict[str, Any]] = []
    for msg, session in rows:
        # Citations sit on `chat_messages.citations_json` (JSONB list of dicts
        # each carrying chunk_id / document_id / etc).
        cits = msg.citations_json or []
        chunk_ids: list[int] = []
        for c in cits:
            if not isinstance(c, dict):
                continue
            cid = c.get("chunk_id")
            if isinstance(cid, int):
                chunk_ids.append(cid)
            elif isinstance(cid, str) and cid.isdigit():
                chunk_ids.append(int(cid))
        if not chunk_ids:
            continue

        # Find the user question right before this assistant turn (same session).
        prev = (
            await db.execute(
                select(ChatMessage)
                .where(
                    ChatMessage.session_id == session.id,
                    ChatMessage.role == "user",
                    ChatMessage.id < msg.id,
                )
                .order_by(ChatMessage.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if prev is None:
            continue
        question = (prev.content or "").strip()
        if len(question) < 8:
            continue

        # Only keep chunk_ids that still exist post-backfill (old IDs are stale).
        existing = (
            await db.execute(select(Chunk.id).where(Chunk.id.in_(chunk_ids)))
        ).scalars().all()
        existing_set = set(existing)
        live_ids = [c for c in chunk_ids if c in existing_set]
        if not live_ids:
            continue

        tag = _MODE_TO_TAG.get(getattr(session, "mode", "default") or "default", "synthesis")
        candidates.append({
            "topic_id": topic_id,
            "question": question[:600],
            "reference_answer": (msg.content or "")[:2000] or None,
            "expected_chunk_ids": live_ids,
            "tag": tag,
            "_session_id": session.id,
            "_assistant_msg_id": msg.id,
        })
        if len(candidates) >= limit:
            break
    return candidates


async def _amain(topic_id: int, limit: int, dry_run: bool) -> None:
    Session = get_async_sessionmaker()
    async with Session() as db:
        candidates = await _build_candidates(db, topic_id, limit)
        print(f"found {len(candidates)} candidates")
        for i, c in enumerate(candidates, 1):
            print(
                f"  [{i:2d}] tag={c['tag']:10} chunks={len(c['expected_chunk_ids']):2d} "
                f"  q={c['question'][:80]!r}"
            )

        if dry_run:
            print("\n--dry-run: nothing inserted")
            return

        # Dedup against existing golden set on (topic_id, question)
        existing_qs = set(
            (
                await db.execute(
                    select(RagEvalQuestion.question).where(RagEvalQuestion.topic_id == topic_id)
                )
            ).scalars().all()
        )
        inserted = 0
        for c in candidates:
            if c["question"] in existing_qs:
                continue
            db.add(RagEvalQuestion(
                topic_id=topic_id,
                question=c["question"],
                reference_answer=c["reference_answer"],
                expected_chunk_ids=c["expected_chunk_ids"],
                tag=c["tag"],
            ))
            inserted += 1
        await db.commit()
        print(f"\ninserted {inserted} new (skipped {len(candidates) - inserted} duplicates)")


def main() -> int:
    p = argparse.ArgumentParser(description="Seed golden-set from chat history.")
    p.add_argument("--topic", type=int, required=True)
    p.add_argument("--limit", type=int, default=30)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    asyncio.run(_amain(args.topic, args.limit, args.dry_run))
    return 0


if __name__ == "__main__":
    main()
