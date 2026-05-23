# TaskRAG · 系统架构设计文档

> 面向研究人员的论文 RAG 系统。最后更新:2026-05-21(Wave-3.5 完工)

## 0. 设计哲学

| 原则 | 体现 |
|---|---|
| **检索精度优先,生成能力其次** | 把工程精力放在"找对 chunk"而不是堆 LLM tokens — Hybrid + Reranker + Parent-Child + Contextual + Query Router 五件套 |
| **每个组件可独立失败** | LLM 翻译挂 → 检索照样跑;CRAG 挂 → 单查询照常返回;Self-RAG critique 失败 → 用首答 |
| **优雅降级,不暴力告警** | Docling 不可用 → PyMuPDF;SS 没 key → 跳过;DeepLX 没配 → UI 自动隐藏按钮 |
| **可观测、可回归** | RAGAS-style 评估闭环;CLI + Admin UI 双路径;每个 RAG 改动都能跑 baseline 对比 |
| **数据迁移可重做** | 任何 chunk-level 改动写一个 backfill 脚本,可在线无停机重建索引 |

---

## 1. 技术栈

```
┌────────────────────────────── Frontend ────────────────────────────────┐
│  React 18 + Vite 5 + TypeScript                                        │
│  · Ant Design 5(组件库) + Zustand(状态) + TanStack Query(数据)     │
│  · React Router v6 + 自研 PageTransition 路由转场                       │
│  · react-pdf 9 + pdfjs-dist 4(站内 PDF 阅读 + 高亮)                   │
│  · Twin themes:Quiet Intelligence(夜) / Atelier(日,N/D 切换)        │
└────────────────────────────────────────────────────────────────────────┘
                                  ↓ /api/v1/* via Vite proxy
┌────────────────────────────── Backend ─────────────────────────────────┐
│  FastAPI + SQLAlchemy 2.x(async)+ Pydantic v2                          │
│  · slowapi(IP/账号限流)  · structlog(JSON 日志)                       │
│  · prometheus-fastapi-instrumentator(可选)  · Sentry(可选)            │
│  · OpenAI-compatible LLM client(DeepSeek / Qwen / SiliconFlow 多 provider)│
└────────────────────────────────────────────────────────────────────────┘
        ↓ SQL                   ↓ HTTP                    ↓ redis
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│  Postgres    │         │  Qdrant      │         │  Redis       │
│  16 张迁移   │         │ 1024-dim HNSW│         │ cache/lock/  │
│  RAG/auth/   │         │ topic_ids    │         │ rate-limit/  │
│  intel/eval  │         │ payload      │         │ session      │
└──────────────┘         └──────────────┘         └──────────────┘
                                  ↑
                       异步事件 + 计划任务
                                  ↓
┌──────────────────── Celery Workers ────────────────────┐
│  Broker: Redis                                          │
│  Queues: urgent / scheduled / backfill / intelligence   │
│  Beat: 每 60s 课题源扫描 · 15m 日报触发 · 6h 信号刷新   │
└─────────────────────────────────────────────────────────┘
```

### 部署拓扑(docker compose · 7 容器)

| 容器 | 镜像 | 端口 | 数据 |
|---|---|---|---|
| `frontend` | node + vite dev | 5173 (Internet → 反向 proxy /api) | `./frontend:/app` (bind) |
| `backend` | python:3.11 + uvicorn | 8000 (仅容器网内) | `./backend:/app` + `/data` volume |
| `worker` (urgent + scheduled + backfill 队列) | 同 backend | — | 共享 |
| `worker-intel` (intelligence 队列) | 同 backend | — | 共享 |
| `celery-beat` | 同 backend | — | — |
| `qdrant` | qdrant/qdrant:latest | 6333 (仅容器内) | `qdrant_data` volume |
| `pg-taskrag` | postgres:15(host network) | 5432 host | host /var/lib/postgresql |

---

## 2. 数据模型

### 2.1 核心 ER 图

```
users ──┬── refresh_tokens                                  notifications
        │                                                          │
        └─── topics ──┬── topic_documents ─── documents ──┬─ chunks (parent_id self-ref)
                     │                                    ├─ annotations
                     │                                    └─ document_signals
                     │
                     ├── chat_sessions ── chat_messages
                     │                  └── chat_session_summaries (长期记忆)
                     │
                     ├── topic_pulses · topic_briefings · reading_paths
                     ├── research_insights · research_notes · topic_terms
                     ├── paper_claims · claim_relations
                     ├── method_entities · method_evolution_edges
                     ├── document_relations(graph 边)
                     └── rag_eval_questions · rag_eval_runs ← Wave-3 评估闭环
```

