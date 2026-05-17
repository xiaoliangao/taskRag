# TaskRAG v1.3+ 新功能实现补全文档（AI Coding Agent 版）

> 目的：补齐上一版文档中“有功能规划，但缺少实现落点”的问题。本文档只写 **怎么实现**，包括数据表、后端模块、Celery 任务、API、前端入口、测试和验收标准。  
> 当前基线：TaskRAG v1.2，已实现 Topic / Document / Chunk / Qdrant / RAG QA / Briefing / Pulse / Reading Path / Gap Finder / Notes / 手动 picker / 自动剪枝 / 任务进度。  
> 推荐版本目标：v1.3 = 研究雷达与争议发现；v1.4 = 写作与产出；v1.5 = 可视化知识组织。  
> 生成日期：2026-05-17。

---

## 0. 这版和上一版的区别

上一版更偏“功能蓝图”，包括 Trend Radar、矛盾检测器、Related Work、图谱、Export Hub 等方向，但没有把每个功能落到：

```text
DB Model
Alembic Migration
Repository
Service
Celery Task
API Route
Schema
Frontend API
Component
权限校验
测试用例
验收标准
```

这版补齐实现细节。AI Coding Agent 应按本文档逐个 Sprint 实现，不要只生成 UI，不要只写 Prompt，不要绕过现有 Topic 隔离与 Qdrant `topic_ids` 过滤。

---

## 1. 总体实现原则

### 1.1 新功能不得破坏现有基线

必须保留：

```text
1. documents / chunks 全局共享。
2. topic_documents 负责 Topic 与 Document 关联。
3. 用户访问文档必须通过 topics.user_id + topic_documents 校验。
4. Topic 级检索必须带 Qdrant payload.topic_ids 过滤。
5. 大模型重任务走 Celery intelligence 队列。
6. worker-intel 当前并发低，所有任务必须限量、可重试、可降级。
```

### 1.2 推荐新增模块命名

后端新增文件建议如下：

```text
backend/app/db/models/research_ext.py
backend/app/db/repositories/research_ext_repo.py
backend/app/schemas/research_ext.py

backend/app/services/trend_service.py
backend/app/services/claim_service.py
backend/app/services/hypothesis_service.py
backend/app/services/comparison_service.py
backend/app/services/writing_service.py
backend/app/services/graph_service.py
backend/app/services/glossary_service.py
backend/app/services/export_service.py
backend/app/services/chat_mode_service.py
backend/app/services/memory_service.py

backend/app/api/routes/trends.py
backend/app/api/routes/claims.py
backend/app/api/routes/hypotheses.py
backend/app/api/routes/comparisons.py
backend/app/api/routes/writing.py
backend/app/api/routes/graph.py
backend/app/api/routes/glossary.py
backend/app/api/routes/exports.py

backend/app/tasks/research_tasks.py
```

前端新增文件建议如下：

```text
frontend/src/api/trends.ts
frontend/src/api/claims.ts
frontend/src/api/hypotheses.ts
frontend/src/api/comparisons.ts
frontend/src/api/writing.ts
frontend/src/api/graph.ts
frontend/src/api/glossary.ts
frontend/src/api/exports.ts

frontend/src/pages/TopicRadar/
frontend/src/pages/TopicStudio/
frontend/src/pages/TopicMap/
frontend/src/components/TrendHeatmap/
frontend/src/components/ConflictCard/
frontend/src/components/HypothesisPanel/
frontend/src/components/ComparisonMatrix/
frontend/src/components/RelatedWorkEditor/
frontend/src/components/KnowledgeGraph/
frontend/src/components/GlossaryHoverCard/
frontend/src/components/ExportHub/
```

### 1.3 Topic 权限统一写法

所有新增 API 必须先获取 owned topic：

```python
@router.get("/topics/{topic_id}/trends/latest")
async def get_latest_trend(
    topic: Topic = Depends(get_owned_topic),
    db: AsyncSession = Depends(get_db),
):
    ...
```

如果某个接口同时传 `document_id`，必须校验该文档属于此 Topic：

```python
await topic_document_repo.ensure_document_in_topic(
    topic_id=topic.id,
    document_id=document_id,
)
```

跨课题功能不得使用“全局无过滤检索”。必须先列出当前用户拥有的 topic ids，再在 Qdrant 里使用：

```json
{
  "key": "topic_ids",
  "match": { "any": [1, 2, 3] }
}
```

---

## 2. Sprint 0：Intelligence Foundation

> 先做基础设施，再做功能。Trend、Conflict、Glossary、Timeline、Related Work 都依赖这些基础能力。

### 2.1 Alembic Migration

新增迁移：

```text
backend/alembic/versions/0003_research_ext.py
```

该迁移先建以下基础表：

```text
topic_terms
term_occurrences
topic_trend_runs
topic_trend_items
paper_claims
claim_relations
comparison_sessions
comparison_items
writing_projects
writing_project_sources
document_relations
method_entities
method_evolution_edges
topic_glossary_terms
hypothesis_checks
hypothesis_evidence
export_jobs
chat_session_summaries
```

如果一次迁移过大，可以拆成：

```text
0003_terms_trends.py
0004_claims_conflicts.py
0005_writing_comparison_exports.py
0006_graph_glossary_memory.py
```

### 2.2 通用任务状态字段

所有 Intelligence 生成类表统一使用：

```text
status: pending / running / success / failed
error_message: text nullable
started_at: timestamptz nullable
finished_at: timestamptz nullable
generated_at: timestamptz nullable
```

### 2.3 LLM JSON 安全解析工具

新增：

```text
backend/app/services/json_llm.py
```

实现：

```python
from __future__ import annotations

import json
import re
from typing import Any
from pydantic import BaseModel, ValidationError


def extract_json_object(text: str) -> dict[str, Any]:
    """Extract the first JSON object from an LLM response."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text)
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def parse_llm_json(text: str, model_cls: type[BaseModel]) -> BaseModel:
    data = extract_json_object(text)
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"LLM JSON does not match schema: {exc}") from exc
```

所有 LLM 输出型功能必须使用该工具，不允许直接 `json.loads(response)`。

### 2.4 Celery 任务包装器

新增：

```text
backend/app/tasks/task_helpers.py
```

实现统一的状态更新、异常捕获、日志记录：

```python
def run_intel_job(job_name: str, fn, *args, **kwargs):
    try:
        logger.info("intel_job_started", job=job_name, args=args)
        return fn(*args, **kwargs)
    except Exception as exc:
        logger.exception("intel_job_failed", job=job_name)
        raise exc
```

如果项目已有类似封装，复用已有封装，不重复造轮子。

---

# Part A：发现层 Discovery

---

## 3. Trend Radar 实现

### 3.1 功能目标

Trend Radar 用于回答：

```text
这个 Topic 最近哪些技术词正在升温？
哪些方法变少了？
哪些关键词是近 60 天新出现的？
这些趋势分别由哪些论文支撑？
```

MVP 不依赖 LLM。先基于 title、abstract、briefing、insight 做术语抽取和时间分桶统计。

### 3.2 数据表

#### `topic_terms`

