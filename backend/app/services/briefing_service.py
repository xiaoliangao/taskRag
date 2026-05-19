"""BriefingService: generate structured per-paper summaries from chunks."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models.chat import ChatMessage  # noqa: F401 - schema link
from app.db.models.document import Chunk, Document
from app.db.models.intel import DocumentBriefing
from app.db.models.topic import Topic
from app.db.repositories.intel_repo import BriefingRepository, TopicInsightRepository
from app.rag.llm_client import get_llm_client

log = logging.getLogger(__name__)


_BRIEFING_SYSTEM = """你是一位严谨的研究论文助手。基于给定论文片段输出结构化 JSON，禁止编造未在片段中出现的信息。

输出 JSON 严格符合以下 schema（不要包裹 markdown 代码块，直接输出 JSON）：
{
  "one_sentence_summary": str,
  "problem": str | null,
  "method": str | null,
  "contributions": [str, ...],
  "experiments": [str, ...],
  "limitations": [str, ...],
  "datasets": [str, ...],
  "metrics": [str, ...],
  "code_available": bool | null,
  "code_url": str | null,
  "reading_time_minutes": int,
  "evidence_chunk_ids": [int, ...]
}

规则：
1. 不确定的字段填 null 或空数组，不要编造。
2. limitations 找不到时写：["未在当前文档片段中明确发现"]。
3. evidence_chunk_ids 是你引用到的 chunk id，必须来自给定列表。
4. reading_time_minutes 基于论文长度估算（短文 5 分钟，长论文 20-40 分钟）。
5. 输出语言：中文。
"""


_INSIGHT_SYSTEM = """你判断一篇论文对某个研究课题的相关性。基于论文摘要和课题关键词输出 JSON：
{
  "relevance_score": float (0.0-1.0),
  "relevance_reason": str,
  "reading_priority": "high" | "medium" | "low",
  "why_read": str,
  "tags": [str, ...]
}

