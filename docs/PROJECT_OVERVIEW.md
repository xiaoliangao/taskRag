# TaskRAG 项目详细介绍

> 面向：想理解 TaskRAG 整体结构、并在此基础上做功能拓展的开发者。
> 配套阅读：`PRD.md`（产品需求 v0.3）、`TaskRAG_AI_Development_Document.md`（v1 实现说明 v1.0）、`TaskRAG_Optimization_Roadmap_AI.md`（v1.1+ 优化方向）。
>
> 文档版本：v1.2 — 已合并截至 2026-05-17 的所有迭代（多采集源 fallback / 自动剪枝 / 手动 picker / 任务进度 / UI 大改）。

---

## 1. 一句话定位

> **TaskRAG = 个人化、按"研究课题（Topic）"组织的研究助手。**
>
> 用户登录 → 创建课题（关键词 + 数据源 + 调度）→ 系统每天自动从 arXiv 等源采集论文 → 全文向量化入 Qdrant → 用户在课题知识库中问答 / 看简报 / 读阅读路径 / 找研究空白 / 沉淀笔记。

---

## 2. 总体架构

```
                        ┌────────────────────────┐
浏览器 ───────────────► │ React 18 + Vite        │   http://49.233.190.200:5173
                        │ AntD + TanStack Query  │
                        └────────┬───────────────┘
                                 │  REST / SSE  (JWT)
                                 ▼
                        ┌────────────────────────┐
                        │ FastAPI (uvicorn)      │   :8000 (容器内)
                        │ Auth/Topic/Doc/QA/...  │
                        └────────┬───────────────┘
                                 │
        ┌────────────────────────┼──────────────────────────────┐
        ▼                        ▼                              ▼
┌──────────────┐         ┌──────────────┐              ┌──────────────────┐
│ Celery       │         │ RAG Engine   │              │ Notification     │
│ urgent       │         │ (LangChain)  │              │ Workflow         │
│ scheduled    │         │  retriever   │              │  InApp + Email + │
│ backfill     │         │  reranker    │              │  Webhook(占位)   │
│ intelligence │         │  llm_client  │              └──────────────────┘
└──────┬───────┘         └──────┬───────┘
       │                        │
       │   ┌────────────────────┘
       ▼   ▼
┌─────────────────────────────────────────────┐
│ Data Layer                                   │
│  PostgreSQL @ 49.233.190.200:5432           │
│    users / refresh_tokens                    │
│    topics / topic_source_states              │
│    documents / chunks / topic_documents      │
│    collection_tasks                          │
│    notifications / notification_deliveries   │
│    chat_sessions / chat_messages             │
│    document_briefings / topic_document_      │
│      insights / user_document_states         │
│    topic_pulses                              │
│    reading_paths / reading_path_items        │
│    research_insights / research_notes        │
│                                              │
│  Redis @ 49.233.190.200:6379                │
│    Celery broker + results                   │
│                                              │
│  Qdrant @ qdrant:6333 (服务器 Docker)       │
│    collection: documents                     │
│    每个 chunk 一个 1024 维 bge-m3 向量       │
│    payload: document_id, topic_ids[], ...    │
│                                              │
│  FS @ /data (服务器 Docker volume)           │
│    /data/pdfs/<source>/<id>.pdf              │
│    /data/fulltext/<source>/<id>.txt          │
└─────────────────────────────────────────────┘
                ▲
                │
┌───────────────┴────────────────────┐
│ 外部服务（HTTP 调用）              │
│  arXiv API     (论文搜索 + PDF)    │
│  SiliconFlow   (bge-m3 embed +     │
│                  bge-reranker rerank) │
│  DeepSeek      (LLM 默认)          │
│  Qwen / OpenAI (LLM 备选)          │
│  Gmail SMTP    (邮件)              │
└────────────────────────────────────┘
```

### 2.1 容器清单（docker-compose.server.yml）

| 服务 | 镜像 / 命令 | 职责 |
|---|---|---|
| `qdrant` | qdrant/qdrant:latest | 向量库 |
| `backend` | task_rag-backend，`alembic upgrade head + uvicorn` | FastAPI |
| `worker` | 同 backend 镜像，`-Q urgent,scheduled,backfill` concurrency=1 | 采集 / 索引 / 通知 |
| `worker-intel` | 同 backend，`-Q intelligence` concurrency=1 | Briefing / Pulse / Path / Gap |
| `celery-beat` | 同 backend，`celery beat` | 60s 扫课题、15min 扫 pulse |
| `frontend` | task_rag-frontend，`npm run dev` | Vite dev server |

PostgreSQL 和 Redis 是宿主机上独立的容器/服务，通过 `host.docker.internal:host-gateway` 让 compose 内服务访问。

---

## 3. 核心概念

| 概念 | 说明 | 主要表 |
|---|---|---|
| **User** | 注册用户 | `users` |
| **Topic** | 用户创建的研究课题，含关键词/数据源/调度配置 | `topics` |
| **Document** | 一篇全局共享的文档（arXiv 论文/Repo/...）| `documents` |
| **Chunk** | Document 的一个分片（800 字符 + 100 重叠），对应一个 Qdrant point | `chunks` |
| **TopicDocument** | M:N 关联：哪个课题引用哪篇文档 | `topic_documents` |
| **CollectionTask** | 一次采集任务（manual/scheduled/backfill） | `collection_tasks` |
| **DocumentBriefing** | 全局共享的论文结构化解读（一句话/方法/贡献/局限/...）| `document_briefings` |
| **TopicDocumentInsight** | 该课题对该文档的相关性判断 | `topic_document_insights` |
| **UserDocumentState** | 用户对文档的私有状态（已读/收藏/笔记）| `user_document_states` |
| **TopicPulse** | 每日课题简报 | `topic_pulses` |
| **ReadingPath** | 阅读路径（含 items 分阶段）| `reading_paths`, `reading_path_items` |
| **ResearchInsight** | Gap / Opportunity / Trend / Contradiction | `research_insights` |
| **ResearchNote** | 用户研究笔记（手动 / Pin from chat / from pulse...）| `research_notes` |