```sql
CREATE TABLE topic_terms (
    id BIGSERIAL PRIMARY KEY,
    topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    term TEXT NOT NULL,
    normalized_term TEXT NOT NULL,
    term_type TEXT NOT NULL DEFAULT 'keyword',
    source TEXT NOT NULL DEFAULT 'auto',
    first_seen_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ,
    document_count INT NOT NULL DEFAULT 0,
    occurrence_count INT NOT NULL DEFAULT 0,
    trend_score FLOAT NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(topic_id, normalized_term)
);

CREATE INDEX idx_topic_terms_topic ON topic_terms(topic_id);
CREATE INDEX idx_topic_terms_type ON topic_terms(topic_id, term_type);
CREATE INDEX idx_topic_terms_score ON topic_terms(topic_id, trend_score DESC);
```

#### `term_occurrences`

```sql
CREATE TABLE term_occurrences (
    id BIGSERIAL PRIMARY KEY,
    topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    term_id BIGINT NOT NULL REFERENCES topic_terms(id) ON DELETE CASCADE,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id BIGINT NULL REFERENCES chunks(id) ON DELETE SET NULL,
    source_field TEXT NOT NULL,
    context_text TEXT,
    occurred_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(topic_id, term_id, document_id, source_field)
);

CREATE INDEX idx_term_occurrences_topic_doc ON term_occurrences(topic_id, document_id);
CREATE INDEX idx_term_occurrences_term_time ON term_occurrences(term_id, occurred_at);
```

#### `topic_trend_runs`

```sql
CREATE TABLE topic_trend_runs (
    id BIGSERIAL PRIMARY KEY,
    topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    window_days INT NOT NULL DEFAULT 60,
    bucket TEXT NOT NULL DEFAULT 'week',
    status TEXT NOT NULL DEFAULT 'pending',
    summary_md TEXT,
    heatmap_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    generated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_trend_runs_topic_time ON topic_trend_runs(topic_id, generated_at DESC);
```

#### `topic_trend_items`

```sql
CREATE TABLE topic_trend_items (
    id BIGSERIAL PRIMARY KEY,
    trend_run_id BIGINT NOT NULL REFERENCES topic_trend_runs(id) ON DELETE CASCADE,
    topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    term_id BIGINT NOT NULL REFERENCES topic_terms(id) ON DELETE CASCADE,
    term TEXT NOT NULL,
    term_type TEXT NOT NULL,
    status TEXT NOT NULL,
    frequency_recent INT NOT NULL DEFAULT 0,
    frequency_baseline INT NOT NULL DEFAULT 0,
    growth_rate FLOAT NOT NULL DEFAULT 0,
    confidence FLOAT NOT NULL DEFAULT 0,
    evidence_document_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    explanation TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_trend_items_run ON topic_trend_items(trend_run_id);
CREATE INDEX idx_trend_items_topic_status ON topic_trend_items(topic_id, status);
```

### 3.3 术语抽取实现

新增：

```text
backend/app/services/term_extraction.py
```

#### 输入文本来源

按优先级收集：

```text
1. documents.title
2. documents.abstract
3. document_briefings.result_json.method
4. document_briefings.result_json.contributions[]
5. document_briefings.result_json.datasets[]
6. document_briefings.result_json.metrics[]
7. topic_document_insights.result_json.why_read
```

不要扫描所有 chunk，避免成本过高。后续可做后台增量 chunk 术语抽取。

#### 规则抽取

实现规则：

```python
TECH_TERM_PATTERNS = [
    r"\b[A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+\b",      # RAFT-Stereo, DINO-v2
    r"\b[A-Z]{2,}[A-Za-z0-9]*\b",                    # RAG, MVSNet, LoRA
    r"\b[a-z]+(?:\s+[a-z]+){0,3}\s+(?:matching|estimation|attention|transformer|diffusion|retrieval|reranking|alignment)\b",
]
```

归一化：

```python
def normalize_term(term: str) -> str:
    return re.sub(r"\s+", " ", term.strip().lower())
```

过滤：

```text
- 长度 < 2 的丢弃
- 纯数字丢弃
- 常见停用词丢弃：paper, method, model, result, dataset, approach 等
- Topic keywords 保留
- 同一 document 同一 source_field 只保留一次
```

#### 可选 LLM 分类

只对 top 100 terms 做 LLM 分类：

```json
{
  "terms": [
    {"term": "RAFT-Stereo", "term_type": "method"},
    {"term": "KITTI", "term_type": "dataset"}
  ]
}
```

`term_type` 允许值：

```text
method / dataset / metric / model / task / keyword / author / venue
```

### 3.4 Trend 计算逻辑

新增：

```text
backend/app/services/trend_service.py
```

核心函数：

```python
class TrendService:
    def rebuild_terms_for_topic(self, db: Session, topic_id: int) -> None:
        """从 Topic 关联文档中抽取 term，并 upsert topic_terms / term_occurrences。"""

    def generate_trend_run(
        self,
        db: Session,
        topic_id: int,
        window_days: int = 60,
        bucket: str = "week",
    ) -> int:
        """生成一次趋势分析，返回 trend_run_id。"""
```

增长率计算：

```python
def growth_rate(recent_count: int, baseline_count: int) -> float:
    return (recent_count - baseline_count) / max(baseline_count, 1)
```

趋势状态：

```python
if first_seen_at >= now - timedelta(days=window_days):
    status = "emerging"
elif growth_rate >= 1.0 and recent_count >= 2:
    status = "rising"
elif growth_rate <= -0.5 and baseline_count >= 3:
    status = "declining"
else:
    status = "stable"
```

置信度：

```python
confidence = min(1.0, 0.2 + 0.15 * recent_count + 0.1 * len(evidence_docs))
```

### 3.5 Celery 任务

新增到 `backend/app/tasks/research_tasks.py`：

```python
@celery_app.task(name="research.generate_topic_trends", queue="intelligence")
def generate_topic_trends_task(topic_id: int, window_days: int = 60) -> int:
    session_factory = get_sync_sessionmaker()
    with session_factory() as db:
        topic_repo.ensure_exists(db, topic_id)
        service = TrendService()
        service.rebuild_terms_for_topic(db, topic_id)
        run_id = service.generate_trend_run(db, topic_id, window_days=window_days)
        db.commit()
        return run_id
```

触发方式：

```text
1. 用户点击“生成趋势”。
2. 每日 Pulse 生成后，如果新增文档数 > 0，异步触发趋势增量更新。
3. 每周自动生成一次 60 天趋势。
```

### 3.6 API

新增 `backend/app/api/routes/trends.py`：

```http
GET  /api/v1/topics/{topic_id}/trends/latest?window_days=60
GET  /api/v1/topics/{topic_id}/trends/runs
GET  /api/v1/topics/{topic_id}/trends/runs/{run_id}
POST /api/v1/topics/{topic_id}/trends/generate
GET  /api/v1/topics/{topic_id}/terms?type=method&limit=50
```

响应示例：

