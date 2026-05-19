from __future__ import annotations

import logging
from functools import lru_cache

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.errors import UpstreamError

log = logging.getLogger(__name__)


class Embedder:
    """OpenAI-compatible embeddings client (SiliconFlow by default)."""

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        if not api_key:
            log.warning("Embedder created with empty API key; calls will fail until configured.")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    @retry(wait=wait_exponential(multiplier=1, min=1, max=10), stop=stop_after_attempt(3), reraise=True)
    def _post(self, payload: dict) -> dict:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        with httpx.Client(timeout=60.0) as c:
            resp = c.post(f"{self.base_url}/embeddings", json=payload, headers=headers)
        if resp.status_code >= 400:
            raise UpstreamError(
                f"Embedding API error {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # Split into batches to be safe; SiliconFlow accepts arrays up to ~32-64 items.
        batch_size = 16
        out: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            chunk = texts[i : i + batch_size]
            data = self._post({"model": self.model, "input": chunk, "encoding_format": "float"})
            for item in data.get("data", []):
                out.append(item["embedding"])
        return out

    def embed_query(self, text: str) -> list[float]:
        result = self.embed_texts([text])
        if not result:
            raise UpstreamError("Embedding API returned empty vector")
        return result[0]


@lru_cache
def get_embedder() -> Embedder:
    s = get_settings()
    return Embedder(base_url=s.embedding_base_url, api_key=s.siliconflow_api_key, model=s.embedding_model)
