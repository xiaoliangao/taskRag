"""Run the retrieval eval against a topic's golden set.

Usage (inside the backend container):
  python -m app.eval.run_eval --topic 2 --label baseline
  python -m app.eval.run_eval --topic 2 --label after-cr --notes "with contextual retrieval enabled"

For each rag_eval_question in the topic, calls the production retriever
exactly the way the chat path does (`retrieve_for_topic`, hybrid + rerank)
and computes Recall@5, Recall@20, MRR. Persists aggregates to
rag_eval_runs along with the commit sha so we can diff future runs.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import subprocess
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.eval import RagEvalQuestion, RagEvalRun
from app.db.session import get_async_sessionmaker
from app.eval.metrics import aggregate, recall_at_k, reciprocal_rank
from app.rag.retriever import retrieve_for_topic

log = logging.getLogger(__name__)


def _current_commit_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            cwd=os.path.dirname(__file__),
            timeout=2,
        )
        return out.stdout.strip()
    except Exception:
        return None


async def _evaluate(
    db: AsyncSession, topic_id: int, top_k_retrieve: int = 20
) -> dict[str, Any]:
    """Run every question through the retriever and collect per-question metrics."""
    rows = (
        await db.execute(
            select(RagEvalQuestion).where(RagEvalQuestion.topic_id == topic_id)
        )
    ).scalars().all()
    questions = list(rows)
    if not questions:
        return {"n_questions": 0}

    per_q: list[dict[str, Any]] = []
    recall5: list[float] = []
    recall20: list[float] = []
    mrrs: list[float] = []

    for q in questions:
        expected = [int(i) for i in (q.expected_chunk_ids or [])]
        # Call the same retriever the chat path uses. top_n covers our
        # measurement window (20).
        cits = await retrieve_for_topic(
            db=db, topic_id=topic_id, query=q.question,
            top_n=top_k_retrieve, dedup_by_document=False,
        )
        retrieved = [c.chunk_id for c in cits if c.chunk_id is not None]
        r5 = recall_at_k(retrieved, expected, 5)
        r20 = recall_at_k(retrieved, expected, top_k_retrieve)
        rr = reciprocal_rank(retrieved, expected)
        recall5.append(r5)
        recall20.append(r20)
        mrrs.append(rr)
        per_q.append({
            "question_id": q.id,
            "question": q.question[:80],
            "tag": q.tag,
            "expected": len(expected),
            "retrieved": len(retrieved),
            "recall@5": round(r5, 3),
            f"recall@{top_k_retrieve}": round(r20, 3),
            "rr": round(rr, 3),
        })

    # Per-tag breakdown lets us see which query types our pipeline serves best.
    by_tag: dict[str, dict[str, float]] = {}
    for q, r5, r20, rr in zip(questions, recall5, recall20, mrrs, strict=False):
        tag = q.tag or "untagged"
        bucket = by_tag.setdefault(tag, {"recall@5": [], "recall@20": [], "mrr": [], "n": 0})
        bucket["recall@5"].append(r5)
        bucket["recall@20"].append(r20)
        bucket["mrr"].append(rr)
        bucket["n"] += 1
    for tag, bucket in by_tag.items():
        by_tag[tag] = {
            "n": bucket["n"],
            "recall@5": round(aggregate(bucket["recall@5"]), 3),
            "recall@20": round(aggregate(bucket["recall@20"]), 3),
            "mrr": round(aggregate(bucket["mrr"]), 3),
        }

    return {
        "n_questions": len(questions),
        "recall@5": round(aggregate(recall5), 3),
        f"recall@{top_k_retrieve}": round(aggregate(recall20), 3),
        "mrr": round(aggregate(mrrs), 3),
        "per_tag": by_tag,
        "per_question": per_q,
    }


async def _amain(topic_id: int, label: str, notes: str | None) -> None:
    Session = get_async_sessionmaker()
    async with Session() as db:
        metrics = await _evaluate(db, topic_id)
        run = RagEvalRun(
            topic_id=topic_id,
            label=label,
            commit_sha=_current_commit_sha(),
            metrics_json=metrics,
            notes=notes,
        )
        db.add(run)
        await db.commit()
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
        print(f"\nrun_id={run.id} label={label} commit={_current_commit_sha()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run retrieval eval against a topic's golden set.")
    parser.add_argument("--topic", type=int, required=True, help="topic_id")
    parser.add_argument(
        "--label", type=str, default="adhoc",
        help="short identifier for this run (baseline / after-cr / ...)",
    )
    parser.add_argument("--notes", type=str, default=None)
    args = parser.parse_args()
    asyncio.run(_amain(args.topic, args.label, args.notes))


if __name__ == "__main__":
    main()