规则：
1. relevance_score 反映与课题关键词的契合度。
2. reading_priority 综合考虑相关性 + 论文是否提出新方法/重要 benchmark。
3. why_read 一句话告诉用户"为什么这篇值得读"。
4. tags 是 2-5 个简短标签（如：survey, baseline, sota, new-method）。
5. 直接输出 JSON，不要包 markdown。
"""


def _select_chunks_for_briefing(db: Session, document_id: int, max_chunks: int = 18) -> list[Chunk]:
    """Pick representative chunks: abstract + intro + method + conclusion preferred."""
    chunks = (
        db.query(Chunk)
        .filter(Chunk.document_id == document_id)
        .order_by(Chunk.chunk_index.asc())
        .all()
    )
    if not chunks:
        return []
    if len(chunks) <= max_chunks:
        return chunks

    # Priority order by section_title
    pri_keywords = [
        "abstract",
        "introduction",
        "method",
        "approach",
        "experiment",
        "result",
        "conclusion",
        "limitation",
        "discussion",
    ]
    pri: list[Chunk] = []
    rest: list[Chunk] = []
    seen_titles: set[str] = set()
    for c in chunks:
        t = (c.section_title or "").lower()
        is_pri = any(k in t for k in pri_keywords)
        if is_pri:
            # Take at most 2 per section
            key = t[:20]
            count_in_pri = sum(1 for p in pri if (p.section_title or "").lower()[:20] == key)
            if count_in_pri < 2:
                pri.append(c)
                seen_titles.add(t)
                continue
        rest.append(c)
    selected = pri[:max_chunks]
    if len(selected) < max_chunks:
        selected += rest[: (max_chunks - len(selected))]
    return selected


def _safe_json_loads(text: str) -> dict[str, Any] | None:
    """Extract JSON object from possibly fenced LLM output."""
    text = text.strip()
    # strip markdown fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        # fallback: find the first {...} block
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


def generate_document_briefing(db: Session, document_id: int, language: str = "zh-CN") -> DocumentBriefing:
    """Sync: load chunks, call LLM, save briefing."""
    get_settings()
    repo = BriefingRepository(db)
    b = repo.upsert_pending(document_id, language)
    b.status = "running"
    db.flush()

    doc = db.get(Document, document_id)
    if not doc:
        repo.save_failure(b, "document missing")
        return b

    chunks = _select_chunks_for_briefing(db, document_id)
    if not chunks:
        # fallback: abstract only
        abs_text = doc.abstract or ""
        if not abs_text:
            repo.save_failure(b, "no chunks and no abstract")
            return b
        chunk_lines = [f"[0] (Abstract) {abs_text[:1500]}"]
        ids_used = [0]
    else:
        chunk_lines = []
        ids_used = []
        budget = 6000
        used = 0
        for c in chunks:
            line = f"[{c.id}] ({c.section_title or 'Body'}) {c.text[:600]}"
            if used + len(line) > budget:
                break
            chunk_lines.append(line)
            ids_used.append(c.id)
            used += len(line)

    user_block = (
        f"论文标题: {doc.title}\n"
        f"作者: {', '.join(doc.authors or [])}\n"
        f"发布日期: {doc.published_at.date() if doc.published_at else '未知'}\n"
        f"摘要: {doc.abstract or '(none)'}\n\n"
        f"文档片段（id 仅供引用使用）：\n" + "\n\n".join(chunk_lines)
    )

    llm = get_llm_client()
    try:
        raw = llm.complete(
            [
                {"role": "system", "content": _BRIEFING_SYSTEM},
                {"role": "user", "content": user_block},
            ],
            temperature=0.1,
            max_tokens=1200,
        )
    except Exception as exc:
        log.exception("LLM briefing failed for doc %s: %s", document_id, exc)
        repo.save_failure(b, str(exc))
        return b

    data = _safe_json_loads(raw)
    if not data:
        log.warning("Briefing JSON parse failed for doc %s: %s", document_id, raw[:300])
        repo.save_failure(b, "LLM JSON parse failed")
        return b

    # Filter evidence chunk ids to ones we provided
    allowed = set(ids_used)
    data["evidence_chunk_ids"] = [int(x) for x in (data.get("evidence_chunk_ids") or []) if int(x) in allowed]

    repo.save_success(b, data, model_provider=llm.cfg.provider, model_name=llm.cfg.model)
    return b


def generate_topic_document_insight(
    db: Session, topic_id: int, document_id: int
) -> None:
    """Sync: compute topic-document relevance using briefing + topic keywords.
    If relevance falls below the prune threshold, also remove the topic_documents
    association and clean the Qdrant payload — the global Document is kept."""
    topic = db.get(Topic, topic_id)
    doc = db.get(Document, document_id)
    if not topic or not doc:
        return

    briefing = BriefingRepository(db).get(document_id)
    summary = (
        briefing.one_sentence_summary
        if briefing and briefing.status == "success"
        else (doc.abstract or "")
    )
    keywords = ", ".join(topic.keywords or [])

    user_block = (
        f"研究课题: {topic.name}\n"
        f"课题关键词: {keywords}\n\n"
        f"论文标题: {doc.title}\n"
        f"论文摘要/简介: {summary[:1500]}\n"
    )
    llm = get_llm_client()
    try:
        raw = llm.complete(
            [
                {"role": "system", "content": _INSIGHT_SYSTEM},
                {"role": "user", "content": user_block},
            ],
            temperature=0.1,
            max_tokens=500,
        )
    except Exception as exc:
        log.warning("Insight LLM failed for topic=%s doc=%s: %s", topic_id, document_id, exc)
        return
    data = _safe_json_loads(raw)
    if not data:
        log.warning("Insight JSON parse failed for topic=%s doc=%s", topic_id, document_id)
        return
    TopicInsightRepository(db).upsert(topic_id, document_id, data)

    # ---- Auto-prune: irrelevant papers should not stay in the topic ----
    score = data.get("relevance_score")
    try:
        score_val = float(score) if score is not None else None
    except (TypeError, ValueError):
        score_val = None
    if score_val is not None and score_val < 0.2:
        _prune_topic_document(db, topic_id=topic_id, document_id=document_id, score=score_val)


def _prune_topic_document(db: Session, *, topic_id: int, document_id: int, score: float) -> None:
    """Remove the topic↔document association for an irrelevant paper and clean
    Qdrant payload. The global Document and Chunks remain (might be relevant to
    a different topic some day)."""
    from app.db.models.document import TopicDocument
    from app.indexer.qdrant_client import remove_topic_id_from_documents

    deleted = (
        db.query(TopicDocument)
        .filter(
            TopicDocument.topic_id == topic_id,
            TopicDocument.document_id == document_id,
        )
        .delete(synchronize_session=False)
    )
    db.flush()
    log.info(
        "Pruned topic_document (topic=%s doc=%s score=%.2f, deleted=%d)",
        topic_id, document_id, score, deleted,
    )
    try:
        remove_topic_id_from_documents([document_id], topic_id)
    except Exception as exc:
        log.warning("Qdrant prune for doc=%s topic=%s failed: %s", document_id, topic_id, exc)
