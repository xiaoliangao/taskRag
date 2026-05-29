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


def summarize_faithfulness(faith_results: list[dict[str, Any]], gen_top_n: int) -> dict[str, Any]:
    """Aggregate per-question judge results into the opt-in faithfulness block.

    A result with score=None is a failed generation/judge (not a 0); we count
    those separately rather than letting them drag the mean down.
    """
    scores = [f["score"] for f in faith_results if f.get("score") is not None]
    return {
        "n_judged": len(faith_results),
        "mean": round(aggregate(scores), 3) if scores else None,
        "unfaithful_count": sum(1 for s in scores if s < 0.5),
        "failed": sum(1 for f in faith_results if f.get("score") is None),
        "gen_top_n": gen_top_n,
    }


async def _judge_one(*, question: str, cits: list, gen_top_n: int) -> dict[str, Any]:
    """Generate an answer from the top retrieved context, then judge its
    faithfulness. We *actually run generation* (not the cached reference_answer)
    so the score reflects the real prompt + retriever (incl. Parent-Child swap),
    catching generation-side regressions that retrieval metrics can't see.

    Returns the judge dict ({score, supported, total, ...}) or {score: None,
    error} on failure so the caller can aggregate while flagging misses.
    """
    from app.eval.faithfulness import judge_faithfulness
    from app.rag.llm_client import get_llm_client
    from app.rag.prompt import build_messages

    gen_cits = list(cits)[:gen_top_n]
    if not gen_cits:
        return {"score": None, "error": "no_citations"}
    citation_dicts = [c.to_dict(drop_text=False) for c in gen_cits]
    messages = build_messages(question=question, chat_history=[], citations=citation_dicts)
    try:
        # .complete is sync + network-bound; off-load so we don't block the loop.
        answer = await asyncio.to_thread(get_llm_client().complete, messages)
    except Exception as exc:
        log.warning("eval generation failed: %s", exc)
        return {"score": None, "error": f"gen_failed: {str(exc)[:160]}"}
    return await asyncio.to_thread(
        judge_faithfulness,
        question=question,
        answer=answer,
        retrieved_chunks=[c.text for c in gen_cits],
    )


async def _evaluate(
    db: AsyncSession,
    topic_id: int,
    top_k_retrieve: int = 20,
    *,
    judge: bool = False,
    gen_top_n: int = 5,
) -> dict[str, Any]:
    """Run every question through the retriever and collect per-question metrics.

    When ``judge`` is set, additionally generate an answer per question and run
    the faithfulness LLM judge — an opt-in, paid pass (one generation + one
    judge call per question) surfaced as a separate ``faithfulness`` block so it
    never perturbs the deterministic retrieval metrics.
    """
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
    faith_results: list[dict[str, Any]] = []

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

        if judge:
            fres = await _judge_one(question=q.question, cits=cits, gen_top_n=gen_top_n)
            faith_results.append(fres)
            score = fres.get("score")
            per_q[-1]["faithfulness"] = round(score, 3) if score is not None else None

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

    result: dict[str, Any] = {
        "n_questions": len(questions),
        "recall@5": round(aggregate(recall5), 3),
        f"recall@{top_k_retrieve}": round(aggregate(recall20), 3),
        "mrr": round(aggregate(mrrs), 3),
        "per_tag": by_tag,
        "per_question": per_q,
    }

    if judge:
        result["faithfulness"] = summarize_faithfulness(faith_results, gen_top_n)

    return result


async def _amain(
    topic_id: int, label: str, notes: str | None, *, judge: bool = False, gen_top_n: int = 5
) -> None:
    Session = get_async_sessionmaker()
    async with Session() as db:
        metrics = await _evaluate(db, topic_id, judge=judge, gen_top_n=gen_top_n)
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
    parser.add_argument(
        "--judge",
        action="store_true",
        help="also generate an answer per question and run the faithfulness "
        "judge (paid: 1 generation + 1 judge LLM call per question)",
    )
    parser.add_argument(
        "--gen-top-n",
        type=int,
        default=5,
        help="how many top citations to feed generation when --judge is set "
        "(default 5, mirrors chat rerank_top_n)",
    )
    args = parser.parse_args()
    asyncio.run(
        _amain(args.topic, args.label, args.notes, judge=args.judge, gen_top_n=args.gen_top_n)
    )


if __name__ == "__main__":
    main()
