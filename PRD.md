# PRD: 课题追踪 RAG 系统（TaskRAG）

| 项目 | 内容 |
|---|---|
| 文档版本 | v0.3（演示版定稿草稿） |
| 创建日期 | 2026-05-15 |
| 更新日期 | 2026-05-15 |
| 状态 | Draft，待评审 |

> **v0.3 关键变更**
> 1. 明确为**演示产品**（Demo），而非生产环境部署 → 砍掉过度工程（监控/备份/HA/MFA 等）。
> 2. **文档全局去重**：documents 与 chunks 跨用户共享，topic 通过 M:N 关联表引用。
> 3. **PDF 全文解析**确认入选（PyMuPDF）。
> 4. **通知按工作流抽象**：可插拔 channel chain（InApp → Email → Webhook）。
> 5. 课题上限 **5**、回填 **30 天**、邮件用 **Gmail App Password + SMTP**（免费）。

---

## 1. 项目背景与目标

### 1.1 背景
AI、计算机视觉、机器学习等领域演进极快，研究人员往往聚焦在某个细分方向（如"立体匹配"、"RLHF"），需要持续追踪。当前痛点：
- **检索重复**：手动在 arXiv / Google Scholar 反复搜索同一组关键词，效率低；
- **缺乏沉淀**：搜到的论文散落各处，难以基于历史积累做关联性问答；
- **更新被动**：靠"想起来才搜"，容易错过关键进展。

### 1.2 项目目标
构建一个**个人化、按课题组织**的演示级 RAG 系统：
1. **多用户**：每个用户拥有独立账户，课题与会话隔离；
2. **课题驱动采集**：用户按课题（如"立体匹配"）配置关键词，系统每日自动检索并向量化；
3. **课题级问答**：在课题知识库中提问，获得带引用来源的回答；
4. **任务状态推送**：采集完成后通过工作流通知用户（站内 + 邮件）。

### 1.3 非目标（Out of Scope）
- 不做生产级 SLA、监控、备份、HA；
- 不做模型微调；
- 不做付费订阅、用户分级；
- 不做团队协作 / 知识库共享 UI；
- 不爬取付费墙 / 登录墙内容。

### 1.4 产品定位：Demo
本项目为**演示产品（Proof of Concept）**：
- 目标是让评审者/观众能完整体验"注册 → 创建课题 → 自动采集 → 问答 → 收到通知"的闭环；
- 默认部署为**单机 Docker Compose**，所有依赖容器化；
- 优先选用**免费/开源**组件（bge-m3 本地 embedding、Gmail SMTP、Qdrant 社区版）；
- 提供**演示账号 + 演示数据种子**（预填 2-3 个课题如"立体匹配"、"RAG"、"扩散模型"，含已采集论文若干）。

### 1.5 核心概念
| 概念 | 说明 |
|---|---|
| **User** | 注册用户，拥有独立账号、课题、会话 |
| **Topic** | 用户创建的研究课题，定义关键词 / 数据源 / 调度；单用户最多 5 个 |
| **Document** | 一条采集结果（论文 / Repo / 博客）。**全局唯一**，不属于任一用户 |
| **TopicDocument** | Topic 与 Document 的 M:N 关联，记录"哪个课题引用了这条文档" |
| **CollectionTask** | 课题的采集任务，定时或手动触发 |
| **NotificationWorkflow** | 通知派发流程，链式经过 InApp → Email → (Webhook) |

---

## 2. 目标用户与场景

### 2.1 用户画像
| 角色 | 核心诉求 |
|---|---|
| 在读研究生 | 跟踪导师指定方向的所有新论文 |
| AI 工程师 | 同时关注多个技术方向 |
| 评审/观众（演示场景）| 通过演示账号快速理解产品价值 |