```json
{
  "run_id": 12,
  "topic_id": 3,
  "window_days": 60,
  "summary_md": "最近 60 天，flow matching 与 long-context retrieval 出现频率上升。",
  "items": [
    {
      "term": "flow matching",
      "term_type": "method",
      "status": "rising",
      "growth_rate": 2.4,
      "confidence": 0.76,
      "evidence_document_ids": [101, 122, 135],
      "explanation": "近 60 天出现 5 次，基线窗口出现 1 次。"
    }
  ],
  "heatmap": {
    "buckets": ["2026-03", "2026-04", "2026-05"],
    "terms": ["flow matching", "Mamba", "long-context RAG"],
    "values": [[1, 2, 5], [0, 1, 3], [2, 2, 2]]
  }
}
```

### 3.7 前端实现

Topic Detail 新增 `Radar` Tab。

组件：

```text
TopicRadarPage
TrendSummaryCard
TrendHeatmap
TrendItemTable
TrendEvidenceDrawer
TermDetailDrawer
```

交互：

```text
1. 打开 Radar Tab，自动请求 latest。
2. 若没有 run，显示“生成趋势雷达”按钮。
3. 点击趋势词，右侧 Drawer 展示 evidence papers。
4. 点击 evidence paper，打开 Document Detail。
5. TrendItem 支持“基于该趋势找 Gap”“加入 Related Work 素材”。
```

### 3.8 测试

后端测试：

```text
test_extract_terms_from_briefings
test_trend_status_emerging
test_trend_status_rising
test_trend_topic_permission
test_trend_generate_task_success
```

前端测试：

```text
Radar 无数据时显示生成按钮
Trend item 点击后打开 evidence drawer
不同 status badge 正确显示
```

### 3.9 验收标准

```text
1. 有 10 篇以上 Topic 文档时，可以生成趋势结果。
2. Heatmap 至少展示 top 20 terms。
3. 每个 rising/emerging term 至少展示 1 篇 evidence paper。
4. 趋势生成失败时，前端能看到失败原因。
5. 用户不能访问其他用户 Topic 的 trend run。
```

---

## 4. Claim Conflict Explorer 实现

### 4.1 功能目标

不要直接叫“矛盾检测器”，实现时命名为：

```text
Claim Conflict Explorer
```

它展示的是“疑似冲突 / 争议信号”，不是事实判决。

### 4.2 数据表

#### `paper_claims`

```sql
CREATE TABLE paper_claims (
    id BIGSERIAL PRIMARY KEY,
    topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id BIGINT NULL REFERENCES chunks(id) ON DELETE SET NULL,
    claim_text TEXT NOT NULL,
    claim_type TEXT NOT NULL,
    method TEXT,
    dataset TEXT,
    metric TEXT,
    setting TEXT,
    polarity TEXT NOT NULL DEFAULT 'neutral',
    confidence FLOAT NOT NULL DEFAULT 0,
    evidence_text TEXT,
    source TEXT NOT NULL DEFAULT 'briefing',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_paper_claims_topic ON paper_claims(topic_id);
CREATE INDEX idx_paper_claims_doc ON paper_claims(document_id);
CREATE INDEX idx_paper_claims_type ON paper_claims(topic_id, claim_type);
CREATE INDEX idx_paper_claims_dataset_metric ON paper_claims(topic_id, dataset, metric);
```

#### `claim_relations`

```sql
CREATE TABLE claim_relations (
    id BIGSERIAL PRIMARY KEY,
    topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    claim_a_id BIGINT NOT NULL REFERENCES paper_claims(id) ON DELETE CASCADE,
    claim_b_id BIGINT NOT NULL REFERENCES paper_claims(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    confidence FLOAT NOT NULL DEFAULT 0,
    reason_md TEXT,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    reviewed_by_user BOOLEAN NOT NULL DEFAULT false,
    user_feedback TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(topic_id, claim_a_id, claim_b_id)
);

CREATE INDEX idx_claim_relations_topic_type ON claim_relations(topic_id, relation_type);
CREATE INDEX idx_claim_relations_confidence ON claim_relations(topic_id, confidence DESC);
```

### 4.3 Claim 抽取实现

新增：

```text
backend/app/services/claim_service.py
```

每篇文档最多抽 8 条 claim，来源优先级：

```text
1. document_briefings.result_json.experiments
2. document_briefings.result_json.contributions
3. document_briefings.result_json.limitations
4. document_briefings.result_json.one_sentence_summary
5. documents.abstract
```

Prompt 输出 JSON：

```json
{
  "claims": [
    {
      "claim_text": "The method improves KITTI 2015 D1-all over prior cost-volume baselines.",
      "claim_type": "result",
      "method": "RAFT-Stereo",
      "dataset": "KITTI 2015",
      "metric": "D1-all",
      "setting": "standard supervised benchmark",
      "polarity": "positive",
      "confidence": 0.82,
      "evidence_text": "..."
    }
  ]
}
```

`claim_type` 允许：

```text
result / limitation / method / assumption / dataset / comparison / negative_result
```

### 4.4 候选 Claim Pair 筛选

禁止全量 O(n²) LLM 判断。先用规则筛：

```python
def candidate_score(a: PaperClaim, b: PaperClaim) -> float:
    score = 0.0
    if a.document_id == b.document_id:
        return 0.0
    if a.claim_type == b.claim_type:
        score += 0.2
    if a.dataset and b.dataset and normalize(a.dataset) == normalize(b.dataset):
        score += 0.3
    if a.metric and b.metric and normalize(a.metric) == normalize(b.metric):
        score += 0.2
    if a.method and b.method and normalize(a.method) != normalize(b.method):
        score += 0.1
    if a.polarity != b.polarity:
        score += 0.2
    return score
```

只将 `score >= 0.45` 的 pair 送 LLM。每次任务最多判断 80 对。

### 4.5 LLM Relation Judge

Prompt 要求：

```text
你是科研论文 claim relation 判断器。
只判断给定两条 claim 的关系。
不要使用外部知识。
如果数据集、指标、实验设置不同，不要判定为 conflict，而应判定为 qualifies 或 unrelated。
输出 JSON。
```

输出：

```json
{
  "relation_type": "conflicts",
  "confidence": 0.73,
  "reason_md": "两条 claim 都讨论 KITTI 2015 的 D1-all，但对同一类方法是否优于 cost-volume baseline 给出相反结论。需要人工确认训练设置是否一致。",
  "evidence": {
    "shared_dataset": "KITTI 2015",
    "shared_metric": "D1-all",
    "caveats": ["training setting not fully specified"]
  }
}
```

`relation_type`：

```text
supports / conflicts / qualifies / unrelated
```

### 4.6 Celery 任务

```python
@celery_app.task(name="research.extract_claims_for_topic", queue="intelligence")
def extract_claims_for_topic_task(topic_id: int, limit_docs: int = 50) -> int:
    ...

@celery_app.task(name="research.detect_claim_conflicts", queue="intelligence")
def detect_claim_conflicts_task(topic_id: int, max_pairs: int = 80) -> int:
    ...
```

任务顺序：

```text
1. 用户点击“扫描争议”。
2. extract_claims_for_topic_task。
3. detect_claim_conflicts_task。
4. 生成 claim_relations。
5. 前端刷新 Conflict 列表。
```

