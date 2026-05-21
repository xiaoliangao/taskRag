"""LLM-driven golden-set seed (Wave-3 Pkg-Eval helper).

When chat history isn't usable (e.g. after a backfill rebuilds all chunk
ids), we can still bootstrap an evaluation set by going the other
direction: sample N parent chunks at random, ask the LLM "what concise
question would this section answer?", and store (question,
[parent's children chunk_ids]) as a golden entry.

This is mildly circular — the same LLM family answers both the question
and judges retrieval — but it gives a deterministic baseline that catches
gross regressions (e.g. "after PC backfill, recall@5 dropped from 0.6 to
0.1"). For real-world quality use complementary hand-curated questions.

Usage:
  python -m app.eval.seed_from_chunks --topic 2 --n 30 --dry-run
  python -m app.eval.seed_from_chunks --topic 2 --n 30
"""
from __future__ import annotations

import argparse
import asyncio
import random
from typing import Any

from sqlalchemy import select

from app.db.models.document import Chunk, TopicDocument
from app.db.models.eval import RagEvalQuestion
from app.db.models.topic import Topic
from app.db.session import get_async_sessionmaker
from app.rag.llm_client import get_llm_client
from app.services.contextual_retrieval import _is_cjk_dominant


_SYSTEM_EN = """Given a passage from an academic paper, write ONE clear English
research question (≤ 25 words) whose ideal answer is grounded in this passage.

Rules:
- The question must be specific enough that retrieval should land on
  THIS passage, not just any paper on the same topic. Use concrete entities
  / terms from the passage.
- Do NOT phrase it as "What does the passage say about X" — write the
  question as the user would ask it directly in a research chat.
- One question. No quotes, no prefixes, no JSON.
"""

_SYSTEM_ZH = """给定一段学术论文正文,请写一个明确的中文研究问题(≤ 30 字),
其理想答案就基于这段正文。

规则:
- 问题要具体到能让检索定位到本段(用段落里的具体术语/实体),而非任何同
  领域论文都能回答。
- 不要写成"段落里说了什么 X"。像研究员在 RAG 聊天里直接提问一样。
- 一句话。不要 quote、不要前缀、不要 JSON。
"""


async def _gen_question(parent_text: str) -> str | None:
    system = _SYSTEM_ZH if _is_cjk_dominant(parent_text) else _SYSTEM_EN
    try:
        out = get_llm_client().complete(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Passage:\n{parent_text[:1800]}"},
            ],
            temperature=0.3,
            max_tokens=80,
            feature="eval_seed",
        )
    except Exception:
        return None
    line = (out or "").strip().splitlines()[0] if out else ""
    return line[:400] if len(line) >= 8 else None


async def _amain(topic_id: int, n: int, dry_run: bool) -> None:
    Session = get_async_sessionmaker()
    async with Session() as db:
        topic = await db.get(Topic, topic_id)
        if topic is None:
            print(f"topic {topic_id} not found"); return

        # Sample parent chunks from docs in this topic
        parents = (
            await db.execute(
                select(Chunk.id, Chunk.text, Chunk.section_title, Chunk.document_id)
                .where(
                    Chunk.is_parent.is_(True),
                    Chunk.document_id.in_(
                        select(TopicDocument.document_id).where(
                            TopicDocument.topic_id == topic_id
                        )
                    ),
                )
            )
        ).all()
        random.shuffle(parents)
        sampled = parents[:n]
        print(f"sampling {len(sampled)} parents from {len(parents)} available")

        # For each parent, generate a question and look up its children's ids
        # (these are what an ideal retrieval should hit).
        candidates: list[dict[str, Any]] = []
        for p in sampled:
            child_ids = (
                await db.execute(
                    select(Chunk.id).where(Chunk.parent_id == p.id)
                )
            ).scalars().all()
            if not child_ids:
                continue
            q = await _gen_question(p.text)
            if not q:
                continue
            tag = "synthesis" if (p.section_title or "").lower().startswith(("intro", "discussion", "summary"))                 else "factual"
            candidates.append({
                "question": q,
                "expected_chunk_ids": [int(c) for c in child_ids],
                "tag": tag,
                "parent_id": p.id,
                "section": p.section_title,
            })

        print(f"generated {len(candidates)} candidates")
        for i, c in enumerate(candidates, 1):
            print(f"  [{i:2d}] tag={c['tag']:10} chunks={len(c['expected_chunk_ids']):2d}"
                  f"  parent={c['parent_id']:5d}  q={c['question'][:80]!r}")

        if dry_run:
            print("\n--dry-run: nothing inserted")
            return

        existing = set((
            await db.execute(
                select(RagEvalQuestion.question).where(RagEvalQuestion.topic_id == topic_id)
            )
        ).scalars().all())
        inserted = 0
        for c in candidates:
            if c["question"] in existing:
                continue
            db.add(RagEvalQuestion(
                topic_id=topic_id,
                question=c["question"],
                reference_answer=None,
                expected_chunk_ids=c["expected_chunk_ids"],
                tag=c["tag"],
            ))
            inserted += 1
        await db.commit()
        print(f"\ninserted {inserted} new questions (skipped {len(candidates) - inserted} dupes)")


def main() -> int:
    p = argparse.ArgumentParser(description="Seed golden-set by reverse-generating questions from chunks.")
    p.add_argument("--topic", type=int, required=True)
    p.add_argument("--n", type=int, default=20)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    asyncio.run(_amain(args.topic, args.n, args.dry_run))
    return 0


if __name__ == "__main__":
    main()
