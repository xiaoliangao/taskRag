"""ReadingPathPlanner: heuristic-only stage assignment from briefings + insights."""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models.document import Document, TopicDocument
from app.db.models.intel import DocumentBriefing, ReadingPath, TopicDocumentInsight
from app.db.models.topic import Topic
from app.db.repositories.intel_repo import ReadingPathRepository

log = logging.getLogger(__name__)


_FOUNDATION_KEYWORDS = re.compile(
    r"\b(survey|review|tutorial|benchmark|baseline|introduc)", re.IGNORECASE
)
_ADVANCED_KEYWORDS = re.compile(
    r"\b(diffusion|transformer|mamba|gan|novel|hybrid|self-supervised|unified|cross-)",
    re.IGNORECASE,
)


def _stage_for(doc: Document, briefing: DocumentBriefing | None, insight: TopicDocumentInsight | None, now: datetime) -> str:
    title = doc.title or ""
    if _FOUNDATION_KEYWORDS.search(title):
        return "foundation"
    age_days = (now - doc.published_at).days if doc.published_at else None
    if age_days is not None and age_days <= 180:
        return "latest"
    if insight and insight.reading_priority == "high":
        return "core"
    if _ADVANCED_KEYWORDS.search(title):
        return "advanced"
    return "optional"


def _score_for(doc: Document, briefing: DocumentBriefing | None, insight: TopicDocumentInsight | None, now: datetime) -> float:
    rel = insight.relevance_score if insight and insight.relevance_score is not None else 0.5
    fresh = 0.5
    if doc.published_at:
        age_days = max((now - doc.published_at).days, 0)
        # 1.0 fresh < 90d, decays linearly to 0 at 5 years.
        fresh = max(0.0, 1.0 - age_days / (5 * 365))
    priority_bonus = {"high": 0.2, "medium": 0.1, "low": 0.0}.get(
        (insight.reading_priority if insight else "low") or "low", 0.0
    )
    has_briefing = 0.05 if (briefing and briefing.status == "success") else 0.0
    return rel * 0.55 + fresh * 0.25 + priority_bonus + has_briefing


def _expected_minutes(briefing: DocumentBriefing | None) -> int:
    if briefing and briefing.reading_time_minutes:
        return int(briefing.reading_time_minutes)
    return 15


def _reason_for(doc: Document, briefing: DocumentBriefing | None, insight: TopicDocumentInsight | None, stage: str) -> str:
    if insight and insight.why_read:
        return insight.why_read
    if briefing and briefing.one_sentence_summary:
        return briefing.one_sentence_summary
    if stage == "foundation":
        return "可作为该方向入门/综述/基准了解。"
    if stage == "latest":
        return "近期论文，覆盖最新进展。"
    if stage == "core":
        return "与课题相关性高，建议作为核心阅读。"
    return "相关补充，可选阅读。"


_STAGE_ORDER = ["foundation", "core", "advanced", "latest", "optional"]


def generate_reading_path(db: Session, topic_id: int, *, max_items: int = 20) -> ReadingPath | None:
    topic = db.get(Topic, topic_id)
    if not topic:
        return None

    rows = (
        db.query(TopicDocument, Document)
        .join(Document, Document.id == TopicDocument.document_id)
        .filter(TopicDocument.topic_id == topic_id)
        .all()
    )
    if not rows:
        return None

    doc_ids = [d.id for _, d in rows]
    briefings = {b.document_id: b for b in db.query(DocumentBriefing).filter(DocumentBriefing.document_id.in_(doc_ids)).all()}
    insights = {
        i.document_id: i
        for i in db.query(TopicDocumentInsight).filter(
            TopicDocumentInsight.topic_id == topic_id,
            TopicDocumentInsight.document_id.in_(doc_ids),
        ).all()
    }

    now = datetime.now(tz=UTC)
    scored: list[tuple[float, Document, DocumentBriefing | None, TopicDocumentInsight | None]] = []
    for _td, doc in rows:
        b = briefings.get(doc.id)
        i = insights.get(doc.id)
        scored.append((_score_for(doc, b, i, now), doc, b, i))

    scored.sort(key=lambda x: -x[0])
    scored = scored[:max_items]

    items: list[dict[str, Any]] = []
    for _s, doc, b, i in scored:
        stage = _stage_for(doc, b, i, now)
        items.append(
            {
                "document_id": doc.id,
                "stage": stage,
                "reason": _reason_for(doc, b, i, stage),
                "expected_minutes": _expected_minutes(b),
                "prerequisite_document_ids": [],
            }
        )

    # Sort by stage then score (preserve score order within stage)
    items.sort(key=lambda x: _STAGE_ORDER.index(x["stage"]) if x["stage"] in _STAGE_ORDER else 99)

    repo = ReadingPathRepository(db)
    p = repo.create(topic_id=topic_id, title=f"{topic.name} 阅读路径", description="按入门 → 核心 → 进阶 → 最新 → 可选 分层")
    repo.save_success(p, items)
    return p