### 4.7 API

```http
POST /api/v1/topics/{topic_id}/claims/extract
GET  /api/v1/topics/{topic_id}/claims
POST /api/v1/topics/{topic_id}/claim-conflicts/detect
GET  /api/v1/topics/{topic_id}/claim-conflicts?type=conflicts&min_confidence=0.6
PATCH /api/v1/topics/{topic_id}/claim-conflicts/{relation_id}/feedback
```

### 4.8 前端实现

组件：

```text
ConflictExplorerPanel
ConflictCard
ClaimEvidenceDrawer
ClaimRelationFilter
ConflictFeedbackButtons
```

卡片展示：

```text
疑似冲突：Paper A vs Paper B
冲突点：...
置信度：0.73
可能原因：实验设置不同 / 指标不同 / 结论相反
证据：Claim A、Claim B、原文片段
操作：标记为有用 / 不成立 / 加入笔记 / 生成对比表
```

UI 文案必须保守：

```text
“疑似冲突”
“可能存在争议”
“需要人工确认”
```

禁止：

```text
“论文 A 证明论文 B 错了”
“已发现事实矛盾”
```

### 4.9 测试

```text
test_claim_extraction_json_schema
test_candidate_pair_rule_filters_same_doc
test_conflict_relation_permission
test_conflict_ui_uses_cautious_copy
test_conflict_task_limits_max_pairs
```

### 4.10 验收标准

```text
1. 对一个已有 20+ 文档的 Topic，可以抽取 claims。
2. Conflict 页面至少展示 supports / qualifies / conflicts 三类关系。
3. 每条 conflict 必须有两个 claim 和两个 document。
4. 每条 relation 必须有 confidence。
5. LLM 输出异常时任务失败可见，不污染旧结果。
```

---

## 5. Breakthrough Signal 实现

### 5.1 功能目标

对新入库论文打“突破候选”标签，用于 Research Pulse 和 Inbox：

```text
短期被快速引用
被多个相关新论文引用
代码 star 增长快
被多个 Topic trend item 关联
```

MVP 只做 Semantic Scholar citation count + 本地 topic 内关联强度。没有外部 citation 数据时降级。

### 5.2 数据表

```sql
CREATE TABLE document_signals (
    id BIGSERIAL PRIMARY KEY,
    topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    signal_type TEXT NOT NULL,
    score FLOAT NOT NULL DEFAULT 0,
    reason_md TEXT,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    source TEXT NOT NULL DEFAULT 'local',
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(topic_id, document_id, signal_type)
);

CREATE INDEX idx_document_signals_topic_type ON document_signals(topic_id, signal_type, score DESC);
```

`signal_type`：

```text
breakthrough_candidate / fast_citation_growth / trend_representative / high_relevance
```

### 5.3 Service

```python
class BreakthroughSignalService:
    def refresh_signals_for_topic(self, db: Session, topic_id: int, max_docs: int = 100) -> None:
        docs = repo.list_recent_topic_documents(db, topic_id, limit=max_docs)
        for doc in docs:
            citation_score = self._semantic_scholar_score(doc)
            local_score = self._local_relevance_score(db, topic_id, doc.id)
            score = 0.6 * citation_score + 0.4 * local_score
            if score >= 0.7:
                repo.upsert_document_signal(...)
```

降级策略：

```text
Semantic Scholar 不可用 → 只用 local_score。
没有引用数据 → 不报错，reason_md 写“外部引用数据不可用，基于本地相关性判断”。
```

### 5.4 API

```http
GET  /api/v1/topics/{topic_id}/signals?type=breakthrough_candidate
POST /api/v1/topics/{topic_id}/signals/refresh
```

### 5.5 前端

在：

```text
Research Pulse
Research Inbox
Document List
Document Detail
```

显示 badge：

```text
🔥 突破候选
```

点击 badge 展示理由。

---

# Part B：理解层 Understanding

---

## 6. Hypothesis Verification 实现

### 6.1 功能目标

用户输入一句研究假设，系统输出：

```text
支持证据
反对证据
限定条件
暂无定论
```

它比 Gap Finder 更适合科研选题阶段。

### 6.2 数据表

```sql
CREATE TABLE hypothesis_checks (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    hypothesis TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    result_md TEXT,
    result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    confidence FLOAT NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE TABLE hypothesis_evidence (
    id BIGSERIAL PRIMARY KEY,
    check_id BIGINT NOT NULL REFERENCES hypothesis_checks(id) ON DELETE CASCADE,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id BIGINT NULL REFERENCES chunks(id) ON DELETE SET NULL,
    stance TEXT NOT NULL,
    quote TEXT,
    explanation TEXT,
    score FLOAT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_hypothesis_checks_topic ON hypothesis_checks(topic_id, created_at DESC);
CREATE INDEX idx_hypothesis_evidence_check ON hypothesis_evidence(check_id);
```

`stance`：

```text
support / oppose / qualify / neutral
```

### 6.3 实现流程

```text
1. 用户输入 hypothesis。
2. 生成 3 个检索 query：原始假设、支持方向 query、反对方向 query。
3. Qdrant 在当前 topic_id 内检索 top_k=30。
4. rerank 后选 top_n=12。
5. LLM 对每个 evidence chunk 判断 stance。
6. 聚合成 Markdown 结果。
7. 保存 hypothesis_checks / hypothesis_evidence。
```

### 6.4 Service

```python
class HypothesisService:
    def create_check(self, db: Session, user_id: int, topic_id: int, hypothesis: str) -> int:
        ...

    def run_check(self, db: Session, check_id: int) -> None:
        ...

    def classify_evidence(self, hypothesis: str, chunk_text: str) -> EvidenceJudgement:
        ...
```

Evidence 判断 JSON：

```json
{
  "stance": "support",
  "score": 0.78,
  "quote": "...",
  "explanation": "该片段表明迭代优化在密集匹配场景下提升了误差指标。"
}
```

### 6.5 API

```http
POST /api/v1/topics/{topic_id}/hypotheses/check
GET  /api/v1/topics/{topic_id}/hypotheses
GET  /api/v1/topics/{topic_id}/hypotheses/{check_id}
DELETE /api/v1/topics/{topic_id}/hypotheses/{check_id}
```

### 6.6 前端

组件：

```text
HypothesisPanel
HypothesisInput
HypothesisResultColumns
EvidenceCard
```

布局：

```text
[输入假设]

支持证据 | 反对证据 | 限定条件 / 不确定
```

### 6.7 验收标准

```text
1. 输入一句假设后能生成 check 任务。
2. 每条 evidence 必须绑定 document_id。
3. 如果没有强证据，必须显示“当前 Topic 暂无充分证据”。
4. 支持用户删除历史 check。
```

---

## 7. Concept Glossary 实现

### 7.1 功能目标

把 Topic 中反复出现的技术词变成可 hover 的概念词典。

例如用户在 Briefing 里看到：

```text
RAFT-Stereo
Mamba
Cost Volume
Depth Anything
```

hover 后展示：

```text
一句话定义
首次出现论文
代表论文
相关趋势
```

### 7.2 数据表