### 隔离原则
1. `topics.user_id` 是所有权限判定的根。
2. `documents` 与 `chunks` 全局共享（不带 user_id）—— 节省向量化成本。
3. 用户访问任何文档 / chunk / briefing 之前都要走 `topics → topic_documents → documents` 验证。
4. Qdrant 检索强制带 `topic_ids contains [topic_id]` 过滤。

---

## 4. 后端代码结构

```
backend/app/
├── main.py                        # FastAPI 工厂 + lifespan（启动时建 Qdrant collection）
├── core/
│   ├── config.py                  # Pydantic Settings；所有环境变量
│   ├── constants.py               # 枚举：SourceType / TaskStatus / 队列名 / ...
│   ├── errors.py                  # APIError 体系 + 全局异常处理
│   ├── security.py                # bcrypt + JWT
│   └── logging.py
├── db/
│   ├── base.py                    # SQLAlchemy DeclarativeBase + TimestampMixin
│   ├── session.py                 # 异步引擎 (asyncpg) + 同步引擎 (psycopg)
│   ├── models/
│   │   ├── user.py                # User / RefreshToken
│   │   ├── topic.py               # Topic / TopicSourceState
│   │   ├── document.py            # Document / Chunk / TopicDocument
│   │   ├── task.py                # CollectionTask
│   │   ├── notification.py        # Notification / NotificationDelivery
│   │   ├── chat.py                # ChatSession / ChatMessage
│   │   └── intel.py               # v1.1+ 全部 7 张新表
│   └── repositories/
│       ├── user_repo.py
│       ├── topic_repo.py
│       ├── document_repo.py       # 含 ChunkRepository + TopicDocumentRepository
│       ├── task_repo.py
│       ├── notification_repo.py
│       ├── chat_repo.py
│       └── intel_repo.py          # Briefing / Insight / Pulse / Path / Notes 等
├── api/
│   ├── deps.py                    # get_current_user / get_owned_topic / get_owned_chat_session
│   ├── router.py                  # 把各 routes 注册到 /api/v1
│   └── routes/
│       ├── auth.py                # /register /login /refresh /me /logout
│       ├── topics.py              # CRUD + manual collect
│       ├── documents.py           # 列表 / 详情 / PDF 流式 / 上传(stub)
│       ├── briefings.py           # GET briefing / POST generate / PATCH user state
│       ├── qa.py                  # chat sessions / 流式 SSE 问答
│       ├── pulses.py              # 列表 / latest / generate
│       ├── reading_paths.py       # latest / generate
│       ├── insights.py            # 列表 / 详情 / generate gaps
│       ├── notes.py               # CRUD + pin chat message
│       ├── tasks.py               # 任务列表 / retry
│       ├── notifications.py       # 通知列表 / 标记已读
│       └── settings_route.py      # 用户偏好 settings
├── schemas/                       # 所有 Pydantic v2 请求/响应模型
├── services/                      # 业务逻辑（由 API + Celery 任务共用）
│   ├── auth_service.py
│   ├── topic_service.py
│   ├── qa_service.py              # 含 _gather_pinned_notes 注入 Pin 记忆
│   ├── briefing_service.py        # 结构化解读 / Insight
│   ├── pulse_service.py           # 每日简报
│   ├── reading_path_service.py    # 启发式分阶段
│   └── gap_service.py             # Gap Finder LLM 分析
├── collectors/
│   ├── base.py                    # BaseCollector Protocol + RawDocument + dedupe
│   ├── arxiv_collector.py         # arxiv lib（搜 + PDF 下载）
│   └── registry.py
├── indexer/
│   ├── qdrant_client.py           # collection init / upsert / search / topic_ids 维护
│   ├── embedder.py                # SiliconFlow /v1/embeddings
│   ├── parser_pdf.py              # PyMuPDF + 60s 超时 + 80 页限制 + 章节启发式
│   ├── cleaner.py                 # 文本清洗（含 \x00 剥离）
│   ├── chunker.py                 # RecursiveCharacterTextSplitter
│   └── ingest_service.py          # 全局去重 + chunk 共享 + topic_ids 更新
├── rag/
│   ├── retriever.py               # Qdrant 检索 + 时间衰减
│   ├── reranker.py                # SiliconFlow /v1/rerank (兼容 TEI)
│   ├── prompt.py                  # 系统提示 + 含 USER_NOTES 段
│   └── llm_client.py              # DeepSeek/Qwen/SiliconFlow/OpenAI 统一适配
├── notifications/
│   ├── workflow.py                # 链式分发
│   └── channels/
│       ├── inapp.py
│       ├── email.py               # Gmail SMTP
│       └── webhook_placeholder.py
└── tasks/                         # Celery 层
    ├── celery_app.py              # broker / 队列路由 / beat schedule
    ├── collect_tasks.py           # collect_topic_source_task / backfill_topic_task
    ├── schedule_tasks.py          # enqueue_due_topic_sources_task / enqueue_daily_pulses_task
    ├── index_tasks.py             # 占位
    ├── notification_tasks.py
    └── intel_tasks.py             # 5 个 intel 任务（briefing/insight/pulse/path/gap）
```

