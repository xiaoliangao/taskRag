"""Inject a curated set of arXiv papers directly into the ingest pipeline.

This bypasses the arXiv search API (which can be heavily rate-limited from
some IP ranges) and pulls PDFs straight from arxiv.org/pdf/<id>, which is
served from a different rate-limit pool.

Usage:
    docker cp scripts/inject_demo_papers.py task_rag-backend-1:/app/inject_demo_papers.py
    docker compose exec backend python /app/inject_demo_papers.py
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/app")

from app.collectors.base import RawDocument  # noqa: E402
from app.core.constants import SourceType  # noqa: E402
from app.db.models.topic import Topic  # noqa: E402
from app.db.models.user import User  # noqa: E402
from app.db.session import get_sync_sessionmaker  # noqa: E402
from app.indexer.ingest_service import ingest_raw_document  # noqa: E402
from app.indexer.qdrant_client import ensure_collection  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# Curated, well-known papers per topic. arXiv IDs picked for stability.
PAPER_SETS: dict[str, list[dict]] = {
    "Stereo Matching": [
        {
            "external_id": "2109.07547",
            "title": "RAFT-Stereo: Multilevel Recurrent Field Transforms for Stereo Matching",
            "authors": ["Lahav Lipson", "Zachary Teed", "Jia Deng"],
            "published_at": "2021-09-15T00:00:00Z",
            "abstract": (
                "We introduce RAFT-Stereo, a new deep architecture for rectified stereo "
                "based on the optical flow network RAFT. We introduce multi-level convolutional "
                "GRUs, which more efficiently propagate information across the image."
            ),
            "keyword": "stereo matching",
        },
        {
            "external_id": "2303.16958",
            "title": "Iterative Geometry Encoding Volume for Stereo Matching",
            "authors": ["Gangwei Xu", "Xianqi Wang", "Xiaohuan Ding", "Xin Yang"],
            "published_at": "2023-03-29T00:00:00Z",
            "abstract": (
                "Recurrent All-Pairs Field Transforms (RAFT) has shown great potentials in "
                "matching tasks. However, all-pairs correlations lack non-local geometry knowledge. "
                "In this paper, we propose Iterative Geometry Encoding Volume (IGEV-Stereo)."
            ),
            "keyword": "stereo matching",
        },
        {
            "external_id": "2407.18443",
            "title": "Selective-Stereo: Adaptive Frequency Information Selection for Stereo Matching",
            "authors": ["Xianqi Wang", "Gangwei Xu", "Hao Jia", "Xin Yang"],
            "published_at": "2024-04-01T00:00:00Z",
            "abstract": (
                "Stereo matching methods based on iterative optimization, like RAFT-Stereo and "
                "IGEV-Stereo, have evolved into a cornerstone in the field of stereo matching. "
                "However, these methods struggle to capture high-frequency information."
            ),
            "keyword": "transformer stereo",
        },
    ],
    "RAG": [
        {
            "external_id": "2005.11401",
            "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
            "authors": ["Patrick Lewis", "Ethan Perez", "Aleksandra Piktus"],
            "published_at": "2020-05-22T00:00:00Z",
            "abstract": (
                "Large pre-trained language models have been shown to store factual knowledge "
                "in their parameters. We explore a general-purpose fine-tuning recipe for "
                "retrieval-augmented generation (RAG) — models which combine pre-trained "
                "parametric and non-parametric memory for language generation."
            ),
            "keyword": "retrieval augmented generation",
        },
        {
            "external_id": "2312.10997",
            "title": "Retrieval-Augmented Generation for Large Language Models: A Survey",
            "authors": ["Yunfan Gao", "Yun Xiong", "Xinyu Gao"],
            "published_at": "2023-12-18T00:00:00Z",
            "abstract": (
                "Large Language Models (LLMs) demonstrate significant capabilities but face "
                "challenges such as hallucination, outdated knowledge, and non-transparent "
                "reasoning. Retrieval-Augmented Generation (RAG) has emerged as a promising "
                "solution."
            ),
            "keyword": "RAG",
        },
        {
            "external_id": "2401.18059",
            "title": "RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval",
            "authors": ["Parth Sarthi", "Salman Abdullah", "Aditi Tuli"],
            "published_at": "2024-01-31T00:00:00Z",
            "abstract": (
                "Retrieval-augmented language models can better adapt to changes in world state "
                "and incorporate long-tail knowledge. However, most existing methods retrieve "
                "only short contiguous chunks. We introduce a novel approach, RAPTOR, which "
                "recursively clusters and summarizes chunks of text bottom-up."
            ),
            "keyword": "reranking",
        },
    ],
    "Diffusion Models": [
        {
            "external_id": "2006.11239",
            "title": "Denoising Diffusion Probabilistic Models",
            "authors": ["Jonathan Ho", "Ajay Jain", "Pieter Abbeel"],
            "published_at": "2020-06-19T00:00:00Z",
            "abstract": (
                "We present high quality image synthesis results using diffusion probabilistic "
                "models, a class of latent variable models inspired by considerations from "
                "nonequilibrium thermodynamics."
            ),
            "keyword": "denoising diffusion",
        },
        {
            "external_id": "2112.10752",
            "title": "High-Resolution Image Synthesis with Latent Diffusion Models",
            "authors": ["Robin Rombach", "Andreas Blattmann", "Dominik Lorenz"],
            "published_at": "2021-12-20T00:00:00Z",
            "abstract": (
                "By decomposing the image formation process into a sequential application of "
                "denoising autoencoders, diffusion models (DMs) achieve state-of-the-art "
                "synthesis results on image data. We apply them in the latent space of "
                "powerful pretrained autoencoders."
            ),
            "keyword": "diffusion model",
        },
        {
            "external_id": "2208.01618",
            "title": "An Image is Worth One Word: Personalizing Text-to-Image Generation",
            "authors": ["Rinon Gal", "Yuval Alaluf", "Yuval Atzmon"],
            "published_at": "2022-08-02T00:00:00Z",
            "abstract": (
                "Text-to-image models offer unprecedented freedom to guide creation through "
                "natural language. We present a simple approach that allows such creative "
                "freedom by personalizing text-to-image generation."
            ),
            "keyword": "text to image",
        },
    ],
}


def inject() -> None:
    ensure_collection()
    Session = get_sync_sessionmaker()
    with Session() as db:
        user = db.query(User).filter(User.email == "demo@example.com").first()
        if not user:
            log.error("Demo user missing. Run seed_demo.py first.")
            return

        for topic_name, papers in PAPER_SETS.items():
            topic = db.query(Topic).filter(Topic.user_id == user.id, Topic.name == topic_name).first()
            if not topic:
                log.warning("Topic %s missing for demo user, skipping", topic_name)
                continue
            log.info("=== Injecting %d papers into Topic %s (id=%s) ===", len(papers), topic_name, topic.id)
            for p in papers:
                raw = RawDocument(
                    source=SourceType.ARXIV.value,
                    external_id=p["external_id"],
                    title=p["title"],
                    authors=p["authors"],
                    published_at=datetime.fromisoformat(p["published_at"].replace("Z", "+00:00")),
                    url=f"https://arxiv.org/abs/{p['external_id']}",
                    abstract=p["abstract"],
                    raw_content_url=f"https://arxiv.org/pdf/{p['external_id']}",
                    matched_keyword=p["keyword"],
                    metadata={"pdf_url": f"https://arxiv.org/pdf/{p['external_id']}", "categories": []},
                )
                try:
                    result = ingest_raw_document(db=db, topic_id=topic.id, raw=raw)
                    db.commit()
                    flag = "NEW" if result.new else "REUSED" if result.reused else "SKIPPED"
                    log.info("  [%s] %s — %s", flag, p["external_id"], p["title"][:80])
                except Exception as exc:
                    db.rollback()
                    log.exception("  [FAIL] %s — %s", p["external_id"], exc)

    log.info("Injection complete.")


if __name__ == "__main__":
    inject()
