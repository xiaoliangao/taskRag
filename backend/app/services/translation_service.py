"""DeepLX-backed translation with Redis cache.

DeepLX is the community open-source DeepL proxy — endpoints typically:
  POST {base_url}/translate
  body: {"text": "...", "source_lang": "EN", "target_lang": "ZH"}
  resp: {"code": 200, "data": "...", "source_lang": "EN", "target_lang": "ZH"}

Translations are deterministic for a given (text, target) pair, so we cache
aggressively. 30-day TTL — long enough that re-reading the same paper costs
zero LLM/proxy roundtrips, short enough that we'd pick up DeepL quality
improvements within a month.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.core.errors import APIError, UpstreamError

log = logging.getLogger(__name__)

_CACHE_TTL = 30 * 86_400  # 30 days
_MAX_TEXT_LEN = 5000      # DeepL hard limit per request


class TranslationDisabledError(APIError):
    def __init__(self) -> None:
        super().__init__(
            "TRANSLATION_DISABLED",
            "翻译服务未配置",
            http_status=503,
            details={"hint": "ask admin to set DEEPLX_BASE_URL"},
        )


@dataclass
class TranslationResult:
    text: str
    source_lang: str  # detected or echoed
    target_lang: str
    cached: bool


def _has_cjk(s: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in (s or ""))


def _auto_target(text: str, explicit_target: str | None) -> str:
    """If caller didn't specify, flip the language: Chinese → EN, else → ZH."""
    if explicit_target:
        return explicit_target.upper()
    return "EN" if _has_cjk(text) else "ZH"


def _cache_key(text: str, target: str) -> str:
    digest = hashlib.md5(f"{target}\0{text}".encode("utf-8")).hexdigest()
    return f"tr:v1:{digest}"


def _redis_client():
    try:
        import redis

        return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    except Exception:
        return None


def is_configured() -> bool:
    return bool(get_settings().deeplx_base_url)


async def translate(text: str, target_lang: str | None = None) -> TranslationResult:
    settings = get_settings()
    if not settings.deeplx_base_url:
        raise TranslationDisabledError()
    text = (text or "").strip()
    if not text:
        return TranslationResult(text="", source_lang="", target_lang=target_lang or "", cached=False)
    if len(text) > _MAX_TEXT_LEN:
        text = text[:_MAX_TEXT_LEN]

    target = _auto_target(text, target_lang)
    cli = _redis_client()
    key = _cache_key(text, target)
    if cli is not None:
        try:
            hit = cli.get(key)
            if hit:
                return TranslationResult(
                    text=hit, source_lang="auto", target_lang=target, cached=True
                )
        except Exception:
            pass

    url = settings.deeplx_base_url.rstrip("/") + "/translate"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if settings.deeplx_access_token:
        headers["Authorization"] = f"Bearer {settings.deeplx_access_token}"

    body = {
        "text": text,
        # DeepLX accepts "auto" for source_lang — proxy detects.
        "source_lang": "auto",
        "target_lang": target,
    }

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(url, json=body, headers=headers)
    except Exception as exc:
        log.warning("deeplx network error: %s", exc)
        raise UpstreamError(f"DeepLX 连接失败: {exc}") from exc

    if resp.status_code >= 400:
        log.warning("deeplx HTTP %s: %s", resp.status_code, resp.text[:200])
        raise UpstreamError(f"DeepLX 返回 {resp.status_code}")

    try:
        data = resp.json()
    except Exception as exc:
        raise UpstreamError(f"DeepLX 响应不是 JSON: {exc}") from exc

    # DeepLX standard shape: {"code": 200, "data": "...", "source_lang": ..., "target_lang": ...}
    out_text = data.get("data") or data.get("text") or ""
    if not out_text:
        raise UpstreamError(f"DeepLX 返回空译文: {str(data)[:200]}")
    detected_source = data.get("source_lang") or "auto"

    if cli is not None:
        try:
            cli.setex(key, _CACHE_TTL, out_text)
        except Exception:
            pass

    return TranslationResult(
        text=out_text,
        source_lang=detected_source,
        target_lang=target,
        cached=False,
    )