### 4.1 同步 vs 异步 Session

- **API 层** 用 `AsyncSession`（asyncpg），通过 `Depends(get_db)` 注入
- **Celery 任务** 用 `Session`（psycopg），通过 `get_sync_sessionmaker()` 获取

Repository 类多数同时提供两套：`*Repository`（sync, 用于 Celery）+ `*AsyncRepository`（async, 用于 API）。

---

## 5. 数据模型详解

### 5.1 v1 核心表

| 表 | 主键 | 关键列 | 索引 |
|---|---|---|---|
| `users` | id | email (UNIQUE), password_hash, settings_json (JSONB) | ix_users_email |
| `refresh_tokens` | id | user_id, token_hash (UNIQUE), expires_at, revoked_at | — |
| `topics` | id | user_id, name, keywords[], sources[], schedule_*, enabled | UQ(user_id, name), ix_user_id, ix_enabled |
| `topic_source_states` | (topic_id, source) | last_fetched_at, last_success_at, last_error_msg | — |
| `documents` | id | source, external_id, title, authors (JSONB), published_at, url, abstract, content_hash, pdf_path, full_text_path, parse_status | UQ(source, external_id), idx(source, published_at), idx(content_hash) |
| `chunks` | id | document_id, chunk_index, text, vector_id (UUID, UNIQUE), section_title, page_start/end | UQ(document_id, chunk_index), idx(document_id) |
| `topic_documents` | (topic_id, document_id) | matched_keyword, added_by_task_id, added_at | idx(document_id) |
| `collection_tasks` | id | topic_id, source, trigger, status, new/reused/skipped, error_msg | idx(topic, created_at), idx(status) |
| `notifications` | id | user_id, type, title, body, payload_json, read_at | idx(user, created_at), partial idx(user) WHERE read IS NULL |
| `notification_deliveries` | id | notification_id, channel, status, error_msg | — |
| `chat_sessions` | id | user_id, topic_id, title | idx(user, topic, created_at) |
| `chat_messages` | id | session_id, role, content, citations_json | idx(session, created_at) |

### 5.2 v1.1+ Intelligence 表（migration 0002）

| 表 | 主键 | 关键列 | 用途 |
|---|---|---|---|
| `document_briefings` | id | document_id (FK), status, one_sentence_summary, problem, method, contributions/experiments/limitations/datasets/metrics (JSONB), reading_time_minutes, evidence_chunk_ids | 全局共享的论文 briefing |
| `topic_document_insights` | id | topic_id, document_id, relevance_score, reading_priority, why_read | Topic 级解读 |
| `user_document_states` | id | user_id, document_id, status (unread/reading/read/archived), favorite, personal_note | 用户私有阅读状态 |
| `topic_pulses` | id | topic_id, pulse_date, status, title, summary_md, highlights/new_documents/important_documents/emerging_keywords/suggested_actions (JSONB) | 每日简报 |
| `reading_paths` | id | topic_id, title, description, status | 阅读路径主表 |
| `reading_path_items` | id | reading_path_id, document_id, order_index, stage, reason, expected_minutes | 路径条目 |
| `research_insights` | id | topic_id, insight_type (gap/...), title, summary, detail_md, confidence, evidence_*_ids, suggested_* | Gap Finder 等 |
| `research_notes` | id | user_id, topic_id, source_type, source_id, title, content_md, pinned | Pin/手动笔记 |

唯一约束总览：
- `documents (source, external_id)` — 同一源同一外部 ID 全局唯一
- `chunks (document_id, chunk_index)`
- `topic_documents (topic_id, document_id)` — M:N 主键
- `topics (user_id, name)`
- `document_briefings (document_id, language)`
- `topic_document_insights (topic_id, document_id)`
- `user_document_states (user_id, document_id)`
- `topic_pulses (topic_id, pulse_date)`

---

## 6. API 总览

所有路径前缀 `/api/v1`。除 `auth/*` 外都需要 `Authorization: Bearer <access_token>`。

### 6.1 Auth (`/auth/*`)

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/register` | email + password 创建用户 |
| POST | `/login` | 返回 access_token + refresh_token + user |
| POST | `/refresh` | 用 refresh_token 换新 access_token（旧的轮转吊销）|
| GET  | `/me` | 当前用户基本信息 + settings_json |
| POST | `/logout` | 吊销 refresh_token |

### 6.2 Topics

| 方法 | 路径 | 说明 |
|---|---|---|
| GET  | `/topics` | 当前用户全部课题 + 文档数 + 最近采集时间 |
| POST | `/topics` | 创建（含 5 个上限、关键词/数据源校验、自动派发 backfill）|
| GET  | `/topics/{id}` | 单个课题详情 |
| PATCH | `/topics/{id}` | 编辑；keywords 改变会派发 `keyword_changed` 紧急采集 |
| DELETE | `/topics/{id}` | 删除关联，**保留全局 documents**，从 Qdrant 移除 topic_id |
| POST | `/topics/{id}/collect` | 手动触发 urgent 采集 |

### 6.3 Documents

| 方法 | 路径 | 说明 |
|---|---|---|
| GET  | `/topics/{tid}/documents` | 列表（支持 source / q / from / to / 分页） |
| GET  | `/topics/{tid}/documents/{did}` | 详情（含 chunks 预览 + 截断后的 full_text） |
| GET  | `/topics/{tid}/documents/{did}/pdf` | 流式返回 PDF 文件 |
| POST | `/topics/{tid}/documents/upload` | 上传（v1 stub） |

### 6.4 Briefings + User State

| 方法 | 路径 | 说明 |
|---|---|---|
| GET  | `/topics/{tid}/documents/{did}/briefing` | 返回 {briefing, topic_insight, user_state}|
| POST | `/topics/{tid}/documents/{did}/briefing/generate` | 派发 LLM 分析（intelligence 队列）|
| PATCH | `/topics/{tid}/documents/{did}/state` | 改 user_document_states (status/favorite/note) |

### 6.5 Chat / QA

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/topics/{tid}/chat/sessions` | 新建会话 |
| GET  | `/topics/{tid}/chat/sessions` | 会话列表 |
| GET  | `/topics/{tid}/chat/sessions/{sid}/messages` | 消息历史 |
| POST | `/topics/{tid}/chat/sessions/{sid}/messages` | 非流式问答（返回完整 + citations） |
| GET  | `/topics/{tid}/chat/sessions/{sid}/stream` | SSE 流式问答（events: citations / token / done / error） |

