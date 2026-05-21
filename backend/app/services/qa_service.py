from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import ChatRole
from app.db.models.chat import ChatSession
from app.db.models.user import User
from app.db.repositories.chat_repo import ChatRepository
from app.rag.llm_client import get_llm_client
from app.rag.prompt import NO_CONTEXT_FALLBACK, build_messages
from app.rag.retriever import Citation, retrieve_for_topic

log = logging.getLogger(__name__)


@dataclass
class QAResult:
    message_id: int
    content: str
    citations: list[dict]


def _llm_for_user(user: User):
    s = get_settings()
    settings_json = user.settings_json or {}
    provider = settings_json.get("preferred_llm_provider") or s.llm_provider
    model = settings_json.get("preferred_llm_model") or s.llm_model
    return get_llm_client(provider, model)


def _history(messages: Sequence) -> list[dict]:
    return [{"role": m.role, "content": m.content} for m in messages]


async def _gather_context(
    db: AsyncSession,
    *,
    topic_id: int,
    question: str,
) -> tuple[list[Citation], list[dict]]:
    """Adaptive retrieval (Wave-3 Pkg-QR).

    The query router classifies the question into factual / comparison /
    synthesis / multi_step, then dials retrieval depth:
      - multi-query rewrite variants (1 / 2 / 3 / 3)
      - whether CRAG corrective-retry runs
      - whether GraphRAG 1-hop expansion runs
    Falls back to "synthesis" (current full pipeline) on any classifier
    failure — correctness over speed.
    """
    from app.rag.query_router import classify_query, config_for

    route = classify_query(question)
    cfg = config_for(route)
    log.info(
        "query_router route=%s variants=%d crag=%s graphrag=%s",
        route, cfg["variants"], cfg["crag"], cfg["graphrag"],
    )

    variants = [question]
    if cfg["variants"] > 1:
        try:
            from app.services.query_rewrite import generate_variants

            # generate_variants returns original + N rewrites, so request
            # one less than the total we want.
            variants = generate_variants(question, n=cfg["variants"] - 1)
        except Exception as exc:
            log.warning("query_rewrite_skipped: %s", exc)

    # Run all variants in parallel (each does BM25+vector+rerank internally).
    all_runs = await asyncio.gather(
        *[
            retrieve_for_topic(db=db, topic_id=topic_id, query=q, dedup_by_document=True)
            for q in variants
        ],
        return_exceptions=True,
    )

    best: dict[int, Citation] = {}
    for run in all_runs:
        if isinstance(run, Exception) or not run:
            continue
        for c in run:
            key = c.chunk_id or -hash(c.text)
            prev = best.get(key)
            if prev is None or c.score > prev.score:
                best[key] = c

    # Multi-query union may surface multiple chunks per document. Dedup again
    # by document_id, keeping the highest-scoring chunk per doc.
    by_doc: dict[int, Citation] = {}
    for c in sorted(best.values(), key=lambda c: c.score, reverse=True):
        if c.document_id not in by_doc:
            by_doc[c.document_id] = c

    citations = sorted(by_doc.values(), key=lambda c: c.score, reverse=True)

    settings = get_settings()

    # v1.5 B-1: CRAG reflection — if grader says "low/medium" relevance, retry
    # once with an LLM-rewritten query and merge. Router can disable this for
    # factual queries where rewriting won't help.
    if settings.crag_enabled and cfg["crag"]:
        try:
            from app.services.crag import reflective_retrieve

            citations, audit = await reflective_retrieve(
                db=db, topic_id=topic_id, question=question, initial=citations
            )
            if audit.get("rewrote"):
                log.info(
                    "crag_retry verdict=%s confidence=%.2f rewritten=%s",
                    audit.get("verdict"),
                    audit.get("confidence"),
                    audit.get("rewritten_query"),
                )
        except Exception as exc:
            log.warning("crag_skipped: %s", exc)

    # v1.5 B-2: GraphRAG — pull 1-hop neighbors of top documents via document_relations.
    # Skipped for factual queries (don't need the wider context).
    if settings.graphrag_enabled and cfg["graphrag"]:
        try:
            from app.services.graphrag import expand_with_neighbors

            citations = await expand_with_neighbors(
                db=db, topic_id=topic_id, citations=citations
            )
        except Exception as exc:
            log.warning("graphrag_skipped: %s", exc)

    citation_dicts = [c.to_dict(drop_text=False) for c in citations]
    return citations, citation_dicts


async def _gather_pinned_notes(db: AsyncSession, user_id: int, topic_id: int, limit: int = 5) -> list[dict]:
    try:
        from app.db.repositories.intel_repo import NotesAsyncRepository

        notes = await NotesAsyncRepository(db).list_recent_pinned(user_id, topic_id, limit=limit)
        return [
            {
                "title": n.title or "(笔记)",
                "content": n.content_md[:800],
                "source_type": n.source_type,
            }
            for n in notes
        ]
    except Exception:
        return []


async def _gather_user_research_context(
    db: AsyncSession, user_id: int, topic_id: int, k: int = 3
) -> str:
    """Inject recent chat-session summaries (v1.4 Sprint 7 Conversation Memory)."""
    try:
        from app.services.memory_service import (
            build_memory_block,
            list_session_summaries,
        )

        summaries = await list_session_summaries(db, user_id=user_id, topic_id=topic_id, limit=k)
        return build_memory_block(summaries)
    except Exception:  # pragma: no cover - memory must never break QA
        return ""


_SUMMARY_DISPATCH_TTL_S = 60  # min seconds between two summarize dispatches per session