### 2.2 典型场景
- **场景 A（首次使用）**：用户注册 → 创建课题"立体匹配" → 填关键词 + 选数据源 + 设调度 → 系统立即跑首次采集（含 30 天回填）→ 完成后通知。
- **场景 B（日常追踪）**：每天 09:00 自动采集 → 09:15 用户收到"新增 7 篇论文" 通知。
- **场景 C（问答）**：进入课题 → 提问 → **仅在该课题知识库中**检索 → 返回带引用的答案。
- **场景 D（多课题切换）**：用户的多个课题之间，会话与召回完全独立。
- **场景 E（演示）**：评审用 `demo / demo123` 登录 → 看到 3 个预填课题，每个有真实论文 → 体验问答与通知。

---

## 3. 功能需求

### 3.1 用户与认证（Auth）
- 注册：邮箱 + 密码；
- 登录：JWT（Access 30 min + Refresh 7 d）；
- 密码加密：bcrypt；
- 用户隔离：所有 API 强制以 `user_id` 维度过滤（Repository 层注入）；
- 演示账号：内置 `demo@example.com / demo123`，启动脚本自动 seed。

### 3.2 课题管理（Topic）
- CRUD：创建 / 编辑 / 删除（删除时仅清理 `topic_documents` 关联与该课题的 sessions/tasks，**不删 documents**）；
- 配置项：
  - 名称、描述；
  - **关键词列表**（多个，每个独立查询后合并去重）；
  - **数据源选择**（多选）；
  - **调度配置**（每日/每周 + 时间，可暂停）；
  - **采集深度**：`max_results_per_source_per_run`，默认 20；
- 状态：`active` / `paused`；
- **限制：单用户最多 5 个课题**（硬限制）；
- **回填**：首次创建课题时回溯 **30 天**（固定）。

### 3.3 数据采集（DataCollector）

#### 3.3.1 采集模式：课题驱动
所有采集均由 Topic 关键词驱动——以课题关键词为查询条件，调用各数据源的搜索 API，只下载匹配结果。

#### 3.3.2 数据源清单
| 来源 | 接入方式 | 全文获取 | 优先级 |
|---|---|---|---|
| arXiv | `arxiv` Python 库（官方 API） | **PDF 下载 + PyMuPDF 解析全文** | P0 |
| HuggingFace Papers | HF Hub API | 摘要 | P0 |
| GitHub | GitHub Search API（repos）| README + 元数据 | P0 |
| Semantic Scholar | Semantic Scholar API（免费） | 摘要 + 部分全文 | P1 |
| RSS（机器之心 / 量子位）| RSS + 关键词过滤 | 网页正文（readability）| P1 |
| 用户手动上传（PDF / URL） | Web 表单 | PyMuPDF / readability | P1 |

#### 3.3.3 采集器要求
- 统一接口：`search(keywords, since, max_results) -> List[RawDocument]`；
- **全局去重**：以 `(source, external_id)` 主键判定，已存在则只新增 `topic_documents` 关联；
- 速率限制：每个数据源独立 token bucket（Redis）；
- 失败重试：指数退避，最多 3 次。

#### 3.3.4 PDF 全文解析
- 工具：PyMuPDF（fitz）；
- 解析后产出：`page_blocks: [{page_num, text, bbox}]`；
- 章节识别：基于字号 + 加粗启发式切分（Title / Section / Body）；
- 体积控制：单文档解析后纯文本超 200KB 截断（Demo 阶段够用）。

### 3.4 数据处理与向量化（Indexer）
- 文本清洗：去 HTML / Markdown 噪声、归一化空白；
- 分块：默认 `RecursiveCharacterTextSplitter`，chunk_size=800，overlap=100；论文按章节优先；
- Embedding：默认 **bge-m3**（本地，免费），可选切换 OpenAI；
- 写入 Qdrant：
  - **单 collection（`documents`）+ 全局共享**；不再按用户/课题分；
  - 每个 chunk 的 payload：
    - `document_id`（指向 PG 中的 documents 表）
    - `topic_ids: int[]`（哪些课题引用了它）
    - `source`、`published_at`
  - 在 `topic_ids`、`published_at` 上建 payload index；
- 当某文档被新课题引用时：**只更新 payload 的 `topic_ids` 数组**，不重新向量化。

### 3.5 调度与动态更新（Scheduler）