### 6.6 Intelligence 新接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET  | `/topics/{tid}/pulses/latest` | 最新 pulse |
| GET  | `/topics/{tid}/pulses` | 所有 pulse |
| GET  | `/topics/{tid}/pulses/{id}` | 单个 |
| POST | `/topics/{tid}/pulses/generate` | 派发生成 |
| GET  | `/topics/{tid}/reading-paths/latest` | 最新路径（含 items 和用户阅读状态） |
| POST | `/topics/{tid}/reading-paths/generate` | 派发生成 |
| GET  | `/topics/{tid}/insights?type=gap` | 列表（按类型过滤） |
| GET  | `/topics/{tid}/insights/{id}` | 单条洞察 |
| POST | `/topics/{tid}/insights/gaps/generate` | 派发 Gap 分析 |
| GET  | `/topics/{tid}/notes` | 笔记列表（pinned 优先）|
| POST | `/topics/{tid}/notes` | 新建笔记 |
| PATCH | `/topics/{tid}/notes/{nid}` | 编辑（含 pin/unpin）|
| DELETE | `/topics/{tid}/notes/{nid}` | 删除 |
| POST | `/topics/{tid}/chat/messages/{mid}/pin` | 把某条助手回答 Pin 成 note |

### 6.7 Tasks / Notifications / Settings

| 方法 | 路径 | 说明 |
|---|---|---|
| GET  | `/topics/{tid}/tasks` | 课题任务列表 |
| GET  | `/tasks/{tid}` | 单个任务 |
| POST | `/tasks/{tid}/retry` | 失败任务重试 |
| GET  | `/notifications` | 通知列表（unread_only） |
| PATCH | `/notifications/{nid}/read` | 标记已读 |
| PATCH | `/notifications/read-all` | 全部已读 |
| GET  | `/settings` | 当前 settings_json |
| PATCH | `/settings` | 更新偏好（含 LLM provider / 邮件开关）|

---

## 7. 关键数据流

### 7.1 创建课题 → 自动采集 → 自动分析

```
POST /topics
  │
  ├─► topic_service.create → topics 行
  │     for each source: topic_source_states upsert
  │     commit
  │
  ├─► backfill_topic_task.delay(topic_id)             [intelligence 队列？不，backfill 队列]
  │       └─► 对每个 source 创建 CollectionTask(trigger=backfill)
  │           └─► collect_topic_source_task.apply_async(queue=backfill)
  │
  └─► 返回 Topic 给前端

collect_topic_source_task (worker 进程)
  │
  ├─► topic_source_state.mark running
  ├─► resolve since (backfill: 30 天前；scheduled: last_success - 1h)
  ├─► arxiv_collector.search(keywords, since, max_results=3)
  │   └─► 对每个 keyword 调 arxiv API；429 中断
  │       去重 by (source, external_id)
  │
  ├─► for each RawDocument:
  │     ingest_raw_document(db, topic_id, raw, task_id)
  │       ├─► upsert documents by (source, external_id)
  │       ├─► insert topic_documents (ignore conflict)
  │       ├─► if chunks 已存在: 只更新 Qdrant.payload.topic_ids
  │       └─► else: 下载 PDF → PyMuPDF parse → clean → chunk → embed → upsert
  │
  ├─► task_row.mark success（new/reused/skipped 计数）
  │
  ├─► for each newly_associated doc_id:
  │     generate_document_briefing_task.apply_async(queue=intelligence)
  │     generate_topic_document_insight_task.apply_async(queue=intelligence, countdown=5)
  │
  └─► notification.emit("task_done", ...)

worker-intel 进程
  └─► generate_document_briefing_task → LLM (DeepSeek) → document_briefings 入库
  └─► generate_topic_document_insight_task → LLM → topic_document_insights 入库

celery-beat (每 15 min)
  └─► enqueue_daily_pulses_task
        └─► 找出 enabled topic 当天没有 success pulse 的
            generate_topic_pulse_task.apply_async(queue=intelligence)
              └─► 聚合最近 24h/7d 新增 doc + 已有 briefings + insights
              └─► LLM 综合 → topic_pulses 入库 → 通知用户
```

### 7.2 问答（含记忆 + 引用）

