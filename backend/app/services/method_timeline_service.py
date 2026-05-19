"""Method Timeline service (v1.5 A-3).

Builds a per-topic timeline of method entities and (optional) LLM-suggested
evolution edges. Source of method entities = topic_terms with term_type='method'.

Pipeline:
  1. rebuild_method_entities(): copy method-type TopicTerm rows into method_entities,
     deriving first_seen_at from earliest term occurrence + document_count.
  2. (optional) extract_evolution_edges(): for the top-N methods, ask the LLM
     to propose likely evolution pairs (improves/extends/replaces/...).
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models.research_ext import (
    MethodEntity,
    MethodEvolutionEdge,
    TermOccurrence,
    TopicTerm,
)
from app.rag.llm_client import get_llm_client
from app.services.json_llm import safe_parse_json_object, truncate_for_llm

log = logging.getLogger(__name__)

_VALID_RELATION = {"improves", "extends", "replaces", "combines", "evaluates", "compares_with"}


_EVOLUTION_SYSTEM = """你是研究方法演化图谱构建助手。给定一个 Topic 里若干方法实体的基础信息
（名称 + 首次出现年份 + 简短描述），请基于通用领域知识 + 时间顺序推断方法之间的演化关系。

relation_type 只能取这些之一：
  improves     B 在 A 基础上改进
  extends      B 是 A 的扩展 / 新场景
  replaces     B 取代 A 成为主流
  combines     B 融合了 A 和其它方法
  evaluates    B 用作 A 的评估对照
  compares_with B 与 A 直接对比

硬性规则：
1. 只对**确实存在普遍认知关系**的方法对推断。不确定的不要写。
2. confidence ∈ [0.4, 0.95]；不确定的低分。
3. 方法名必须严格使用给定列表中的字符串（区分大小写）。
4. 不允许引入列表外的方法名。
5. 严格输出 JSON object。
"""

_EVOLUTION_USER_TMPL = """topic: {topic_name}

methods (按首次出现年份排序):
{method_list}

输出 JSON：
{{
  "edges": [
    {{
      "from_method": "...",
      "to_method": "...",
      "relation_type": "improves",
      "confidence": 0.7,
      "explanation": "..."
    }}
  ]
}}
"""


def rebuild_method_entities(db: Session, topic_id: int) -> int:
    """Materialize / refresh method_entities from method-type TopicTerm rows."""
    # Pull method terms (term_type='method') along with first/last seen + doc count.
    sub = (
        db.query(
            TermOccurrence.term_id.label("tid"),
            func.min(TermOccurrence.occurred_at).label("first_at"),
            func.count(func.distinct(TermOccurrence.document_id)).label("doc_count"),
            func.min(TermOccurrence.document_id).label("first_doc"),
        )
        .filter(TermOccurrence.topic_id == topic_id)
        .group_by(TermOccurrence.term_id)
        .subquery()
    )
    rows = (
        db.query(TopicTerm, sub.c.first_at, sub.c.doc_count, sub.c.first_doc)
        .outerjoin(sub, sub.c.tid == TopicTerm.id)
        .filter(
            TopicTerm.topic_id == topic_id,
            TopicTerm.term_type.in_(("method", "model")),
        )
        .all()
    )

    upserted = 0
    for term, first_at, doc_count, first_doc in rows:
        if not term.term:
            continue
        existing = (
            db.query(MethodEntity)
            .filter(
                MethodEntity.topic_id == topic_id,
                MethodEntity.normalized_name == term.normalized_term,
            )
            .first()
        )
        if existing:
            existing.first_seen_at = first_at
            existing.first_seen_document_id = first_doc
            existing.document_count = int(doc_count or 0)
            existing.updated_at = datetime.utcnow()
        else:
            db.add(
                MethodEntity(
                    topic_id=topic_id,
                    name=term.term,
                    normalized_name=term.normalized_term,
                    first_seen_at=first_at,
                    first_seen_document_id=first_doc,
                    document_count=int(doc_count or 0),
                    aliases_json=list(term.metadata_json.get("aliases") or [])
                    if isinstance(term.metadata_json, dict)
                    else [],
                )
            )
            upserted += 1
    db.flush()
    return upserted


def extract_evolution_edges(
    db: Session, topic_id: int, topic_name: str, top_n: int = 20
) -> int:
    """Ask the LLM to suggest evolution edges between top-N methods. Replaces existing edges."""
    rows = (
        db.query(MethodEntity)
        .filter(MethodEntity.topic_id == topic_id)
        .order_by(
            MethodEntity.document_count.desc(),
            MethodEntity.first_seen_at.asc().nullslast(),
        )
        .limit(top_n)
        .all()
    )
    if len(rows) < 2:
        return 0

    def _year(m: MethodEntity) -> str:
        return str(m.first_seen_at.year) if m.first_seen_at else "n.d."

    method_lines = "\n".join(
        f"- {m.name} (first_seen={_year(m)}, docs={m.document_count})" for m in rows
    )
    by_name = {m.name: m for m in rows}

    client = get_llm_client()
    try:
        raw = client.complete(
            [
                {"role": "system", "content": _EVOLUTION_SYSTEM},
                {
                    "role": "user",
                    "content": _EVOLUTION_USER_TMPL.format(
                        topic_name=topic_name,
                        method_list=truncate_for_llm(method_lines, 2200),
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=900,
            feature="method_evolution",
        )
    except Exception as exc:
        log.warning("method_evolution_llm_failed: %s", exc)
        return 0

    data = safe_parse_json_object(raw, fallback={})
    edges_raw = data.get("edges") or []
    if not isinstance(edges_raw, list):
        return 0

    # Clear previous edges before re-inserting (idempotent regenerate)
    db.query(MethodEvolutionEdge).filter(
        MethodEvolutionEdge.topic_id == topic_id
    ).delete(synchronize_session=False)

    inserted = 0
    for e in edges_raw:
        if not isinstance(e, dict):
            continue
        rt = (e.get("relation_type") or "").strip().lower()
        if rt not in _VALID_RELATION:
            continue
        f_name = (e.get("from_method") or "").strip()
        t_name = (e.get("to_method") or "").strip()
        if f_name == t_name or not f_name or not t_name:
            continue
        f = by_name.get(f_name)
        t = by_name.get(t_name)
        if not f or not t:
            continue
        conf = float(e.get("confidence", 0.5) or 0.5)
        conf = max(0.0, min(1.0, conf))
        db.add(
            MethodEvolutionEdge(
                topic_id=topic_id,
                from_method_id=f.id,
                to_method_id=t.id,
                relation_type=rt,
                confidence=conf,
                explanation=(e.get("explanation") or "")[:600],
                evidence_document_ids=[],
            )
        )
        inserted += 1
    db.flush()
    return inserted


def list_methods_for_topic(db: Session, topic_id: int) -> Sequence[MethodEntity]:
    return (
        db.query(MethodEntity)
        .filter(MethodEntity.topic_id == topic_id)
        .order_by(MethodEntity.first_seen_at.asc().nullslast(), MethodEntity.document_count.desc())
        .all()
    )


def list_edges_for_topic(db: Session, topic_id: int) -> Sequence[MethodEvolutionEdge]:
    return (
        db.query(MethodEvolutionEdge)
        .filter(MethodEvolutionEdge.topic_id == topic_id)
        .order_by(MethodEvolutionEdge.confidence.desc())
        .all()
    )


__all__ = [
    "extract_evolution_edges",
    "list_edges_for_topic",
    "list_methods_for_topic",
    "rebuild_method_entities",
]


# Silence unused import warnings
_ = Any
