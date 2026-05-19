"""Concept Glossary service (Sprint 5 MVP)."""
from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.document import Document
from app.db.models.research_ext import (
    TermOccurrence,
    TopicGlossaryTerm,
    TopicTerm,
)
from app.rag.llm_client import get_llm_client
from app.services.json_llm import (
    normalize_confidence,
    safe_parse_json_object,
    truncate_for_llm,
)

log = logging.getLogger(__name__)


_GLOSSARY_SYSTEM = """你是研究领域术语解释助手。给定一个术语和它在 Topic 中出现的若干证据片段，
输出一段简短中文定义（1-2 句）。

硬性规则：
1. 定义只能基于传入证据，不允许引入外部知识。
2. 证据不足时返回 {"definition": null, "confidence": 0}。
3. 定义 ≤ 200 字符。
4. 严格输出 JSON object。
"""

_GLOSSARY_USER_TMPL = """term: {term}
term_type: {term_type}

evidence:
{evidence}

输出 JSON：
{{
  "definition": "...",
  "confidence": 0.7
}}
"""


async def generate_glossary_for_topic(
    db: AsyncSession, topic_id: int, limit_terms: int = 20
) -> dict[str, int]:
    """Generate / refresh glossary entries for top terms."""
    terms = (
        await db.execute(
            select(TopicTerm)
            .where(TopicTerm.topic_id == topic_id)
            .order_by(TopicTerm.occurrence_count.desc())
            .limit(limit_terms)
        )
    ).scalars().all()
    if not terms:
        return {"generated": 0, "skipped": 0}

    client = get_llm_client()
    generated = 0
    skipped = 0
    for term in terms:
        # Skip if already present and recent (last 24h)
        existing = (
            await db.execute(
                select(TopicGlossaryTerm).where(
                    TopicGlossaryTerm.topic_id == topic_id,
                    TopicGlossaryTerm.normalized_term == term.normalized_term,
                )
            )
        ).scalar_one_or_none()

        # Gather a few evidence rows (term_occurrence context + doc title)
        occ_rows = (
            await db.execute(
                select(TermOccurrence.context_text, TermOccurrence.document_id)
                .where(
                    TermOccurrence.topic_id == topic_id,
                    TermOccurrence.term_id == term.id,
                )
                .limit(5)
            )
        ).all()
        if not occ_rows:
            skipped += 1
            continue
        doc_ids = list({r.document_id for r in occ_rows if r.document_id})[:3]
        title_map = {}
        if doc_ids:
            title_rows = (
                await db.execute(select(Document.id, Document.title).where(Document.id.in_(doc_ids)))
            ).all()
            title_map = {r.id: r.title for r in title_rows}

        evidence_text = "\n".join(
            f"- [{title_map.get(r.document_id, 'doc')}]: {(r.context_text or '')[:240]}"
            for r in occ_rows[:5]
        )

        try:
            raw = client.complete(
                [
                    {"role": "system", "content": _GLOSSARY_SYSTEM},
                    {
                        "role": "user",
                        "content": _GLOSSARY_USER_TMPL.format(
                            term=term.term,
                            term_type=term.term_type,
                            evidence=truncate_for_llm(evidence_text, 1200),
                        ),
                    },
                ],
                temperature=0.2,
                max_tokens=200,
            )
        except Exception as exc:
            log.warning("glossary_gen_failed term=%s err=%s", term.term, exc)
            skipped += 1
            continue
        data = safe_parse_json_object(raw, fallback={})
        definition = (data.get("definition") or "").strip()
        confidence = normalize_confidence(data.get("confidence"), default=0.5)
        if not definition:
            skipped += 1
            continue

        if existing is None:
            db.add(
                TopicGlossaryTerm(
                    topic_id=topic_id,
                    term_id=term.id,
                    term=term.term,
                    normalized_term=term.normalized_term,
                    definition=definition,
                    representative_document_ids=doc_ids,
                    confidence=confidence,
                    source="llm",
                )
            )
        else:
            existing.definition = definition
            existing.representative_document_ids = doc_ids
            existing.confidence = confidence
            existing.updated_at = datetime.now(tz=UTC)
        generated += 1
    await db.flush()
    return {"generated": generated, "skipped": skipped}


async def list_glossary(
    db: AsyncSession, topic_id: int, limit: int = 80
) -> Sequence[TopicGlossaryTerm]:
    return (
        await db.execute(
            select(TopicGlossaryTerm)
            .where(TopicGlossaryTerm.topic_id == topic_id)
            .order_by(TopicGlossaryTerm.confidence.desc())
            .limit(limit)
        )
    ).scalars().all()


__all__ = ["generate_glossary_for_topic", "list_glossary"]
