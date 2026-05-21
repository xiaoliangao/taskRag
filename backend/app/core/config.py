from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "production"] = "development"
    api_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:5173"

    # DB / Cache / Vector
    database_url: str = "postgresql+asyncpg://taskrag:taskrag@postgres:5432/taskrag"
    sync_database_url: str = "postgresql+psycopg://taskrag:taskrag@postgres:5432/taskrag"
    redis_url: str = "redis://redis:6379/0"
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "documents"

    # JWT
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Storage
    pdf_storage_dir: Path = Path("/data/pdfs")
    fulltext_storage_dir: Path = Path("/data/fulltext")
    upload_storage_dir: Path = Path("/data/uploads")

    # Embedding
    embedding_provider: Literal["siliconflow", "openai"] = "siliconflow"
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    siliconflow_api_key: str = ""

    # Reranker (SiliconFlow rerank API by default; TEI also supported)
    reranker_enabled: bool = True
    reranker_base_url: str = "https://api.siliconflow.cn/v1"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"

    # LLM
    llm_provider: Literal["deepseek", "qwen", "siliconflow", "openai"] = "deepseek"
    llm_model: str = "deepseek-chat"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-plus"

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    siliconflow_llm_model: str = "Qwen/Qwen2.5-7B-Instruct"

    # Email — port 465 uses implicit TLS (SMTP_SSL); 587 uses STARTTLS.
    # 465 is recommended when reaching Gmail from networks where 587 is blocked.
    gmail_smtp_host: str = "smtp.gmail.com"
    gmail_smtp_port: int = 465
    gmail_username: str = ""
    gmail_app_password: str = ""
    email_from: str = ""
    initial_admin_email: str = ""  # bootstrap: matching user promoted to admin on startup

    # DeepLX self-hosted translation proxy. Endpoint should accept
    # POST {base}/translate body {text, source_lang, target_lang}.
    # Empty disables translation feature; UI hides the button gracefully.
    deeplx_base_url: str = ""
    deeplx_access_token: str = ""  # optional bearer token if your instance requires one

    # Source API keys
    github_token: str = ""
    semantic_scholar_api_key: str = ""

    # Demo
    demo_user_email: str = "demo@example.com"
    demo_user_password: str = "demo123"

    # Business rules
    max_topics_per_user: int = 5
    backfill_days: int = 180                  # how far back the initial fill reaches
    backfill_max_results: int = 10            # papers to pull on first-time backfill
    manual_preview_max_results: int = 20      # search-preview list size for manual picker
    manual_preview_cache_ttl_s: int = 600     # Redis TTL for search-preview cache (10 min)
    manual_preview_source_timeout_s: float = 35.0  # per-source soft timeout before falling back
    history_turns: int = 5
    vector_top_k: int = 20
    rerank_top_n: int = 5
    relevance_prune_threshold: float = 0.2    # auto-remove topic↔doc if score below this

    # Rate / retry
    upload_max_bytes: int = 20 * 1024 * 1024
    fulltext_max_bytes: int = 200 * 1024

    # v1.4 — security
    cors_extra_origins: str = ""  # comma-separated
    rate_limit_login: str = "10/minute"
    rate_limit_register: str = "5/minute"
    rate_limit_llm_trigger: str = "30/minute"
    rate_limit_default: str = "120/minute"

    # v1.5 — retrieval feature flags
    crag_enabled: bool = True
    graphrag_enabled: bool = True

    def ensure_storage_dirs(self) -> None:
        for path in (self.pdf_storage_dir, self.fulltext_storage_dir, self.upload_storage_dir):
            path.mkdir(parents=True, exist_ok=True)

    def assert_production_secrets(self) -> None:
        """Fail fast if running with insecure defaults in non-dev envs."""
        if self.app_env.lower() in {"production", "prod", "staging"}:
            secret = (self.jwt_secret_key or "").strip().lower()
            if not secret or secret.startswith("change-me"):
                raise RuntimeError(
                    "JWT_SECRET_KEY must be set to a strong value in production "
                    "(current value looks like default placeholder)."
                )
            if self.jwt_secret_key and len(self.jwt_secret_key) < 32:
                raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters in production.")

    def cors_origins(self) -> list[str]:
        base = [self.frontend_base_url, "http://localhost:5173"]
        extra = [o.strip() for o in (self.cors_extra_origins or "").split(",") if o.strip()]
        # dedupe preserving order
        seen: set[str] = set()
        out: list[str] = []
        for o in base + extra:
            if o and o not in seen:
                seen.add(o)
                out.append(o)
        return out


@lru_cache
def get_settings() -> Settings:
    return Settings()
