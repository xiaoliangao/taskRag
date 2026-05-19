"""Cross-cutting observability: Sentry / structlog / Prometheus / LLM cost tracking.

Activated at process start by `init_observability()` in app.main + Celery worker.
All components no-op silently when env vars are missing (safe for dev).
"""
from __future__ import annotations

import contextvars
import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

from app.core.config import get_settings

log = logging.getLogger(__name__)

# ---- request-scoped context ----

request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)
user_id_ctx: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "user_id", default=None
)
topic_id_ctx: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "topic_id", default=None
)


def get_request_id() -> str:
    return request_id_ctx.get()


# ---- structlog ----

_STRUCTLOG_READY = False


def _init_structlog() -> None:
    global _STRUCTLOG_READY
    if _STRUCTLOG_READY:
        return
    try:
        import structlog
    except ImportError:  # pragma: no cover - dep is optional
        return

    def _inject_ctx(_, __, event_dict: dict[str, Any]) -> dict[str, Any]:
        rid = request_id_ctx.get()
        if rid and rid != "-":
            event_dict.setdefault("request_id", rid)
        uid = user_id_ctx.get()
        if uid is not None:
            event_dict.setdefault("user_id", uid)
        tid = topic_id_ctx.get()
        if tid is not None:
            event_dict.setdefault("topic_id", tid)
        return event_dict

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _inject_ctx,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )
    _STRUCTLOG_READY = True


# ---- Sentry ----


def _init_sentry() -> None:
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    except ImportError:  # pragma: no cover
        log.warning("Sentry DSN set but sentry-sdk not installed")
        return

    sentry_sdk.init(
        dsn=dsn,
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_RATE", "0.1")),
        environment=os.getenv("APP_ENV", "development"),
        integrations=[
            FastApiIntegration(),
            CeleryIntegration(),
            SqlalchemyIntegration(),
        ],
    )


# ---- Prometheus ----

_PROM_READY = False


def _init_prometheus_metrics() -> None:
    """Declare process-wide metric instances. Idempotent.

    v1.5: when env PROMETHEUS_MULTIPROC_DIR is set (e.g. /tmp/prom),
    metrics from worker-intel processes are also aggregated into the
    backend `/metrics` endpoint via prometheus_client multiprocess mode.
    """
    global _PROM_READY, intel_task_total, intel_task_duration_seconds
    global intel_llm_call_total, intel_llm_cost_dollars_today, intel_llm_latency_seconds

    if _PROM_READY:
        return
    try:
        from prometheus_client import Counter, Gauge, Histogram
    except ImportError:  # pragma: no cover
        return

    multiproc_dir = os.getenv("PROMETHEUS_MULTIPROC_DIR")
    if multiproc_dir:
        os.makedirs(multiproc_dir, exist_ok=True)

    intel_task_total = Counter(
        "intel_task_total",
        "Total intelligence-queue task executions.",
        ["task", "status"],
    )
    intel_task_duration_seconds = Histogram(
        "intel_task_duration_seconds",
        "Task duration in seconds.",
        ["task"],
        buckets=(1, 5, 15, 30, 60, 120, 300, 600),
    )
    intel_llm_call_total = Counter(
        "intel_llm_call_total",
        "LLM completion calls.",
        ["feature", "model", "success"],
    )
    intel_llm_latency_seconds = Histogram(
        "intel_llm_latency_seconds",
        "LLM completion call latency.",
        ["feature", "model"],
        buckets=(0.5, 1, 2, 5, 10, 30, 60, 120),
    )
    # Gauges in multiproc mode require `multiprocess_mode` arg.
    if multiproc_dir:
        intel_llm_cost_dollars_today = Gauge(
            "intel_llm_cost_dollars_today",
            "Estimated LLM cost (USD) accumulated today.",
            ["feature"],
            multiprocess_mode="livesum",
        )
    else:
        intel_llm_cost_dollars_today = Gauge(
            "intel_llm_cost_dollars_today",
            "Estimated LLM cost (USD) accumulated today.",
            ["feature"],
        )
    _PROM_READY = True


# placeholders so imports don't fail when prom-client missing
intel_task_total = None
intel_task_duration_seconds = None
intel_llm_call_total = None
intel_llm_latency_seconds = None
intel_llm_cost_dollars_today = None