```
POST /topics/{tid}/chat/sessions/{sid}/messages (或 SSE stream)
  │
  ├─► get_owned_chat_session 校验 session ∈ user ∈ topic
  ├─► 写入 user message 到 chat_messages
  │
  ├─► retriever.retrieve_for_topic(query)
  │     1. embedder.embed_query (SiliconFlow bge-m3)
  │     2. qdrant.query_points filter=topic_ids contains [tid] top_k=20
  │     3. hydrate chunk text from PG
  │     4. reranker.rerank (SiliconFlow bge-reranker-v2-m3) → 失败降级
  │     5. 时间衰减加权 final = rerank*0.8 + freshness*0.2
  │     6. top_n=5
  │
  ├─► _gather_pinned_notes (前 5 条课题内 pinned notes)
  │
  ├─► build_messages(question, history, citations, pinned_notes)
  │
  ├─► llm_client.complete / .stream (DeepSeek 默认)
  │
  └─► 写入 assistant message + citations_json 到 chat_messages
```

### 7.3 文档 PDF 预览

```
浏览器 → /topics/{tid}/documents/{did}/pdf
  ├─► get_owned_topic 校验
  ├─► 校验 topic_documents 关联存在
  ├─► 读 documents.pdf_path 返回 FileResponse(media_type=application/pdf)
前端用 axios responseType=blob 获取，URL.createObjectURL 后嵌 <iframe>
```

---

## 8. Celery 队列与任务

| 队列 | 消费者 | 任务 | 触发 |
|---|---|---|---|
| `urgent` | worker | `collect_topic_source_task` (trigger=manual/keyword_changed/upload) | 用户主动 |
| `scheduled` | worker | `collect_topic_source_task` (scheduled) / `enqueue_due_topic_sources_task` | Beat 每 60s |
| `backfill` | worker | `backfill_topic_task` → `collect_topic_source_task` (backfill) | 创建课题 |
| `intelligence` | worker-intel | `generate_document_briefing_task` | 入库后 |
| | | `generate_topic_document_insight_task` | 入库后 |
| | | `generate_topic_pulse_task` | Beat 每 15 min |
| | | `generate_reading_path_task` | 用户手动 |
| | | `generate_research_gaps_task` | 用户手动 |
| | | `enqueue_daily_pulses_task` | Beat 每 15 min |

**`worker-intel` 并发 = 1**，避免内存压力（服务器 2GB RAM）。

---

## 9. 前端结构

```
frontend/src/
├── main.tsx                       # AntD ConfigProvider + zh_CN + 主题色 + QueryClientProvider
├── routes.tsx                     # React Router v6 配置
├── api/                           # axios 客户端 + 各模块 API 封装
│   ├── client.ts                  # JWT 拦截 + auto refresh
│   ├── auth.ts / topics.ts / documents.ts / qa.ts
│   ├── tasks.ts / notifications.ts / settings.ts
│   ├── briefings.ts               # v1.1+
│   └── intel.ts                   # pulse / reading path / insights / notes
├── stores/
│   └── authStore.ts               # Zustand persist token + user
├── utils/
│   └── sse.ts                     # fetchEventSource 包装 + Bearer header
├── types/
│   └── api.ts                     # 全部接口的 TypeScript 类型
├── components/
│   ├── AppLayout.tsx              # Sider + Header + NotificationBell
│   ├── RequireAuth.tsx
│   ├── TopicCreateModal.tsx       # 课题创建表单
│   ├── TopicSettingsForm.tsx
│   ├── DocumentList.tsx
│   ├── DocumentDetailDrawer.tsx   # PDF iframe + Briefing Tab
│   ├── BriefingPanel.tsx          # v1.1+
│   ├── PulseCard.tsx              # v1.1+
│   ├── ReadingPathView.tsx        # v1.1+
│   ├── InsightsView.tsx           # v1.1+
│   ├── NotesView.tsx              # v1.1+
│   ├── ChatPanel.tsx              # 含 SSE 消费 + Pin 按钮
│   ├── CitationPanel.tsx
│   └── TaskTable.tsx
└── pages/
    ├── LoginPage.tsx
    ├── RegisterPage.tsx
    ├── TopicListPage.tsx          # 课题卡片网格
    ├── TopicDetailPage.tsx        # 8 Tab：概览/问答/知识浏览/阅读路径/研究洞察/研究笔记/任务记录/设置
    ├── NotificationsPage.tsx
    └── SettingsPage.tsx
```

### 9.1 状态管理边界

| 状态类型 | 库 | 例子 |
|---|---|---|
| 服务器数据缓存 | TanStack Query | topics / messages / pulses 等 |
| 全局 UI 与认证 | Zustand (persist) | accessToken / refreshToken / user |
| 局部 UI | useState | 抽屉开关、输入框、Pulse 折叠 |

### 9.2 SSE 实现要点

`utils/sse.ts` 用 `@microsoft/fetch-event-source`，因为原生 `EventSource` 不支持自定义 header（无法带 Bearer）。事件类型：
- `citations` → 引用面板展开
- `token` → 逐字追加到 assistant placeholder
- `done` → refetch 历史
- `error` → 弹错并关闭流

---

## 10. 部署

### 10.1 环境
- 服务器：49.233.190.200 (Tencent Cloud, CentOS 7, 2C2G)
- 项目路径：`/root/task_rag/`
- SSH：`root@49.233.190.200`（密码外部记录）
- 端口：5173（外部）/ 8000 / 6333 / 5432 / 6379

### 10.2 启动 / 重启

```bash
ssh root@49.233.190.200
cd /root/task_rag

# 启动全栈
docker compose up -d --build

# 仅重启某服务（代码改了）
docker compose restart backend worker worker-intel

# 跑数据库 migration
docker compose exec backend alembic upgrade head
```

### 10.3 .env 关键变量

