"""Hypothesis verification service (Sprint 3)."""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.research_ext import HypothesisCheck, HypothesisEvidence
from app.rag.llm_client import get_llm_client
from app.rag.retriever import Citation, retrieve_for_topic
from app.services.json_llm import (
    normalize_confidence,
    safe_parse_json_object,
    truncate_for_llm,
)

log = logging.getLogger(__name__)

_TOP_K = 24
_TOP_N = 10


_STANCE_SYSTEM = """你是论文证据立场判定器。给定一段研究假设和一段论文证据，
判断该证据相对于假设的立场。

stance 取值且只能取一个：
  support     直接支持该假设
  oppose      明确与该假设矛盾
  qualify     讨论了相同主题，但条件/数据集/设置不同；不能直接支持或反驳
  neutral     话题不相关或仅简单提及

硬性规则：
1. 仅基于给定证据判断，不引入外部知识。
2. quote 必须是证据中的原文片段（≤ 220 字符），不要改写。
3. explanation ≤ 160 字，用中性表述。
4. score ∈ [0,1]：仅 support/oppose 且证据明确时给 ≥ 0.7；qualify 默认 0.5；neutral 给 0.2。
5. 严格输出 JSON object。
"""

_STANCE_USER_TMPL = """假设: {hypothesis}

证据 (来自论文: {doc_title}):
{evidence}

输出 JSON：
{{
  "stance": "support",
  "score": 0.78,
  "quote": "...",
  "explanation": "..."
}}
"""

_SUMMARY_SYSTEM = """你是研究假设结论汇总器。给定假设和若干已判定的证据，输出 markdown 报告。
段落要求：
1. 开头一行给出 verdict（supported / refuted / mixed / insufficient）。
2. 简短解释 verdict 的原因（≤ 80 字）。
3. 三个小标题：支持证据 / 反对证据 / 限定条件。
4. 每条证据带 [文档标题, 简短引用]。
5. 末尾给一个 confidence（0-1）。
不要编造证据。
"""


_STANCE_VALUES = {"support", "oppose", "qualify", "neutral"}


def _aggregate_verdict(stances: list[str]) -> str:
    if not stances:
        return "insufficient"
    counter = Counter(stances)
    sup = counter.get("support", 0)
    opp = counter.get("oppose", 0)
    qual = counter.get("qualify", 0)
    if sup + opp + qual == 0:
        return "insufficient"
    if sup >= max(1, 2 * opp) and sup >= 2:
        return "supported"
    if opp >= max(1, 2 * sup) and opp >= 2:
        return "refuted"
    if sup > 0 and opp > 0:
        return "mixed"
    if qual >= 2 and sup + opp == 0:
        return "qualified"
    return "insufficient" if sup + opp + qual < 2 else "mixed"


