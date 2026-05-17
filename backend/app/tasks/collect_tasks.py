from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.collectors.base import CollectorRateLimitedError, dedupe_raw_docs
from app.collectors.registry import get_collector, get_fallback_sources
from app.core.config import get_settings
from app.core.constants import CollectionTrigger, TaskStatus
from app.db.models.notification import Notification
from app.db.models.task import CollectionTask
from app.db.models.topic import Topic, TopicSourceState
from app.db.session import get_sync_sessionmaker
from app.indexer.ingest_service import ingest_raw_document
from app.tasks.celery_app import celery_app

log = logging.getLogger(__name__)


def _search_with_fallback(
    *,
    primary_source: str,
    keywords: list[str],
    since: datetime,
    max_results: int,
) -> list:
    """Try primary collector; on CollectorRateLimitedError, walk the fallback
    chain. Re-raises CollectorRateLimitedError if every source is rate-limited
    and no docs were obtained anywhere."""
    chain = [primary_source] + get_fallback_sources(primary_source)
    last_exc: CollectorRateLimitedError | None = None
    aggregate: list = []
    for src in chain:
        collector = get_collector(src)
        try:
            docs = collector.search(keywords, since, max_results)
            if docs:
                aggregate.extend(docs)
                # If primary returned something, no need to call fallbacks.
                if src == primary_source:
                    return dedupe_raw_docs(aggregate)
            # otherwise (no docs but no exception) keep trying fallback for empty primary
        except CollectorRateLimitedError as exc:
            log.warning("Source %s rate-limited (%s); trying fallback if any", src, exc.detail)
            last_exc = exc
            continue
        except Exception as exc:
            log.warning("Source %s search error: %s", src, exc)
            continue
    if aggregate:
        return dedupe_raw_docs(aggregate)
    if last_exc:
        raise last_exc
    return []


def _resolve_since(topic: Topic, source: str, trigger: str, source_state: TopicSourceState | None) -> datetime:
    now = datetime.now(tz=timezone.utc)
    if trigger == CollectionTrigger.BACKFILL.value:
        return now - timedelta(days=get_settings().backfill_days)
    if source_state and source_state.last_success_at:
        # Add small overlap for safety
        return source_state.last_success_at - timedelta(hours=1)
    # No prior state: behave like a small backfill
    return now - timedelta(days=get_settings().backfill_days)


