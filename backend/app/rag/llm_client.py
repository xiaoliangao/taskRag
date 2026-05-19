from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache

from openai import OpenAI

from app.core.config import get_settings
from app.core.errors import UpstreamError

log = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    provider: str
    model: str
    base_url: str
    api_key: str


def _resolve_config(provider: str | None = None, model: str | None = None) -> LLMConfig:
    s = get_settings()
    provider = (provider or s.llm_provider).lower()
    if provider == "deepseek":
        return LLMConfig(provider, model or s.llm_model or "deepseek-chat", s.deepseek_base_url, s.deepseek_api_key)
    if provider == "qwen":
        return LLMConfig(provider, model or s.qwen_model, s.qwen_base_url, s.qwen_api_key)
    if provider == "siliconflow":
        return LLMConfig(provider, model or s.siliconflow_llm_model, s.embedding_base_url, s.siliconflow_api_key)
    if provider == "openai":
        return LLMConfig(provider, model or s.openai_model, s.openai_base_url, s.openai_api_key)
    raise UpstreamError(f"Unsupported LLM provider: {provider}")


class LLMClient:
    """OpenAI-compatible chat completion client (DeepSeek / Qwen / SiliconFlow / OpenAI)."""

    def __init__(self, cfg: LLMConfig) -> None:
        self.cfg = cfg
        if not cfg.api_key:
            log.warning("LLM client created without API key for provider=%s", cfg.provider)
        self._client = OpenAI(api_key=cfg.api_key or "missing", base_url=cfg.base_url)

    def complete(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        feature: str = "generic",
    ) -> str:
        """Synchronous chat completion. Records to llm_usage_logs."""
        from app.core.observability import track_llm_usage

        with track_llm_usage(
            feature=feature, provider=self.cfg.provider, model=self.cfg.model
        ) as ctx:
            try:
                resp = self._client.chat.completions.create(
                    model=self.cfg.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=False,
                )
            except Exception as exc:
                raise UpstreamError(f"LLM call failed: {exc}") from exc
            if not resp.choices:
                raise UpstreamError("LLM returned no choices")
            usage = getattr(resp, "usage", None)
            if usage is not None:
                ctx["prompt_tokens"] = getattr(usage, "prompt_tokens", 0) or 0
                ctx["completion_tokens"] = getattr(usage, "completion_tokens", 0) or 0
            content = resp.choices[0].message.content or ""
            return content.strip()

    def stream(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        feature: str = "chat_stream",
    ) -> Iterator[str]:
        """Streaming chat completion. Records to llm_usage_logs on completion."""
        from app.core.observability import track_llm_usage

        with track_llm_usage(
            feature=feature, provider=self.cfg.provider, model=self.cfg.model
        ) as ctx:
            try:
                stream = self._client.chat.completions.create(
                    model=self.cfg.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                )
            except Exception as exc:
                raise UpstreamError(f"LLM stream failed: {exc}") from exc
            char_count = 0
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                text = getattr(delta, "content", None)
                if text:
                    char_count += len(text)
                    yield text
            # Most streaming providers don't surface usage; rough estimate:
            # ~4 chars/token. Real-world fine for prom histogram, off for cost.
            ctx["completion_tokens"] = max(1, char_count // 4)


@lru_cache
def get_llm_client(provider: str | None = None, model: str | None = None) -> LLMClient:
    return LLMClient(_resolve_config(provider, model))