class HypothesisService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_check(self, user_id: int, topic_id: int, hypothesis: str) -> HypothesisCheck:
        row = HypothesisCheck(
            user_id=user_id,
            topic_id=topic_id,
            hypothesis=hypothesis.strip()[:2000],
            status="pending",
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def run(self, check: HypothesisCheck) -> HypothesisCheck:
        check.status = "running"
        await self.db.flush()
        try:
            citations: list[Citation] = await retrieve_for_topic(
                db=self.db,
                topic_id=check.topic_id,
                query=check.hypothesis,
                top_k=_TOP_K,
                top_n=_TOP_N,
            )
        except Exception as exc:
            check.status = "failed"
            check.error_message = f"retrieval_failed: {exc}"[:1000]
            check.finished_at = datetime.now(tz=timezone.utc)
            await self.db.flush()
            return check

        if not citations:
            check.status = "success"
            check.verdict = "insufficient"
            check.result_md = (
                f"**Verdict**: insufficient\n\n"
                f"当前 Topic 中未检索到与该假设相关的证据。\n"
            )
            check.confidence = 0.1
            check.result_json = {"verdict": "insufficient", "evidence_count": 0}
            check.finished_at = datetime.now(tz=timezone.utc)
            await self.db.flush()
            return check

        client = get_llm_client()
        stances: list[str] = []
        evidence_rows: list[HypothesisEvidence] = []
        for c in citations[:_TOP_N]:
            user_msg = _STANCE_USER_TMPL.format(
                hypothesis=truncate_for_llm(check.hypothesis, 600),
                doc_title=c.title or "(unknown)",
                evidence=truncate_for_llm(c.text or "", 1200),
            )
            try:
                raw = client.complete(
                    [
                        {"role": "system", "content": _STANCE_SYSTEM},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.1,
                    max_tokens=300,
                )
            except Exception as exc:
                log.warning("hypothesis_stance_failed: %s", exc)
                continue
            data = safe_parse_json_object(raw, fallback={})
            stance = (data.get("stance") or "").strip().lower()
            if stance not in _STANCE_VALUES:
                stance = "neutral"
            stances.append(stance)
            evidence_rows.append(
                HypothesisEvidence(
                    check_id=check.id,
                    document_id=c.document_id,
                    chunk_id=c.chunk_id,
                    stance=stance,
                    quote=(data.get("quote") or c.text or "")[:600],
                    explanation=(data.get("explanation") or "")[:600],
                    score=normalize_confidence(data.get("score"), default=0.5),
                )
            )

        for row in evidence_rows:
            self.db.add(row)
        await self.db.flush()

        verdict = _aggregate_verdict(stances)
        non_neutral = [s for s in stances if s != "neutral"]
        confidence = round(min(1.0, 0.2 + 0.1 * len(non_neutral)), 2)

        # Optional LLM summary; on failure fall back to local md.
        summary_md = self._build_local_summary_md(check.hypothesis, verdict, evidence_rows)
        try:
            raw = client.complete(
                [
                    {"role": "system", "content": _SUMMARY_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"假设: {check.hypothesis}\n\n"
                            f"verdict: {verdict}\n\n"
                            + "\n".join(
                                f"- [{e.stance}] {e.quote}" for e in evidence_rows if e.stance != "neutral"
                            )
                            + "\n\n请输出 markdown 报告。"
                        ),
                    },
                ],
                temperature=0.3,
                max_tokens=900,
            )
            if raw and raw.strip():
                summary_md = raw.strip()
        except Exception:
            pass

        check.status = "success"
        check.verdict = verdict
        check.confidence = confidence
        check.result_md = summary_md
        check.result_json = {
            "verdict": verdict,
            "evidence_count": len(evidence_rows),
            "stance_breakdown": dict(Counter(stances)),
        }
        check.finished_at = datetime.now(tz=timezone.utc)
        await self.db.flush()
        return check

    @staticmethod
    def _build_local_summary_md(
        hypothesis: str, verdict: str, evidence: list[HypothesisEvidence]
    ) -> str:
        lines = [f"**Verdict**: {verdict}", "", "## 支持证据"]
        sup = [e for e in evidence if e.stance == "support"]
        opp = [e for e in evidence if e.stance == "oppose"]
        qual = [e for e in evidence if e.stance == "qualify"]
        for e in sup:
            lines.append(f"- “{e.quote}” — {e.explanation or ''}")
        if not sup:
            lines.append("- （无）")
        lines.append("")
        lines.append("## 反对证据")
        for e in opp:
            lines.append(f"- “{e.quote}” — {e.explanation or ''}")
        if not opp:
            lines.append("- （无）")
        lines.append("")
        lines.append("## 限定条件 / 不确定")
        for e in qual:
            lines.append(f"- “{e.quote}” — {e.explanation or ''}")
        if not qual:
            lines.append("- （无）")
        return "\n".join(lines)


async def list_checks(db: AsyncSession, topic_id: int, limit: int = 50) -> list[HypothesisCheck]:
    result = await db.execute(
        select(HypothesisCheck)
        .where(HypothesisCheck.topic_id == topic_id)
        .order_by(HypothesisCheck.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_evidence(db: AsyncSession, check_id: int) -> list[HypothesisEvidence]:
    result = await db.execute(
        select(HypothesisEvidence)
        .where(HypothesisEvidence.check_id == check_id)
        .order_by(HypothesisEvidence.score.desc())
    )
    return list(result.scalars().all())


__all__ = ["HypothesisService", "list_checks", "list_evidence"]
