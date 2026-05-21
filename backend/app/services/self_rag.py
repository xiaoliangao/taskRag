"""Self-RAG style answer critique + retry.

Wraps the existing retrieve→generate pipeline with a final faithfulness
judge. When the first answer comes back unfaithful (judge score below
threshold), we ask the LLM to rewrite the query into something narrower /
better-targeted at the unsupported claims, re-retrieve, and regenerate
once.

Why one retry instead of N? In practice, the cheap LLM judge already
catches 70-80% of obvious hallucinations after the first retry; adding
more loops doubles cost for diminishing returns. If the second answer is
still unfaithful, we return it WITH the audit so the UI / logs can flag.

Streaming is not supported here — once tokens are pushed to the client we
can't recall them. Self-RAG runs in `qa_service.answer_nonstream` only.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.eval.faithfulness import judge_faithfulness
from app.rag.llm_client import get_llm_client
from app.rag.prompt import build_messages
from app.rag.retriever import Citation, retrieve_for_topic
from app.services.json_llm import safe_parse_json_object, truncate_for_llm

log = logging.getLogger(__name__)

# Faithfulness < this triggers a retry. The judge is calibrated 0..1; 0.5 is
# the "more than half the claims are grounded" mark. Set higher to be stricter.
_FAITHFULNESS_FLOOR = 0.5


_REWRITE_SYSTEM = """You are helping fix an unfaithful answer. Given a user
question, a draft answer, and the specific claims that weren't supported by
retrieved context, rewrite ONE more focused search query that would better
retrieve evidence for those claims.

Rules:
- Output a single short query (≤ 20 words). No quotes, no prefixes, no JSON.
- Stay in the user's intent — don't drift to a different topic.
- Use concrete terms from the unsupported claims if they're specific.
"""


def _rewrite_query_for_unsupported(
    question: str, answer: str, unsupported_examples: list[str]
) -> str:
    """Ask the LLM to propose a better query targeting the unsupported claims."""
    user_msg = (
        f"Original question:\n{truncate_for_llm(question, 400)}\n\n"
        f"Draft answer (don't trust):\n{truncate_for_llm(answer, 800)}\n\n"
        f"Unsupported claims:\n- " + "\n- ".join(unsupported_examples[:3])
        + "\n\nBetter query:"
    )
    try:
        out = get_llm_client().complete(
            [
                {"role": "system", "content": _REWRITE_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=80,
            feature="self_rag_rewrite",
        )
        return (out or "").strip().splitlines()[0][:300]
    except Exception as exc:
        log.warning("self-rag rewrite failed: %s", exc)
        return ""


@dataclass
class SelfRagResult:
    answer: str
    citations: list[Citation]
    audit: dict[str, Any] = field(default_factory=dict)


async def critique_and_maybe_retry(
    *,
    db: AsyncSession,
    topic_id: int,
    question: str,
    initial_answer: str,
    initial_citations: list[Citation],
    history: list[dict],
    system_extra: str = "",
) -> SelfRagResult:
    """Judge the initial answer. If unfaithful, rewrite query, re-retrieve,
    regenerate once. Returns the final answer + citations + a small audit
    dict so callers can log / surface to UI.

    `history` and `system_extra` follow the same shape `qa_service` already
    passes to `build_messages`. We pass them through unchanged so the
    regenerated answer keeps the chat personality / long-term memory block.
    """
    audit: dict[str, Any] = {"retried": False}

    chunk_texts = [c.text for c in initial_citations]
    judgment = judge_faithfulness(
        question=question, answer=initial_answer, retrieved_chunks=chunk_texts
    )
    audit["initial_judgment"] = judgment

    score = judgment.get("score")
    if score is None or score >= _FAITHFULNESS_FLOOR:
        # Either the judge failed (be lenient — don't gate on a flaky judge)
        # or the answer passed. Return original.
        return SelfRagResult(
            answer=initial_answer, citations=initial_citations, audit=audit
        )

    log.info(
        "self_rag: faithfulness %.2f < %.2f — retrying", score, _FAITHFULNESS_FLOOR
    )
    rewritten = _rewrite_query_for_unsupported(
        question, initial_answer, judgment.get("unsupported_examples") or []
    )
    if not rewritten:
        return SelfRagResult(answer=initial_answer, citations=initial_citations, audit=audit)

    audit["retried"] = True
    audit["rewritten_query"] = rewritten

    # Re-retrieve with the rewritten query. Use a smaller pool — we're
    # supplementing, not replacing, so 6-8 fresh chunks is plenty.
    fresh = await retrieve_for_topic(
        db=db, topic_id=topic_id, query=rewritten, top_n=8, dedup_by_document=True
    )

    # Merge fresh citations into the pool, dedupe by chunk_id, keep highest score.
    merged: dict[int | None, Citation] = {}
    for c in initial_citations + fresh:
        key = c.chunk_id
        prev = merged.get(key)
        if prev is None or c.score > prev.score:
            merged[key] = c
    citations_v2 = sorted(merged.values(), key=lambda c: c.score, reverse=True)[:8]

    # Regenerate using the merged pool.
    messages = build_messages(
        question=question,
        chat_history=history,
        citations=[c.to_dict(drop_text=False) for c in citations_v2],
        chat_mode=None,
    )
    if system_extra:
        # Append extra system context (e.g. memory block) the caller had.
        messages.insert(0, {"role": "system", "content": system_extra})
    try:
        answer_v2 = get_llm_client().complete(
            messages, temperature=0.2, max_tokens=1024, feature="self_rag_regen"
        )
    except Exception as exc:
        log.warning("self-rag regenerate failed: %s — returning initial", exc)
        return SelfRagResult(
            answer=initial_answer, citations=initial_citations, audit=audit
        )

    # Re-judge to record final score, but don't loop again.
    final_judgment = judge_faithfulness(
        question=question,
        answer=answer_v2,
        retrieved_chunks=[c.text for c in citations_v2],
    )
    audit["final_judgment"] = final_judgment
    log.info(
        "self_rag: retry complete initial=%.2f final=%s",
        score, final_judgment.get("score"),
    )
    return SelfRagResult(answer=answer_v2, citations=citations_v2, audit=audit)
