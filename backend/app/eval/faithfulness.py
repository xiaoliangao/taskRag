"""Faithfulness judge for the eval pipeline.

A generated answer is "faithful" when every assertion it makes is supported
by the retrieved context. We ask an LLM judge to read (question, answer,
[retrieved chunks]) and produce a 0-1 score plus a short justification.

Why no automatic citation-string check? Because models often paraphrase the
chunk content rather than quoting verbatim — substring matching misses real
groundings. The LLM judge tolerates paraphrase and catches actual
hallucinations.

Why a separate judge instead of RAGAS lib? RAGAS pulls heavy deps and
defaults to OpenAI. We already have a multi-provider LLM client and a
structured-JSON parser; this is a 100-line file that fits the project's
style.
"""
from __future__ import annotations

import logging
from typing import Any

from app.rag.llm_client import get_llm_client
from app.services.json_llm import safe_parse_json_object, truncate_for_llm

log = logging.getLogger(__name__)


_SYSTEM = """You are evaluating whether an answer is faithfully grounded in the
retrieved context. You receive a question, an answer, and N retrieved
context chunks.

Your job:
1. Identify each distinct factual claim in the answer (skip generic filler
   like "I see your question").
2. For each claim, decide if it is SUPPORTED by at least one chunk
   (allowing paraphrase). Be strict: if a claim contains specific
   numbers, dates, methods, or names not present in any chunk → unsupported.
3. Compute score = supported_claims / total_claims (0 if no claims).

Output strict JSON, no markdown fences, no prefix:
{"score": 0.0–1.0, "supported": N, "total": N, "unsupported_examples": [..]}

`unsupported_examples` is at most 2 short strings citing which claims
weren't grounded. Empty list when score = 1.0.
"""


_USER_TMPL = """QUESTION:
{question}

ANSWER:
{answer}

RETRIEVED CONTEXT ({n_chunks} chunks):
{chunks}

JSON:"""


def _format_chunks(chunks: list[str], per_chunk_limit: int = 1500) -> str:
    parts = []
    for i, ch in enumerate(chunks, 1):
        text = (ch or "").strip()
        if not text:
            continue
        if len(text) > per_chunk_limit:
            text = text[: per_chunk_limit - 3] + "..."
        parts.append(f"[chunk {i}]\n{text}")
    return "\n\n".join(parts)


def judge_faithfulness(
    *, question: str, answer: str, retrieved_chunks: list[str]
) -> dict[str, Any]:
    """Return {score, supported, total, unsupported_examples, error?}.

    On any LLM failure returns {error: ..., score: None} so the caller can
    aggregate scores while flagging failed evaluations.
    """
    if not (answer or "").strip():
        return {"score": 0.0, "supported": 0, "total": 0, "unsupported_examples": []}
    if not retrieved_chunks:
        # An answer with no retrieved context can only be faithful by accident.
        return {
            "score": 0.0, "supported": 0, "total": 1,
            "unsupported_examples": ["answer produced without any retrieved chunks"],
        }

    user_msg = _USER_TMPL.format(
        question=truncate_for_llm(question, 600),
        answer=truncate_for_llm(answer, 2000),
        n_chunks=len(retrieved_chunks),
        chunks=_format_chunks(retrieved_chunks),
    )
    try:
        raw = get_llm_client().complete(
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            max_tokens=400,
            feature="eval_faithfulness",
        )
    except Exception as exc:
        log.warning("faithfulness judge LLM failed: %s", exc)
        return {"score": None, "error": str(exc)[:200]}

    data = safe_parse_json_object(raw, fallback={})
    score = data.get("score")
    try:
        score = float(score) if score is not None else None
    except (TypeError, ValueError):
        score = None
    if score is not None:
        score = max(0.0, min(1.0, score))
    return {
        "score": score,
        "supported": int(data.get("supported") or 0),
        "total": int(data.get("total") or 0),
        "unsupported_examples": list(data.get("unsupported_examples") or [])[:3],
    }
