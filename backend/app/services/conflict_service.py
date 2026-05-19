"""Claim conflict detection service (Sprint 2)."""
from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.db.models.research_ext import PaperClaim
from app.db.repositories.research_ext_repo import (
    ClaimRelationRepository,
    PaperClaimRepository,
)
from app.rag.llm_client import get_llm_client
from app.services.json_llm import (
    normalize_confidence,
    safe_parse_json_object,
    truncate_for_llm,
)

log = logging.getLogger(__name__)

_MAX_PAIRS_PER_RUN = 80
_MIN_SCORE = 0.45

_RELATION_TYPES = {"supports", "conflicts", "qualifies", "unrelated", "insufficient_info"}


_RELATION_SYSTEM = """你是一位严谨的论文 claim 关系判定器。

relation_type 取值且只能取一个：
  supports         在相近设置下互相支持
  conflicts        在大体一致的数据集/指标/任务下结论相反
  qualifies        话题相关但实验设置/数据集/指标/规模有差异，应视为"条件不同"
  unrelated        话题不相关
  insufficient_info 证据不足无法判定

硬性规则：
1. 任何一个维度（数据集/指标/任务/训练设置/规模）有显著差异且未被显式控制，
   优先返回 qualifies，而不是 conflicts。
2. 不要使用"X 错了""已证伪"等措辞。
3. reason_md 中性表述，引用 claim 原文短片段。
4. confidence ∈ [0,1]，仅在证据明确时给 ≥ 0.7。
5. 严格输出 JSON object。
"""

_RELATION_USER_TMPL = """topic: {topic_name}

claim_a:
  document_title: {a_title}
  claim_text: {a_text}
  claim_type: {a_type}
  method: {a_method}
  dataset: {a_dataset}
  metric: {a_metric}
  setting: {a_setting}
  polarity: {a_polarity}
  evidence: {a_evidence}

claim_b:
  document_title: {b_title}
  claim_text: {b_text}
  claim_type: {b_type}
  method: {b_method}
  dataset: {b_dataset}
  metric: {b_metric}
  setting: {b_setting}
  polarity: {b_polarity}
  evidence: {b_evidence}

输出 JSON：
{{
  "relation_type": "qualifies",
  "confidence": 0.62,
  "reason_md": "两条 claim 都讨论 ...",
  "evidence": {{
    "shared_dataset": "...",
    "shared_metric": "...",
    "caveats": ["..."]
  }}
}}
"""


def _normalize(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s.strip().lower())


def _candidate_score(a: PaperClaim, b: PaperClaim) -> float:
    if a.document_id == b.document_id:
        return 0.0
    score = 0.0
    if a.claim_type == b.claim_type:
        score += 0.2
    if a.claim_type in {"result", "comparison", "limitation", "negative_result"}:
        score += 0.1
    da, db = _normalize(a.dataset), _normalize(b.dataset)
    if da and db and da == db:
        score += 0.35
    ma, mb = _normalize(a.metric), _normalize(b.metric)
    if ma and mb and ma == mb:
        score += 0.25
    mtha, mthb = _normalize(a.method), _normalize(b.method)
    if mtha and mthb and mtha != mthb:
        score += 0.1
    if a.polarity != b.polarity and "neutral" not in {a.polarity, b.polarity}:
        score += 0.2
    return score


_MIN_SCORE_FALLBACK = 0.30


def _build_candidates(claims: list[PaperClaim]) -> list[tuple[PaperClaim, PaperClaim, float]]:
    """Pick claim pairs to send to the LLM relation judge.

    v1.4 adaptive threshold: if the strict threshold (0.45) yields fewer than 5
    candidates, fall back to 0.30 so cross-method comparisons in less-overlapping
    topics still surface some pairs for human review.
    """
    out: list[tuple[PaperClaim, PaperClaim, float]] = []
    all_pairs: list[tuple[PaperClaim, PaperClaim, float]] = []
    n = len(claims)
    for i in range(n):
        a = claims[i]
        for j in range(i + 1, n):
            b = claims[j]
            score = _candidate_score(a, b)
            if score <= 0:
                continue
            all_pairs.append((a, b, score))
            if score >= _MIN_SCORE:
                out.append((a, b, score))

    # Adaptive fallback: not enough strict candidates -> loosen threshold
    if len(out) < 5:
        loosened = [p for p in all_pairs if p[2] >= _MIN_SCORE_FALLBACK]
        if len(loosened) > len(out):
            out = loosened

    out.sort(key=lambda t: t[2], reverse=True)
    return out[:_MAX_PAIRS_PER_RUN]


class ConflictService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.claim_repo = PaperClaimRepository(db)
        self.rel_repo = ClaimRelationRepository(db)

    def detect_for_topic(
        self,
        topic_id: int,
        topic_name: str,
        title_lookup: dict[int, str],
    ) -> dict[str, int]:
        claims = list(self.claim_repo.list_for_topic(topic_id))
        candidates = _build_candidates(claims)
        if not candidates:
            return {"pairs_evaluated": 0, "conflicts": 0, "qualifies": 0}

        conflicts = 0
        qualifies = 0
        supports = 0
        # Replace previous LLM-produced relations cleanly; user-reviewed survive only briefly,
        # but for MVP we just clear.
        self.rel_repo.clear_for_topic(topic_id)

        client = get_llm_client()
        for a, b, _score in candidates:
            user_msg = _RELATION_USER_TMPL.format(
                topic_name=topic_name,
                a_title=title_lookup.get(a.document_id, ""),
                a_text=truncate_for_llm(a.claim_text, 600),
                a_type=a.claim_type,
                a_method=a.method or "",
                a_dataset=a.dataset or "",
                a_metric=a.metric or "",
                a_setting=a.setting or "",
                a_polarity=a.polarity,
                a_evidence=truncate_for_llm(a.evidence_text or "", 360),
                b_title=title_lookup.get(b.document_id, ""),
                b_text=truncate_for_llm(b.claim_text, 600),
                b_type=b.claim_type,
                b_method=b.method or "",
                b_dataset=b.dataset or "",
                b_metric=b.metric or "",
                b_setting=b.setting or "",
                b_polarity=b.polarity,
                b_evidence=truncate_for_llm(b.evidence_text or "", 360),
            )
            try:
                raw = client.complete(
                    [
                        {"role": "system", "content": _RELATION_SYSTEM},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.1,
                    max_tokens=400,
                )
            except Exception as exc:
                log.warning(
                    "conflict_pair_failed topic=%s pair=(%s,%s) err=%s",
                    topic_id, a.id, b.id, exc,
                )
                continue
            data = safe_parse_json_object(raw, fallback={})
            rtype = (data.get("relation_type") or "").strip().lower()
            if rtype not in _RELATION_TYPES:
                continue
            if rtype == "unrelated":
                continue
            conf = normalize_confidence(data.get("confidence"), default=0.5)
            reason = (data.get("reason_md") or "")[:1500] or None
            evidence = data.get("evidence") if isinstance(data.get("evidence"), dict) else {}
            self.rel_repo.upsert(
                topic_id=topic_id,
                claim_a_id=a.id,
                claim_b_id=b.id,
                relation_type=rtype,
                confidence=conf,
                reason_md=reason,
                evidence_json=evidence,
            )
            if rtype == "conflicts":
                conflicts += 1
            elif rtype == "qualifies":
                qualifies += 1
            elif rtype == "supports":
                supports += 1

        return {
            "pairs_evaluated": len(candidates),
            "conflicts": conflicts,
            "qualifies": qualifies,
            "supports": supports,
        }


__all__ = ["ConflictService"]
