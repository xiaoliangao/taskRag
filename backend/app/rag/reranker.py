from __future__ import annotations

import logging
from functools import lru_cache
from typing import Sequence

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)


class Reranker:
    """Rerank client compatible with both SiliconFlow and TEI.

    - SiliconFlow: POST {base_url}/rerank
        body: {"model": "...", "query": "...", "documents": [...], "top_n": N}
        resp: {"results": [{"index": int, "relevance_score": float}, ...]}
    - TEI: POST {base_url}/rerank
        body: {"query": "...", "texts": [...]}
        resp: [{"index": int, "score": float}, ...]
    """

    def __init__(self, base_url: str, enabled: bool, model: str, api_key: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.enabled = enabled
        self.model = model
        self.api_key = api_key

    def rerank(self, query: str, passages: Sequence[str]) -> list[float] | None:
        """Returns score per passage in original order, or None if skipped/failed."""
        if not self.enabled or not passages:
            return None
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload_siliconflow = {
            "model": self.model,
            "query": query,
            "documents": list(passages),
            "top_n": len(passages),
            "return_documents": False,
        }
        try:
            with httpx.Client(timeout=20.0) as c:
                resp = c.post(f"{self.base_url}/rerank", json=payload_siliconflow, headers=headers)
            if resp.status_code >= 400:
                log.warning("Reranker returned %s: %s", resp.status_code, resp.text[:300])
                return None
            data = resp.json()
            scores = [0.0] * len(passages)
            # SiliconFlow format
            if isinstance(data, dict) and "results" in data:
                for item in data["results"]:
                    idx = item.get("index")
                    score = float(item.get("relevance_score", item.get("score", 0.0)))
                    if isinstance(idx, int) and 0 <= idx < len(scores):
                        scores[idx] = score
                return scores
            # TEI format (list of {index, score})
            if isinstance(data, list):
                for item in data:
                    idx = item.get("index")
                    score = float(item.get("score", 0.0))
                    if isinstance(idx, int) and 0 <= idx < len(scores):
                        scores[idx] = score
                return scores
            log.warning("Reranker returned unrecognized payload: %.200s", str(data))
            return None
        except Exception as exc:
            log.warning("Reranker call failed, skipping: %s", exc)
            return None


@lru_cache
def get_reranker() -> Reranker:
    s = get_settings()
    return Reranker(
        base_url=s.reranker_base_url,
        enabled=s.reranker_enabled,
        model=s.reranker_model,
        api_key=s.siliconflow_api_key,
    )