### 2.2 迁移历史(16 张)

| 版本 | 内容 |
|---|---|
| 0001 | 核心 4 表(topics/documents/chunks/chat) |
| 0002 | Intel 层(briefing/insight/pulse/note/reading_path) |
| 0003 | Research 扩展(term/trend_snapshot) |
| 0004 | Conflict 探索(claim/claim_relation/document_signal) |
| 0005 | Hypothesis 验证 + chat_sessions.mode |
| 0006 | Comparison + writing_project |
| 0007 | Knowledge Graph + Glossary + Export |
| 0008 | llm_usage_logs(观测) |
| 0009 | chunks.text_tsv tsvector + GIN(BM25 全文检索) |
| 0010 | chat_session_summaries(对话长期记忆) |
| 0011 | method_entities + method_evolution_edges(方法时间线) |
| 0012 | users.is_admin + disabled_at(admin 面板) |
| 0013 | annotations(PDF 标注) |
| **0014** | **chunks.parent_id + is_parent(Parent-Child)** |
| **0015** | **chunks.context_summary(Contextual Retrieval)** |
| **0016** | **rag_eval_questions + rag_eval_runs(评估闭环)** |

### 2.3 chunks 表(RAG 核心)

```sql
CREATE TABLE chunks (
    id                BIGSERIAL PRIMARY KEY,
    document_id       BIGINT NOT NULL REFERENCES documents ON DELETE CASCADE,
    chunk_index       INT    NOT NULL,
    text              TEXT   NOT NULL,                  -- 原文,UI/BM25 见到的
    section_title     TEXT,
    page_start        INT,
    page_end          INT,
    vector_id         UUID UNIQUE,                      -- NULL for parents
    parent_id         BIGINT REFERENCES chunks ON DELETE SET NULL,
    is_parent         BOOLEAN NOT NULL DEFAULT FALSE,
    context_summary   TEXT,                             -- LLM 生成的定位句
    token_count       INT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, chunk_index)
);
-- text_tsv 自动生成列 + GIN 索引(BM25 用)
-- 部分索引 idx_chunks_parent_id ON parent_id WHERE parent_id IS NOT NULL
```

**关键属性**:
- `is_parent=true` 的行**不进 Qdrant**(vector_id NULL),只做生成上下文
- `text_tsv` BM25 检索 WHERE `is_parent=false`(避免父子内容重复匹配)
- `context_summary` 在 embed 前拼到 chunk text 头部(用户看不到,Qdrant 看到)

---

## 3. RAG 流水线

### 3.1 入库(Ingest)— Celery 任务

```
[ scheduled / manual_pick / discover ingest ]
         ↓
collect_topic_source_task     (queue: scheduled / urgent)
         ↓
┌─────────────────────────────────────────────────────────────┐
│ collector.search(keywords, since, max_results)              │
│   · arxiv   : 公开 API,可被 CN 网络阻断,有 timeout 兜底     │
│   · openalex: search= 顶层参数 + sort=relevance_score       │
│   · semantic: 无 key 时自动跳过(返回 429 立刻 abort)        │
│ ↓                                                            │
│ collector.download_pdf(raw)                                  │
│   · arxiv   : 直接抓 arxiv.org/pdf/                          │
│   · openalex: primary_location.pdf_url → locations[*]        │
│               → open_access.oa_url → Unpaywall DOI 兜底       │
│ ↓                                                            │
│ parser_pdf.parse_pdf(path)  →  ParsedPdf{sections, full_text}│
│   · PyMuPDF + 启发式 section regex,60s 硬超时               │
│ ↓                                                            │
│ chunker.split_sections(sections)                             │
│   · 每节 1 parent (≤ 2000 char) + N children (~600 char,    │
│     100 overlap)                                             │
│ ↓                                                            │
│ contextual_retrieval.generate_contexts_by_parent_idx         │
│   · 每个 parent 一次 LLM 调用,bilingual 系统提示             │
│   · 50-100 token 的"该段在论文里讲什么、起什么作用"          │
│ ↓                                                            │
│ embedder.embed_texts([context + "\n\n" + child for each])    │
│   · BAAI/bge-m3 1024-d via SiliconFlow,batch 16             │
│ ↓                                                            │
│ Postgres: parents 先 flush → children 写 parent_id ←─┐       │
│ Qdrant:   只 upsert children,payload {topic_ids,...} │       │
│ Documents.metadata_json["abstract_only"] = T/F        ←── flag│
└──────────────────────────────────────────────────────────────┘
```