def _maybe_dispatch_summary(db: AsyncSession, session_id: int) -> None:
    """Fire-and-forget Celery summarization, throttled with a Redis lock.

    Without throttling, every chat turn enqueues a Celery message that
    short-circuits inside `needs_resummary` — wasteful at scale. We hold a
    `mem:dispatch:{sid}` lock with `SETNX` for 60s so back-to-back turns
    coalesce into one job. The Celery task still re-checks `needs_resummary`,
    which is the real correctness gate; this is purely a noise reduction.
    """
    try:
        from app.tasks.research_tasks import summarize_chat_session_task

        if _should_skip_summary_dispatch(session_id):
            return
        summarize_chat_session_task.apply_async(
            kwargs={"session_id": session_id}, queue="intelligence"
        )
    except Exception:  # pragma: no cover - dispatch best-effort
        pass


def _should_skip_summary_dispatch(session_id: int) -> bool:
    """True when a dispatch happened for this session within the TTL window."""
    try:
        import redis

        cli = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
        # SET key value NX EX ttl → returns True only if the key did not exist.
        acquired = cli.set(
            f"mem:dispatch:{session_id}", "1", nx=True, ex=_SUMMARY_DISPATCH_TTL_S
        )
        return not acquired
    except Exception:
        # If Redis is unhappy we'd rather dispatch (correct but noisy) than miss.
        return False


async def answer_nonstream(
    *,
    db: AsyncSession,
    user: User,
    chat: ChatSession,
    question: str,
) -> QAResult:
    settings = get_settings()
    chats = ChatRepository(db)
    # Persist user message
    user_msg = await chats.add_message(session_id=chat.id, role=ChatRole.USER.value, content=question)
    await db.commit()

    history_msgs = await chats.recent_history(chat.id, settings.history_turns)
    # Exclude the just-added user message from history (it's already in question)
    history = _history([m for m in history_msgs if m.id != user_msg.id])

    citations, citation_dicts = await _gather_context(db, topic_id=chat.topic_id, question=question)
    if not citations:
        assistant_msg = await chats.add_message(
            session_id=chat.id,
            role=ChatRole.ASSISTANT.value,
            content=NO_CONTEXT_FALLBACK,
            citations=[],
        )
        await db.commit()
        return QAResult(message_id=assistant_msg.id, content=NO_CONTEXT_FALLBACK, citations=[])

    pinned = await _gather_pinned_notes(db, user.id, chat.topic_id)
    user_ctx = await _gather_user_research_context(db, user.id, chat.topic_id)
    messages = build_messages(
        question=question,
        chat_history=history,
        citations=citation_dicts,
        pinned_notes=pinned,
        chat_mode=getattr(chat, "mode", None),
        user_research_context=user_ctx,
    )
    llm = _llm_for_user(user)
    content = llm.complete(messages)

    public_citations = [c.to_dict(drop_text=True) for c in citations]
    assistant_msg = await chats.add_message(
        session_id=chat.id,
        role=ChatRole.ASSISTANT.value,
        content=content,
        citations=public_citations,
    )
    await db.commit()
    _maybe_dispatch_summary(db, chat.id)
    return QAResult(message_id=assistant_msg.id, content=content, citations=public_citations)


async def answer_stream(
    *,
    db: AsyncSession,
    user: User,
    chat: ChatSession,
    question: str,
) -> AsyncIterator[dict]:
    """Yields events: {"event": "token"|"citations"|"done"|"error", "data": {...}}"""
    settings = get_settings()
    chats = ChatRepository(db)

    user_msg = await chats.add_message(session_id=chat.id, role=ChatRole.USER.value, content=question)
    await db.commit()

    history_msgs = await chats.recent_history(chat.id, settings.history_turns)
    history = _history([m for m in history_msgs if m.id != user_msg.id])

    citations, citation_dicts = await _gather_context(db, topic_id=chat.topic_id, question=question)
    public_citations = [c.to_dict(drop_text=True) for c in citations]
    yield {"event": "citations", "data": {"items": public_citations}}

    if not citations:
        assistant_msg = await chats.add_message(
            session_id=chat.id,
            role=ChatRole.ASSISTANT.value,
            content=NO_CONTEXT_FALLBACK,
            citations=[],
        )
        await db.commit()
        yield {"event": "token", "data": {"text": NO_CONTEXT_FALLBACK}}
        yield {"event": "done", "data": {"message_id": assistant_msg.id}}
        return

    pinned = await _gather_pinned_notes(db, user.id, chat.topic_id)
    user_ctx = await _gather_user_research_context(db, user.id, chat.topic_id)
    messages = build_messages(
        question=question,
        chat_history=history,
        citations=citation_dicts,
        pinned_notes=pinned,
        chat_mode=getattr(chat, "mode", None),
        user_research_context=user_ctx,
    )
    llm = _llm_for_user(user)

    buffer: list[str] = []
    try:
        # OpenAI client.stream is a sync iterator; iterate in a thread-friendly manner.
        # FastAPI's StreamingResponse can consume an async generator that yields strings.
        for token in llm.stream(messages):
            buffer.append(token)
            yield {"event": "token", "data": {"text": token}}
    except Exception as exc:
        log.exception("LLM stream error: %s", exc)
        yield {"event": "error", "data": {"code": "UPSTREAM_ERROR", "message": str(exc)[:200]}}
        return

    final_content = "".join(buffer).strip()
    assistant_msg = await chats.add_message(
        session_id=chat.id,
        role=ChatRole.ASSISTANT.value,
        content=final_content,
        citations=public_citations,
    )
    await db.commit()
    _maybe_dispatch_summary(db, chat.id)
    yield {"event": "done", "data": {"message_id": assistant_msg.id}}