#### 3.5.1 定时增量更新
- 每个 Topic 一个调度任务（Celery Beat + DB-backed schedule，支持运行时增删）；
- 任务粒度：`(topic, source)` 拆分并行；
- 增量水位：`last_fetched_at` per `(topic, source)`，每次只拉新窗口。

#### 3.5.2 事件驱动更新
- 触发：UI 点击"立即采集" / 上传文档 / 修改关键词；
- 延迟目标：触发到可检索 ≤ 60s。

#### 3.5.3 混合优先级队列
- Celery 多队列：
  - `urgent`（用户主动触发）
  - `scheduled`（每日定时）
  - `backfill`（首次创建课题的 30 天回填）
- urgent 独立 worker，避免被批量任务阻塞。

### 3.6 检索与问答（RAG Engine）
- **强制隔离**：检索前先校验 topic 归属用户，向 Qdrant 传 `topic_ids contains <topic_id>` 过滤；
- 框架：LangChain（LCEL）；
- 检索：向量召回 top_k=20 → 时间衰减加权 + Cross-Encoder rerank → top_n=5；
- LLM：默认 **Claude Sonnet 4.6**（Demo 控制成本可降级 Haiku），可切换 OpenAI；
- Prompt：
  - 必须基于检索上下文回答，无信息时如实告知；
  - 输出：先结论 → 要点 → **引用列表**（标题 + URL + 发布日期）；
- 多轮：session 与 topic 绑定，保留最近 5 轮上下文。

### 3.7 通知工作流（NotificationWorkflow）

#### 3.7.1 工作流抽象
通知派发设计为**链式工作流**，每个 channel 是独立步骤，可启用/跳过：

```
event(task_done, task_failed, system)
   ↓
[NotificationWorkflow]
   ├─ Step 1: InAppChannel       (始终启用)
   ├─ Step 2: EmailChannel       (用户开关)
   └─ Step 3: WebhookChannel     (用户配置 URL，v2)
```

每个 channel 实现统一接口：
```python
class NotificationChannel:
    def send(self, user: User, event: NotificationEvent) -> ChannelResult
```

#### 3.7.2 v1 实现的 Channel
| Channel | 实现 | 备注 |
|---|---|---|
| InApp | 写入 `notifications` 表 + 前端徽标 | 必启用 |
| Email | **Gmail SMTP + App Password**（免费）；HTML 模板 | 用户可关 |
| Webhook | 占位（v2） | 留接口，便于后续接入 n8n/飞书机器人/Slack |

#### 3.7.3 事件类型
- `task_done` — 采集完成（payload: 课题、新增数）；
- `task_failed` — 采集失败（payload: 课题、错误摘要）；
- `system` — 系统消息。

### 3.8 前端 UI（React）

#### 3.8.1 页面清单
| 页面 | 核心功能 |
|---|---|
| 登录 / 注册 | 邮箱密码；演示账号一键填充 |
| 课题列表（首页） | 我的课题卡片（最近更新数、最近采集时间）；新建课题入口；课题数 N/5 提示 |
| 课题详情 | Tabs：问答 / 知识浏览 / 任务记录 / 课题设置 |
| └ 问答 Tab | 对话 UI + 引用面板 |
| └ 知识浏览 Tab | 文档列表，按时间/来源筛选，点击查看解析后的全文 |
| └ 任务记录 Tab | 历次采集任务，状态、新增数、可重跑 |
| └ 课题设置 Tab | 关键词、数据源、调度、删除课题 |
| 通知中心 | 消息列表，标记已读 |
| 个人设置 | 修改密码、邮件通知开关、模型切换 |

#### 3.8.2 技术选型
- React 18 + TypeScript + Vite；
- Ant Design 5；
- Zustand + TanStack Query；
- 流式输出：SSE。

---

## 4. 系统架构