```
DATABASE_URL = postgresql+asyncpg://taskrag:%40Yl0504.Pg@host.docker.internal:5432/taskrag
SYNC_DATABASE_URL = postgresql+psycopg://...
REDIS_URL = redis://:%40Yl0504.Redis@host.docker.internal:6379/0
QDRANT_URL = http://qdrant:6333

SILICONFLOW_API_KEY = sk-...   # embedding + reranker 共用
DEEPSEEK_API_KEY = sk-...      # 默认 LLM
QWEN_API_KEY = sk-...          # 备选

LLM_PROVIDER = deepseek
LLM_MODEL = deepseek-chat

VITE_API_BASE_URL = http://backend:8000   # 容器内 vite 代理目标
```

### 10.4 演示账号

```
demo@example.com / demo123
```

---

## 11. 关键防御性设计（"已踩过的坑"）

| 问题 | 解决 |
|---|---|
| arXiv 429 限流 | delay=5s + num_retries=1，遇 429 中断当前 topic 剩余 keyword |
| PyMuPDF 个别 PDF 死循环 | ThreadPoolExecutor 60s 超时 + 80 页上限，超时则降级到 abstract |
| PostgreSQL 不允许 \x00 字节 | cleaner.py 剥离 NUL |
| Qdrant 1.18 移除 `search()` | 改用 `query_points()` |
| URL 编码密码触发 configparser 插值 | alembic env.py 把 `%` 转义为 `%%` |
| Vite proxy localhost 不通容器 | `.env` 用 `http://backend:8000` |
| Celery beat 反复触发 stale 任务 | scheduled 改成"24h 无 success 才入队" |
| Email 通道未配置 | 自动 status=skipped，不影响 InApp |

---

## 12. 如何拓展功能（最常见的 3 类）

### 12.1 新增一个数据源（例如 GitHub）

1. **后端**
   - `app/collectors/github_collector.py`：实现 `BaseCollector.search()` → 返回 `RawDocument[]`
   - 在 `collectors/registry.py` 注册
   - 如需 PDF/全文，仿 arxiv_collector.download_pdf；否则在 ingest_service 的 `_parse_to_chunks` 加 GitHub 分支（用 README/repo metadata 作为内容）
   - 在 `core/constants.py SourceType` 已经有 `GITHUB`，无需新增
2. **前端**
   - `TopicCreateModal.tsx` 的 SOURCE_OPTIONS 把 `disabled: true` 去掉
3. **测试**
   - 用户创建带 `github` 数据源的 Topic → 检查 collect_tasks 跑通

### 12.2 新增一个 LLM provider

1. `core/config.py`：加 `xxxx_api_key` / `xxxx_base_url` / `xxxx_model`
2. `rag/llm_client.py`：在 `_resolve_config` 加分支（基本就是改 base_url）
3. `services/qa_service.py` 不需要改（通过 `preferred_llm_provider` 用户设置驱动）
4. `frontend/src/pages/SettingsPage.tsx` 的 `PROVIDER_OPTIONS` + `MODEL_HINTS` 加新条目

### 12.3 新增一个 Intelligence 功能（例如 "Trend Radar"）

参考 v1.1 Sprint 1-4 全套模式：

1. **DB**: `db/models/intel.py` 加表 → 写 Alembic migration `0003_xxx.py`
2. **Repo**: `db/repositories/intel_repo.py` 加同步 + 异步 Repository
3. **Service**: `services/trend_service.py` 写 LLM/统计逻辑（产出严格 JSON）
4. **Task**: `tasks/intel_tasks.py` 加 Celery 任务 + 在 `celery_app.py` 加路由
5. **API**: `api/routes/trends.py` 加 router → 在 `api/router.py` try-import 注册
6. **Schema**: `schemas/trend.py` 加 Pydantic 模型
7. **触发**: 决定是定时（加 beat schedule）还是用户手动
8. **前端**:
   - `types/api.ts` 加类型
   - `api/intel.ts`（或新文件）加调用函数
   - `components/TrendView.tsx` 写 UI
   - `pages/TopicDetailPage.tsx` Tabs 加新 tab
9. **部署**:
   - rsync 推到服务器
   - `docker compose exec backend alembic upgrade head`
   - `docker compose restart backend worker worker-intel`

### 12.4 完整的拓展心智模型

```
新功能 = (数据模型 +  Service 计算逻辑) + (Celery 任务 if 重活) + (API + Pydantic)
       + (前端类型 + API client + 组件 + Tab 注入)
       + (Migration + 部署步骤)
```

---

## 13. 监控与排查

### 13.1 看日志

```bash
docker compose logs backend --tail 50
docker compose logs worker --tail 50
docker compose logs worker-intel --tail 50
docker compose logs celery-beat --tail 30
```

### 13.2 直查数据库

```bash
docker exec pg-taskrag psql -U taskrag -d taskrag

# 常用查询
SELECT t.name, count(td.document_id) FROM topics t
  LEFT JOIN topic_documents td ON td.topic_id=t.id
  GROUP BY t.name;

SELECT id, status, new_docs_count, error_msg
  FROM collection_tasks ORDER BY id DESC LIMIT 10;

SELECT document_id, status, length(one_sentence_summary) AS summary_len
  FROM document_briefings ORDER BY id DESC LIMIT 10;
```

### 13.3 看 Celery 队列

```bash
docker compose exec worker celery -A app.tasks.celery_app inspect active
docker compose exec worker celery -A app.tasks.celery_app inspect reserved
docker compose exec worker celery -A app.tasks.celery_app purge -f   # 清空所有队列（小心）
```

### 13.4 看 Qdrant