@celery_app.task(name="app.tasks.collect_tasks.collect_topic_source_task", bind=True)
def collect_topic_source_task(
    self,
    *,
    topic_id: int,
    source: str,
    trigger: str,
    requested_by_user_id: int | None = None,
    collection_task_id: int | None = None,
) -> dict:
    Session = get_sync_sessionmaker()
    with Session() as db:
        topic = db.get(Topic, topic_id)
        if not topic:
            log.warning("collect_topic_source_task: topic %s missing", topic_id)
            return {"status": "skipped", "reason": "topic_missing"}

        # Get or create CollectionTask row
        if collection_task_id:
            task_row = db.get(CollectionTask, collection_task_id)
        else:
            task_row = CollectionTask(
                topic_id=topic_id,
                source=source,
                trigger=trigger,
                status=TaskStatus.PENDING.value,
                requested_by_user_id=requested_by_user_id,
            )
            db.add(task_row)
            db.flush()

        task_row.status = TaskStatus.RUNNING.value
        task_row.started_at = datetime.now(tz=timezone.utc)
        db.commit()

        state = (
            db.query(TopicSourceState)
            .filter(TopicSourceState.topic_id == topic_id, TopicSourceState.source == source)
            .first()
        )
        if not state:
            state = TopicSourceState(topic_id=topic_id, source=source)
            db.add(state)
            db.flush()

        since = _resolve_since(topic, source, trigger, state)

        # ---- progress helper ----
        def _set_progress(step: str, **extra) -> None:
            meta = dict(task_row.metadata_json or {})
            meta["progress"] = {"step": step, **(meta.get("progress") or {}), **extra}
            task_row.metadata_json = meta
            db.commit()

        new_count = reused_count = skipped_count = 0
        intel_doc_ids: list[tuple[int, bool, bool]] = []  # (doc_id, briefing_needed, insight_needed)
        # First-time backfill pulls more papers from a wider window;
        # ongoing collections stay small per the user's per-topic config.
        effective_max = (
            get_settings().backfill_max_results
            if trigger == CollectionTrigger.BACKFILL.value
            else topic.max_results_per_source_per_run
        )
        try:
            _set_progress("searching", total=0, processed=0)
            raw_docs = _search_with_fallback(
                primary_source=source,
                keywords=topic.keywords,
                since=since,
                max_results=effective_max,
            )
            total = len(raw_docs)
            _set_progress("ingesting", total=total, processed=0)
            for idx, raw in enumerate(raw_docs):
                _set_progress(
                    "ingesting",
                    total=total,
                    processed=idx,
                    current_doc=f"{raw.source}:{raw.external_id}",
                    current_title=raw.title[:80],
                )
                try:
                    result = ingest_raw_document(
                        db=db,
                        topic_id=topic_id,
                        raw=raw,
                        collection_task_id=task_row.id,
                    )
                    if result.new:
                        new_count += 1
                    elif result.reused:
                        reused_count += 1
                    elif result.skipped:
                        skipped_count += 1
                    if result.document_id and (result.new or result.newly_associated):
                        intel_doc_ids.append(
                            (result.document_id, result.new, result.newly_associated)
                        )
                    db.commit()
                    _set_progress(
                        "ingesting",
                        total=total,
                        processed=idx + 1,
                        new=new_count,
                        reused=reused_count,
                        skipped=skipped_count,
                    )
                except Exception as exc:
                    db.rollback()
                    log.warning("ingest failed for %s/%s: %s", raw.source, raw.external_id, exc)
                    skipped_count += 1
                    _set_progress(
                        "ingesting",
                        total=total,
                        processed=idx + 1,
                        new=new_count,
                        reused=reused_count,
                        skipped=skipped_count,
                        last_error=str(exc)[:120],
                    )

            _set_progress("done", total=total, processed=total,
                          new=new_count, reused=reused_count, skipped=skipped_count)

            now = datetime.now(tz=timezone.utc)
            state.last_fetched_at = now
            state.last_success_at = now
            state.last_error_at = None
            state.last_error_msg = None
            task_row.status = TaskStatus.SUCCESS.value
            task_row.finished_at = now
            task_row.new_docs_count = new_count
            task_row.reused_docs_count = reused_count
            task_row.skipped_docs_count = skipped_count
            db.commit()

            # Dispatch intelligence tasks for newly ingested / newly associated docs
            try:
                from app.tasks.intel_tasks import (
                    generate_document_briefing_task,
                    generate_topic_document_insight_task,
                )

                for doc_id, need_briefing, need_insight in intel_doc_ids:
                    if need_briefing:
                        generate_document_briefing_task.apply_async(
                            kwargs=dict(document_id=doc_id), queue="intelligence"
                        )
                    if need_insight:
                        generate_topic_document_insight_task.apply_async(
                            kwargs=dict(topic_id=topic_id, document_id=doc_id),
                            queue="intelligence",
                            countdown=5,
                        )
            except Exception as exc:
                log.warning("Failed to dispatch intel tasks: %s", exc)

            # Emit notification
            _emit_notification(
                db,
                user_id=topic.user_id,
                type_="task_done",
                title=f"采集完成：{topic.name}",
                body=f"{source} 新增 {new_count} 篇，复用 {reused_count} 篇，跳过 {skipped_count} 篇",
                payload={
                    "topic_id": topic_id,
                    "task_id": task_row.id,
                    "source": source,
                    "new_docs_count": new_count,
                    "reused_docs_count": reused_count,
                    "skipped_docs_count": skipped_count,
                },
            )
            return {
                "status": "success",
                "new": new_count,
                "reused": reused_count,
                "skipped": skipped_count,
            }
        except CollectorRateLimitedError as exc:
            db.rollback()
            log.warning("All sources rate-limited for topic=%s source=%s: %s", topic_id, source, exc)
            now = datetime.now(tz=timezone.utc)
            state.last_fetched_at = now
            state.last_error_at = now
            state.last_error_msg = f"rate limited: {exc.detail}"[:1000]
            task_row.status = TaskStatus.FAILED.value
            task_row.finished_at = now
            task_row.error_msg = (
                f"{exc.source} 限流（已尝试 fallback 仍失败）。建议 30-60 分钟后重试。"
            )[:2000]
            db.commit()
            _emit_notification(
                db,
                user_id=topic.user_id,
                type_="task_failed",
                title=f"采集被限流：{topic.name}",
                body=(
                    f"{source} 数据源临时限流（备用源也不可用）。"
                    "已记录失败，可在任务记录页稍后重试。"
                ),
                payload={
                    "topic_id": topic_id,
                    "task_id": task_row.id,
                    "source": source,
                    "reason": "rate_limited",
                },
            )
            return {"status": "failed", "error": "rate_limited"}
        except Exception as exc:
            db.rollback()
            log.exception("collect_topic_source_task failed: %s", exc)
            now = datetime.now(tz=timezone.utc)
            state.last_fetched_at = now
            state.last_error_at = now
            state.last_error_msg = str(exc)[:1000]
            task_row.status = TaskStatus.FAILED.value
            task_row.finished_at = now
            task_row.error_msg = str(exc)[:2000]
            db.commit()
            _emit_notification(
                db,
                user_id=topic.user_id,
                type_="task_failed",
                title=f"采集失败：{topic.name}",
                body=f"{source}: {str(exc)[:200]}",
                payload={"topic_id": topic_id, "task_id": task_row.id, "source": source},
            )
            return {"status": "failed", "error": str(exc)}