```
┌──────────────────────────────────────────────────────────┐
│                  React Frontend (UI)                      │
└──────────────────────┬───────────────────────────────────┘
                       │ REST / SSE  (JWT)
┌──────────────────────▼───────────────────────────────────┐
│              FastAPI Backend (API Gateway)                │
│  Auth │ Topic │ Doc │ QA │ Task │ Notification │ Setting  │
└────────┬───────────────────┬───────────────┬────────────┘
         │                   │               │
┌────────▼─────────┐ ┌───────▼──────┐ ┌──────▼────────────────┐
│   RAG Engine     │ │   Indexer    │ │  NotificationWorkflow │
│  (LangChain)     │ │              │ │  InApp → Email → ...  │
└────────┬─────────┘ └───────┬──────┘ └──────┬────────────────┘
         │                   │               │
┌────────▼───────────────────▼───────────────▼──────────┐
│              Async Worker Layer (Celery)               │
│   urgent  │  scheduled  │  backfill                    │
└────────┬─────────────────────────────────────┬────────┘
         │                                     │
┌────────▼────────────────────┐    ┌───────────▼────────┐
│       Data Collectors       │    │   Beat Scheduler   │
│ arXiv │ HF │ GitHub │ S2 │..│    │  (per-topic jobs)  │
└─────────────────────────────┘    └────────────────────┘

存储层（全部 Docker Compose）：
  - Qdrant       向量库（payload 过滤 topic_ids 实现隔离）
  - PostgreSQL   用户、课题、文档元数据、任务、通知、消息
  - Redis        队列、缓存、rate limiter
  - 本地 FS      论文 PDF 原件（演示用，挂载 volume）
```

---

## 5. 数据模型（核心表）

> v0.3 重要变化：documents/chunks 全局共享，通过 `topic_documents` 关联。

| 表 | 关键字段 | 备注 |
|---|---|---|
| `users` | id, email, password_hash, created_at, settings_json | settings 含邮件开关、模型偏好 |
| `topics` | id, **user_id**, name, description, keywords[], sources[], schedule_cron, max_results, enabled, created_at | 单用户最多 5 行 |
| `documents` | id, source, external_id, title, authors, published_at, url, abstract, content_hash, doc_version, full_text_path, created_at | **全局共享，无 user_id** |
| `chunks` | id, document_id, text, vector_id, chunk_index | **全局共享** |
| `topic_documents` | topic_id, document_id, matched_keyword, added_at | **M:N 关联**，PK=(topic_id, document_id) |
| `collection_tasks` | id, topic_id, source, trigger, started_at, finished_at, status, new_docs_count, error_msg | trigger ∈ {scheduled, manual, upload} |
| `notifications` | id, user_id, type, title, body, read_at, created_at | InApp 渠道落表 |
| `chat_sessions` | id, user_id, topic_id, title, created_at | |
| `chat_messages` | id, session_id, role, content, citations_json, created_at | citations 为 document_id 引用 |

**唯一约束**：
- `documents (source, external_id)`
- `topics (user_id, name)`
- `topic_documents (topic_id, document_id)` PK

**关键查询路径**：
- 用户访问课题文档：`topics → topic_documents → documents`，权限校验在 `topics.user_id`；
- 向量检索：Qdrant 过滤 `topic_ids contains <id>`，检索结果回到 PG 查 `documents` 详情。

---

## 6. 技术栈

| 层 | 选型 | 免费 |
|---|---|---|
| 前端 | React 18 + TS + Vite + Ant Design 5 + Zustand + TanStack Query | ✅ |
| 后端 API | Python 3.11 + FastAPI + Pydantic v2 + SQLAlchemy 2 | ✅ |
| 鉴权 | JWT（python-jose）+ bcrypt | ✅ |
| RAG 框架 | LangChain | ✅ |
| 向量库 | Qdrant（社区版 Docker） | ✅ |
| 元数据库 | PostgreSQL 16 | ✅ |
| 缓存/队列 | Redis 7 | ✅ |
| 异步任务 | Celery + Celery Beat（DB-backed schedule） | ✅ |
| Embedding | **bge-m3**（本地） | ✅ |
| LLM | Claude Sonnet 4.6 / Haiku 4.5（备选） | API 计费 |
| 文档解析 | PyMuPDF（PDF）、readability-lxml（HTML） | ✅ |
| 邮件 | **Gmail SMTP + App Password** | ✅（每日 500 封限额，演示足够） |
| 部署 | Docker Compose | ✅ |

