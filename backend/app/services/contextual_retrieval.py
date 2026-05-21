"""Contextual Retrieval (Wave-3 Pkg-CR).

Anthropic's 2024 technique: prepend a 1-sentence situating context to each
chunk before embedding so chunks like "Table 3 shows..." or "as discussed
above..." carry their framing into the vector space. Anthropic's
end-to-end numbers: top-20 retrieval failure rate -49% when combined with
BM25 + reranking.

We make two pragmatic deviations from the original recipe:

1. **Context is generated per PARENT, not per child**. The parent already
   represents the section that all its children live in, so one LLM call
   per section (~5-10 calls per paper) instead of per child (~50-100)
   gives ~80% of the recall benefit at ~10% of the LLM cost.

2. **Context is stored on the child**, prepended only at embed-time. The
   user-visible `chunk.text` stays unchanged, so BM25 and citation
   rendering are unaffected. Only the vector reflects the contextualized
   text — matching Anthropic's hybrid approach.
"""
from __future__ import annotations

import logging

from app.rag.llm_client import get_llm_client

log = logging.getLogger(__name__)


_SYSTEM_EN = """You will receive a paper title, a section name, and a passage
from the paper. Output ONE short English sentence (≤ 35 words) that situates
the passage — what topic it discusses and what role it plays in the paper.
This sentence is prepended to the passage before embedding, so it adds the
context the passage lost when sliced out of the section.

HARD RULES — violations are bugs:
1. Output language is ENGLISH. Do not translate or output Chinese.
2. Do NOT summarize content. Describe what the passage is ABOUT and its role
   (introduction / method / experiment / discussion).
3. One sentence, ≤ 35 words. No quotes, no prefixes ("This passage..."),
   no bullets, no JSON, no newlines.
"""

_SYSTEM_ZH = """你将收到论文标题、章节名、以及一段论文正文。请输出一句简短的中文
(≤ 60 字)定位句:说明该段落讨论什么主题,以及在论文里扮演的角色。这句话会
被拼接到段落前面用于嵌入,作用是补回切段时丢失的上下文。

硬性规则 — 违反即 bug:
1. 输出语言为中文,不要翻译成英文,不要混用。
2. 不要总结具体内容,只描述"段落讲什么"+"在论文里扮演的角色(引言 / 方法 /
   实验 / 讨论)"。
3. 一句话,≤ 60 字,不要 quote、不要前缀(如 "该段落..."),不要 bullet、
   不要 JSON、不要换行。
"""

_USER_TMPL = """Title: {title}
Section: {section_title}

Passage:
{parent_text}

Situating sentence:"""


def _is_cjk_dominant(text: str) -> bool:
    """True if >30% of non-whitespace chars are CJK. Most English chunks fail
    even when authors are Chinese; most Chinese chunks pass even with English
    citations sprinkled in."""
    if not text:
        return False
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    visible = sum(1 for ch in text if not ch.isspace())
    return visible > 0 and cjk / visible > 0.3


def _truncate(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else text[: max_chars - 3] + "..."


def generate_context_for_parent(
    *, title: str, section_title: str | None, parent_text: str
) -> str:
    """Single LLM call. Returns one short line of situating context, or empty
    string on failure (caller falls back to embedding raw text).
    """
    # Pick the system prompt by the passage's dominant language. Putting the
    # rule in the system role rather than in the user payload makes LLMs that
    # default to Chinese (DeepSeek, Qwen) actually respect English-output
    # requests on English passages.
    system = _SYSTEM_ZH if _is_cjk_dominant(parent_text) else _SYSTEM_EN
    client = get_llm_client()
    messages = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": _USER_TMPL.format(
                title=_truncate(title or "Untitled", 200),
                section_title=section_title or "(no section)",
                parent_text=_truncate(parent_text, 1800),
            ),
        },
    ]
    try:
        out = client.complete(
            messages,
            temperature=0.1,
            max_tokens=120,
            feature="contextual_retrieval",
        )
    except Exception as exc:
        log.warning("contextual context generation failed: %s", exc)
        return ""
    # Keep the first line only; defensive truncation against runaway output.
    return (out or "").strip().splitlines()[0][:400] if out else ""


def generate_contexts_by_parent_idx(
    *, document_title: str, parent_chunks: list
) -> dict[int, str]:
    """Run context generation for each parent chunk; returns
    {parent.chunk_index: context_summary}. Failures are silent (empty string).
    """
    out: dict[int, str] = {}
    for p in parent_chunks:
        ctx = generate_context_for_parent(
            title=document_title,
            section_title=getattr(p, "section_title", None),
            parent_text=getattr(p, "text", "") or "",
        )
        out[p.chunk_index] = ctx
    return out


def compose_embedding_text(chunk_text: str, context_summary: str | None) -> str:
    """Prepend the situating context to the chunk text used for embedding.
    Stored chunk.text is unchanged — only the embedding input differs."""
    if not context_summary:
        return chunk_text
    return f"{context_summary}\n\n{chunk_text}"