```sql
CREATE TABLE topic_glossary_terms (
    id BIGSERIAL PRIMARY KEY,
    topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    term_id BIGINT NULL REFERENCES topic_terms(id) ON DELETE SET NULL,
    term TEXT NOT NULL,
    normalized_term TEXT NOT NULL,
    definition TEXT,
    aliases_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    representative_document_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence FLOAT NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'auto',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(topic_id, normalized_term)
);

CREATE INDEX idx_glossary_topic ON topic_glossary_terms(topic_id);
```

### 7.3 Service

```python
class GlossaryService:
    def generate_for_topic(self, db: Session, topic_id: int, limit_terms: int = 80) -> None:
        terms = topic_terms_repo.list_top_terms(db, topic_id, limit=limit_terms)
        for term in terms:
            evidence_docs = repo.find_representative_docs(db, topic_id, term.id, limit=3)
            definition = self._generate_definition(term, evidence_docs)
            repo.upsert_glossary_term(...)
```

Prompt 输出：

```json
{
  "definition": "RAFT-Stereo 是一种将 RAFT 的迭代更新思想用于双目立体匹配的模型。",
  "aliases": ["RAFT Stereo"],
  "confidence": 0.83
}
```

### 7.4 API

```http
GET  /api/v1/topics/{topic_id}/glossary
GET  /api/v1/topics/{topic_id}/glossary/lookup?term=RAFT-Stereo
POST /api/v1/topics/{topic_id}/glossary/generate
PATCH /api/v1/topics/{topic_id}/glossary/{term_id}
```

### 7.5 前端

```text
GlossaryPage
GlossaryHoverCard
GlossaryTermDrawer
```

在 Briefing / Related Work / Trend 页面中，把已知 glossary term 自动包装成 hover span。

### 7.6 验收标准

```text
1. Glossary 可以从 topic_terms 生成。
2. 每个定义必须有 representative_document_ids。
3. 用户可以手动编辑定义。
4. Hover 卡片加载失败不影响正文显示。
```

---

## 8. Knowledge Graph 与 Method Timeline 实现

### 8.1 功能目标

Graph 和 Timeline 用于让知识“看得见”。

MVP 不强依赖真实 citation graph。先做弱关系图谱：

```text
same_method
same_dataset
same_metric
same_keyword_cluster
same_author
cites，如果 metadata_json.references 存在
```

### 8.2 数据表

#### `document_relations`

```sql
CREATE TABLE document_relations (
    id BIGSERIAL PRIMARY KEY,
    topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    source_document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    target_document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    confidence FLOAT NOT NULL DEFAULT 0,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    source TEXT NOT NULL DEFAULT 'local',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(topic_id, source_document_id, target_document_id, relation_type)
);

CREATE INDEX idx_doc_rel_topic ON document_relations(topic_id);
CREATE INDEX idx_doc_rel_type ON document_relations(topic_id, relation_type);
```

#### `method_entities`

```sql
CREATE TABLE method_entities (
    id BIGSERIAL PRIMARY KEY,
    topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    description TEXT,
    first_seen_document_id BIGINT NULL REFERENCES documents(id) ON DELETE SET NULL,
    first_seen_at TIMESTAMPTZ,
    aliases_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(topic_id, normalized_name)
);
```

#### `method_evolution_edges`

```sql
CREATE TABLE method_evolution_edges (
    id BIGSERIAL PRIMARY KEY,
    topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    from_method_id BIGINT NOT NULL REFERENCES method_entities(id) ON DELETE CASCADE,
    to_method_id BIGINT NOT NULL REFERENCES method_entities(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    confidence FLOAT NOT NULL DEFAULT 0,
    evidence_document_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    explanation TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(topic_id, from_method_id, to_method_id, relation_type)
);
```

### 8.3 Graph 生成逻辑

```python
class GraphService:
    def rebuild_document_relations(self, db: Session, topic_id: int) -> None:
        docs = repo.list_topic_docs_with_briefings(db, topic_id)
        self._build_citation_edges(db, topic_id, docs)
        self._build_same_dataset_edges(db, topic_id, docs)
        self._build_same_method_edges(db, topic_id, docs)
        self._build_same_term_edges(db, topic_id, docs)
```

边权：

```text
cites: 1.0
same_method: 0.75
same_dataset: 0.6
same_metric: 0.5
same_keyword_cluster: 0.4
same_author: 0.4
```

### 8.4 Method Timeline 生成逻辑

从 `topic_terms` 中取 `term_type='method'`，结合 `document_briefings` 的方法描述。

```python
class MethodTimelineService:
    def rebuild_methods(self, db: Session, topic_id: int) -> None:
        methods = term_repo.list_terms_by_type(db, topic_id, "method")
        for term in methods:
            first_doc = occurrence_repo.find_first_document(db, topic_id, term.id)
            repo.upsert_method_entity(...)
```

LLM 只用于判断方法关系：

```json
{
  "edges": [
    {
      "from_method": "GwcNet",
      "to_method": "RAFT-Stereo",
      "relation_type": "replaces",
      "confidence": 0.62,
      "explanation": "后者采用迭代更新机制，与前者的 cost volume 处理方式不同。"
    }
  ]
}
```

`relation_type`：

```text
improves / extends / replaces / combines / evaluates / compares_with
```

### 8.5 API

```http
POST /api/v1/topics/{topic_id}/graph/rebuild
GET  /api/v1/topics/{topic_id}/graph
GET  /api/v1/topics/{topic_id}/timeline/methods
POST /api/v1/topics/{topic_id}/timeline/rebuild
```

Graph 响应：

```json
{
  "nodes": [
    {
      "id": 101,
      "type": "document",
      "title": "RAFT-Stereo...",
      "year": 2021,
      "size": 8,
      "status": "read"
    }
  ],
  "edges": [
    {
      "source": 101,
      "target": 122,
      "type": "same_dataset",
      "weight": 0.6
    }
  ]
}
```

### 8.6 前端

```text
TopicMapPage
KnowledgeGraph
GraphFilterPanel
MethodTimeline
DocumentNodeDrawer
```

注意：D3 图不要一次渲染超过 300 节点。超过时按重要度筛 top 300。

### 8.7 验收标准

```text
1. 无 citation metadata 时仍可生成弱关系图谱。
2. Graph 节点点击能打开文档详情。
3. Timeline 按 published_at 排序。
4. Graph 生成失败不影响 Topic 其他页面。
```

---

# Part C：写作层 Writing

---

## 9. Method Comparison Table 实现

### 9.1 功能目标

用户选择 2-8 篇论文，生成方法对比矩阵，并支持导出 Markdown / LaTeX。

### 9.2 数据表

```sql
CREATE TABLE comparison_sessions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    result_md TEXT,
    result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE TABLE comparison_items (
    id BIGSERIAL PRIMARY KEY,
    comparison_session_id BIGINT NOT NULL REFERENCES comparison_sessions(id) ON DELETE CASCADE,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'target',
    order_index INT NOT NULL DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(comparison_session_id, document_id)
);
```

### 9.3 Result JSON 格式

