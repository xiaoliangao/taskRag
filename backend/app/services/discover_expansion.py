"""Query expansion for the /discover page.

The upstream paper APIs (OpenAlex, Semantic Scholar) index mostly English
metadata. A Chinese-language query like "目标检测" matches Chinese characters
that incidentally appear in unrelated papers' abstracts, returning noise.

We ask the LLM to translate the CJK query into 2-3 English research-keyword
forms. Both the original (so any Chinese-titled paper still matches) and the
English translations are passed to the collector chain.

For pure English queries we skip expansion — the collectors' built-in keyword
matching is already strong enough.

Cached in Redis 7 days keyed by md5(query) to avoid hitting the LLM on every
search. Falls back to [original] on any LLM failure.
"""
from __future__ import annotations

import hashlib
import json
import logging

from app.core.config import get_settings
from app.rag.llm_client import get_llm_client
from app.services.json_llm import safe_parse_json_object, truncate_for_llm

log = logging.getLogger(__name__)


_CACHE_TTL = 7 * 86_400  # 7 days
_MAX_EXPANSIONS = 3


_SYSTEM = """你是一个科研检索查询翻译助手。给定一个用户输入的研究主题(可能是中文/英文/混合),
输出 2-3 个对应的【英文学术关键词或短语】,以及保留原始查询。这些关键词将作为 OpenAlex
/ Semantic Scholar 的搜索词使用,必须是真实学术界使用的术语。

硬性规则:
1. 输出必须是合法 JSON object。
2. "english" 字段是字符串数组,2-3 条,每条是英文学术术语(短语,通常 1-4 个词)。
3. 不要复述原文,不要解释,不要加引号包裹整体。
4. 如果输入本身就是英文学术术语,输出的 english 是它的近义术语扩展(例如 "object detection" → ["object detection","object recognition","object localization"])。
5. 不能编造领域。如果不确定,选择该术语在英文文献中最直接的翻译。

示例:
  输入: "目标检测"
  输出: {"english": ["object detection","object recognition","visual detection"]}
  输入: "图像分割"
  输出: {"english": ["image segmentation","semantic segmentation","instance segmentation"]}
  输入: "retrieval augmented generation"
  输出: {"english": ["retrieval augmented generation","RAG","retrieval-augmented language model"]}
"""

_USER_TMPL = """user_query: {query}

输出 JSON:
{{
  "english": ["...","..."]
}}
"""


def _has_cjk(text: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in (text or ""))


def _cache_key(query: str) -> str:
    digest = hashlib.md5(query.encode("utf-8")).hexdigest()
    return f"qexp_disc:v1:{digest}"


def _redis_client():
    try:
        import redis

        return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    except Exception:  # pragma: no cover
        return None


def expand_query_for_discover(query: str) -> list[str]:
    """Return a list of keywords to actually feed the collector chain.

    Always includes `query` itself as element 0. For CJK queries, appends
    up to 3 LLM-suggested English equivalents. Pure-ASCII queries are
    returned unchanged (the collectors already handle English well).
    """
    original = (query or "").strip()
    if not original:
        return []
    if not _has_cjk(original):
        return [original]

    cli = _redis_client()
    key = _cache_key(original)
    if cli is not None:
        try:
            hit = cli.get(key)
            if hit:
                data = json.loads(hit)
                if isinstance(data, list) and all(isinstance(s, str) for s in data):
                    return data
        except Exception:
            pass

    expansions: list[str] = []
    try:
        raw = get_llm_client().complete(
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": _USER_TMPL.format(query=truncate_for_llm(original, 400))},
            ],
            temperature=0.1,
            max_tokens=200,
            feature="discover_expansion",
        )
        data = safe_parse_json_object(raw, fallback={})
        for v in (data.get("english") or [])[:_MAX_EXPANSIONS]:
            if isinstance(v, str):
                s = v.strip()
                if s and s.lower() != original.lower():
                    expansions.append(s)
    except Exception as exc:
        log.warning("discover_expansion_failed: %s", exc)

    result = [original] + expansions
    if cli is not None:
        try:
            cli.set(key, json.dumps(result, ensure_ascii=False), ex=_CACHE_TTL)
        except Exception:
            pass
    return result


__all__ = ["expand_query_for_discover"]