@celery_app.task(name="app.tasks.collect_tasks.ingest_picked_documents_task")
def ingest_picked_documents_task(
    *,
    topic_id: int,
    picks: list[dict],
    collection_task_id: int,
    requested_by_user_id: int | None = None,
) -> dict:
    """Ingest a user-selected list of RawDocument-like dicts (from the picker UI)."""
    from app.collectors.base import RawDocument
    from app.indexer.ingest_service import ingest_raw_document

    Session = get_sync_sessionmaker()
    with Session() as db:
        task_row = db.get(CollectionTask, collection_task_id)
        if not task_row:
            return {"status": "skipped"}

        def _set_progress(step: str, **extra) -> None:
            meta = dict(task_row.metadata_json or {})
            meta["progress"] = {"step": step, **(meta.get("progress") or {}), **extra}
            task_row.metadata_json = meta
            db.commit()

        task_row.status = TaskStatus.RUNNING.value
        task_row.started_at = datetime.now(tz=timezone.utc)
        db.commit()

        total = len(picks)
        _set_progress("ingesting", total=total, processed=0)

        new_count = reused_count = skipped_count = 0
        intel_doc_ids: list[tuple[int, bool, bool]] = []

        for idx, pick in enumerate(picks):
            try:
                raw = RawDocument(**pick)
            except Exception as exc:
                log.warning("invalid pick %s: %s", pick.get("external_id"), exc)
                skipped_count += 1
                _set_progress(
                    "ingesting",
                    total=total,
                    processed=idx + 1,
                    new=new_count,
                    reused=reused_count,
                    skipped=skipped_count,
                    last_error=str(exc)[:120],
                )
                continue
            _set_progress(
                "ingesting",
                total=total,
                processed=idx,
                current_doc=f"{raw.source}:{raw.external_id}",
                current_title=raw.title[:80],
            )
            try:
                result = ingest_raw_document(
                    db=db, topic_id=topic_id, raw=raw, collection_task_id=task_row.id
                )
                if result.new:
                    new_count += 1
                elif result.reused:
                    reused_count += 1
                elif result.skipped:
                    skipped_count += 1
                if result.document_id and (result.new or result.newly_associated):
                    intel_doc_ids.append(
                        (result.document_id, result.new, result.newly_associated)
                    )
                db.commit()
            except Exception as exc:
                db.rollback()
                log.warning("ingest pick failed: %s", exc)
                skipped_count += 1
            _set_progress(
                "ingesting",
                total=total,
                processed=idx + 1,
                new=new_count,
                reused=reused_count,
                skipped=skipped_count,
            )

        now = datetime.now(tz=timezone.utc)
        task_row.status = TaskStatus.SUCCESS.value
        task_row.finished_at = now
        task_row.new_docs_count = new_count
        task_row.reused_docs_count = reused_count
        task_row.skipped_docs_count = skipped_count
        db.commit()
        _set_progress(
            "done",
            total=total,
            processed=total,
            new=new_count,
            reused=reused_count,
            skipped=skipped_count,
        )

        try:
            from app.tasks.intel_tasks import (
                generate_document_briefing_task,
                generate_topic_document_insight_task,
            )

            for doc_id, need_briefing, need_insight in intel_doc_ids:
                if need_briefing:
                    generate_document_briefing_task.apply_async(
                        kwargs=dict(document_id=doc_id), queue="intelligence"
                    )
                if need_insight:
                    generate_topic_document_insight_task.apply_async(
                        kwargs=dict(topic_id=topic_id, document_id=doc_id),
                        queue="intelligence",
                        countdown=5,
                    )
        except Exception as exc:
            log.warning("failed to dispatch intel tasks for picked: %s", exc)

        topic = db.get(Topic, topic_id)
        if topic:
            _emit_notification(
                db,
                user_id=topic.user_id,
                type_="task_done",
                title=f"已入库 {new_count} 篇：{topic.name}",
                body=f"手动选择入库 {new_count} 新 / 复用 {reused_count} / 跳过 {skipped_count}",
                payload={
                    "topic_id": topic_id,
                    "task_id": task_row.id,
                    "source": "manual_pick",
                },
            )
        return {
            "status": "success",
            "new": new_count,
            "reused": reused_count,
            "skipped": skipped_count,
        }