- 浏览器：http://49.233.190.200:6333/dashboard
- API：
  ```bash
  curl http://localhost:6333/collections/documents
  curl -X POST http://localhost:6333/collections/documents/points/scroll \
    -H "Content-Type: application/json" \
    -d '{"limit":3,"with_payload":true}'
  ```

---

## 14. 已知限制 / 待改进

| 项 | 说明 |
|---|---|
| 无 LLM 模型微调 | demo 阶段不做 |
| 通知 Webhook 未实现 | placeholder，按 §12.3 模式补 |
| Reading Path 不调 LLM | 启发式分阶段；可后续加 LLM 重排 |
| Contradiction Detector / Trend Radar | roadmap §11 §12，尚未实现 |
| 单 worker 并发 = 1 | 受限于 2GB RAM，扩 RAM 后可调 |
| 邮件渠道用 Gmail SMTP | 演示够用，生产建议 Resend/SES |
| 文档全文存本地 FS | 单机够，多机要上对象存储 |
| 无团队协作 | v1 只做个人 |

---

## 15. 推荐学习路径（接手开发者）

1. **跑起来**：按 §10 启动 demo，用 demo 账号体验全部 Tab
2. **读 v1 主干**：`PRD.md` v0.3 → `TaskRAG_AI_Development_Document.md` v1.0
3. **读本文 §16**：了解所有后续迭代的关键改动
4. **跟踪一次 ingest**：从 `POST /topics/{id}/collect` 开始，看 `topic_service.manual_collect → collect_topic_source_task → ingest_raw_document → qdrant_client.upsert_points`
5. **跟踪一次 QA**：从前端 `ChatPanel.send` → backend `qa_service.answer_stream` → `retrieve_for_topic` → `llm_client.stream`
6. **读 roadmap**：`TaskRAG_Optimization_Roadmap_AI.md`，了解 v1.3+ 还要做哪些（Graph / Timeline / Trend / Contradiction）
7. **照 §12.3 模式实现一个简单的新功能练手**（如 v1.3 的 Trend Radar）

---

## 16. 迭代历史（v1.2 增量 / 已合并）

> 这一节追溯了 v1.1 全套之后又做的所有改动 — 主要是**采集稳健性 / 进度可见性 / 视觉重设计**。
> 阅读本节的目的是：当你想再加一个采集源 / 再加一个智能功能时，知道当前体系是怎么演进的、可以复用哪些模式。

### 16.1 多采集源 + 自动 fallback 链

**问题**：arXiv 直连 API 经常被 IP 段限流（429），导致 demo 当天无法采集。

**解决**：从单源 arXiv 扩展为三源 + 智能 fallback：

```
arXiv (直连)
   ↓ 429
OpenAlex (240M+ works, 无 key, 100k/天/IP)
   ↓ 429
Semantic Scholar (覆盖 arxiv + 期刊, 可选 free key)
```

**实现位置**
- `app/collectors/openalex_collector.py` — 调 `api.openalex.org/works`
- `app/collectors/semantic_scholar_collector.py` — 调 `api.semanticscholar.org/graph/v1/paper/search`
- `app/collectors/registry.py` — `FALLBACK_CHAIN` 定义优先级
- `app/collectors/base.py` — 新增 `CollectorRateLimitedError`，主源 0 结果 + 限流时抛
- `app/tasks/collect_tasks.py` — `_search_with_fallback()` 串联整条链

**关键设计**：
- 当 OpenAlex / SS 返回的论文带 arXiv ID → **自动转成 `source='arxiv'` 入库**，与直连 arXiv 去重
- 三个 collector 都各自实现 `download_pdf()`，`ingest_service._parse_to_chunks` 按 `document.source` 派发

**新增配置**（`.env` 可选）：
```
SEMANTIC_SCHOLAR_API_KEY=    # 不填走 free tier，间隔 1.1s
```

**故障语义改写**：
- 之前：429 silently → task=success / new=0（骗用户）
- 现在：所有源都限流 + 0 结果 → task=**failed** + `error_msg=arxiv 限流（已尝试 fallback 仍失败）`
- 通知体也改为"采集被限流"

### 16.2 搜索精度收紧 + 自动剪枝

**问题**：`all:"yolo"` 在 arXiv 会搜全文（含参考文献），结果一篇 metaverse-ethics 论文被拉进 object-detection 课题。

**解决**：

| 层级 | 改动 |
|---|---|
| **查询语法** | arXiv: `all:"X"` → `(ti:"X" OR abs:"X")`；OpenAlex: `search=X` → `filter=title_and_abstract.search:X`。SS 默认就是 title+abstract |
| **自动剪枝** | LLM 评 `topic_document_insight` 后，若 `relevance_score < 0.2`，删除 `topic_documents` 关联 + 从 Qdrant payload 的 `topic_ids[]` 移除该 topic — **全局 Document 保留**（别的课题可能用得上）|
| **UI 默认隐藏** | DocumentList 加 👁 toggle，默认隐藏 `reading_priority='low'` 的论文 |

**新增配置**（`app/core/config.py`）：
```python
relevance_prune_threshold: float = 0.2
```

**新增方法**：`services/briefing_service._prune_topic_document()`

### 16.3 首次回填 vs 增量采集 — 不同 max_results

**问题**：用户希望 "新建课题填 10 篇/180 天，之后每次只更新 3 篇"。

**实现**：在 `collect_topic_source_task` 中按 trigger 切换：

```python
effective_max = (
    settings.backfill_max_results          # = 10
    if trigger == CollectionTrigger.BACKFILL.value
    else topic.max_results_per_source_per_run   # = 3
)
```

