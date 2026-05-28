"""「为你推荐」recommendation service.

Hybrid: in-corpus vector similarity (fast, exploits the already-embedded chunks
of the user's favorites) + online discovery (LLM extracts research-direction
keywords from favorite abstracts → existing discover_search runs the multi-
source fallback). Results are merged, dedupe by (source, external_id) and DOI,
then a single batched LLM call writes a ≤2 sentence rationale per item.

Cached in Redis for 6h under a fingerprint of the current favorite set so the
expensive parts (vector centroid + LLM extract + LLM rationales) don't rerun
on every page load. Cache invalidates the moment the favorite set changes
(fingerprint flips), which is the right thing for this UX.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.document import Document, TopicDocument
from app.db.models.intel import UserDocumentState
from app.db.models.topic import Topic
from app.indexer.qdrant_client import (
    fetch_vectors_for_documents,
    search_similar_to_vector,
)
from app.rag.llm_client import get_llm_client
from app.services.discover_service import discover_search
from app.services.json_llm import safe_parse_json_object
from app.services.picker_service import _redis_client

log = logging.getLogger(__name__)

_CACHE_TTL_S = 6 * 3600  # 6h — short enough that new favorites visibly shift recs


# --- Internal helpers ---


def _favorites_fingerprint(doc_ids: Sequence[int]) -> str:
    payload = ",".join(str(i) for i in sorted(doc_ids))
    return hashlib.md5(payload.encode()).hexdigest()[:16]


def _centroid(vectors: list[list[float]]) -> list[float] | None:
    if not vectors:
        return None
    dim = len(vectors[0])
    total = [0.0] * dim
    for v in vectors:
        if len(v) != dim:
            continue
        for i, val in enumerate(v):
            total[i] += val
    n = len(vectors)
    return [x / n for x in total]


def _normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    s = value.strip().lower()
    s = s.removeprefix("https://doi.org/").removeprefix("http://doi.org/").removeprefix("doi:")
    return s or None


# --- Stage 1: in-corpus similarity (vector branch) ---


def _in_corpus_candidates(
    db: Session,
    *,
    user_id: int,
    favorite_doc_ids: Sequence[int],
    top_k: int = 30,
) -> list[dict[str, Any]]:
    """Find papers similar to the favorites' vector centroid, in the user's own corpus.

    Returns a list of normalized dicts ready to merge with the online branch:
    {document_id, source, external_id, title, ..., score, in_corpus=True, topic_ids}
    """
    if not favorite_doc_ids:
        return []
    # Pull up to 8 chunks per favorited doc — keeps the centroid representative
    # without exploding memory when a user has many favorites.
    vecs_by_doc = fetch_vectors_for_documents(favorite_doc_ids, max_per_doc=8)
    all_vecs: list[list[float]] = [v for vs in vecs_by_doc.values() for v in vs]
    centroid = _centroid(all_vecs)
    if centroid is None:
        return []

    points = search_similar_to_vector(
        query_vector=centroid,
        exclude_document_ids=favorite_doc_ids,
        top_k=top_k * 3,  # we'll filter by user-visibility, so over-pull
    )

    # Group by document_id, take each doc's best chunk score
    best_by_doc: dict[int, float] = {}
    for p in points:
        doc_id = int((p.payload or {}).get("document_id") or 0)
        if not doc_id:
            continue
        score = float(p.score or 0.0)
        if score > best_by_doc.get(doc_id, -1.0):
            best_by_doc[doc_id] = score

    if not best_by_doc:
        return []

    # Verify visibility: only docs in this user's topics. (Single SQL join.)
    rr = db.execute(
        select(Document, TopicDocument.topic_id)
        .join(TopicDocument, TopicDocument.document_id == Document.id)
        .join(Topic, Topic.id == TopicDocument.topic_id)
        .where(
            Topic.user_id == user_id,
            Document.id.in_(list(best_by_doc.keys())),
        )
    )
    visible: dict[int, dict[str, Any]] = {}
    for doc, topic_id in rr.all():
        if doc.id not in visible:
            meta = doc.metadata_json or {}
            visible[doc.id] = {
                "document_id": doc.id,
                "source": doc.source,
                "external_id": doc.external_id,
                "title": doc.title,
                "authors": list(doc.authors or []),
                "published_at": doc.published_at,
                "url": doc.url,
                "abstract": doc.abstract,
                "score": best_by_doc[doc.id],
                "in_corpus": True,
                "topic_ids": [],
                "doi": _normalize_doi((meta.get("doi") if isinstance(meta, dict) else None)),
            }
        visible[doc.id]["topic_ids"].append(topic_id)

    out = list(visible.values())
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:top_k]


# --- Stage 2: online discovery (keyword branch) ---


def _extract_directions(favorite_titles: list[str], favorite_abstracts: list[str]) -> list[str]:
    """LLM extracts 3-5 English keyword phrases capturing the user's research interests.

    These then drive the existing discover_search to surface fresh papers from
    arxiv/openalex/SS. Pure ASCII to keep arxiv usable; degrades gracefully to
    [] on any LLM failure (we just skip the online branch).
    """
    if not favorite_titles:
        return []
    abstracts_blurb = "\n\n".join(
        f"[{i + 1}] {t}\n{(a or '')[:500]}"
        for i, (t, a) in enumerate(zip(favorite_titles, favorite_abstracts, strict=False))
    )
    prompt = (
        "Below are titles + abstracts of papers a researcher has starred. "
        "Identify the 3 to 5 most specific research directions or methods they "
        "care about. Output STRICTLY a JSON object with key 'keywords' whose "
        'value is a JSON array of short English phrases (each 2-5 words). No commentary.\n\n'
        f"PAPERS:\n{abstracts_blurb}\n\n"
        'Example output: {"keywords": ["contextual retrieval", "self-RAG", "graph RAG"]}'
    )
    try:
        raw = get_llm_client().complete(
            messages=[
                {"role": "system", "content": "You are a research librarian. Return STRICT JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=200,
            feature="reco_keyword_extract",
        )
    except Exception as exc:
        log.warning("recommendation keyword-extract failed: %s", exc)
        return []
    parsed = safe_parse_json_object(raw, fallback={"keywords": []})
    kws = parsed.get("keywords") or []
    if not isinstance(kws, list):
        return []
    cleaned: list[str] = []
    for k in kws:
        if isinstance(k, str) and 2 <= len(k.strip()) <= 80:
            cleaned.append(k.strip())
    return cleaned[:5]


def _online_candidates(
    favorite_titles: list[str],
    favorite_abstracts: list[str],
    *,
    seen_doi: set[str],
    seen_source_ext: set[tuple[str, str]],
    limit: int = 20,
) -> list[dict[str, Any]]:
    keywords = _extract_directions(favorite_titles, favorite_abstracts)
    if not keywords:
        return []
    docs, _rate_limited = discover_search(
        keywords=keywords,
        sources=None,
        limit=limit,
        days=180,  # only show recent — older papers more likely already in corpus
        user_query=", ".join(keywords),
    )
    out: list[dict[str, Any]] = []
    for d in docs:
        key = (d.source, d.external_id)
        doi = _normalize_doi(d.metadata.get("doi") if d.metadata else None)
        if key in seen_source_ext:
            continue
        if doi and doi in seen_doi:
            continue
        seen_source_ext.add(key)
        if doi:
            seen_doi.add(doi)
        out.append(
            {
                "document_id": None,
                "source": d.source,
                "external_id": d.external_id,
                "title": d.title,
                "authors": list(d.authors or []),
                "published_at": d.published_at,
                "url": d.url,
                "abstract": d.abstract,
                "score": float(d.metadata.get("rerank_score") or 0.0) if d.metadata else 0.0,
                "in_corpus": False,
                "topic_ids": [],
                "doi": doi,
            }
        )
    return out


# --- Stage 3: batched LLM rationales ---


def _generate_rationales(
    favorite_titles: list[str],
    candidates: list[dict[str, Any]],
) -> dict[int, str]:
    """One LLM call → up to N rationales. Returns {index: rationale}.

    Doing this in a single shot trades a slightly longer prompt for an O(1)
    instead of O(N) LLM call count. Empty / unparseable response degrades to
    no rationales (cards still render, just without the highlight box).
    """
    if not candidates:
        return {}
    favs_blurb = "\n".join(f"- {t}" for t in favorite_titles[:10])
    cands_blurb = "\n".join(
        f"[{i}] {c['title']} (abstract: {(c.get('abstract') or '')[:300]})"
        for i, c in enumerate(candidates)
    )
    prompt = (
        "The user has starred these papers (representing their research interests):\n"
        f"{favs_blurb}\n\n"
        "For each candidate paper below, write ONE Chinese sentence (≤ 35 字) "
        "explaining concretely why it might interest the user — reference a "
        "specific concept, method, or starred paper. Do NOT write generic praise.\n\n"
        f"CANDIDATES:\n{cands_blurb}\n\n"
        'Return STRICTLY a JSON object: {"rationales": {"0": "...", "1": "...", ...}}'
    )
    try:
        raw = get_llm_client().complete(
            messages=[
                {"role": "system", "content": "You are a personal research librarian. Return STRICT JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=900,
            feature="reco_rationale_batch",
        )
    except Exception as exc:
        log.warning("recommendation rationale batch failed: %s", exc)
        return {}
    parsed = safe_parse_json_object(raw, fallback={"rationales": {}})
    rats = parsed.get("rationales") or {}
    if not isinstance(rats, dict):
        return {}
    out: dict[int, str] = {}
    for k, v in rats.items():
        try:
            idx = int(k)
        except (TypeError, ValueError):
            continue
        if isinstance(v, str) and v.strip():
            out[idx] = v.strip()[:200]
    return out


# --- Public entry point ---


def get_recommendations_for_user(
    db: Session,
    *,
    user_id: int,
    limit: int = 10,
    refresh: bool = False,
) -> dict[str, Any]:
    """Top-level entry. Caller is a sync FastAPI route using the sync session."""
    # 1. Fetch favorites (latest 50 — beyond that the centroid stops shifting).
    rr = db.execute(
        select(UserDocumentState.document_id)
        .where(
            UserDocumentState.user_id == user_id,
            UserDocumentState.favorite.is_(True),
        )
        .order_by(UserDocumentState.last_opened_at.desc().nulls_last())
        .limit(50)
    )
    fav_doc_ids = [int(r) for (r,) in rr.all()]
    favorites_count = len(fav_doc_ids)

    fingerprint = _favorites_fingerprint(fav_doc_ids)
    cache_key = f"reco:v1:{user_id}:{fingerprint}:n={limit}"

    cli = _redis_client()
    if cli is not None and not refresh and favorites_count > 0:
        try:
            hit = cli.get(cache_key)
            if hit:
                blob = json.loads(hit)
                blob["cached"] = True
                return blob
        except Exception as exc:
            log.warning("reco cache read failed: %s", exc)

    if favorites_count == 0:
        return {
            "items": [],
            "favorites_count": 0,
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "cached": False,
        }

    # 2. Load favorite metadata (titles + abstracts for LLM, ids for centroid).
    rr = db.execute(select(Document).where(Document.id.in_(fav_doc_ids)))
    fav_docs = list(rr.scalars().all())
    fav_titles = [d.title or "" for d in fav_docs]
    fav_abstracts = [d.abstract or "" for d in fav_docs]

    # 3. Two-branch candidates.
    in_corpus = _in_corpus_candidates(
        db, user_id=user_id, favorite_doc_ids=fav_doc_ids, top_k=max(limit * 2, 15)
    )
    seen_source_ext = {(c["source"], c["external_id"]) for c in in_corpus}
    seen_doi: set[str] = {c["doi"] for c in in_corpus if c.get("doi")}
    online = _online_candidates(
        fav_titles,
        fav_abstracts,
        seen_doi=seen_doi,
        seen_source_ext=seen_source_ext,
        limit=max(limit, 15),
    )

    # 4. Interleave: prefer in-corpus first (lower latency to access, higher
    # signal), then top online picks. Cap at `limit`.
    merged: list[dict[str, Any]] = []
    a, b = iter(in_corpus), iter(online)
    while len(merged) < limit:
        added = False
        for it in (next(a, None), next(b, None)):
            if it is None:
                continue
            merged.append(it)
            added = True
            if len(merged) >= limit:
                break
        if not added:
            break

    # 5. Batched LLM rationales.
    rationales = _generate_rationales(fav_titles, merged)
    for i, item in enumerate(merged):
        item["rationale"] = rationales.get(i)

    payload = {
        "items": [_serialize_item(it) for it in merged],
        "favorites_count": favorites_count,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "cached": False,
    }

    if cli is not None:
        try:
            cli.setex(cache_key, _CACHE_TTL_S, json.dumps(payload, ensure_ascii=False, default=str))
        except Exception as exc:
            log.warning("reco cache write failed: %s", exc)

    return payload


def _serialize_item(it: dict[str, Any]) -> dict[str, Any]:
    """Normalize Document.published_at (datetime) → ISO string for JSON."""
    pub = it.get("published_at")
    if isinstance(pub, datetime):
        pub_s: str | None = pub.isoformat()
    else:
        pub_s = pub if isinstance(pub, str) else None
    return {
        "source": it["source"],
        "external_id": it["external_id"],
        "title": it["title"],
        "authors": it.get("authors") or [],
        "published_at": pub_s,
        "url": it.get("url"),
        "abstract": it.get("abstract"),
        "score": it.get("score"),
        "rationale": it.get("rationale"),
        "in_corpus": bool(it.get("in_corpus")),
        "document_id": it.get("document_id"),
        "topic_ids": list(it.get("topic_ids") or []),
    }


