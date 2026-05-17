"""Claim extraction service (Sprint 2)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.orm import Session

from app.db.models.document import Document, TopicDocument
from app.db.models.intel import DocumentBriefing
from app.db.repositories.research_ext_repo import PaperClaimRepository
from app.rag.llm_client import get_llm_client
from app.services.json_llm import (
    normalize_confidence,
    safe_parse_json_object,
    truncate_for_llm,
)

log = logging.getLogger(__name__)


_CLAIM_SYSTEM = """你是一位论文 claim 抽取助手。任务：从一篇论文的 briefing + 摘要中，
抽取"可被验证的事实性主张"。

claim_type 取值且只能取一个：
  result            实验结果 / 性能数字
  method            方法层面的主张（如"使用 iterative refinement 比单次预测更稳定"）
  limitation        本文承认或暴露的局限
  assumption        理论或实验假设
  dataset           关于数据集本身的主张
  comparison        与其它方法的直接比较
  negative_result   显式的负向结论

硬性规则：
1. 只抽文中明确陈述的主张，不要做跨段推理或外部知识补全。
2. 单篇文档最多 6 条 claim；优先抽 result / comparison / limitation。
3. method / dataset / metric / setting / result_value 能识别就填，不能识别留 null。
4. polarity ∈ {positive, negative, neutral}：以本文方法的视角，结果是有利、不利、还是中性。
5. confidence ∈ [0,1]：原文直接陈述给 ≥ 0.7，需要拼接信息给 ≤ 0.5。
6. evidence_text ≤ 220 字符，从原文截取，不要改写。
7. 严格输出 JSON object，不要 markdown、不要注释。
"""

_CLAIM_USER_TMPL = """title: {title}
abstract: {abstract}
briefing:
  one_sentence_summary: {summary}
  problem: {problem}
  method: {method}
  contributions: {contributions}
  experiments: {experiments}
  limitations: {limitations}
  datasets: {datasets}
  metrics: {metrics}

输出 JSON：
{{
  "claims": [
    {{
      "claim_text": "...",
      "claim_type": "result",
      "method": "...",
      "dataset": "...",
      "metric": "...",
      "setting": "...",
      "polarity": "positive",
      "confidence": 0.75,
      "evidence_text": "..."
    }}
  ]
}}
"""


_VALID_TYPES = {
    "result", "method", "limitation", "assumption",
    "dataset", "comparison", "negative_result",
}
_VALID_POLARITY = {"positive", "negative", "neutral"}


@dataclass
class ClaimRecord:
    claim_text: str
    claim_type: str
    method: str | None
    dataset: str | None
    metric: str | None
    setting: str | None
    polarity: str
    confidence: float
    evidence_text: str | None


def _coerce(item: dict) -> ClaimRecord | None:
    text = (item.get("claim_text") or "").strip()
    if not text:
        return None
    ctype = (item.get("claim_type") or "").strip().lower()
    if ctype not in _VALID_TYPES:
        ctype = "method"
    polarity = (item.get("polarity") or "neutral").strip().lower()
    if polarity not in _VALID_POLARITY:
        polarity = "neutral"
    return ClaimRecord(
        claim_text=text[:1000],
        claim_type=ctype,
        method=(item.get("method") or None) or None,
        dataset=(item.get("dataset") or None) or None,
        metric=(item.get("metric") or None) or None,
        setting=(item.get("setting") or None) or None,
        polarity=polarity,
        confidence=normalize_confidence(item.get("confidence"), default=0.5),
        evidence_text=((item.get("evidence_text") or "")[:1000] or None),
    )


def _fmt_list(values: list | None, limit: int = 6) -> str:
    if not values:
        return "—"
    out = []
    for v in values[:limit]:
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            out.append(v.get("name") or v.get("title") or str(v))
        else:
            out.append(str(v))
    return "; ".join(out)


class ClaimService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = PaperClaimRepository(db)

    def extract_for_topic(self, topic_id: int, limit_docs: int = 30) -> dict[str, int]:
        rows = (
            self.db.query(Document, DocumentBriefing)
            .join(TopicDocument, TopicDocument.document_id == Document.id)
            .outerjoin(DocumentBriefing, DocumentBriefing.document_id == Document.id)
            .filter(TopicDocument.topic_id == topic_id)
            .order_by(Document.published_at.desc().nullslast())
            .limit(limit_docs)
            .all()
        )
        total = 0
        skipped = 0
        for doc, briefing in rows:
            count = self._extract_one(topic_id, doc, briefing)
            total += count
            if count == 0:
                skipped += 1
        return {"documents_seen": len(rows), "claims_inserted": total, "skipped": skipped}

    def _extract_one(
        self,
        topic_id: int,
        doc: Document,
        briefing: DocumentBriefing | None,
    ) -> int:
        if not (briefing or doc.abstract):
            return 0
        client = get_llm_client()
        user_msg = _CLAIM_USER_TMPL.format(
            title=truncate_for_llm(doc.title or "", 200),
            abstract=truncate_for_llm(doc.abstract or "", 1200),
            summary=(briefing.one_sentence_summary if briefing else "") or "",
            problem=(briefing.problem if briefing else "") or "",
            method=(briefing.method if briefing else "") or "",
            contributions=_fmt_list(briefing.contributions if briefing else []),
            experiments=_fmt_list(briefing.experiments if briefing else []),
            limitations=_fmt_list(briefing.limitations if briefing else []),
            datasets=_fmt_list(briefing.datasets if briefing else []),
            metrics=_fmt_list(briefing.metrics if briefing else []),
        )
        try:
            raw = client.complete(
                [
                    {"role": "system", "content": _CLAIM_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.1,
                max_tokens=900,
            )
        except Exception as exc:
            log.warning(
                "claim_extract_failed topic=%s doc=%s err=%s", topic_id, doc.id, exc
            )
            return 0
        data = safe_parse_json_object(raw, fallback={"claims": []})
        items = data.get("claims") or []
        if not isinstance(items, list):
            return 0
        records = [c for c in (_coerce(it) for it in items if isinstance(it, dict)) if c]
        records = records[:6]
        rows = [
            dict(
                topic_id=topic_id,
                document_id=doc.id,
                chunk_id=None,
                claim_text=r.claim_text,
                claim_type=r.claim_type,
                method=r.method,
                dataset=r.dataset,
                metric=r.metric,
                setting=r.setting,
                polarity=r.polarity,
                confidence=r.confidence,
                evidence_text=r.evidence_text,
                source="briefing+abstract" if briefing else "abstract",
                metadata_json={},
            )
            for r in records
        ]
        self.repo.replace_for_document(topic_id, doc.id, rows)
        return len(rows)


__all__ = ["ClaimService"]
