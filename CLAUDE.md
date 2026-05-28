# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Read `docs/ARCHITECTURE.md` first** for the canonical Wave-3.5 design snapshot — pipeline diagrams, ADRs, data model, and decision rationale. This file gives you only the operating instructions.

---

## Project shape

TaskRAG is a per-topic research RAG demo. One Python FastAPI backend + React/Vite frontend, glued together by Celery workers (`urgent`, `scheduled`, `backfill`, `intelligence` queues) and four data stores (Postgres, Redis, Qdrant, `/data` volume for PDFs/fulltext). Single-user demo; ~16 alembic migrations; 7-container docker compose deployment.

## Commands

### Local dev (docker compose)

```bash
docker compose up --build                                   # full stack on localhost
docker compose exec backend python scripts/seed_demo.py     # demo user + 3 topics
docker compose exec backend alembic upgrade head            # apply migrations (auto-run on backend boot)
docker compose exec backend alembic revision -m "msg" --autogenerate
docker logs task_rag-backend-1 -f                           # structlog JSON
```

Backend: http://localhost:8000 (Swagger `/docs`) · Frontend: http://localhost:5173 · Qdrant: http://localhost:6333/dashboard.

### Backend (run inside the `backend` container or a venv where pyproject.toml is installed)

```bash
pytest                                              # all unit tests (asyncio_mode=auto)
pytest app/tests/unit/test_retriever_rrf.py -k rrf  # single test
ruff check . && ruff format .                       # lint + format (line-length 110, py311)
mypy app                                            # type-check (lenient: check_untyped_defs=false)
```

### Frontend (run inside `frontend/`)

```bash
npm run dev          # vite, expects backend on 8000 via vite proxy
npm run build        # tsc -b && vite build
npm run typecheck    # tsc --noEmit
npm run test:e2e     # playwright; set E2E_BASE_URL to override localhost:5173
```

### RAG evaluation (the closed loop — use this to verify any retrieval change)

```bash
# Seed a golden set (LLM reverse-generates Q from chunks)
docker compose exec backend python -m app.eval.seed_from_chunks --topic 2 --n 30
docker compose exec backend python -m app.eval.seed_from_chats   --topic 2 --limit 30
docker compose exec backend python -m app.eval.add_question      --topic 2  # interactive

# Run the eval — writes a row to rag_eval_runs with commit_sha + metrics_json
docker compose exec backend python -m app.eval.run_eval --topic 2 --label baseline
```

Wave-3 baseline on Topic 2 (RAG): **recall@5=0.434, recall@20=0.667, MRR=0.783**. Any retrieval-side change should diff against this.

### Backfill / index rebuild

```bash
docker compose exec backend python -m app.scripts.backfill_chunks --topic 2  # rebuild parent-child + context_summary
```

---

## Architecture in two minutes

### Ingest → Retrieve → Generate

1. **Ingest** (Celery `scheduled`/`urgent`/`backfill`): `collectors/` (arxiv · openalex · semantic_scholar, with Unpaywall fallback) → `indexer/parser_pdf.py` (PyMuPDF, 60s timeout) → `indexer/chunker.py` (Parent-Child: ~2000-char parents, ~600/100 children) → `services/contextual_retrieval.py` (per-parent LLM call adds a 50–100 token "what is this section about" summary) → `indexer/embedder.py` (bge-m3 1024-d via SiliconFlow, batch 16) → Postgres rows + Qdrant points (children only; parents stay PG-side with `is_parent=true`, `vector_id=NULL`).

2. **Retrieve** (`services/qa_service.py`): `rag/query_router.classify_query` (LLM 1x, Redis 7d cache) routes into `factual` / `comparison` / `synthesis` / `multi_step` branches that differ in variant count and whether CRAG + GraphRAG run → `services/query_rewrite` multi-query expansion → per-variant Qdrant + Postgres BM25 (`text_tsv` GIN, `WHERE is_parent=false`) fused via RRF (k=60) → cross-variant union → bge-reranker-v2-m3 (top_n=5) → final score = `rerank*0.8 + freshness*0.2` → optional CRAG self-grade + retry → GraphRAG 1-hop via `document_relations` → **Parent-Child swap** (replace child text with its parent for LLM context).

3. **Generate**: `rag/prompt.build_messages` mixes system + chat mode (`default/mentor/beginner/debate/reviewer/what_if`) + `chat_session_summaries` (long-term memory injected by `services/memory_service`) + pinned notes + citations + last 5 turns. For `multi_step` non-streaming routes only, `services/self_rag.critique_and_maybe_retry` may re-retrieve + regenerate once if faithfulness < 0.5.