**性能数字**(Wave-3 backfill 实测,Topic 2 = 24 篇 RAG 论文):
- 单文档全流程 ~5-30s(取决于页数)
- Topic 2 全量重建 ≈ **16 分钟**
- 产物:805 parents · 2927 children · 全部带 context_summary

### 3.2 检索(Retrieve)— 用户请求路径

```
user question
    ↓
query_router.classify_query   (LLM 1 次,Redis 7d 缓存,默认 synthesis)
    ↓ 分支
factual            comparison         synthesis / multi_step
(variants=1)       (variants=2)       (variants=3)
(no CRAG)          (+CRAG +GraphRAG)  (+CRAG +GraphRAG)
    ↓
query_rewrite.generate_variants   (LLM,multi-query 扩展)
    ↓ 并行 N 个变体
retrieve_for_topic per variant:
    ├─ Qdrant 向量搜索  (filter topic_ids contains, top_k=50)
    ├─ Postgres BM25    (WHERE is_parent=false + ts_rank_cd)
    └─ RRF fuse  (k=60)
    ↓
跨变体 union by chunk_id (best score)
    ↓
bge-reranker-v2-m3   (top_pool, top_n=5)
    ↓
final_score = rerank·0.8 + freshness·0.2
    ↓
CRAG 自评(verdict in {low,medium}? → 重写 query → 二次检索 → merge)
    ↓
GraphRAG 1-hop expansion via document_relations
    ↓
Parent-Child swap:
   对 top_n,将 child.text 替换为 parent.text(LLM 拿到节级上下文)
    ↓
Citations[]  →  下一步喂 LLM
```

### 3.3 生成(Generate)+ Self-RAG critique

```
build_messages(
  system     = base_system + chat_mode hint (default/mentor/beginner/debate/reviewer/what_if)
  user_research_context = chat_session_summaries 最近 3 条(长期记忆)
  pinned_notes          = 用户固定的笔记
  citations[]           = parent text + meta
  chat_history[]        = 最近 5 轮
  question
)
    ↓
llm_client.complete(messages)   →  initial_answer
    ↓ if route == multi_step (and non-streaming)
self_rag.critique_and_maybe_retry:
    judge_faithfulness(question, initial_answer, [c.text])
        → score 0..1, 哪些 claim 没被支持
    if score < 0.5:
        rewrite_query_for_unsupported  (LLM 1 次)
        retrieve_for_topic(rewritten, top_n=8)
        merge with original citations
        regenerate                     (LLM 1 次)
        re-judge (audit only)
    ↓
最终 answer + citations
    ↓
持久化 chat_messages.{content, citations_json}
    ↓ fire-and-forget
_maybe_dispatch_summary(session_id)   (60s Redis 节流 → Celery 任务异步总结)
```

### 3.4 评估(Eval)

```
rag_eval_questions[]
   (question, expected_chunk_ids[], tag, reference_answer?)
        ↓
run_eval._evaluate(db, topic_id):
   for q in questions:
      retrieved = retrieve_for_topic(q.question, top_n=20)
      metrics:
        · recall@5  = |expected ∩ top5| / |expected|
        · recall@20 = |expected ∩ top20| / |expected|
        · mrr       = 1 / first_rank(expected ∩ retrieved)
   aggregate + per_tag breakdown
        ↓
INSERT rag_eval_runs (commit_sha, metrics_json, notes)
        ↓
CLI : `python -m app.eval.run_eval --topic N --label baseline`
UI  : /admin/eval (sparkline + 表格 + per-run drawer + 触发按钮)
Seed: `python -m app.eval.seed_from_chunks --topic N --n 30` (LLM 反向生成)
      `python -m app.eval.seed_from_chats   --topic N --limit 30` (历史问答)
      `python -m app.eval.add_question     --topic N` (单题交互式)
```

**Wave-3 backfilled baseline**(30 题反向生成):
- Recall@5 = **0.434**
- Recall@20 = **0.667**
- MRR = **0.783**

后续任何 RAG 调整都对此基线 diff。

---

## 4. 功能模块清单

### 4.1 用户面

