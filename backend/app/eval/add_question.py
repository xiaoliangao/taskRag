"""Add a golden-set question (Wave-3 Pkg-Eval helper).

Two ways to use it from inside the backend container:

  # one-off interactive prompt
  python -m app.eval.add_question --topic 2

  # import a JSON file (list of {question, reference_answer?, expected_chunk_ids[], tag?})
  python -m app.eval.add_question --topic 2 --json /tmp/golden.json

The JSON form is the realistic path — curate offline, paste a list of dicts,
run once. The interactive form is for ad-hoc additions.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from sqlalchemy import select

from app.db.models.eval import RagEvalQuestion
from app.db.session import get_async_sessionmaker


async def _insert(topic_id: int, items: list[dict[str, Any]]) -> int:
    Session = get_async_sessionmaker()
    n_added = 0
    async with Session() as db:
        for it in items:
            q = (it.get("question") or "").strip()
            if not q:
                continue
            row = RagEvalQuestion(
                topic_id=topic_id,
                question=q,
                reference_answer=it.get("reference_answer"),
                expected_chunk_ids=list(it.get("expected_chunk_ids") or []),
                tag=it.get("tag"),
            )
            db.add(row)
            n_added += 1
        await db.commit()
    return n_added


def _interactive_prompt() -> dict[str, Any]:
    print("Adding one golden-set question. Empty line aborts.")
    q = input("question: ").strip()
    if not q:
        print("Aborted.")
        sys.exit(0)
    ref = input("reference_answer (optional): ").strip() or None
    raw_ids = input("expected_chunk_ids (comma-sep ints, optional): ").strip()
    chunk_ids: list[int] = []
    if raw_ids:
        try:
            chunk_ids = [int(x.strip()) for x in raw_ids.split(",") if x.strip()]
        except ValueError:
            print("expected_chunk_ids must be comma-separated integers; got:", raw_ids)
            sys.exit(1)
    tag = input("tag (factual/comparison/synthesis/multi_step, optional): ").strip() or None
    return {
        "question": q,
        "reference_answer": ref,
        "expected_chunk_ids": chunk_ids,
        "tag": tag,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Seed RAG golden-set questions.")
    p.add_argument("--topic", type=int, required=True)
    p.add_argument("--json", type=str, default=None, help="path to JSON list of questions")
    args = p.parse_args()

    if args.json:
        with open(args.json, encoding="utf-8") as f:
            items = json.load(f)
        if not isinstance(items, list):
            print("JSON must be a list of dicts"); return 1
    else:
        items = [_interactive_prompt()]

    n = asyncio.run(_insert(args.topic, items))
    print(f"inserted {n} question(s) into topic={args.topic}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