**新增配置**：
```python
backfill_days: int = 180          # 之前 30
backfill_max_results: int = 10
manual_preview_max_results: int = 20
```

### 16.4 手动采集 = 搜索预览 + 用户选择 + 入库

**问题**：之前 "立即采集" 是黑盒 fire-and-forget；用户没法挑论文。

**新流程**：

```
用户点 [手动采集]
   ↓
POST /api/v1/topics/{tid}/search-preview         # 跑 collector + 返回 RawDocs（不入库）
   ↓
modal 展示候选论文（标题/作者/年份/摘要/已入库标记）
   ↓
用户勾选 N 篇 → POST /api/v1/topics/{tid}/collect-selected
   ↓
ingest_picked_documents_task (Celery urgent 队列)
   ↓
逐条 ingest_raw_document → 进度可见
```

**新增文件**
- `app/schemas/picker.py` — PreviewRequest / PreviewItem / CollectSelectedRequest
- `app/services/picker_service.py` — `search_preview()`，含 `already_in_topic` 标记（DB 反查）
- `app/tasks/collect_tasks.py` — `ingest_picked_documents_task`（urgent 队列）
- `frontend/src/components/SearchPickerModal.tsx` — 多选 modal

**API**:
```
POST /api/v1/topics/{tid}/search-preview       body: {sources?, limit?}
POST /api/v1/topics/{tid}/collect-selected     body: {picks: PreviewItem[]}
```

**遗留**：`POST /topics/{tid}/collect`（fire-and-forget）保留，自动化脚本可用。

### 16.5 任务进度可见 + 失败原因展开

**问题**：之前任务只有最终 success/failed，跑 5 分钟用户不知道在干啥。

**实现**：每个 `collect_topic_source_task` 在 `metadata_json.progress` 实时写入：

```json
{
  "step": "ingesting",          // searching / ingesting / done
  "total": 10,
  "processed": 3,
  "current_doc": "arxiv:2406.12345",
  "current_title": "...",
  "new": 2, "reused": 0, "skipped": 1,
  "last_error": "PDF parse timeout"      // 若有
}
```

**前端**：`TaskTable` 每行可展开，主行渲染 accent 黄绿色进度条；展开后两栏（progress / outcome）。失败的 `error_msg` 以红色框完整显示。

**Schema 改动**：`app/schemas/task.py` 加 `TaskProgress` + `TaskPublic.progress`。

### 16.6 视觉系统大改（v1.2 UI）

**方向**：Linear / Vercel 风的"研究台 at 2am"
- 深底 `#0a0a0c` + 电气夏特绿 accent `#d4ff4a`（仅在主按钮、live 状态、重要标题"研究"字使用）
- 字体三件套：`Instrument Serif` (italic 大标题) / `Inter` (正文) / `JetBrains Mono`（数字、ID、时间戳）
- 1px hairline 边框；所有 hover/focus 用 `cubic-bezier(0.16, 1, 0.3, 1)` / 200ms

**关键新文件**
- `frontend/src/styles/globals.css`（~1200 行）— 设计 token + 自定义 utility class + 全部 AntD overrides
- `frontend/src/main.tsx` 桥接 AntD theme token

**布局变化**
- AppLayout 从默认 AntD Sider 改成自定义 sidebar，**课题列表 inline**（Linear 风），每个课题 dot 实时反映 enabled
- 课题列表页大 serif 标题 + dot 状态 + papers/keywords metric
- Topic 详情页 8 tab 改 pill 风（accent 下划线）
- Chat 三列布局（会话 / 对话 / 引用），输入框无 AntD 框，send 改圆形 accent 按钮
- 任务记录用 log 风 mono 表 + 进度条

### 16.7 v1.2 数据流补丁

新增的 Celery 任务路由（`app/tasks/celery_app.py`）：

| 任务 | 队列 | 何时触发 |
|---|---|---|
| `ingest_picked_documents_task` | urgent | 用户在 picker modal 点"入库" |

注意 `worker-intel` 容器并发=1（2GB RAM 限制），生产建议拆到独立机器后调高。

### 16.8 文件清单更新（v1.2 新增）

```
backend/app/
├── collectors/
│   ├── openalex_collector.py          ← NEW (v1.2)
│   └── semantic_scholar_collector.py  ← NEW (v1.2)
├── schemas/
│   └── picker.py                      ← NEW (v1.2)
├── services/
│   └── picker_service.py              ← NEW (v1.2)
└── tasks/
    └── collect_tasks.py               ← 增 ingest_picked_documents_task + 进度写入

frontend/src/
├── styles/
│   └── globals.css                    ← NEW (v1.2 重设计)
└── components/
    └── SearchPickerModal.tsx          ← NEW (v1.2 手动选择 modal)
```

### 16.9 拓展提示

如果你要加第 4 个数据源（如 PubMed、CORE）：
1. `app/collectors/xxx_collector.py` — 实现 `search()` + `download_pdf()`
2. `app/core/constants.SourceType` 加值
3. `app/collectors/registry.py` 注册 + 加入 `FALLBACK_CHAIN`（若想自动 fallback）
4. `app/indexer/ingest_service._parse_to_chunks` 加 `if document.source == ...`（如果需要不同 PDF 下载逻辑）
5. 前端 `TopicCreateModal.tsx` / `TopicSettingsForm.tsx` 的 source 下拉加选项

如果你要加 Trend Radar / Contradiction Detector（roadmap v1.3+）：
照 §12.3 步骤 + 参考 `pulse_service.py` / `gap_service.py` 的 LLM JSON 输出 + safe parse 模式即可。
