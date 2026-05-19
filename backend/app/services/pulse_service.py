"""PulseService: daily Topic briefing combining new docs + briefings + insights."""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db.models.document import Document, TopicDocument
from app.db.models.intel import DocumentBriefing, TopicDocumentInsight, TopicPulse
from app.db.models.topic import Topic
from app.db.repositories.intel_repo import PulseRepository
from app.rag.llm_client import get_llm_client

log = logging.getLogger(__name__)


_PULSE_SYSTEM = """你是一个研究助手。基于当前课题最近一段时间的新增论文、结构化解读和相关性判断，
生成一份每日研究脉搏简报。输出严格 JSON：

{
  "title": str,
  "summary_md": str (3-6 句话简短 markdown 总结，可以用 - 列表),
  "highlights": [
    {"type": "new_doc"|"keyword"|"trend", "text": str, "document_id": int (optional)}
  ],
  "important_documents": [
    {"document_id": int, "title": str, "reason": str}
  ],
  "emerging_keywords": [
    {"term": str, "score": number (optional)}
  ],
  "suggested_actions": [
    {"action": "read"|"ask", "document_id": int (optional), "question": str (optional), "reason": str}
  ]
}

规则：
1. 必须严格基于提供的数据，不要编造文档 id 或标题。
2. 如果没有新增文档，simulate "无新增，建议复习" 风格。
3. summary_md 用中文；不要包裹 markdown 代码块。
4. important_documents 最多 3 个。
5. suggested_actions 最多 3 个。
"""


def _today_utc_date() -> datetime:
    now = datetime.now(tz=UTC)
    return datetime(now.year, now.month, now.day, tzinfo=UTC)


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


def generate_topic_pulse(db: Session, topic_id: int, *, force: bool = False) -> TopicPulse | None:
    today = _today_utc_date()
    repo = PulseRepository(db)
    existing = repo.get_by_date(topic_id, today)
    if existing and existing.status == "success" and not force:
        log.info("topic %s pulse for %s already exists", topic_id, today.date())
        return existing

    topic = db.get(Topic, topic_id)
    if not topic:
        return None

    p = existing or repo.upsert_pending(topic_id, today)
    p.status = "running"
    db.flush()

    # Gather corpus for the last 24h (or last 7d if no new in 24h)
    cutoff_24h = datetime.now(tz=UTC) - timedelta(hours=24)
    cutoff_7d = datetime.now(tz=UTC) - timedelta(days=7)

    recent_q = (
        db.query(TopicDocument, Document)
        .join(Document, Document.id == TopicDocument.document_id)
        .filter(TopicDocument.topic_id == topic_id)
        .filter(TopicDocument.added_at >= cutoff_24h)
        .order_by(desc(TopicDocument.added_at))
        .limit(20)
        .all()
    )
    if not recent_q:
        recent_q = (
            db.query(TopicDocument, Document)
            .join(Document, Document.id == TopicDocument.document_id)
            .filter(TopicDocument.topic_id == topic_id)
            .filter(TopicDocument.added_at >= cutoff_7d)
            .order_by(desc(TopicDocument.added_at))
            .limit(15)
            .all()
        )

    new_docs_payload: list[dict] = []
    for td, doc in recent_q:
        new_docs_payload.append(
            {
                "document_id": doc.id,
                "title": doc.title,
                "published_at": doc.published_at.date().isoformat() if doc.published_at else None,
                "matched_keyword": td.matched_keyword,
                "abstract": (doc.abstract or "")[:400],
            }
        )

    # Fetch briefings + insights for these docs
    doc_ids = [d["document_id"] for d in new_docs_payload]
    briefings: dict[int, DocumentBriefing] = {}
    insights: dict[int, TopicDocumentInsight] = {}
    if doc_ids:
        for b in db.query(DocumentBriefing).filter(DocumentBriefing.document_id.in_(doc_ids)).all():
            briefings[b.document_id] = b
        for i in db.query(TopicDocumentInsight).filter(
            TopicDocumentInsight.topic_id == topic_id,
            TopicDocumentInsight.document_id.in_(doc_ids),
        ).all():
            insights[i.document_id] = i

    enriched: list[dict] = []
    for d in new_docs_payload:
        did = d["document_id"]
        b = briefings.get(did)
        i = insights.get(did)
        enriched.append(
            {
                **d,
                "one_sentence_summary": (b.one_sentence_summary if b else None),
                "method": (b.method if b else None),
                "contributions": (b.contributions if b else []),
                "datasets": (b.datasets if b else []),
                "reading_priority": (i.reading_priority if i else None),
                "relevance_score": (i.relevance_score if i else None),
                "why_read": (i.why_read if i else None),
            }
        )

    # Simple emerging-keyword heuristic over recent titles+matched_keywords
    word_counts: Counter[str] = Counter()
    for d in enriched:
        for w in re.findall(r"[A-Za-z][A-Za-z\-]{3,}", d["title"] or ""):
            word_counts[w.lower()] += 1
        if d.get("matched_keyword"):
            word_counts[d["matched_keyword"].lower()] += 2
    emerging = [w for w, _ in word_counts.most_common(8)]

    user_block = (
        f"课题: {topic.name}\n"
        f"课题关键词: {', '.join(topic.keywords or [])}\n"
        f"今天日期: {today.date().isoformat()}\n"
        f"最近窗口内新增/相关文档（最多 20 篇）:\n"
        + json.dumps(enriched, ensure_ascii=False, indent=2)
        + "\n\n"
        f"候选关键词（按出现频次降序）: {emerging}\n\n"
        "请输出 JSON 简报。"
    )

    llm = get_llm_client()
    try:
        raw = llm.complete(
            [
                {"role": "system", "content": _PULSE_SYSTEM},
                {"role": "user", "content": user_block},
            ],
            temperature=0.3,
            max_tokens=1400,
        )
    except Exception as exc:
        log.exception("LLM pulse failed topic=%s: %s", topic_id, exc)
        repo.save_failure(p, str(exc))
        return p

    data = _safe_json(raw)
    if not data:
        log.warning("Pulse JSON parse failed topic=%s: %s", topic_id, raw[:300])
        repo.save_failure(p, "JSON parse failed")
        return p

    # Sanitize ids
    allowed_ids = {d["document_id"] for d in enriched}
    for key in ("highlights", "important_documents", "suggested_actions"):
        items = data.get(key) or []
        cleaned = []
        for item in items:
            did = item.get("document_id")
            if did is None or did in allowed_ids:
                cleaned.append(item)
        data[key] = cleaned

    data["new_documents"] = [
        {"document_id": d["document_id"], "title": d["title"]} for d in enriched
    ]

    repo.save_success(p, data, model_provider=llm.cfg.provider, model_name=llm.cfg.model)

    # Emit a notification
    try:
        from app.db.models.notification import Notification
        from app.notifications.workflow import dispatch_notification_sync

        n = Notification(
            user_id=topic.user_id,
            type="task_done",
            title=f"今日研究脉搏：{topic.name}",
            body=(p.title or "今日简报已生成"),
            payload_json={"topic_id": topic_id, "pulse_id": p.id},
        )
        db.add(n)
        db.flush()
        db.commit()
        dispatch_notification_sync(db, n)
    except Exception as exc:
        log.warning("Pulse notification failed: %s", exc)

    return p