### Where things live

```
backend/app/
  api/routes/        # FastAPI route modules — one per feature (qa, qa_cross, agent, discover, admin, admin_eval, …)
  rag/               # retriever · reranker · query_router · prompt · llm_client · chat_modes
  services/          # qa_service · crag · graphrag · self_rag · contextual_retrieval · memory_service · …
  indexer/           # PDF parse → chunk → embed → qdrant_client
  collectors/        # arxiv · openalex · semantic_scholar (search + download_pdf)
  tasks/             # celery_app + 4-queue routing; collect/index/intel/research/notification/schedule tasks
  eval/              # metrics · run_eval · seed_from_chunks · seed_from_chats · add_question · faithfulness
  db/                # SQLAlchemy 2.x async models + sync sessionmaker (Celery uses sync)
  core/              # config (pydantic-settings) · errors · logging · observability · security
frontend/src/
  pages/             # TopicListPage · TopicDetailPage · DiscoverPage · AdminUsersPage · AdminEvalPage · …
  components/        # ChatPanel · PdfReader · SearchPickerModal · TopicMapTab · PageTransition · …
  stores/            # zustand (auth, theme)
  styles/globals.css # Twin themes: Quiet Intelligence (dark) / Atelier (light)
docs/ARCHITECTURE.md # canonical design doc — read before changing the pipeline
```

### Celery queues & beat

| Queue | Worker container | Schedule |
|---|---|---|
| `urgent` / `scheduled` / `backfill` | `worker` (concurrency=1) | Beat: `enqueue_due_topic_sources_task` every 60s |
| `intelligence` (briefing/pulse/path/insight/trend/signal) | `worker-intel` (concurrency=1) | Beat: pulse every 15min, signals every 6h |

Beat scheduler is the `celery-beat` container — never run two beats.

### LLM client

`rag/llm_client.py` is OpenAI-compatible; provider is `LLM_PROVIDER` env (`deepseek` / `qwen` / `siliconflow` / `openai`). Every call is logged to `llm_usage_logs` (tokens, latency, cost, feature) — useful for tuning. Embeddings + reranker both go through SiliconFlow.

---

## Gotchas

- **Don't run two `celery beat` instances.** Only the `celery-beat` container schedules.
- **Server SMTP is QQ, not Gmail** (ADR-010 in ARCHITECTURE.md). Env vars are still named `GMAIL_*` but `GMAIL_SMTP_HOST=smtp.qq.com`, port 465 (SSL). Gmail SMTP is blocked by GFW from CN servers.
- **PDF parser is PyMuPDF only** — Docling was reverted (ADR-007). Don't reintroduce it without checking the rollback rationale.
- **`is_parent=true` chunks are not in Qdrant** and must be excluded from BM25 (`WHERE is_parent=false`). Both retrieval paths depend on this — breaking it causes duplicate hits.
- **`context_summary` is prepended to child text only at embed time**, not stored in the visible `text` column. The user sees `text`; Qdrant sees `context_summary + "\n\n" + text`.
- **Self-RAG only runs on `multi_step` route + non-streaming responses** (ADR-005). Streaming can't rewind already-sent tokens.
- **Celery uses the sync sessionmaker** (`app.db.session.get_sync_sessionmaker`), not the async one. FastAPI request handlers use async.
- **`JWT_SECRET_KEY` must be non-default in prod** — `settings.assert_production_secrets()` refuses to boot otherwise.
- **`INITIAL_ADMIN_EMAIL`** is auto-promoted to admin on every backend boot (idempotent) — set it to bootstrap the first admin.
- **`abstract_only=true` docs** (set in `documents.metadata_json` when PDF download failed or parser timed out) still appear in retrieval but the UI tags them with a "仅摘要" pill.

## Workflow conventions

- Per ADR record, this repo prefers **fix-forward via new alembic migration** over editing existing ones; migrations are numbered `0001..NNNN` and reflect ordered intent.
- Ruff is wired into `.pre-commit-config.yaml` (auto-fix) + a local hook for `frontend && npx tsc --noEmit`. Don't disable hooks.
- Any retrieval-side change → run the eval (above) and capture the before/after in the commit message. The `rag_eval_runs.commit_sha` column makes regressions reviewable from `/admin/eval`.
- Production deploy = `git pull` on the server (`49.233.190.200`) + `docker compose up -d --force-recreate`. The backend container auto-runs `alembic upgrade head` on boot.