@celery_app.task(name="app.tasks.collect_tasks.backfill_topic_task")
def backfill_topic_task(topic_id: int) -> dict:
    Session = get_sync_sessionmaker()
    dispatched: list[int] = []
    with Session() as db:
        topic = db.get(Topic, topic_id)
        if not topic:
            return {"status": "skipped", "reason": "topic_missing"}
        for source in topic.sources:
            task_row = CollectionTask(
                topic_id=topic_id,
                source=source,
                trigger=CollectionTrigger.BACKFILL.value,
                status=TaskStatus.PENDING.value,
            )
            db.add(task_row)
            db.flush()
            dispatched.append(task_row.id)
            db.commit()
            collect_topic_source_task.apply_async(
                kwargs=dict(
                    topic_id=topic_id,
                    source=source,
                    trigger=CollectionTrigger.BACKFILL.value,
                    collection_task_id=task_row.id,
                ),
                queue="backfill",
            )
    return {"dispatched_task_ids": dispatched}


def _emit_notification(db, *, user_id: int, type_: str, title: str, body: str, payload: dict) -> None:
    """Synchronously emit a notification via the workflow. Imported lazily to avoid cycles."""
    try:
        from app.notifications.workflow import dispatch_notification_sync

        n = Notification(user_id=user_id, type=type_, title=title, body=body, payload_json=payload)
        db.add(n)
        db.flush()
        db.commit()
        dispatch_notification_sync(db, n)
    except Exception as exc:
        log.warning("notification dispatch failed: %s", exc)
