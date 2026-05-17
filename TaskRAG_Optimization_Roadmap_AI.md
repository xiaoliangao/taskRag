# TaskRAG 优化与拓展开发文档（AI 实现版）

| 项目 | 内容 |
|---|---|
| 文档类型 | Markdown / 工程实现说明 |
| 面向对象 | AI Coding Agent、后端/前端开发者 |
| 适用阶段 | Demo v1 已完成后的 v1.1 / v1.2 / v1.3 优化 |
| 当前版本 | v1.0 |
| 核心目标 | 让 TaskRAG 从“可演示的课题 RAG”升级为“有生命感的个人研究助手” |
| 基于文档 | `PRD.md` v0.3、`TaskRAG_AI_Development_Document.md` v1.0 |

---

## 0. 给 AI 开发代理的执行原则

本文件不是产品创意清单，而是 **Demo v1 之后的优化开发说明**。AI Coding Agent 在实现时必须遵守以下原则。

### 0.1 保留 v1 的架构边界

1. **继续以 Topic 为核心边界**：所有 Pulse、阅读路径、Gap、图谱、草稿、记忆都必须绑定到 `topic_id`。
2. **继续保证用户隔离**：任何 Topic 级数据读取前必须校验 `topics.user_id = current_user.id`。
3. **继续保持 documents / chunks 全局共享**：不要把 `user_id` 加入 `documents` 或 `chunks`。用户私有状态通过新增用户态表表达。
4. **继续使用 Celery 异步生成重任务**：Briefing、Pulse、Gap、Graph、Trend、Contradiction 不允许阻塞普通 API 请求。
5. **继续使用 Qdrant 的 `topic_ids` 过滤**：所有检索类能力必须按当前 Topic 过滤后再生成。
6. **不要过早生产化**：不引入复杂监控、HA、备份、计费、团队权限。当前目标是增强产品体验和研究价值。

### 0.2 本阶段的产品方向

v1 已经解决：

```text
注册 / 登录 → 创建课题 → 自动采集 → 解析入库 → 课题问答 → 通知
```

下一阶段要解决：

```text
系统主动发现 → 帮用户判断优先级 → 组织阅读路径 → 发现研究空白 → 生成研究产物
```

一句话目标：

> 让用户每天打开 TaskRAG 时感觉“它昨晚又帮我做了一些研究工作”。

### 0.3 AI 实现时的优先顺序

如果资源有限，严格按以下顺序实现：

1. **Paper Briefing**：每篇论文的一键结构化解读。
2. **Research Pulse**：每日 Topic 简报。
3. **Reading Path**：新 Topic 的阅读路径规划。
4. **Research Gap Finder**：研究空白发现。
5. **Related Work Draft**：相关工作草稿生成。
6. **Conversation Memory + Notes**：对话记忆、Pin、研究备忘录。
7. **Knowledge Graph / Method Timeline**：图谱和方法演化可视化。
8. **Trend Radar**：趋势雷达。
9. **Contradiction Detector**：矛盾检测器，作为高阶 Alpha 能力。

---

## 1. 优化目标与版本规划

### 1.1 产品优化目标

| 目标 | 说明 | 对用户的感受 |
|---|---|---|
| 主动性 | 系统不只等用户提问，而是主动生成简报、提醒变化、推荐阅读 | “它在帮我盯进展” |
| 判断力 | 系统能判断论文重要性、阅读优先级、潜在研究空白 | “它不只是搬运摘要” |
| 可视化 | 系统把论文关系、方法演化、趋势变化展示出来 | “我的研究领域被看见了” |
| 研究产出 | 系统能生成 Related Work、对比表、研究备忘录 | “它能帮我推进论文写作” |
| 可信度 | 所有结论都可追溯到文档、chunk、引用 | “我知道它为什么这么说” |

### 1.2 版本拆分

| 版本 | 名称 | 核心交付 | 不做什么 |
|---|---|---|---|
| v1.1 | 研究助手唤醒版 | Paper Briefing、Research Pulse、阅读状态、简报通知 | 不做复杂图谱和矛盾检测 |
| v1.2 | 研究 Agent 增强版 | Reading Path、Gap Finder、Related Work Draft、对话 Pin | 不做团队协作 |
| v1.3 | 知识可视化与趋势版 | Paper Graph、Method Timeline、Trend Radar MVP | 不追求大规模数据分析平台 |
| v1.4 Alpha | 高阶推理版 | Contradiction Detector、What-if、辩论模式 | 不把推断当事实 |
| v2 | 产品化 | Workspace、共享、Webhook 实发、对象存储、正式监控 | 不在当前文档展开 |

---

## 2. 总体架构增量

### 2.1 新增能力层

在 v1 架构上新增 `Research Intelligence Layer`。

```text
React Frontend
  ├─ Topic Dashboard
  ├─ Research Pulse Panel
  ├─ Paper Briefing Drawer
  ├─ Reading Path View
  ├─ Research Gap View
  ├─ Related Work Writer
  ├─ Notes / Pins
  └─ Graph / Timeline Views

FastAPI Backend
  ├─ Existing: Auth / Topic / Doc / QA / Task / Notification
  └─ New:
      ├─ Briefing API
      ├─ Pulse API
      ├─ Reading Path API
      ├─ Insight API
      ├─ Writing Draft API
      ├─ Research Note API
      ├─ Entity / Trend API
      └─ Graph API

Celery Workers
  ├─ urgent
  ├─ scheduled
  ├─ backfill
  └─ intelligence   # 新增，负责分析型任务

Research Intelligence Layer
  ├─ Paper Briefing Generator
  ├─ Research Pulse Generator
  ├─ Reading Path Planner
  ├─ Research Gap Analyzer
  ├─ Related Work Composer
  ├─ Entity / Method Extractor
  ├─ Trend Analyzer
  └─ Contradiction Analyzer

Storage
  ├─ PostgreSQL: 新增结构化研究智能表
  ├─ Qdrant: 继续用于 chunk 召回与 topic 过滤
  └─ Local FS: 可继续保存 PDF、fulltext、导出草稿
```

### 2.2 新增 Celery 队列

新增一个队列：

```text
intelligence
```

用途：

- 生成 Paper Briefing
- 生成 Research Pulse
- 生成 Reading Path
- 生成 Research Gap
- 提取 Method / Entity / Claim
- 生成 Related Work Draft
- 计算 Trend Radar
- 计算 Contradiction Detector

推荐路由：

| 任务 | 队列 | 触发方式 |
|---|---|---|
| `generate_document_briefing_task` | intelligence | 新文档入库后 / 用户点击 |
| `generate_topic_pulse_task` | intelligence | 每日定时 / 采集完成后 |
| `generate_reading_path_task` | intelligence | Topic 创建后 / 用户手动刷新 |
| `generate_research_gaps_task` | intelligence | 用户点击 / 每周定时 |
| `generate_related_work_draft_task` | urgent 或 intelligence | 用户点击，优先 urgent |
| `extract_topic_entities_task` | intelligence | 新文档入库后批处理 |
| `compute_topic_trends_task` | intelligence | 每日定时 |
| `detect_contradictions_task` | intelligence | 每周定时 / 手动触发 |

