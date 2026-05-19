from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable, Sequence
from functools import lru_cache
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as rest

from app.core.config import get_settings

log = logging.getLogger(__name__)


_NAMESPACE = uuid.UUID("d3b07384-d9a4-4f0c-90a1-2a3e0f0c4f0b")


@lru_cache
def get_qdrant() -> QdrantClient:
    s = get_settings()
    return QdrantClient(url=s.qdrant_url, timeout=30.0)


def stable_vector_id(source: str, external_id: str, chunk_index: int, doc_version: int = 1) -> uuid.UUID:
    name = f"{source}:{external_id}:{chunk_index}:{doc_version}"
    return uuid.uuid5(_NAMESPACE, name)


def ensure_collection() -> None:
    settings = get_settings()
    client = get_qdrant()
    name = settings.qdrant_collection
    dim = settings.embedding_dim
    try:
        collections = {c.name for c in client.get_collections().collections}
    except Exception as exc:
        log.warning("Qdrant unreachable: %s", exc)
        raise

    if name not in collections:
        client.create_collection(
            collection_name=name,
            vectors_config=rest.VectorParams(size=dim, distance=rest.Distance.COSINE),
        )
        log.info("Created Qdrant collection %s (dim=%d)", name, dim)

    # Payload indexes (idempotent)
    for field, schema in (
        ("topic_ids", rest.PayloadSchemaType.INTEGER),
        ("published_at", rest.PayloadSchemaType.DATETIME),
        ("source", rest.PayloadSchemaType.KEYWORD),
        ("document_id", rest.PayloadSchemaType.INTEGER),
    ):
        try:
            client.create_payload_index(collection_name=name, field_name=field, field_schema=schema)
        except Exception as exc:
            # Already exists or unsupported — Qdrant raises on duplicates; safe to ignore.
            log.debug("create_payload_index %s skipped: %s", field, exc)


def upsert_points(
    *,
    points: list[dict],
) -> None:
    """points: [{id, vector, payload}]"""
    settings = get_settings()
    client = get_qdrant()
    client.upsert(
        collection_name=settings.qdrant_collection,
        points=[
            rest.PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
            for p in points
        ],
    )


def add_topic_id_to_documents(document_ids: Sequence[int], topic_id: int) -> None:
    """Append topic_id into the payload.topic_ids array for all chunks of these documents."""
    if not document_ids:
        return
    settings = get_settings()
    client = get_qdrant()
    name = settings.qdrant_collection

    # Scroll all points for these documents (small N expected in demo)
    next_offset = None
    while True:
        points, next_offset = client.scroll(
            collection_name=name,
            scroll_filter=rest.Filter(
                must=[rest.FieldCondition(key="document_id", match=rest.MatchAny(any=list(document_ids)))]
            ),
            with_payload=True,
            with_vectors=False,
            limit=256,
            offset=next_offset,
        )
        if not points:
            break
        for p in points:
            existing = list((p.payload or {}).get("topic_ids") or [])
            if topic_id in existing:
                continue
            existing.append(topic_id)
            client.set_payload(
                collection_name=name,
                payload={"topic_ids": existing},
                points=[p.id],
            )
        if next_offset is None:
            break


def remove_topic_id_from_documents(document_ids: Sequence[int], topic_id: int) -> None:
    if not document_ids:
        return
    settings = get_settings()
    client = get_qdrant()
    name = settings.qdrant_collection
    next_offset = None
    while True:
        points, next_offset = client.scroll(
            collection_name=name,
            scroll_filter=rest.Filter(
                must=[rest.FieldCondition(key="document_id", match=rest.MatchAny(any=list(document_ids)))]
            ),
            with_payload=True,
            with_vectors=False,
            limit=256,
            offset=next_offset,
        )
        if not points:
            break
        for p in points:
            existing = list((p.payload or {}).get("topic_ids") or [])
            if topic_id not in existing:
                continue
            existing = [t for t in existing if t != topic_id]
            client.set_payload(
                collection_name=name,
                payload={"topic_ids": existing},
                points=[p.id],
            )
        if next_offset is None:
            break


def search_for_topic(*, topic_id: int, query_vector: list[float], top_k: int) -> list[Any]:
    return search_for_topics(topic_ids=[topic_id], query_vector=query_vector, top_k=top_k)


def search_for_topics(
    *, topic_ids: Sequence[int], query_vector: list[float], top_k: int
) -> list[Any]:
    """Cross-topic vector search. The caller MUST have already verified that
    all topic_ids belong to the current user (see Cross-topic QA route).
    """
    settings = get_settings()
    client = get_qdrant()
    if not topic_ids:
        return []
    flt = rest.Filter(
        must=[
            rest.FieldCondition(key="topic_ids", match=rest.MatchAny(any=list(topic_ids)))
        ]
    )
    response = client.query_points(
        collection_name=settings.qdrant_collection,
        query=query_vector,
        query_filter=flt,
        limit=top_k,
        with_payload=True,
    )
    return response.points


def delete_points_for_documents(document_ids: Iterable[int]) -> None:
    settings = get_settings()
    client = get_qdrant()
    client.delete(
        collection_name=settings.qdrant_collection,
        points_selector=rest.FilterSelector(
            filter=rest.Filter(
                must=[rest.FieldCondition(key="document_id", match=rest.MatchAny(any=list(document_ids)))]
            )
        ),
    )