```json
{
  "columns": ["paper", "problem", "method", "datasets", "metrics", "results", "strengths", "limitations", "code"],
  "rows": [
    {
      "document_id": 101,
      "paper": "RAFT-Stereo",
      "problem": "Stereo matching",
      "method": "Iterative update operator",
      "datasets": ["KITTI", "Scene Flow"],
      "metrics": ["EPE", "D1-all"],
      "results": "...",
      "strengths": "...",
      "limitations": "...",
      "code": "unknown"
    }
  ],
  "summary": "这几篇工作的主要差异在于..."
}
```

### 9.4 Service

```python
class ComparisonService:
    def create_session(self, db, user_id, topic_id, document_ids, title=None) -> int:
        # 校验每个 document_id 都属于 topic
        ...

    def generate(self, db, session_id: int) -> None:
        # 优先使用 document_briefings，不足时回退 abstract / chunks
        ...

    def export_markdown(self, session_id: int) -> str:
        ...

    def export_latex(self, session_id: int) -> str:
        ...
```

### 9.5 API

```http
POST /api/v1/topics/{topic_id}/comparisons
GET  /api/v1/topics/{topic_id}/comparisons
GET  /api/v1/topics/{topic_id}/comparisons/{comparison_id}
POST /api/v1/topics/{topic_id}/comparisons/{comparison_id}/generate
GET  /api/v1/topics/{topic_id}/comparisons/{comparison_id}/export?format=markdown
GET  /api/v1/topics/{topic_id}/comparisons/{comparison_id}/export?format=latex
```

### 9.6 前端

入口：

```text
DocumentList 多选 → Compare
ReadingPath 阶段 → Compare this stage
ConflictCard → Compare these papers
Chat Citation Panel → Compare cited papers
```

组件：

```text
ComparisonCreateModal
ComparisonMatrix
ComparisonSummary
ComparisonExportButtons
```

### 9.7 验收标准

```text
1. 用户最多选择 8 篇，少于 2 篇时报错。
2. 生成结果优先复用 briefing，不能重新全量读 PDF。
3. Markdown / LaTeX 可复制。
4. 跨用户 document_id 不可比较。
```

---

## 10. Related Work Studio 实现

### 10.1 功能目标

用户输入自己的研究问题或方法描述，系统基于 Topic 文档生成可编辑的 Related Work 草稿，带引用。

### 10.2 数据表

```sql
CREATE TABLE writing_projects (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    writing_type TEXT NOT NULL DEFAULT 'related_work',
    user_intent TEXT,
    scope_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    outline_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    draft_md TEXT,
    citation_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'draft',
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE writing_project_sources (
    id BIGSERIAL PRIMARY KEY,
    writing_project_id BIGINT NOT NULL REFERENCES writing_projects(id) ON DELETE CASCADE,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id BIGINT NULL REFERENCES chunks(id) ON DELETE SET NULL,
    role TEXT NOT NULL DEFAULT 'supporting',
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 10.3 Scope 选项

```json
{
  "source_scope": "topic_all | recent | favorites | read | selected_documents | reading_path | comparison",
  "recent_days": 180,
  "document_ids": [101, 122],
  "reading_path_id": 3,
  "comparison_id": 5,
  "language": "zh-CN",
  "citation_style": "numbered"
}
```

### 10.4 实现流程

```text
1. 创建 writing_project。
2. 根据 scope 召回候选 documents。
3. 对候选 documents 读取 briefing + insight + selected chunks。
4. 生成 source groups：同类方法 / 对比方法 / 数据集 / 评估指标 / 局限。
5. 生成 outline。
6. 用户确认或编辑 outline。
7. 生成 draft。
8. citation validator 检查每个引用存在于 writing_project_sources。
9. 保存 draft_md / citation_json。
```

### 10.5 Citation Validator

新增：

```text
backend/app/services/citation_validator.py
```

规则：

```text
1. draft 中的每个 [n] 必须能映射到 citation_json。
2. citation_json 中的 document_id 必须在 writing_project_sources。
3. 如果某句话没有证据，不允许伪造引用。
4. 验证失败时，返回 failed 状态，并提示重新生成。
```

### 10.6 API

```http
POST  /api/v1/topics/{topic_id}/writing-projects
GET   /api/v1/topics/{topic_id}/writing-projects
GET   /api/v1/topics/{topic_id}/writing-projects/{project_id}
PATCH /api/v1/topics/{topic_id}/writing-projects/{project_id}
POST  /api/v1/topics/{topic_id}/writing-projects/{project_id}/select-sources
POST  /api/v1/topics/{topic_id}/writing-projects/{project_id}/generate-outline
POST  /api/v1/topics/{topic_id}/writing-projects/{project_id}/generate-draft
GET   /api/v1/topics/{topic_id}/writing-projects/{project_id}/export?format=markdown
```

### 10.7 前端

页面：

```text
TopicStudioPage
```

模块：

```text
WritingProjectList
WritingProjectCreateModal
SourceScopeSelector
SourceGroupPanel
OutlineEditor
RelatedWorkEditor
CitationSidebar
ExportButtons
```

### 10.8 Prompt 约束

Related Work Prompt 必须包含：

```text
你只能基于给定 sources 写作。
每个具体 claim 后必须有引用编号。
不要编造文献、作者、年份、指标。
证据不足时写“当前 Topic 文献中未找到充分证据”。
输出 Markdown。
```

### 10.9 验收标准

```text
1. 用户可以基于 favorites / selected_documents 生成草稿。
2. 草稿每个引用都能在 citation sidebar 中定位到文档。
3. 用户可以编辑 draft 并保存。
4. 可以导出 Markdown。
5. citation validation 失败时不展示为成功草稿。
```

---

## 11. Export Hub 实现

### 11.1 功能目标

低成本、高留存功能：

```text
BibTeX
Markdown
Obsidian Vault zip
Notion CSV
Comparison Markdown / LaTeX
Related Work Markdown
```

### 11.2 数据表

```sql
CREATE TABLE export_jobs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    export_type TEXT NOT NULL,
    scope_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending',
    file_path TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX idx_export_jobs_user_topic ON export_jobs(user_id, topic_id, created_at DESC);
```

### 11.3 Export Service

```python
class ExportService:
    def export_bibtex(self, db, topic_id, scope) -> str:
        ...

    def export_obsidian_zip(self, db, topic_id, scope) -> Path:
        ...

    def export_notion_csv(self, db, topic_id, scope) -> Path:
        ...
```

### 11.4 BibTeX 拼接规则

优先级：

```text
1. metadata_json.bibtex 如果存在，直接用。
2. arXiv 文献用 @misc。
3. title / authors / year / url 不足时使用 fallback。
```

示例：

```bibtex
@misc{raftstereo2021,
  title={RAFT-Stereo: Multilevel Recurrent Field Transforms for Stereo Matching},
  author={...},
  year={2021},
  eprint={...},
  archivePrefix={arXiv},
  url={...}
}
```

### 11.5 Obsidian Vault

每篇论文一个 Markdown：

```markdown
# Paper Title

- Source: arXiv
- URL: ...
- Status: unread
- Tags: #stereo-matching #RAFT

## Briefing
...

## Contributions
...