| 类别 | 功能 |
|---|---|
| **课题(topics)** | 多源采集 · 调度 · 关键词 · 配额 · 软删 · 重排 |
| **全局检索(/discover)** | LLM 翻译扩展(CJK→EN)+ bge 重排 · 任意源选入库 + 新建临时课题 |
| **课题问答(qa)** | 6 模式(default/mentor/beginner/debate/reviewer/what_if)· cross-topic · agent · streaming |
| **PDF 阅读** | 站内 react-pdf · 高亮/批注/笔记(回流到 research_notes)· DeepLX 选区翻译 · 缩放 / 适宽 |
| **智能模块** | Pulse 日报 · Reading Path · Insights(4 象限)· Trends 雷达 · Conflicts · Hypotheses · Comparisons · Writing · Glossary · Method Timeline · Knowledge Graph |
| **认证** | JWT + refresh rotate · 邮箱验证码注册(QQ SMTP)· INITIAL_ADMIN_EMAIL bootstrap |
| **通知** | 站内 + 邮件 · per-user opt-out · webhook 通道预留 |

### 4.2 管理员面

| 路径 | 功能 |
|---|---|
| `/admin/users` | 用户 CRUD · 禁用/启用 · 升降级 admin · 重置密码(临时密码邮件)· 群发 |
| `/admin/health` | Postgres / Redis / Qdrant / SMTP / Celery 5 组件状态 |
| `/admin/eval` | RAG 评估闭环:历史 run + sparkline + per-run 详情 + 触发按钮 |

### 4.3 后台模块(用户感知不到)

- **observability**:`llm_usage_logs` 记每次 LLM 调用的 prompt/completion tokens + latency + cost
- **`signal_service`**:每 6h Celery beat 重算 document_signals(突破信号);Pulse 卡片显示 🔥 角标
- **`memory_service`**:每 N 轮(默认 6)对话自动总结 → chat_session_summaries → 注入下次 system prompt
- **`crag`**:retrieval 阶段 LLM 自评 verdict 低于阈值则重写 + 重检索 + merge
- **`graphrag`**:1-hop 邻居扩展,基于 document_relations 表

---

## 5. RAG 五件套技术决策

| 维度 | 选 | 理由 | 替代方案 |
|---|---|---|---|
| **Chunking** | Parent-Child(~600/2000) | 论文章节天然层级;parent 给 LLM,child 给检索 | semantic chunking(NAACL 2025 实证不如固定);late chunking(要换 Jina 模型) |
| **Contextual** | per-parent LLM 一次(双语 prompt) | 80% 收益,10% 成本 | Anthropic 原版 per-child(贵) |
| **Embedding** | BAAI/bge-m3 1024-d via SiliconFlow | 中英 SOTA,多模式 | jina-embeddings-v3(可商用),OpenAI ada |
| **Sparse 检索** | Postgres ts_rank_cd | 已有 PG 不增成本 | SPLADE / Qdrant sparse vec |
| **Fusion** | RRF k=60 | 经典,免训练 | learning-to-rank |
| **Reranker** | bge-reranker-v2-m3 via SiliconFlow | 中英强,自托管友好 | jina-reranker-v3,cohere v4 |
| **Query Router** | LLM 1 次 + Redis 7d 缓存 | 训练成本 0,缓存命中后免费 | BERT/T5 分类器(要标注) |
| **Self-RAG** | 仅 multi_step 路由 + non-streaming + 1 次重试 | 成本可控,UX 不破坏 | 全部走 / 多轮迭代(贵) |
| **PDF 解析** | PyMuPDF | 轻量稳定;Docling 安装失败回滚 | Docling(IBM,结构更全,但 1.5G 依赖) |
| **评估** | Recall@K + MRR(结构指标) | 确定性,无额外 LLM 调用 | RAGAS faithfulness(已实现,默认关) |
| **翻译** | DeepLX(用户自托管) | DeepL 质量稳,Redis 30d 缓存 | LLM 直翻(贵) |
| **邮件** | QQ SMTP 465 | 腾讯云内地→Gmail 被墙,QQ 国内稳 | Gmail / 阿里云邮件推送 |

---

## 6. 关键约束与失败模式

### 6.1 已知边界

| 情景 | 行为 |
|---|---|
| arxiv 网络阻断 | 35s timeout → 切 OpenAlex |
| OpenAlex 无 OA PDF | 进 Unpaywall 兜底;还失败 → 仅摘要,标 `abstract_only=true` UI 显示"仅摘要" pill |
| Semantic Scholar 无 key | 429 立即 abort,从 discover 默认源剔除 |
| DeepLX 未配 | 翻译按钮 UI 自动隐藏(GET /translate/status) |
| SMTP 未配 | 验证码改打 backend log,admin 重置密码弹临时密码 modal |
| LLM 翻译/分类/critique 失败 | 各组件优雅退化,主流程不阻塞 |
| Self-RAG 重试仍不通 | 返回首答 + audit dict |
| PDF 解析超时(60s) | 走 abstract-only 路径 |