---

## 7. 非功能需求（演示版）

| 维度 | 要求 |
|---|---|
| 性能 | 问答首 token ≤ 5s；检索 ≤ 1s（Demo 体感够用） |
| 可用性 | 单机部署；进程崩溃由 Docker restart 兜底；不追求 SLA |
| 时效性 | 事件驱动入库 ≤ 60s |
| **数据隔离** | 所有跨用户查询必须带 `user_id` 过滤；写测试用例 |
| 数据合规 | 遵守各源 ToS / robots.txt；不采付费墙内容 |
| 安全 | 密码 bcrypt；JWT；ORM 防 SQL 注入；XSS 转义 |
| 监控 | **Out of scope**（演示不需要）|
| 备份 | **Out of scope**（演示不需要）|

---

## 8. 里程碑

| 阶段 | 周期 | 交付内容 |
|---|---|---|
| **M1：单用户基线** | Week 1-2 | 用户登录 + Topic CRUD + arXiv 采集器（含 PDF 全文解析）+ Qdrant 入库 + 课题级问答（Swagger 验证）|
| **M2：调度与通知** | Week 3 | Celery 调度（每 Topic 独立）+ 任务记录 + NotificationWorkflow（InApp + Gmail SMTP）|
| **M3：完整前端** | Week 4-5 | React 全部页面、问答流式输出、知识浏览、通知中心、设置 |
| **M4：数据源扩展 + 演示打磨** | Week 6 | HuggingFace + GitHub + Semantic Scholar + RSS + 用户上传；演示账号与种子数据 |
| **M5：单机部署** | Week 7 | Docker Compose 一键启动；README 演示脚本 |

> 砍掉了 v0.2 的 M5 上云监控；演示阶段单机即可。如有云演示需求，最后追加一个 1-2 天的 nginx + 域名打包步骤即可。

---

## 9. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 用户隔离漏配 | 数据泄露 | Repository 层强制 `user_id` 注入；隔离测试用例覆盖 |
| LLM API 成本超预期 | 演示费用失控 | Demo 默认用 Haiku；问答开 Prompt Cache；按 IP 限频 |
| arXiv PDF 解析慢/失败 | 首批回填卡住 | 解析超时 30s 跳过；失败入死信队列；只索引 abstract 兜底 |
| Gmail SMTP 限额 | 通知发不出 | 演示账号用单独 Gmail；超限降级仅 InApp |
| 数据源反爬 / 封 IP | 数据中断 | 优先官方 API；UA 池 + rate limit |
| Qdrant `topic_ids` 数组过滤性能 | 检索变慢 | 在 `topic_ids` 上建 keyword payload index；Demo 数据量下不是问题 |
| 演示当天网络不稳定 | 现场翻车 | 准备本地完整数据快照；可离线展示静态结果 |

---

## 10. 已确认决策（v0.3 收口）

| # | 决策 |
|---|---|
| 1 | 单用户课题数上限 = **5** |
| 2 | 首次回填深度 = **30 天** |
| 3 | 文档跨课题/跨用户 **全局去重共享**（M:N 关联）|
| 4 | 邮件通道 = **Gmail SMTP + App Password**；通知按工作流抽象（InApp → Email → Webhook 预留）|
| 5 | arXiv 论文 **解析全文 PDF**（PyMuPDF）|
| 6 | 项目定位 = **演示产品**，单机 Docker Compose；不做监控/备份/HA |

---

## 11. 演示脚本（建议）

1. 用 `demo@example.com / demo123` 登录 → 看到 3 个预填课题；
2. 点开"立体匹配" → 展示已采集论文（含全文）；
3. 在问答 Tab 提问"最近用 Transformer 做立体匹配的工作有哪些？" → 流式输出 + 引用面板；
4. 切到"任务记录" → 点"立即采集" → 30s 内出新增条目通知；
5. 切到通知中心 → 展示 InApp 通知；演示者邮箱收到 HTML 邮件；
6. 新建一个课题"NeRF" → 配置后立即触发回填 → 完成后通知；
7. 切回"立体匹配"展示问答上下文独立。