# ---- LLM cost tracking ----

# Per-1K-token prices (USD). Update when contracts change.
_PRICE_TABLE: dict[str, tuple[float, float]] = {
    # provider/model: (input_per_1k, output_per_1k)
    "deepseek/deepseek-chat": (0.00014, 0.00028),
    "deepseek/deepseek-reasoner": (0.00055, 0.0022),
    "qwen/qwen-plus": (0.0004, 0.0012),
    "openai/gpt-4o-mini": (0.00015, 0.0006),
    "openai/gpt-4o": (0.0025, 0.01),
    "siliconflow/qwen/qwen2.5-7b-instruct": (0.0, 0.0),  # free tier
}


def _estimate_cost(provider: str, model: str, prompt_tok: int, completion_tok: int) -> Decimal | None:
    key = f"{provider}/{model}".lower()
    pricing = _PRICE_TABLE.get(key)
    if pricing is None:
        return None
    in_p, out_p = pricing
    cost = (prompt_tok / 1000.0) * in_p + (completion_tok / 1000.0) * out_p
    return Decimal(f"{cost:.6f}")


@contextmanager
def track_llm_usage(
    *,
    feature: str,
    provider: str,
    model: str,
    user_id: int | None = None,
    topic_id: int | None = None,
    document_id: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Wrap an LLM call. Records into Prometheus + llm_usage_logs.

    Usage:
        with track_llm_usage(feature="claim_extract", provider="deepseek", model="deepseek-chat") as ctx:
            resp = client.complete(...)
            ctx["prompt_tokens"] = resp.usage.prompt_tokens
            ctx["completion_tokens"] = resp.usage.completion_tokens
    """
    ctx: dict[str, Any] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "success": True,
        "error_msg": None,
    }
    start = time.monotonic()
    try:
        yield ctx
    except Exception as exc:
        ctx["success"] = False
        ctx["error_msg"] = str(exc)[:500]
        raise
    finally:
        latency = time.monotonic() - start
        latency_ms = int(latency * 1000)
        success = bool(ctx.get("success", True))
        prompt_tok = int(ctx.get("prompt_tokens") or 0)
        completion_tok = int(ctx.get("completion_tokens") or 0)
        cost = _estimate_cost(provider, model, prompt_tok, completion_tok)

        # Prometheus
        if intel_llm_call_total is not None:
            intel_llm_call_total.labels(
                feature=feature, model=model, success=str(success).lower()
            ).inc()
            intel_llm_latency_seconds.labels(feature=feature, model=model).observe(latency)
            if cost is not None and intel_llm_cost_dollars_today is not None:
                intel_llm_cost_dollars_today.labels(feature=feature).inc(float(cost))

        # Persist to llm_usage_logs (best-effort, never raises)
        try:
            from app.db.models.observability import LLMUsageLog
            from app.db.session import get_sync_sessionmaker

            SessionLocal = get_sync_sessionmaker()
            with SessionLocal() as db:
                db.add(LLMUsageLog(
                    user_id=user_id_ctx.get() if user_id is None else user_id,
                    topic_id=topic_id_ctx.get() if topic_id is None else topic_id,
                    document_id=document_id,
                    feature=feature[:64],
                    provider=provider[:64],
                    model=model[:128],
                    prompt_tokens=prompt_tok or None,
                    completion_tokens=completion_tok or None,
                    estimated_cost=cost,
                    latency_ms=latency_ms,
                    success=success,
                    error_msg=ctx.get("error_msg"),
                    request_id=request_id_ctx.get() if request_id_ctx.get() != "-" else None,
                ))
                db.commit()
        except Exception as exc:  # pragma: no cover - tracking must never break callers
            log.warning("llm_usage_log_write_failed: %s", exc)


# ---- public init entrypoints ----


def init_observability() -> None:
    """Initialize all observability components. Safe to call multiple times."""
    settings = get_settings()  # noqa: F841 - reserved for future env-driven config
    _init_structlog()
    _init_sentry()
    _init_prometheus_metrics()


__all__ = [
    "init_observability",
    "track_llm_usage",
    "get_request_id",
    "request_id_ctx",
    "user_id_ctx",
    "topic_id_ctx",
]