### 6.2 安全

- JWT access ≤ 30 min + refresh ≤ 7d,刷新 rotate
- Admin 守卫:`CurrentAdminDep` 二级判定;admin 不能自删/自降/自禁
- 限流:slowapi `default / register / login` 三档 IP 限流
- 输入:Pydantic v2 + slowapi + 字段长度 cap
- 密码:bcrypt;refresh token 哈希后存表
- 邮箱验证码:6 位 · 60s cooldown · 5/天 · 10 min TTL(Redis)
- 路由权限:`/admin/*` + `/admin/eval/*` 全部 CurrentAdminDep

---

## 7. 部署 / 运维

### 7.1 服务器

- 单机:腾讯云 `49.233.190.200`(VM-0-13-centos)
- 7 容器 docker compose,bind-mount `./backend` / `./frontend` 支持热重载
- Postgres 在宿主(`pg-taskrag`,host network)
- 部分数据(/data/pdfs, /data/fulltext)用 docker volume

### 7.2 同步与发布

代码改 → 本地 commit → push origin/main → 服务器 git pull → docker compose up -d --force-recreate(若有迁移会自动跑 alembic upgrade head)。

为了快速迭代,大多数 dev 走 scp tar + docker restart 直接替换 bind-mount 内的文件,vite HMR 自动刷新,backend 需 restart。

### 7.3 关键 env

```
JWT_SECRET_KEY               # 启动校验,prod 必填非默认
DATABASE_URL / SYNC_DATABASE_URL / REDIS_URL / QDRANT_URL
EMBEDDING_PROVIDER=siliconflow + EMBEDDING_MODEL=BAAI/bge-m3
DEEPSEEK_API_KEY / QWEN_API_KEY / SILICONFLOW_API_KEY
GMAIL_SMTP_HOST=smtp.qq.com  GMAIL_SMTP_PORT=465
GMAIL_USERNAME / GMAIL_APP_PASSWORD / EMAIL_FROM    # 实际是 QQ 凭证
DEEPLX_BASE_URL=https://api.deeplx.org/<token>
INITIAL_ADMIN_EMAIL=...      # 启动时 promote 该 user 为 admin
```

### 7.4 监控

- `/admin/health` 五组件状态 + 30s 自动刷新
- `llm_usage_logs` 表:每次 LLM 调用的 tokens / latency / feature
- Prometheus `/metrics` 端点(可选启用)
- Sentry(可选)
- `docker logs task_rag-backend-1` 结构化日志(structlog JSON)

### 7.5 备份(目前没自动化)

需要手工:
- `pg_dump taskrag` 至少每周
- /data/pdfs · /data/fulltext 同步备份
- Qdrant `snapshots` API

---

## 8. 设计决策记录(部分)

| ID | 决策 | 时间 | 理由 |
|---|---|---|---|
| ADR-001 | bge-m3 over jina-v3 | Wave-2 | 中英 SOTA + SiliconFlow 已接入,jina 要换 provider |
| ADR-002 | Parent-Child 优先于 Late Chunking | Wave-3 | 保留 bge-m3;parent FK 简单;Anthropic 验证有效 |
| ADR-003 | Contextual 走 per-parent 而非 per-child | Wave-3 | 单文档 LLM 调用 5-10 次 vs 50-100,成本 1/10,效果保 80% |
| ADR-004 | Query Router 用 LLM 而非 BERT | Wave-3 | 无训练数据;LLM zero-shot 已足够,Redis 命中后免费 |
| ADR-005 | Self-RAG 仅 non-streaming | Wave-3.5 | 流式无法回退已发 token;`multi_step` 路由用户感知到延迟可接受 |
| ADR-006 | 评估走结构指标而非 RAGAS faithfulness | Wave-3 | 确定性可重复;LLM 评判作为 Self-RAG 已用,evaluation 不再付费 |
| ADR-007 | Docling 撤销 | Wave-3.5 | 腾讯云 → PyPI 装 1.5G 失败;PyMuPDF 满足绝大多数学术论文 |
| ADR-008 | OpenAlex 用 `search=` 顶层而非 filter | Wave-2.5 | filter 模式无相关性评分;search= 触发 TF-IDF + 真实 ranking |
| ADR-009 | Atelier 日间主题 | Wave-2 | 与 Quiet Intelligence 镜像对称,同字体同 grain |
| ADR-010 | QQ SMTP 465 over Gmail 587 | Wave-2 | GFW 对 smtp.gmail.com:587 不稳定;465 也时通时不通;QQ 全程国内 |

