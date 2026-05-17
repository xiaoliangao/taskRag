from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import CollectionTrigger
from app.core.errors import DuplicateResourceError, TopicLimitExceededError
from app.db.models.topic import Topic
from app.db.models.user import User
from app.db.repositories.document_repo import TopicDocumentRepository
from app.db.repositories.task_repo import CollectionTaskRepository
from app.db.repositories.topic_repo import TopicRepository, TopicSourceStateRepository
from app.schemas.topic import TopicCreate, TopicPublic, TopicUpdate


class TopicService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.topics = TopicRepository(db)
        self.source_states = TopicSourceStateRepository(db)
        self.topic_docs = TopicDocumentRepository(db)
        self.tasks_repo = CollectionTaskRepository(db)

    async def list_for_user(self, user: User) -> list[TopicPublic]:
        topics = await self.topics.list_for_user(user.id)
        result: list[TopicPublic] = []
        for t in topics:
            doc_count = await self.topic_docs.count_for_topic(t.id)
            latest = await self.tasks_repo.latest_for_topic(t.id)
            pub = TopicPublic.model_validate(t)
            pub.document_count = doc_count
            pub.last_collected_at = latest.finished_at if latest else None
            result.append(pub)
        return result

    async def to_public(self, topic: Topic) -> TopicPublic:
        doc_count = await self.topic_docs.count_for_topic(topic.id)
        latest = await self.tasks_repo.latest_for_topic(topic.id)
        pub = TopicPublic.model_validate(topic)
        pub.document_count = doc_count
        pub.last_collected_at = latest.finished_at if latest else None
        return pub

    async def create(self, user: User, body: TopicCreate) -> Topic:
        settings = get_settings()
        count = await self.topics.count_for_user(user.id)
        if count >= settings.max_topics_per_user:
            raise TopicLimitExceededError()
        existing = await self.topics.get_by_user_and_name(user.id, body.name)
        if existing:
            raise DuplicateResourceError("Topic name already used", {"field": "name"})
        topic = await self.topics.create(
            user_id=user.id,
            name=body.name,
            description=body.description,
            keywords=body.keywords,
            sources=body.sources,
            schedule_type=body.schedule_type,
            schedule_time=body.schedule_time,
            max_results_per_source_per_run=body.max_results_per_source_per_run,
            enabled=body.enabled,
        )
        for src in body.sources:
            await self.source_states.upsert_initial(topic.id, src)
        await self.db.commit()
        await self.db.refresh(topic)

        # Trigger backfill (best-effort: import here to avoid hard celery dep in tests)
        try:
            from app.tasks.collect_tasks import backfill_topic_task

            backfill_topic_task.delay(topic.id)
        except Exception:
            pass
        return topic

    async def update(self, topic: Topic, body: TopicUpdate) -> Topic:
        fields = body.model_dump(exclude_unset=True)
        keyword_changed = "keywords" in fields and fields["keywords"] != topic.keywords
        old_sources = set(topic.sources)

        if "name" in fields and fields["name"] != topic.name:
            existing = await self.topics.get_by_user_and_name(topic.user_id, fields["name"])
            if existing and existing.id != topic.id:
                raise DuplicateResourceError("Topic name already used", {"field": "name"})

        await self.topics.update(topic, fields)

        new_sources = set(topic.sources)
        for added in new_sources - old_sources:
            await self.source_states.upsert_initial(topic.id, added)

        await self.db.commit()
        await self.db.refresh(topic)

        if keyword_changed:
            try:
                from app.tasks.collect_tasks import collect_topic_source_task

                for src in topic.sources:
                    collect_topic_source_task.apply_async(
                        kwargs=dict(
                            topic_id=topic.id,
                            source=src,
                            trigger=CollectionTrigger.KEYWORD_CHANGED.value,
                            requested_by_user_id=topic.user_id,
                        ),
                        queue="urgent",
                    )
            except Exception:
                pass
        return topic

    async def delete(self, topic: Topic) -> None:
        # Capture document ids before cascade
        doc_ids = list(await self.topic_docs.list_document_ids_for_topic(topic.id))
        topic_id = topic.id
        await self.topics.delete(topic)
        await self.db.commit()

        # Best-effort Qdrant payload cleanup (remove topic_id from chunks of these docs)
        try:
            from app.indexer.qdrant_client import remove_topic_id_from_documents

            remove_topic_id_from_documents(doc_ids, topic_id)
        except Exception:
            pass

    async def manual_collect(self, topic: Topic, requested_by_user_id: int) -> list[dict]:
        from app.tasks.collect_tasks import collect_topic_source_task

        created: list[dict] = []
        for src in topic.sources:
            task = await self.tasks_repo.create(
                topic_id=topic.id,
                source=src,
                trigger=CollectionTrigger.MANUAL.value,
                requested_by_user_id=requested_by_user_id,
            )
            created.append({"id": task.id, "source": src, "status": task.status})
        await self.db.commit()
        # Dispatch celery tasks AFTER commit so the rows are visible
        for c in created:
            try:
                collect_topic_source_task.apply_async(
                    kwargs=dict(
                        topic_id=topic.id,
                        source=c["source"],
                        trigger=CollectionTrigger.MANUAL.value,
                        requested_by_user_id=requested_by_user_id,
                        collection_task_id=c["id"],
                    ),
                    queue="urgent",
                )
            except Exception:
                pass
        return created