### 2.3 统一生成状态

所有 AI 生成结果建议使用统一状态枚举：

```text
pending
running
success
failed
stale
cancelled
```

说明：

- `pending`：任务已创建，等待执行。
- `running`：正在生成。
- `success`：生成完成。
- `failed`：生成失败。
- `stale`：底层文档更新后结果过期，需要重新生成。
- `cancelled`：用户取消或系统跳过。

---

## 3. 数据模型增量设计

本节是 AI 实现的核心约束。新增表要尽量保持：

- 全局文档分析结果全局共享。
- 用户阅读状态用户私有。
- Topic 洞察和简报 Topic 私有。
- 所有用户可见结果都必须通过 Topic 权限校验。

### 3.1 全局文档分析表：`document_briefings`

用于存储每篇 Document 的结构化解读。因为 `documents` 全局共享，所以 briefing 也可以全局共享。

```sql
CREATE TABLE document_briefings (
  id BIGSERIAL PRIMARY KEY,
  document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  language VARCHAR(16) NOT NULL DEFAULT 'zh-CN',

  one_sentence_summary TEXT,
  problem TEXT,
  method TEXT,
  contributions JSONB NOT NULL DEFAULT '[]',
  experiments JSONB NOT NULL DEFAULT '[]',
  limitations JSONB NOT NULL DEFAULT '[]',
  datasets JSONB NOT NULL DEFAULT '[]',
  metrics JSONB NOT NULL DEFAULT '[]',
  code_available BOOLEAN,
  code_url TEXT,
  reading_time_minutes INTEGER,

  evidence_chunk_ids JSONB NOT NULL DEFAULT '[]',
  model_provider VARCHAR(64),
  model_name VARCHAR(128),
  error_msg TEXT,
  generated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  UNIQUE(document_id, language)
);
```

实现规则：

- 文档入库后可自动异步生成。
- 用户点击“一键 Briefing”时，如果已有 `success` 结果则直接返回。
- 如果 `documents.doc_version` 变化，需要将旧 briefing 标为 `stale`。
- 返回给用户前必须确认该 `document_id` 属于当前用户的某个 Topic。

### 3.2 Topic 相关性解读表：`topic_document_insights`

同一篇论文对不同 Topic 的意义不同，因此需要 Topic 级补充说明。

```sql
CREATE TABLE topic_document_insights (
  id BIGSERIAL PRIMARY KEY,
  topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  relevance_score FLOAT,
  relevance_reason TEXT,
  reading_priority VARCHAR(16), -- high / medium / low
  tags JSONB NOT NULL DEFAULT '[]',
  why_read TEXT,
  generated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(topic_id, document_id)
);
```

用途：

- 知识浏览列表显示“为什么这篇和当前 Topic 相关”。
- Research Pulse 推荐必读论文。
- Reading Path 排序。

### 3.3 用户阅读状态表：`user_document_states`

用于“稍后读 / 已读 / 收藏 / 个人笔记”。这是用户私有数据。

```sql
CREATE TABLE user_document_states (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  status VARCHAR(32) NOT NULL DEFAULT 'unread', -- unread / reading / read / archived
  favorite BOOLEAN NOT NULL DEFAULT FALSE,
  rating INTEGER,
  personal_note TEXT,
  tags JSONB NOT NULL DEFAULT '[]',
  last_opened_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_id, document_id)
);
```

权限规则：

- 用户只能修改自己的状态。
- 修改前必须确认该 document 当前可通过用户 Topic 访问。

### 3.4 Research Pulse 表：`topic_pulses`

用于每日 Topic 简报。

```sql
CREATE TABLE topic_pulses (
  id BIGSERIAL PRIMARY KEY,
  topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  pulse_date DATE NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  title TEXT,
  summary_md TEXT,
  highlights JSONB NOT NULL DEFAULT '[]',
  new_documents JSONB NOT NULL DEFAULT '[]',
  important_documents JSONB NOT NULL DEFAULT '[]',
  emerging_keywords JSONB NOT NULL DEFAULT '[]',
  suggested_actions JSONB NOT NULL DEFAULT '[]',
  citations_json JSONB NOT NULL DEFAULT '[]',
  model_provider VARCHAR(64),
  model_name VARCHAR(128),
  error_msg TEXT,
  generated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(topic_id, pulse_date)
);
```

### 3.5 Reading Path 表：`reading_paths` / `reading_path_items`

```sql
CREATE TABLE reading_paths (
  id BIGSERIAL PRIMARY KEY,
  topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  description TEXT,
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  scope VARCHAR(32) NOT NULL DEFAULT 'topic', -- topic / recent / custom
  config_json JSONB NOT NULL DEFAULT '{}',
  generated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE reading_path_items (
  id BIGSERIAL PRIMARY KEY,
  reading_path_id BIGINT NOT NULL REFERENCES reading_paths(id) ON DELETE CASCADE,
  document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  order_index INTEGER NOT NULL,
  stage VARCHAR(64), -- foundation / core / advanced / latest / optional
  reason TEXT,
  expected_minutes INTEGER,
  prerequisite_document_ids JSONB NOT NULL DEFAULT '[]',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(reading_path_id, document_id)
);
```

### 3.6 研究洞察表：`research_insights`

用于 Gap Finder、机会点、风险点、趋势解释等。