---

## 9. 已知限制 / 后续路线

### 9.1 本轮明确不做(已收口)

- ❌ Docling 替换 PyMuPDF(装失败,撤回)
- ❌ Late Chunking / 切换 Jina embedding(模型迁移代价大)
- ❌ ColBERT v2 / SPLADE 多向量(基础设施改动大)
- ❌ 协作 / 多用户课题分享(单用户够用)
- ❌ 移动端响应式
- ❌ 多语言(en-US)
- ❌ 移动端 App
- ❌ 自动备份策略(手动周备)

### 9.2 可选下一轮

| 候选 | 价值 | 量级 |
|---|---|---|
| **Faithfulness LLM judge 写入 eval pipeline** | 评估覆盖生成质量 | S |
| **LongLLMLingua 上下文压缩** | LLM token 成本节省 | M |
| **HyDE 假设答案嵌入(factual 路由)** | factual 查询 recall 可能再提 | S |
| **Docling via 远程 docling-serve 微服务** | 公式/表格论文质量 | M |
| **OpenAlex citation velocity → signal** | 让 🔥 突破信号有外部信号源 | M |
| **协作 + 公开分享(只读链接)** | 扩团队 | L |
| **移动端响应式** | 通勤场景 | M |

---

## 10. 当前数据快照

```
Topic 2 "RAG"
├── 24 documents (23 with PDF + full-text parsed; 1 abstract-only)
├── 805 parent chunks (section-sized, no embeddings)
├── 2,927 child chunks (all with context_summary, all in Qdrant)
├── 30 golden-set questions
└── 评估基线: recall@5=0.434, recall@20=0.667, MRR=0.783

Server (49.233.190.200)
├── 7 containers, 5 days uptime
├── /data/pdfs 49 MB
├── Qdrant 2951 points
└── Postgres 16 migrations applied
```

---

## 11. 仓库布局

```
task_rag/
├── backend/
│   ├── app/
│   │   ├── api/routes/     # FastAPI 路由层(auth · topics · qa · agent · admin · admin_eval · ...)
│   │   ├── core/           # config · errors · logging · observability · security
│   │   ├── collectors/     # arxiv · openalex · semantic_scholar(含 download_pdf)
│   │   ├── indexer/        # parser_pdf · chunker · embedder · ingest_service · qdrant_client
│   │   ├── rag/            # llm_client · prompt · reranker · retriever · query_router · chat_modes
│   │   ├── services/       # qa_service · crag · graphrag · self_rag · contextual_retrieval · memory_service · ...
│   │   ├── tasks/          # collect_tasks · research_tasks · schedule_tasks · celery_app
│   │   ├── db/             # models · repositories · session · base
│   │   ├── schemas/        # Pydantic
│   │   ├── notifications/  # email · inapp · workflow
│   │   ├── eval/           # metrics · run_eval · seed_from_chunks · seed_from_chats · add_question · faithfulness
│   │   └── tests/unit/     # pytest 关键路径覆盖
│   ├── alembic/versions/   # 0001..0016
│   ├── scripts/            # backfill_chunks 等运维脚本
│   ├── alembic.ini · Dockerfile · pyproject.toml
│
├── frontend/
│   ├── src/
│   │   ├── api/            # axios 客户端 · 类型
│   │   ├── components/     # Page transitions · ChatPanel · PdfReader · SearchPickerModal · TopicMapTab · ...
│   │   ├── pages/          # TopicListPage · TopicDetailPage · DiscoverPage · AdminUsersPage · AdminEvalPage · ...
│   │   ├── stores/         # zustand: auth · theme
│   │   ├── styles/         # globals.css (Quiet Intelligence / Atelier)
│   │   └── utils/          # chatModes · sse
│   ├── public/ · vite.config.ts · package.json · Dockerfile
│
├── docs/
│   ├── ARCHITECTURE.md    ← 本文
│   └── PROJECT_OVERVIEW.md
│
├── docker-compose.yml  · docker-compose.server.yml
├── .env / .env.example / .env.server
└── README.md
```

---

**这份文档是 Wave-3.5 收尾点的快照。任何后续修改要么补到 §9.2,要么写新 ADR。**
