"""LLM-driven query rewrite (multi-query expansion) — v1.4 Sprint 6.

Given a user query, ask the LLM for up to N semantically-different variants
that together cover more of the relevant document space. Cached in Redis
for 24h keyed by md5(query) to avoid LLM cost on repeat queries.
"""
from __future__ import annotations

import hashlib
import json
import logging

from app.core.config import get_settings
from app.rag.llm_client import get_llm_client
from app.services.json_llm import safe_parse_json_object, truncate_for_llm

log = logging.getLogger(__name__)

_MAX_VARIANTS = 3
_CACHE_TTL = 86_400  # 24h

_REWRITE_SYSTEM = """你是研究检索查询改写助手。给定一个用户问题，输出 N 个语义相近
但角度不同的改写变体，覆盖更广的文献空间。

硬性规则：
1. 不要回答问题本身。
2. 每个变体保持原意，但可改写为：同义词替换 / 子问题拆分 / 同领域不同术语。
3. 变体之间应互相补充，避免完全重复。
4. 严格输出 JSON object。
"""

_REWRITE_USER_TMPL = """user_query: {query}

输出 JSON：
{{
  "variants": ["...", "...", "..."]
}}
"""


def _cache_key(query: str, n: int) -> str:
    digest = hashlib.md5(f"{n}:{query}".encode()).hexdigest()
    return f"qrw:v1:{digest}"


def _redis_client():
    try:
        import redis

        return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    except Exception:  # pragma: no cover
        return None


def generate_variants(query: str, *, n: int = _MAX_VARIANTS, feature: str = "query_rewrite") -> list[str]:
    """Return up to `n` alternate queries. Always includes the original as the first element."""
    original = (query or "").strip()
    if not original:
        return []
    if n <= 0:
        return [original]

    # 1) cache lookup
    cli = _redis_client()
    key = _cache_key(original, n)
    if cli is not None:
        try:
            hit = cli.get(key)
            if hit:
                data = json.loads(hit)
                if isinstance(data, list) and all(isinstance(s, str) for s in data):
                    return data
        except Exception:  # pragma: no cover
            pass

    # 2) call LLM
    client = get_llm_client()
    try:
        raw = client.complete(
            [
                {"role": "system", "content": _REWRITE_SYSTEM.replace("N", str(n))},
                {"role": "user", "content": _REWRITE_USER_TMPL.format(query=truncate_for_llm(original, 600))},
            ],
            temperature=0.2,
            max_tokens=400,
            feature=feature,
        )
    except Exception as exc:
        log.warning("query_rewrite_failed: %s", exc)
        return [original]

    data = safe_parse_json_object(raw, fallback={})
    variants_raw = data.get("variants") or []
    cleaned: list[str] = [original]
    seen = {original.lower()}
    for v in variants_raw:
        if not isinstance(v, str):
            continue
        s = v.strip()
        if not s:
            continue
        if s.lower() in seen:
            continue
        seen.add(s.lower())
        cleaned.append(s)
        if len(cleaned) >= n + 1:  # original + N variants
            break

    # 3) cache result (best-effort)
    if cli is not None:
        try:
            cli.set(key, json.dumps(cleaned, ensure_ascii=False), ex=_CACHE_TTL)
        except Exception:  # pragma: no cover
            pass
    return cleaned


__all__ = ["generate_variants"]