## Limitations
...

## Related
- [[Another Paper]]
```

打包 zip：

```text
exports/topic-{topic_id}/obsidian-{job_id}.zip
```

### 11.6 API

```http
POST /api/v1/topics/{topic_id}/exports
GET  /api/v1/topics/{topic_id}/exports
GET  /api/v1/topics/{topic_id}/exports/{job_id}/download
```

### 11.7 前端

```text
ExportHub
ExportScopeSelector
ExportJobList
```

### 11.8 验收标准

```text
1. 用户可以导出当前 Topic 的 BibTeX。
2. Obsidian zip 至少包含每篇论文一个 .md 文件。
3. 下载接口必须校验 user_id + topic_id。
4. 导出文件不永久公开暴露 URL。
```

---

# Part D：对话层 Conversation

---

## 12. Multi-role Chat 实现

### 12.1 功能目标

在 Chat 中增加模式：

```text
默认模式
导师模式
入门模式
辩论模式
审稿人模式
```

这是低成本高体验功能，主要修改 Prompt。

### 12.2 数据模型

如果 `chat_sessions` 可以扩展字段：

```sql
ALTER TABLE chat_sessions ADD COLUMN mode TEXT NOT NULL DEFAULT 'default';
```

如果不想改旧表，也可以在 `chat_messages.metadata_json` 中保存每条消息的 mode。

推荐改 `chat_sessions.mode`，因为 session 级模式更自然。

### 12.3 Prompt 模板

新增：

```text
backend/app/rag/chat_modes.py
```

```python
CHAT_MODE_SYSTEM_HINTS = {
    "default": "保持准确、基于引用回答。",
    "mentor": "你像研究导师一样回答。指出假设、局限、潜在实验缺口，并在必要时反问用户。",
    "beginner": "你用入门友好的方式解释，避免不必要术语，必要时使用类比。",
    "debate": "你必须分别列出支持观点和反对观点，并给出各自文献依据。",
    "reviewer": "你像审稿人一样严格评价方法贡献、实验充分性、局限和威胁。",
}
```

在 `rag/prompt.py` 中注入：

```python
def build_system_prompt(..., chat_mode: str = "default"):
    mode_hint = CHAT_MODE_SYSTEM_HINTS.get(chat_mode, CHAT_MODE_SYSTEM_HINTS["default"])
    ...
```

### 12.4 API

```http
POST /api/v1/topics/{topic_id}/chat/sessions
Body: {"title": "...", "mode": "mentor"}

