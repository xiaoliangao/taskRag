"""GapFinder: synthesize research gaps from briefings + topic context."""
from __future__ import annotations

import json
import logging
import re
from datetime import UTC
from typing import Any

from sqlalchemy.orm import Session

from app.db.models.document import Document, TopicDocument
from app.db.models.intel import DocumentBriefing, TopicDocumentInsight
from app.db.models.topic import Topic
from app.db.repositories.intel_repo import InsightRepository
from app.rag.llm_client import get_llm_client

log = logging.getLogger(__name__)


_GAP_SYSTEM = """你是研究方向分析师。基于课题最近一段时间的论文结构化解读，识别 3-5 个潜在的研究空白
（gap）。每个 gap 必须基于多篇论文的证据。

输出严格 JSON：
{
  "gaps": [
    {
      "title": str,
      "summary": str,
      "detail_md": str (markdown，3-6 句话解释为什么这是 gap),
      "confidence": "low"|"medium"|"high",
      "evidence_document_ids": [int, ...],
      "suggested_questions": [str, ...],
      "suggested_experiments": [str, ...]
    }
  ]
}

规则：
1. 不要写 "无人研究" 这类绝对表述；用 "在当前课题已采集文档中，系统尚未发现…" 这类不确定语言。
2. 每个 gap 至少引用 2 个 evidence_document_ids（除非语料不足）。
3. evidence_document_ids 必须来自给定列表。
4. confidence 反映你的把握程度，绝大多数情况下为 low/medium。
5. 直接输出 JSON，不包 markdown 代码块。
"""


def _safe_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
        return None


def generate_research_gaps(db: Session, topic_id: int, *, max_docs: int = 12) -> list[int]:
    topic = db.get(Topic, topic_id)
    if not topic:
        return []

    rows = (
        db.query(TopicDocument, Document)
        .join(Document, Document.id == TopicDocument.document_id)
        .filter(TopicDocument.topic_id == topic_id)
        .order_by(TopicDocument.added_at.desc())
        .limit(40)
        .all()
    )
    if not rows:
        return []

    doc_ids = [d.id for _, d in rows]
    briefings = {
        b.document_id: b
        for b in db.query(DocumentBriefing)
        .filter(DocumentBriefing.document_id.in_(doc_ids), DocumentBriefing.status == "success")
        .all()
    }
    insights = {
        i.document_id: i
        for i in db.query(TopicDocumentInsight).filter(
            TopicDocumentInsight.topic_id == topic_id,
            TopicDocumentInsight.document_id.in_(doc_ids),
        ).all()
    }

    # Prefer docs that have briefings; fall back to abstract.
    candidates: list[dict[str, Any]] = []
    for _td, doc in rows:
        b = briefings.get(doc.id)
        i = insights.get(doc.id)
        if not b and not doc.abstract:
            continue
        candidates.append(
            {
                "document_id": doc.id,
                "title": doc.title,
                "published_at": doc.published_at.date().isoformat() if doc.published_at else None,
                "problem": b.problem if b else None,
                "method": b.method if b else None,
                "contributions": (b.contributions if b else []),
                "limitations": (b.limitations if b else []),
                "datasets": (b.datasets if b else []),
                "metrics": (b.metrics if b else []),
                "abstract": (doc.abstract or "")[:300] if not b else None,
                "relevance": i.relevance_score if i else None,
            }
        )
        if len(candidates) >= max_docs:
            break

    user_block = (
        f"课题: {topic.name}\n"
        f"关键词: {', '.join(topic.keywords or [])}\n"
        f"候选论文（{len(candidates)} 篇）:\n"
        + json.dumps(candidates, ensure_ascii=False, indent=2)
        + "\n\n请输出 JSON 形式的 3-5 个研究空白。"
    )

    llm = get_llm_client()
    try:
        raw = llm.complete(
            [
                {"role": "system", "content": _GAP_SYSTEM},
                {"role": "user", "content": user_block},
            ],
            temperature=0.4,
            max_tokens=2000,
        )
    except Exception as exc:
        log.exception("Gap LLM failed topic=%s: %s", topic_id, exc)
        return []

    data = _safe_json(raw)
    if not data or not isinstance(data.get("gaps"), list):
        log.warning("Gap JSON parse failed topic=%s: %s", topic_id, raw[:400])
        return []

    allowed = {c["document_id"] for c in candidates}
    repo = InsightRepository(db)
    created_ids: list[int] = []
    confidence_map = {"low": 0.3, "medium": 0.6, "high": 0.85}

    for g in data["gaps"][:5]:
        evidence = [int(x) for x in (g.get("evidence_document_ids") or []) if int(x) in allowed]
        i = repo.add(
            topic_id=topic_id,
            insight_type="gap",
            title=str(g.get("title") or "")[:280],
            summary=g.get("summary"),
            detail_md=g.get("detail_md"),
            confidence=confidence_map.get(str(g.get("confidence", "low")).lower(), 0.4),
            evidence_document_ids=evidence,
            suggested_questions=g.get("suggested_questions") or [],
            suggested_experiments=g.get("suggested_experiments") or [],
            model_provider=llm.cfg.provider,
            model_name=llm.cfg.model,
            generated_at=None,
        )
        from datetime import datetime

        i.generated_at = datetime.now(tz=UTC)
        created_ids.append(i.id)
    db.flush()
    return created_ids