```sql
CREATE TABLE research_insights (
  id BIGSERIAL PRIMARY KEY,
  topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  insight_type VARCHAR(32) NOT NULL, -- gap / opportunity / risk / trend / contradiction
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  title TEXT NOT NULL,
  summary TEXT,
  detail_md TEXT,
  confidence FLOAT,
  evidence_document_ids JSONB NOT NULL DEFAULT '[]',
  evidence_chunk_ids JSONB NOT NULL DEFAULT '[]',
  suggested_questions JSONB NOT NULL DEFAULT '[]',
  suggested_experiments JSONB NOT NULL DEFAULT '[]',
  model_provider VARCHAR(64),
  model_name VARCHAR(128),
  generated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 3.7 对话记忆与研究笔记：`research_notes` / `session_summaries`

```sql
CREATE TABLE research_notes (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  source_type VARCHAR(32) NOT NULL, -- manual / chat_pin / pulse / briefing / gap
  source_id BIGINT,
  title TEXT,
  content_md TEXT NOT NULL,
  tags JSONB NOT NULL DEFAULT '[]',
  pinned BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE session_summaries (
  id BIGSERIAL PRIMARY KEY,
  session_id BIGINT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
  topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  summary_md TEXT NOT NULL,
  key_findings JSONB NOT NULL DEFAULT '[]',
  open_questions JSONB NOT NULL DEFAULT '[]',
  cited_document_ids JSONB NOT NULL DEFAULT '[]',
  generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(session_id)
);
```

设计原则：

- 不做“不可见的永久记忆”。
- 所有记忆都要能在 UI 中看见、编辑、删除。
- QA 使用记忆时，只加载当前 Topic 的 notes 和 session summaries。

### 3.8 图谱、方法、趋势和矛盾检测相关表

#### `document_citation_edges`

```sql
CREATE TABLE document_citation_edges (
  id BIGSERIAL PRIMARY KEY,
  source_document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  target_document_id BIGINT REFERENCES documents(id) ON DELETE SET NULL,
  target_title TEXT,
  target_url TEXT,
  edge_source VARCHAR(64), -- semantic_scholar / parsed_pdf / manual
  confidence FLOAT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(source_document_id, target_document_id, target_title)
);
```

#### `method_entities` / `document_methods`

```sql
CREATE TABLE method_entities (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  normalized_name TEXT,
  aliases JSONB NOT NULL DEFAULT '[]',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE document_methods (
  id BIGSERIAL PRIMARY KEY,
  document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  method_id BIGINT NOT NULL REFERENCES method_entities(id) ON DELETE CASCADE,
  role VARCHAR(32), -- proposed / compared / baseline / dataset / metric
  evidence_chunk_ids JSONB NOT NULL DEFAULT '[]',
  confidence FLOAT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(document_id, method_id, role)
);
```

#### `topic_trend_terms`

```sql
CREATE TABLE topic_trend_terms (
  id BIGSERIAL PRIMARY KEY,
  topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  term TEXT NOT NULL,
  term_type VARCHAR(32), -- method / dataset / metric / keyword / author
  window_start DATE NOT NULL,
  window_end DATE NOT NULL,
  frequency INTEGER NOT NULL DEFAULT 0,
  previous_frequency INTEGER NOT NULL DEFAULT 0,
  burst_score FLOAT,
  example_document_ids JSONB NOT NULL DEFAULT '[]',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(topic_id, term, window_start, window_end)
);
```

#### `document_claims` / `contradiction_pairs`

```sql
CREATE TABLE document_claims (
  id BIGSERIAL PRIMARY KEY,
  document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  claim_type VARCHAR(32), -- sota / limitation / dataset_result / conclusion / comparison
  normalized_subject TEXT,
  normalized_predicate TEXT,
  normalized_object TEXT,
  claim_text TEXT NOT NULL,
  evidence_chunk_id BIGINT REFERENCES chunks(id) ON DELETE SET NULL,
  confidence FLOAT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE contradiction_pairs (
  id BIGSERIAL PRIMARY KEY,
  topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  claim_a_id BIGINT NOT NULL REFERENCES document_claims(id) ON DELETE CASCADE,
  claim_b_id BIGINT NOT NULL REFERENCES document_claims(id) ON DELETE CASCADE,
  status VARCHAR(32) NOT NULL DEFAULT 'suspected', -- suspected / confirmed_by_model / dismissed
  explanation_md TEXT,
  severity VARCHAR(16), -- low / medium / high
  confidence FLOAT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(topic_id, claim_a_id, claim_b_id)
);
```

---

## 4. Feature 1：Paper Briefing（一键论文简报）

### 4.1 用户价值

用户不需要打开 PDF，就可以快速判断一篇论文是否值得细读。

### 4.2 MVP 范围

每篇文档提供一个结构化 Briefing：

```text
- 一句话贡献
- 解决的问题
- 核心方法
- 主要贡献点
- 实验结论
- 局限性
- 数据集 / 指标
- 是否有代码
- 预计阅读时间
- 和当前 Topic 的相关性
```

### 4.3 触发方式

| 触发 | 行为 |
|---|---|
| 新文档索引完成 | 异步生成全局 `document_briefings` |
| 用户点击 Briefing | 若已有结果直接返回；否则创建 urgent 分析任务 |
| Topic 新增文档关联 | 生成或刷新 `topic_document_insights` |

### 4.4 后端 API

```http
GET  /api/topics/{topic_id}/documents/{document_id}/briefing
POST /api/topics/{topic_id}/documents/{document_id}/briefing/generate
PATCH /api/topics/{topic_id}/documents/{document_id}/state
```

`GET` 响应示例：

```json
{
  "document_id": 123,
  "title": "Example Paper",
  "briefing": {
    "one_sentence_summary": "本文提出...",
    "problem": "...",
    "method": "...",
    "contributions": ["..."],
    "experiments": ["..."],
    "limitations": ["..."],
    "datasets": ["KITTI", "Scene Flow"],
    "metrics": ["EPE", "D1-all"],
    "reading_time_minutes": 18,
    "evidence_chunk_ids": [1, 2, 3]
  },
  "topic_insight": {
    "relevance_score": 0.86,
    "reading_priority": "high",
    "why_read": "该论文直接讨论 Topic 关注的 Transformer stereo matching。"
  },
  "user_state": {
    "status": "unread",
    "favorite": false,
    "personal_note": null
  }
}
```

### 4.5 Prompt 约束

AI 必须遵守：

1. 只基于给定文档 chunks 总结。
2. 不确定的信息填 `null` 或空数组，不要编造。
3. 每个重要结论都尽量关联 `evidence_chunk_ids`。
4. `limitations` 不存在时写“未在当前文档片段中明确发现”。
5. 输出严格 JSON，不输出 Markdown。

### 4.6 前端设计

知识浏览列表新增：

- “Briefing”按钮。
- 阅读优先级徽标：High / Medium / Low。
- 预计阅读时间。
- 收藏、已读、稍后读。

点击后打开 Drawer：

```text
标题
一句话贡献
为什么和当前课题相关
核心方法
主要实验
局限性
引用片段
用户笔记
```

### 4.7 验收标准

- 新文档入库后能自动生成 Briefing。
- 同一 Document 的全局 Briefing 不重复生成。
- 不同 Topic 能有不同的 `why_read` 和 `reading_priority`。
- 用户不能访问不属于自己 Topic 的 Document Briefing。
- Briefing 失败不影响文档入库和问答。

---

## 5. Feature 2：Research Pulse（每日研究脉搏）

### 5.1 用户价值

每天自动告诉用户：当前 Topic 昨天发生了什么、哪些值得看、出现了哪些新关键词或新方向。

### 5.2 MVP 范围

每日简报包含：

```text
1. 今日摘要
2. 新增文档数量
3. 必读论文 / Repo
4. 新出现或明显变多的关键词
5. 系统建议用户下一步做什么
6. 引用来源
```

不做：

- 大规模学术趋势预测。
- 复杂统计显著性。
- 跨 Topic 竞品雷达。

### 5.3 生成时机

推荐两种触发：

1. 每日定时：例如用户本地时间 09:00。
2. 采集任务完成后：如果当天还没有 Pulse，则生成；如果已有，则标记为 `stale` 并可刷新。

### 5.4 数据输入

生成 Pulse 时读取：

- 当前 Topic 最近 24 小时新增的 `topic_documents`。
- 最近新增文档的 `document_briefings`。
- `topic_document_insights` 中 reading priority 为 high 的文档。
- 最近趋势词 `topic_trend_terms`。
- 用户尚未阅读的高优先级文档。
- 最近任务状态。

### 5.5 任务流程

```text
scheduled trigger / collection finished
  ↓
create topic_pulses(status=pending)
  ↓
generate missing document_briefings
  ↓
collect candidate documents and terms
  ↓
LLM synthesize daily pulse
  ↓
write topic_pulses(summary_md, highlights, citations_json)
  ↓
create notification(task_done / system)
  ↓
frontend shows pulse card
```

### 5.6 后端 API

```http
GET  /api/topics/{topic_id}/pulses
GET  /api/topics/{topic_id}/pulses/latest
GET  /api/topics/{topic_id}/pulses/{pulse_id}
POST /api/topics/{topic_id}/pulses/generate
```

`latest` 响应示例：

```json
{
  "id": 88,
  "topic_id": 12,
  "pulse_date": "2026-05-17",
  "title": "Stereo Matching 今日研究脉搏",
  "summary_md": "昨天新增 5 篇相关论文，其中 2 篇值得优先阅读...",
  "highlights": [
    {"type": "new_doc", "text": "新增一篇关注 Mamba 的立体匹配论文", "document_id": 123},
    {"type": "keyword", "text": "depth anything 在最近文档中出现频次上升", "term": "depth anything"}
  ],
  "suggested_actions": [
    {"action": "read", "document_id": 123, "reason": "与当前 Topic 高相关"},
    {"action": "ask", "question": "最近 Mamba 在 stereo matching 中解决了什么问题？"}
  ],
  "citations": []
}
```

### 5.7 前端设计

首页 Topic Card 展示：

```text
今日脉搏：新增 5 篇，2 篇必读，1 个新关键词
```

Topic 详情页顶部展示 Pulse Card：

```text
Research Pulse
- 今天最重要的发现
- 必读
- 新关键词
- 建议提问
```

通知中心新增：

```text
你的「立体匹配」今日研究脉搏已生成
```

### 5.8 验收标准

- 每个 active Topic 每天最多自动生成一条 Pulse。
- 用户可手动刷新当天 Pulse。
- Pulse 必须有引用来源或文档依据。
- 无新增文档时也能生成“无新增，但建议复习/阅读”的简报。
- Pulse 生成失败不影响采集任务结果。

---

## 6. Feature 3：Reading Path Generator（阅读路径规划）

### 6.1 用户价值

用户新建 Topic 后，系统不只是列出论文，而是告诉用户：

```text
先读什么 → 再读什么 → 哪些是核心方法 → 哪些是最新进展 → 哪些可选
```

### 6.2 MVP 范围

生成一个 Topic 级阅读路径：

```text
阶段 1：入门 / 奠基
阶段 2：核心方法
阶段 3：重要改进
阶段 4：最新进展
阶段 5：可选拓展
```

每篇文档标注：

- 推荐顺序。
- 为什么读。
- 预计阅读时间。
- 是否前置依赖。
- 用户阅读状态。

### 6.3 排序算法建议

MVP 不强依赖完整引用图谱，采用混合启发式：

```text
score =
  topic_relevance * 0.35
  + citation_or_importance_score * 0.25
  + method_foundation_score * 0.20
  + recency_score * 0.10
  + source_quality_score * 0.10
```

阶段划分规则：

| 阶段 | 规则 |
|---|---|
| foundation | 早期、高引用、被多篇文档引用、标题/摘要含 survey / benchmark / baseline |
| core | Topic 高相关、方法贡献明确、被后续方法对比 |
| advanced | 方法复杂或依赖前置论文 |
| latest | 最近 6-12 个月新增，高相关 |
| optional | 相关但非主线，或工程实现类 Repo |

如果没有引用数据，使用：

- `published_at`
- `source`
- `topic_document_insights.relevance_score`
- `document_briefings.contributions`
- LLM 判断的 prerequisite 关系

### 6.4 后端 API

```http
GET  /api/topics/{topic_id}/reading-paths
GET  /api/topics/{topic_id}/reading-paths/latest
POST /api/topics/{topic_id}/reading-paths/generate
PATCH /api/topics/{topic_id}/reading-paths/{path_id}/items/{item_id}
```

### 6.5 前端设计

新增 Topic Tab：`阅读路径`。

展示形式：

```text
进度：3 / 18 已读

阶段 1：奠基论文
[ ] Paper A   预计 20 min   为什么读：...
[x] Paper B   预计 15 min   为什么读：...

阶段 2：核心方法
[ ] Paper C   预计 25 min   前置：Paper A
```

用户交互：

- 标记已读。
- 收藏。
- 添加笔记。
- 跳转 Briefing。
- 从某篇文档开始问答。

### 6.6 验收标准

- 新 Topic 完成首次回填后可生成 Reading Path。
- Reading Path 至少包含 5 篇文档；文档不足时给出原因。
- 每个 item 必须有 `reason`。
- 用户阅读进度和路径生成结果分离：刷新路径不应清空用户已读状态。

---

## 7. Feature 4：Research Gap Finder（研究空白发现）

### 7.1 用户价值

帮助用户从已有论文中发现潜在选题方向，例如：

```text
当前大多数方法只在室内场景测试，室外强光鲁棒性研究不足。
跨域泛化经常被提到，但缺少系统 benchmark。
很多方法追求精度，但实时部署成本讨论较少。
```

### 7.2 MVP 范围

Gap Finder 输出 3-5 条研究空白：

- Gap 标题。
- 证据摘要。
- 为什么可能有价值。
- 支撑文档。
- 可追问的问题。
- 可尝试的实验方向。
- 置信度。

### 7.3 输入数据

优先使用结构化数据，避免每次扫全量 chunk：

- `document_briefings.problem`
- `document_briefings.method`
- `document_briefings.limitations`
- `document_briefings.datasets`
- `document_briefings.metrics`
- `topic_document_insights`
- 当前 Topic 的高相关文档集合
- 最近 6-12 个月文档集合

必要时再从 Qdrant 按 Topic 召回补充 chunks。

### 7.4 分析流程

```text
load topic corpus
  ↓
ensure key documents have briefings
  ↓
cluster documents by method/problem/dataset
  ↓
summarize each cluster
  ↓
identify repeated limitations and under-covered dimensions
  ↓
compare claimed problems vs solved problems
  ↓
generate 3-5 gap insights with evidence
  ↓
write research_insights(insight_type='gap')
```

### 7.5 后端 API

```http
GET  /api/topics/{topic_id}/insights?type=gap
POST /api/topics/{topic_id}/insights/gaps/generate
GET  /api/topics/{topic_id}/insights/{insight_id}
POST /api/topics/{topic_id}/insights/{insight_id}/pin
```

### 7.6 Prompt 约束

AI 输出必须明确区分：

- 证据中明确存在的事实。
- 模型基于多个证据做出的推断。
- 不确定性。

禁止写成：

```text
这个方向一定没人做。
```

应该写成：

```text
在当前 Topic 已采集文档中，系统没有发现专门研究该问题的论文；这可能是一个值得进一步检索验证的方向。
```

### 7.7 前端设计

新增 Topic Tab：`研究洞察`。

卡片结构：

```text
标题：室外强光鲁棒性研究不足
置信度：中
为什么重要：...
证据：3 篇论文都只在室内/标准数据集测试
建议下一步：
- 检索 outdoor stereo robustness
- 对比 KITTI / Middlebury / 自建强光数据
- 询问系统：有哪些论文提到泛化问题？
```

### 7.8 验收标准

- 生成的每条 Gap 至少引用 2 篇文档，除非 Topic 文档数量不足。
- 每条 Gap 必须包含不确定性表达。
- Gap 不得跨越当前 Topic 私自引用其他用户 Topic 的文档。
- 用户可以把 Gap Pin 到研究笔记。

---

## 8. Feature 5：Related Work Draft（相关工作草稿生成）

### 8.1 用户价值

用户输入研究问题或方法描述，系统从 Topic 内文档生成一段可修改的 Related Work 草稿，带引用。

### 8.2 MVP 范围

支持 3 种模板：

| 模板 | 用途 |
|---|---|
| Literature Review | 按主题组织相关工作 |
| Method Comparison | 对比几类方法 |
| Weekly Digest | 基于最近新增文档生成周报 |

### 8.3 生成流程

```text
user input research question
  ↓
query rewrite into retrieval queries
  ↓
Qdrant topic-filtered retrieval
  ↓
merge with document_briefings and topic_document_insights
  ↓
group by method / dataset / problem / chronology
  ↓
generate outline
  ↓
generate draft with citations
  ↓
save writing_drafts
```

### 8.4 数据表：`writing_drafts`

```sql
CREATE TABLE writing_drafts (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  draft_type VARCHAR(32) NOT NULL, -- related_work / comparison / weekly_digest
  title TEXT NOT NULL,
  prompt TEXT,
  content_md TEXT NOT NULL,
  citations_json JSONB NOT NULL DEFAULT '[]',
  source_document_ids JSONB NOT NULL DEFAULT '[]',
  status VARCHAR(32) NOT NULL DEFAULT 'success',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 8.5 后端 API

```http
GET  /api/topics/{topic_id}/drafts
POST /api/topics/{topic_id}/drafts
GET  /api/topics/{topic_id}/drafts/{draft_id}
PATCH /api/topics/{topic_id}/drafts/{draft_id}
DELETE /api/topics/{topic_id}/drafts/{draft_id}
```

请求示例：

```json
{
  "draft_type": "related_work",
  "title": "RAFT-style stereo matching related work",
  "research_question": "我想写一段关于迭代优化机制在 stereo matching 中的发展。",
  "style": "academic_zh",
  "max_documents": 12
}
```

### 8.6 生成约束

1. 草稿必须标注“这是草稿，不建议直接提交”。
2. 每段至少有一个引用，或明确说明该段是综合性总结。
3. 引用必须来自当前 Topic。
4. 不允许捏造作者、年份、实验结果。
5. 生成后用户可编辑，编辑不应覆盖原始生成版本，建议保留 `updated_at`。

### 8.7 前端设计

新增页面或 Tab：`写作助手`。

功能：

- 输入研究问题。
- 选择模板。
- 选择引用文档数量。
- 生成草稿。
- 展示引用面板。
- 保存为研究笔记。
- 导出 Markdown。

---

## 9. Feature 6：对话记忆 + 研究备忘录

### 9.1 用户价值

用户和系统的研究过程应该能沉淀下来，而不是每次对话都从零开始。

### 9.2 MVP 范围

实现 3 个能力：

1. **Session 主题**：用户可以给对话命名。
2. **Pin 到研究笔记**：用户可将回答片段、引用、Gap、Pulse 保存为 Note。
3. **Session Summary**：对话结束或超过 N 条消息后自动总结。

### 9.3 记忆加载规则

QA 时加载：

```text
当前 Topic 最近 5 轮对话
+ 当前 session summary
+ 当前 Topic pinned notes top 5
+ 当前 Topic 最近 research insights top 3
```

必须避免：

- 加载其他 Topic 的记忆。
- 加载其他用户的记忆。
- 把所有历史笔记塞进 Prompt。

### 9.4 后端 API

```http
PATCH /api/topics/{topic_id}/chat/sessions/{session_id}
POST  /api/topics/{topic_id}/chat/sessions/{session_id}/summarize
GET   /api/topics/{topic_id}/notes
POST  /api/topics/{topic_id}/notes
PATCH /api/topics/{topic_id}/notes/{note_id}
DELETE /api/topics/{topic_id}/notes/{note_id}
POST  /api/topics/{topic_id}/chat/messages/{message_id}/pin
```

### 9.5 前端设计

- 对话列表显示 session title。
- 每条 assistant message 增加“Pin”按钮。
- Topic 详情新增 `研究笔记` 区块。
- Note 支持标签、收藏、搜索。

### 9.6 验收标准

- 用户能 Pin 一段回答到当前 Topic 的研究笔记。
- QA 下一次回答时可引用已 Pin 的 Note，但必须标明它来自用户笔记。
- 用户可以删除 Note；删除后不再进入 Prompt。

---

## 10. Feature 7：论文关系图谱与方法演化时间线

### 10.1 用户价值

把研究领域“看得见”：

- 哪些论文是核心节点。
- 哪些方法沿着什么路线演化。
- 当前 Topic 的研究主线是什么。

### 10.2 Paper Graph MVP

节点：

```text
Document
```

边：

```text
citation / same_method / method_extension / compares_with
```

MVP 先做 citation edge：

- Semantic Scholar 返回的引用 / 参考文献。
- PDF 解析出的 reference title 粗匹配。
- 同 Topic 内 title 相似匹配。

节点属性：

```json
{
  "document_id": 123,
  "title": "...",
  "published_at": "2024-05-01",
  "source": "arxiv",
  "briefing_ready": true,
  "reading_status": "unread",
  "importance_score": 0.82
}
```

### 10.3 Method Timeline MVP

流程：

```text
extract method entities from title/abstract/fulltext
  ↓
normalize aliases
  ↓
link methods to documents
  ↓
sort by published_at
  ↓
generate timeline cards
```

展示：

```text
2018 PSMNet
  ↓
2019 GwcNet
  ↓
2021 RAFT-Stereo
  ↓
2023 IGEV
  ↓
2024 Selective-IGEV
```

每个节点展示：

- 方法名。
- 代表论文。
- 核心创新点。
- 相关文档数量。
- 可点击进入 Briefing。

### 10.4 后端 API

```http
GET  /api/topics/{topic_id}/graph
POST /api/topics/{topic_id}/graph/rebuild
GET  /api/topics/{topic_id}/methods/timeline
POST /api/topics/{topic_id}/methods/extract
```

### 10.5 前端设计

新增 Topic Tab：`图谱`。

包含两个子视图：

1. `论文关系图`
2. `方法时间线`

交互：

- 点击节点打开 Document Drawer。
- 支持按年份、来源、阅读状态筛选。
- 支持只看 high priority 文档。

### 10.6 验收标准

- 图谱只显示当前 Topic 可访问文档。
- 关系边必须有 `edge_source` 和 `confidence`。
- 方法时间线每个方法至少关联 1 篇文档。
- 低置信度边在 UI 上标记为“推测”。

---

## 11. Feature 8：Trend Radar（趋势雷达）

### 11.1 用户价值

用户能看到 Topic 中哪些方法、关键词、数据集正在升温或降温。

### 11.2 MVP 范围

只做 Topic 内趋势，不做全网趋势。

指标：

- 最近 30 天频次。
- 最近 60 天频次。
- 与前一窗口相比的变化。
- burst score。
- 示例文档。

### 11.3 Burst Score 简化公式

```text
current = frequency(term, current_window)
previous = frequency(term, previous_window)
burst_score = (current + 1) / (previous + 1)
```

排序：

```text
sort by burst_score desc, current frequency desc
```

### 11.4 趋势类型

| 类型 | 来源 |
|---|---|
| method | `method_entities` / `document_methods` |
| dataset | `document_briefings.datasets` |
| metric | `document_briefings.metrics` |
| keyword | title / abstract / chunks 的关键词抽取 |
| author | documents.authors |

### 11.5 后端 API

```http
GET  /api/topics/{topic_id}/trends?window_days=60
POST /api/topics/{topic_id}/trends/recompute
```

### 11.6 前端设计

展示：

- 趋势词排行榜。
- 时间轴。
- 热力图。
- 点击 term 显示相关文档。

示例：

```text
新兴关键词
1. mamba              burst 3.2x    4 篇新文档
2. depth anything     burst 2.5x    3 篇新文档
3. real-time stereo   burst 2.1x    5 篇新文档
```

### 11.7 验收标准

- 趋势只基于当前 Topic 文档。
- 每个趋势词必须能展示示例文档。
- 文档数量少于阈值时，UI 显示“数据不足，趋势仅供参考”。

---

## 12. Feature 9：Contradiction Detector（矛盾检测器）

### 12.1 用户价值

自动找出 Topic 内可能互相冲突的论文结论，例如：

```text
Paper A 声称方法 X 在数据集 Y 上优于所有 baseline。
Paper B 在相同或相似设置下报告方法 X 表现不稳定。
```

### 12.2 重要原则

该功能必须命名为：

```text
疑似矛盾 / Suspected Contradictions
```

不要向用户宣称系统已经证明两篇论文矛盾。论文实验设置、数据划分、指标差异可能导致表面冲突。

### 12.3 Alpha 范围

只检测以下类型：

| 类型 | 说明 |
|---|---|
| SOTA claim conflict | 两篇论文都声称在相同数据集/指标上最好 |
| limitation conflict | 一篇认为某方法有效，另一篇指出明显失败场景 |
| dataset result conflict | 相同 dataset/metric 下结果方向不一致 |
| method comparison conflict | 对同一方法优劣评价相反 |

### 12.4 流程

```text
extract claims from document chunks
  ↓
normalize subject / predicate / object
  ↓
find candidate pairs by same method/dataset/metric
  ↓
LLM or NLI judge whether claims are in tension
  ↓
write contradiction_pairs(status='suspected')
  ↓
show with evidence and caveats
```

### 12.5 后端 API

```http
GET  /api/topics/{topic_id}/contradictions
POST /api/topics/{topic_id}/contradictions/detect
PATCH /api/topics/{topic_id}/contradictions/{pair_id}
```

### 12.6 前端设计

展示卡片：

```text
疑似矛盾：方法 X 在 KITTI 上的表现

Paper A：声称 X 达到 SOTA
证据片段：...

Paper B：报告 X 在遮挡区域表现不稳定
证据片段：...

系统解释：两者可能存在实验设置差异，需要进一步核对数据划分和指标。
置信度：中
```

### 12.7 验收标准

- 每个矛盾 pair 必须展示两个 claim 的原文证据。
- UI 必须显示“疑似”。
- 用户可以标记为 dismissed。
- 检测失败不影响其他功能。

---

## 13. Feature 10：多角色问答与 What-if 推演

### 13.1 用户价值

同一个问题，用户可能需要不同风格：

- 导师模式：严格指出问题和局限。
- 学生模式：用简单语言解释。
- 辩论模式：列出支持与反对证据。
- What-if：基于已有论文做假设推演。

### 13.2 Chat Request 增量

```json
{
  "content": "如果把 RAFT 的迭代优化机制用于 Transformer stereo matching 会有什么问题？",
  "answer_mode": "what_if",
  "tone": "mentor",
  "use_notes": true
}
```

`answer_mode`：

```text
normal
mentor
student
debate
what_if
```

### 13.3 Prompt 规则

#### 导师模式

```text
你需要严格评价用户的想法，指出依据、漏洞、需要补充验证的实验。
不得只给鼓励性回答。
```

#### 学生模式

```text
用清晰类比解释，减少术语。必要术语必须解释。
```

#### 辩论模式

```text
分成“支持该观点的证据”和“反对/保留意见”。每一侧都必须引用文档。
```

#### What-if 模式

```text
明确分成：
1. 当前文献证据
2. 基于证据的推演
3. 不确定性与验证实验
```

### 13.4 验收标准

- 所有模式仍然必须使用 Topic 过滤检索。
- What-if 的推演部分必须明确标注为推演。
- 辩论模式必须至少尝试召回支持和反对两类证据；没有反对证据时要说明。

---

## 14. API 汇总

### 14.1 Briefing

```http
GET    /api/topics/{topic_id}/documents/{document_id}/briefing
POST   /api/topics/{topic_id}/documents/{document_id}/briefing/generate
PATCH  /api/topics/{topic_id}/documents/{document_id}/state
```

### 14.2 Research Pulse

```http
GET    /api/topics/{topic_id}/pulses
GET    /api/topics/{topic_id}/pulses/latest
GET    /api/topics/{topic_id}/pulses/{pulse_id}
POST   /api/topics/{topic_id}/pulses/generate
```

### 14.3 Reading Path

```http
GET    /api/topics/{topic_id}/reading-paths
GET    /api/topics/{topic_id}/reading-paths/latest
POST   /api/topics/{topic_id}/reading-paths/generate
PATCH  /api/topics/{topic_id}/reading-paths/{path_id}/items/{item_id}
```

### 14.4 Research Insights / Gap

```http
GET    /api/topics/{topic_id}/insights
GET    /api/topics/{topic_id}/insights/{insight_id}
POST   /api/topics/{topic_id}/insights/gaps/generate
POST   /api/topics/{topic_id}/insights/{insight_id}/pin
```

### 14.5 Writing Drafts

```http
GET    /api/topics/{topic_id}/drafts
POST   /api/topics/{topic_id}/drafts
GET    /api/topics/{topic_id}/drafts/{draft_id}
PATCH  /api/topics/{topic_id}/drafts/{draft_id}
DELETE /api/topics/{topic_id}/drafts/{draft_id}
```

### 14.6 Notes / Memory

```http
GET    /api/topics/{topic_id}/notes
POST   /api/topics/{topic_id}/notes
PATCH  /api/topics/{topic_id}/notes/{note_id}
DELETE /api/topics/{topic_id}/notes/{note_id}
POST   /api/topics/{topic_id}/chat/messages/{message_id}/pin
POST   /api/topics/{topic_id}/chat/sessions/{session_id}/summarize
```

### 14.7 Graph / Trend / Contradiction

```http
GET    /api/topics/{topic_id}/graph
POST   /api/topics/{topic_id}/graph/rebuild
GET    /api/topics/{topic_id}/methods/timeline
POST   /api/topics/{topic_id}/methods/extract
GET    /api/topics/{topic_id}/trends
POST   /api/topics/{topic_id}/trends/recompute
GET    /api/topics/{topic_id}/contradictions
POST   /api/topics/{topic_id}/contradictions/detect
PATCH  /api/topics/{topic_id}/contradictions/{pair_id}
```

---

## 15. 前端导航结构调整

现有 Topic 详情 Tabs：

```text
问答 / 知识浏览 / 任务记录 / 课题设置
```

优化后建议：

```text
概览
问答
知识浏览
阅读路径
研究洞察
写作助手
图谱
任务记录
课题设置
```

### 15.1 概览 Tab

概览页是“有生命感”的核心入口。

包含：

1. 今日 Research Pulse。
2. 新增文档。
3. 必读论文。
4. 研究空白提示。
5. 阅读进度。
6. 建议提问。

### 15.2 知识浏览增强

新增列：

- Briefing 状态。
- 阅读优先级。
- 阅读状态。
- 预计阅读时间。
- 收藏。
- 相关性原因。

### 15.3 问答增强

新增：

- Answer Mode Selector：普通 / 导师 / 学生 / 辩论 / What-if。
- Pin 按钮。
- 引用跳转到 Briefing。
- “基于这次回答生成研究笔记”。

---

## 16. 任务与事件流

### 16.1 新文档入库后的事件链

```text
index_document_task success
  ↓
ensure topic_documents relation
  ↓
enqueue generate_document_briefing_task(document_id)
  ↓
enqueue generate_topic_document_insight_task(topic_id, document_id)
  ↓
enqueue extract_document_entities_task(document_id)
  ↓
mark today's topic_pulse stale
```

### 16.2 每日计划任务

```text
for each active topic:
  collect scheduled sources
  generate missing briefings
  compute trends
  generate research pulse
  send notification
```

### 16.3 用户手动生成 Related Work

```text
POST /drafts
  ↓
create writing_drafts(status=pending)
  ↓
enqueue generate_related_work_draft_task
  ↓
SSE / polling 返回生成状态
  ↓
完成后展示草稿
```

---

## 17. RAG 与生成质量控制

### 17.1 所有生成类功能必须保留引用

以下功能必须写入 `citations_json` 或 evidence ids：

- Research Pulse
- Paper Briefing
- Research Gap
- Related Work Draft
- Contradiction Detector
- What-if QA

引用结构建议：

```json
{
  "document_id": 123,
  "chunk_id": 456,
  "title": "...",
  "url": "...",
  "source": "arxiv",
  "published_at": "2026-05-01",
  "quote": "...",
  "reason": "supports limitation claim"
}
```

### 17.2 不确定性表达

Research Gap、Trend、Contradiction、What-if 必须包含不确定性表达。

不允许：

```text
该方向无人研究。
```

允许：

```text
在当前 Topic 已采集文档中，系统尚未发现专门研究该问题的文档。
```

### 17.3 缓存策略

| 功能 | 缓存粒度 | 失效条件 |
|---|---|---|
| Paper Briefing | document_id + language | document doc_version 变化 |
| Topic Document Insight | topic_id + document_id | topic keywords 变化 / briefing 变化 |
| Research Pulse | topic_id + date | 当天新增文档 / 手动刷新 |
| Reading Path | topic_id | Topic 文档集合变化较大 / 手动刷新 |
| Gap Finder | topic_id + corpus_snapshot | 高相关文档集合变化 |
| Related Work Draft | draft_id | 用户手动重新生成 |
| Trend Radar | topic_id + window | 每日重算 |
| Contradiction Detector | topic_id + claims_snapshot | 新 claims 增加 |

### 17.4 成本控制

- Briefing 使用较便宜模型；Related Work 和 Gap 可用更强模型。
- 新文档批量生成 Briefing，避免逐条高频请求。
- 对同一 document_id 去重，不重复生成。
- 每个 Topic 每天自动 Pulse 最多一次。
- Trend 和 Contradiction 默认异步、低频。
- 用户手动触发生成需要 UI 显示“正在生成”，避免重复点击。

---

## 18. 测试与验收计划

### 18.1 权限隔离测试

必须覆盖：

- 用户 A 不能访问用户 B Topic 的 Pulse。
- 用户 A 不能通过 document_id 访问用户 B 独有 Topic 中的 Briefing。
- 用户 A 不能读取用户 B 的 Notes、Drafts、Reading Path。
- Qdrant 检索必须只召回当前 Topic。

### 18.2 功能测试

| 功能 | 测试点 |
|---|---|
| Briefing | 新文档生成、缓存复用、失败重试、权限校验 |
| Pulse | 每日唯一、无新增文档兜底、通知触发 |
| Reading Path | 生成阶段、阅读状态独立、刷新不丢进度 |
| Gap Finder | 每条 Gap 有证据、有不确定性、不越权 |
| Related Work | 引用来自当前 Topic、可保存、可编辑 |
| Notes | Pin、删除、QA 加载、Topic 隔离 |
| Graph | 节点边均来自当前 Topic |
| Trend | 数据不足提示、趋势词有示例文档 |
| Contradiction | 必须展示两个 claim 证据，默认疑似 |

### 18.3 质量评测集

为每个 Demo Topic 准备：

```text
10 个 Briefing 验证文档
10 个 Pulse 期望输出样例
10 个 Reading Path 验证问题
10 个 Gap Finder 期望方向
10 个 Related Work 生成问题
5 个 What-if 问题
```

评估指标：

| 指标 | 说明 |
|---|---|
| groundedness | 输出是否基于文档 |
| citation accuracy | 引用是否支持结论 |
| topic isolation | 是否只使用当前 Topic |
| usefulness | 是否对研究决策有帮助 |
| novelty | 是否能提出非平庸观察 |
| latency | 用户体感是否可接受 |
| cost | 单次生成成本是否可控 |

---

## 19. Demo 数据增强

为了让优化功能稳定演示，需要扩展 seed 数据。

### 19.1 新增 Seed 内容

每个 Demo Topic 至少包含：

```text
20-40 篇文档
10 篇已有 Briefing
1 条当天 Research Pulse
1 条 Reading Path
3 条 Research Gap
1 个 Related Work Draft
10 条 Method Entities
若干 Citation Edges
若干用户阅读状态
```

### 19.2 演示脚本升级

演示顺序建议：

1. 登录 demo 账号。
2. 首页展示每个 Topic 的 Research Pulse 摘要。
3. 进入“立体匹配” Topic。
4. 展示今天新增文档和必读推荐。
5. 点击一篇论文 Briefing，快速判断是否值得读。
6. 切到 Reading Path，展示系统规划的阅读路线。
7. 切到 Research Gap，展示系统发现的潜在选题。
8. 用导师模式问一个 What-if 问题。
9. 把回答 Pin 到研究笔记。
10. 生成一段 Related Work 草稿。
11. 切到图谱 / 时间线，展示方法演化。

---

## 20. 详细实施路线

### 20.1 v1.1：研究助手唤醒版

目标：每天打开都有新东西。

任务：

1. 新增 `document_briefings`。
2. 新增 `topic_document_insights`。
3. 新增 `user_document_states`。
4. 实现 Paper Briefing API 和 UI Drawer。
5. 新增 `topic_pulses`。
6. 实现 Research Pulse 生成任务。
7. 首页和 Topic 概览展示 Pulse。
8. Pulse 完成后走 NotificationWorkflow。
9. 增加 demo seed pulse。

验收：

```text
用户进入 Topic 后，可以看到今日简报、必读论文、论文 Briefing 和阅读状态。
```

### 20.2 v1.2：研究 Agent 增强版

目标：系统开始帮用户组织研究过程。

任务：

1. 新增 Reading Path 表和 UI。
2. 实现 Reading Path Generator。
3. 新增 Research Insights 表。
4. 实现 Gap Finder。
5. 新增 Writing Drafts。
6. 实现 Related Work Draft。
7. 新增 Research Notes 和 Pin。
8. 实现 Session Summary。

验收：

```text
用户可以从新 Topic 获得阅读路线、研究空白、写作草稿，并把研究过程沉淀为笔记。
```

### 20.3 v1.3：知识可视化与趋势版

目标：让知识结构可视化。

任务：

1. 新增 citation edges。
2. 新增 method entities。
3. 实现论文关系图 API。
4. 实现方法演化时间线。
5. 新增 topic trend terms。
6. 实现 Trend Radar。
7. 增强 Topic 概览：展示趋势词。

验收：

```text
用户可以看到 Topic 的论文网络、方法时间线和最近升温关键词。
```

### 20.4 v1.4 Alpha：高阶推理版

目标：做出惊喜感，但保持谨慎。

任务：

1. 新增 document claims。
2. 实现 claim extraction。
3. 实现 contradiction candidate matching。
4. 实现 contradiction judge。
5. 前端展示“疑似矛盾”。
6. QA 增加导师 / 学生 / 辩论 / What-if 模式。

验收：

```text
用户可以看到系统发现的疑似矛盾，并在问答中获得多角色、有证据的分析。
```

---

## 21. 不建议当前阶段优先实现

以下功能暂不优先：

| 功能 | 原因 |
|---|---|
| 团队 workspace | 会改变权限模型，当前先打磨个人研究体验 |
| 计费 / 套餐 | 产品价值还未验证 |
| 大规模监控与 HA | 与 Demo / PoC 定位不符 |
| 复杂 Webhook 实发 | v1 已预留接口，当前先做好 InApp + Email |
| 模型微调 | 成本高，收益不如优化 briefing / retrieval / prompt |
| 自动爬付费墙内容 | 合规风险高 |
| 移动端 App | Web 端体验未稳定前不做 |
| Google Scholar 抓取 | 反爬和合规成本较高，先用官方/开放源 |

---

## 22. AI Coding Agent Checklist

实现任何一个优化功能前，AI 必须检查：

```text
[ ] 是否先校验 topic.user_id = current_user.id？
[ ] 是否没有把 user_id 加入 documents / chunks？
[ ] 是否复用了已有 document / chunk / Qdrant 数据？
[ ] 是否避免同步阻塞 API？
[ ] 是否有生成状态 status？
[ ] 是否有 error_msg 和失败兜底？
[ ] 是否有 citations_json 或 evidence ids？
[ ] 是否避免跨 Topic / 跨用户数据泄露？
[ ] 是否有最小测试用例？
[ ] 是否有 Demo seed 或 mock 数据？
```

---

## 23. 最小可交付 Backlog

### Sprint 1：Paper Briefing

- [ ] Alembic migration：`document_briefings`
- [ ] Alembic migration：`topic_document_insights`
- [ ] Alembic migration：`user_document_states`
- [ ] Briefing Service
- [ ] Briefing Celery Task
- [ ] Document Briefing API
- [ ] Document State API
- [ ] 前端 Briefing Drawer
- [ ] 知识浏览列表新增阅读状态和优先级
- [ ] 权限测试

### Sprint 2：Research Pulse

- [ ] Alembic migration：`topic_pulses`
- [ ] Pulse Generator Service
- [ ] Pulse Celery Task
- [ ] Pulse API
- [ ] NotificationWorkflow 接入 Pulse 完成事件
- [ ] 首页 Topic Card 显示 Pulse 摘要
- [ ] Topic 概览页
- [ ] Demo seed pulse

### Sprint 3：Reading Path

- [ ] Alembic migration：`reading_paths`
- [ ] Alembic migration：`reading_path_items`
- [ ] Reading Path Planner
- [ ] Reading Path API
- [ ] 阅读路径 Tab
- [ ] 阅读进度组件
- [ ] 结合 user_document_states

### Sprint 4：Gap + Notes

- [ ] Alembic migration：`research_insights`
- [ ] Gap Finder Service
- [ ] Gap API
- [ ] Gap UI Cards
- [ ] Alembic migration：`research_notes`
- [ ] Pin to Note API
- [ ] Notes UI

### Sprint 5：Related Work

- [ ] Alembic migration：`writing_drafts`
- [ ] Related Work Composer
- [ ] Draft API
- [ ] 写作助手 UI
- [ ] Markdown 导出
- [ ] Citation Panel

### Sprint 6：Graph + Timeline + Trend

- [ ] Alembic migration：`document_citation_edges`
- [ ] Alembic migration：`method_entities` / `document_methods`
- [ ] Alembic migration：`topic_trend_terms`
- [ ] Entity Extractor
- [ ] Graph API
- [ ] Timeline API
- [ ] Trend API
- [ ] 图谱 UI
- [ ] 时间线 UI
- [ ] 趋势雷达 UI

### Sprint 7：Contradiction + Advanced QA

- [ ] Alembic migration：`document_claims`
- [ ] Alembic migration：`contradiction_pairs`
- [ ] Claim Extractor
- [ ] Contradiction Detector
- [ ] Contradiction UI
- [ ] Chat answer modes
- [ ] What-if Prompt
- [ ] Debate Prompt

---

## 24. 最终优先级结论

最推荐先做的组合：

```text
Paper Briefing + Research Pulse + Reading Path + Research Gap Finder
```

原因：

- Paper Briefing 让每篇论文“可快速消费”。
- Research Pulse 让系统“每天主动出现价值”。
- Reading Path 让新 Topic “不再只是一堆文档”。
- Gap Finder 让系统开始“帮用户产生研究灵感”。

这四个功能完成后，TaskRAG 的体验会从：

```text
我有一个能问论文的知识库
```

升级为：

```text
我有一个每天帮我盯方向、筛论文、规划阅读、找选题的研究助手
```