PATCH /api/v1/topics/{topic_id}/chat/sessions/{session_id}
Body: {"mode": "debate"}
```

### 12.5 前端

Chat 输入框上方增加 Segmented：

```text
默认 / 导师 / 入门 / 辩论 / 审稿人
```

切换时：

```text
1. 只影响当前 session。
2. 已有消息不重写。
3. 下一条用户消息使用新 mode。
```

### 12.6 验收标准

```text
1. 不同模式下系统 prompt 明显不同。
2. Debate 模式回答必须分“支持 / 反对”。
3. Beginner 模式回答不得过度使用术语。
4. 模式切换不影响 Topic 检索过滤。
```

---

## 13. Conversation Memory 实现

### 13.1 功能目标

让系统记住用户在某个 Topic 的长期研究上下文：

```text
用户的研究目标
已经讨论过的关键结论
排除方向
实验想法
写作计划
```

### 13.2 数据表

```sql
CREATE TABLE chat_session_summaries (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    chat_session_id BIGINT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    summary_md TEXT NOT NULL,
    memory_items_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(chat_session_id)
);
```

可选新增：

```sql
CREATE TABLE research_memory_items (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    memory_type TEXT NOT NULL,
    content_md TEXT NOT NULL,
    evidence_document_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_type TEXT NOT NULL DEFAULT 'chat',
    confidence FLOAT NOT NULL DEFAULT 0.7,
    pinned BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

如果当前版本已有 `research_notes` 并支持 pinned notes，可先不建 `research_memory_items`，只做 `chat_session_summaries`。

### 13.3 生成策略

触发条件：

```text
1. session 有至少 6 条消息。
2. 距离上次 summary 超过 10 条消息。
3. 用户关闭 session 或切换 topic 时异步生成。
```

Prompt 输出：

```json
{
  "summary_md": "本轮对话主要讨论了...",
  "memory_items": [
    {
      "memory_type": "user_goal",
      "content": "用户更关注实时 stereo matching，而非 medical stereo。",
      "confidence": 0.85
    }
  ]
}
```

### 13.4 QA 注入策略

在 `qa_service.py` 中：

```text
1. 取当前 Topic 最近 3 个 chat_session_summaries。
2. 取 pinned research_notes。
3. 取与当前 query 语义相关的 memory items。
4. 拼成 USER_RESEARCH_CONTEXT 段。
```

不要注入过多，建议总长度小于 1500 tokens。

### 13.5 API

```http
GET  /api/v1/topics/{topic_id}/chat/memory
POST /api/v1/topics/{topic_id}/chat/sessions/{session_id}/summarize
DELETE /api/v1/topics/{topic_id}/chat/memory/{summary_id}
```

### 13.6 前端

```text
ChatMemoryDrawer
SessionSummaryCard
PinMemoryButton
```

### 13.7 验收标准

```text
1. 长 session 可以生成 summary。
2. 新 session 可以看到历史摘要被注入 prompt。
3. 用户可以删除不想保留的 summary。
4. Summary 不得包含其他用户 Topic 信息。
```

---

## 14. Cross-topic QA 实现

### 14.1 功能目标

支持用户比较自己多个 Topic 的关系：

```text
“RAG 和 Agent 方向最近有什么共同趋势？”
“Stereo Matching 和 Depth Estimation 的方法是否在融合？”
```

### 14.2 安全约束

绝对不能直接取消 topic filter。

正确做法：

```python
owned_topic_ids = topic_repo.list_topic_ids_by_user(db, current_user.id)
allowed_topic_ids = requested_topic_ids or owned_topic_ids
assert set(allowed_topic_ids).issubset(set(owned_topic_ids))
```

Qdrant filter：

```json
{
  "key": "topic_ids",
  "match": { "any": [1, 2, 3] }
}
```

### 14.3 API

```http
POST /api/v1/qa/cross-topic
Body:
{
  "topic_ids": [1, 2],
  "question": "...",
  "mode": "debate"
}
```

响应引用必须包含 topic 信息：

```json
{
  "answer": "...",
  "citations": [
    {"topic_id": 1, "topic_name": "RAG", "document_id": 101, "chunk_id": 5001},
    {"topic_id": 2, "topic_name": "Agent", "document_id": 122, "chunk_id": 6123}
  ]
}
```

### 14.4 前端

新增入口可以放在全局 Chat 或 Topic Chat 的“跨课题”按钮里。

组件：

```text
CrossTopicSelector
CrossTopicChatPanel
CitationTopicBadge
```

### 14.5 验收标准

```text
1. 用户只能选择自己的 topics。
2. 引用必须标注 topic。
3. 未选择 topic 时默认使用当前用户全部 topics，但仍然按 owned_topic_ids 过滤。
```

---

# Part E：实现顺序与文件级任务

---

## 15. 推荐 Sprint 顺序

### Sprint 0：基础迁移与工具

```text
后端：
- research_ext.py models
- Alembic migration
- research_ext_repo.py
- json_llm.py
- task_helpers.py
- api/router.py 预留路由注册

验收：
- alembic upgrade head 成功
- backend 启动成功
- pytest 基础模型导入成功
```

### Sprint 1：Trend Radar

```text
后端：
- term_extraction.py
- trend_service.py
- research_tasks.generate_topic_trends_task
- trends.py route

前端：
- api/trends.ts
- TopicRadarPage
- TrendHeatmap
- TrendItemTable

验收：
- 可以从 Topic 生成趋势
- 有 heatmap
- 有 evidence documents
```

### Sprint 2：Claim Conflict Explorer

```text
后端：
- claim_service.py
- claim extraction task
- conflict detection task
- claims.py route

前端：
- api/claims.ts
- ConflictExplorerPanel
- ConflictCard
- ClaimEvidenceDrawer

验收：
- 能抽 claims
- 能生成 claim_relations
- UI 展示疑似冲突
```

### Sprint 3：Hypothesis Verification + Multi-role Chat

```text
后端：
- hypothesis_service.py
- hypotheses.py route
- rag/chat_modes.py
- qa_service.py 注入 mode

前端：
- HypothesisPanel
- Chat mode selector

验收：
- 假设验证输出三列证据
- 聊天模式切换生效
```

### Sprint 4：Comparison + Related Work Studio

```text
后端：
- comparison_service.py
- writing_service.py
- citation_validator.py
- comparisons.py route
- writing.py route

前端：
- ComparisonMatrix
- TopicStudioPage
- RelatedWorkEditor
- CitationSidebar

验收：
- 多论文对比矩阵可生成
- Related Work 草稿可生成且带引用
```

### Sprint 5：Graph + Glossary + Export Hub

```text
后端：
- graph_service.py
- glossary_service.py
- export_service.py
- graph.py / glossary.py / exports.py routes

前端：
- TopicMapPage
- KnowledgeGraph
- MethodTimeline
- GlossaryHoverCard
- ExportHub

验收：
- Graph 可展示弱关系
- Glossary 可 hover
- BibTeX / Obsidian zip 可导出
```

---

## 16. API 路由注册清单

在 `backend/app/api/router.py` 中新增：

```python
from app.api.routes import trends, claims, hypotheses, comparisons, writing, graph, glossary, exports

api_router.include_router(trends.router, prefix="/topics/{topic_id}/trends", tags=["trends"])
api_router.include_router(claims.router, prefix="/topics/{topic_id}", tags=["claims"])
api_router.include_router(hypotheses.router, prefix="/topics/{topic_id}/hypotheses", tags=["hypotheses"])
api_router.include_router(comparisons.router, prefix="/topics/{topic_id}/comparisons", tags=["comparisons"])
api_router.include_router(writing.router, prefix="/topics/{topic_id}/writing-projects", tags=["writing"])
api_router.include_router(graph.router, prefix="/topics/{topic_id}", tags=["graph"])
api_router.include_router(glossary.router, prefix="/topics/{topic_id}/glossary", tags=["glossary"])
api_router.include_router(exports.router, prefix="/topics/{topic_id}/exports", tags=["exports"])
```

注意：如果项目当前 router 风格不同，按现有风格注册，但 URL 保持一致。

---

## 17. 前端信息架构

不要继续堆 10 个 Tab。建议压缩成 4 个主工作区：

```text
Overview / Inbox
Chat
Radar
Studio
Map
```

各功能归属：

| 工作区 | 功能 |
|---|---|
| Overview / Inbox | Pulse、Breakthrough Signal、推荐论文 |
| Chat | RAG QA、Multi-role Chat、Cross-topic QA |
| Radar | Trend Radar、Claim Conflict、Hypothesis Verification |
| Studio | Comparison、Related Work、Export Hub |
| Map | Knowledge Graph、Method Timeline、Glossary |

---

## 18. 测试总清单

### 18.1 权限测试

每个新增 API 必须覆盖：

```text
user_a 创建 topic_a
user_b 创建 topic_b
user_a 访问 topic_b 的新功能接口 → 403 / 404
user_a 用 topic_a 传入 topic_b document_id → 403 / 404
```

### 18.2 任务测试

```text
Trend task 成功 / 失败
Claim extraction task 成功 / LLM JSON 失败
Conflict detection max_pairs 限制
Writing draft citation validation 失败
Export job 文件不存在时返回错误
```

### 18.3 UI 测试

```text
Radar Tab 无数据状态
Heatmap 渲染
ConflictCard 谨慎文案
Comparison 多选上限
RelatedWork citation sidebar
Export download 权限
```

### 18.4 回归测试

新增功能不得破坏：

```text
Topic CRUD
Document list/detail
PDF preview
Briefing generate
Pulse generate
Reading Path
Gap Finder
RAG Chat SSE
Manual Picker
Task Progress
```

---

## 19. 风险与降级策略

| 风险 | 降级策略 |
|---|---|
| LLM JSON 不稳定 | 使用 parse_llm_json + schema 校验；失败展示 task error |
| worker-intel 资源不足 | 每个任务加 limit；批处理；用户手动触发优先 |
| citation metadata 缺失 | Graph 用 same_method / same_dataset 弱关系 |
| Conflict 误判 | UI 用“疑似冲突”；必须展示 evidence 和 confidence |
| Related Work 伪引用 | citation_validator 必须通过后才保存 success |
| Trend 噪声大 | 支持用户 dismiss term；加入 stop terms |
| Export 文件泄露 | 下载接口必须鉴权；文件路径不直接公开 |

---

## 20. 最终验收路径

实现完 v1.3 的最小闭环后，用户应该能完成：

```text
1. 打开 Topic → Radar。
2. 点击“生成趋势雷达”。
3. 看到近 60 天 rising / emerging terms。
4. 点击某个 term → 查看 evidence papers。
5. 点击“扫描疑似争议”。
6. 看到 Claim Conflict Cards。
7. 从 conflict 选择两篇论文 → 生成 Comparison Table。
8. 输入自己的研究想法 → 生成 Related Work 草稿。
9. 导出 Markdown / BibTeX。
```

这才是“新功能有实现”的版本。

---

## 21. 给 AI Coding Agent 的执行提示

实现时按这个顺序做，不要跳：

```text
1. 先建表和 Repository。
2. 再写 Service，Service 先用同步 Session 适配 Celery。
3. 再接 Celery task。
4. 再接 API route。
5. 再接前端页面。
6. 最后补测试。
```

每个功能先做 MVP，不要一开始追求完美：

```text
Trend Radar：先规则统计，不上复杂 NLP。
Conflict：先 claim 抽取 + 候选 pair + LLM 判断，不全量对比。
Graph：先弱关系图谱，不依赖真实引用。
Related Work：先 selected_documents scope，不一开始支持所有 scope。
Export：先 BibTeX + Markdown，再做 Obsidian / Notion。
```

