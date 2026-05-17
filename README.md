# TaskRAG

个人化、按课题（Topic）组织的研究追踪 RAG **演示系统**。

每个用户可创建最多 5 个研究课题（如"立体匹配"、"RAG"）；系统每天自动从 arXiv / HuggingFace / GitHub 等搜索匹配论文/项目，下载并向量化到 Qdrant；用户在课题知识库中进行问答，得到带引用的答案；采集完成后通过站内通知 + 邮件推送结果。

详见 `PRD.md`（v0.3）与 `TaskRAG_AI_Development_Document.md`（v1.0）。

---

## 快速开始

### 1. 准备 API Key

在项目根目录复制 `.env.example` 为 `.env`，填入：

```env
# 必填：embedding（SiliconFlow，免费/低价 bge-m3）
SILICONFLOW_API_KEY=sk-xxx

# 必填：LLM（任选其一，默认 deepseek）
DEEPSEEK_API_KEY=sk-xxx
# 或
QWEN_API_KEY=sk-xxx
# 然后把 LLM_PROVIDER 改成对应值

# 可选：邮件通知
GMAIL_USERNAME=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
EMAIL_FROM=you@gmail.com

# 可选：GitHub 采集器
GITHUB_TOKEN=ghp_xxx
```

### 2. 启动

```bash
docker compose up --build
```

首次启动会拉取镜像、构建后端镜像、下载 TEI reranker 模型（约 1GB）。请耐心等待。

### 3. 灌入演示数据

```bash
docker compose exec backend python scripts/seed_demo.py
```

会创建：

- 演示用户 `demo@example.com / demo123`
- 3 个预置课题：Stereo Matching / RAG / Diffusion Models

### 4. 打开浏览器

- 前端：http://localhost:5173
- 后端 Swagger：http://localhost:8000/docs
- Qdrant Dashboard：http://localhost:6333/dashboard

---

## 服务清单

| 服务 | 端口 | 用途 |
|---|---|---|
| frontend | 5173 | React + Vite |
| backend | 8000 | FastAPI |
| postgres | 5432 | 业务数据 |
| redis | 6379 | Celery broker / cache |
| qdrant | 6333 | 向量库 |
| reranker | 8081 | TEI（bge-reranker-v2-m3） |
| worker-urgent / scheduled / backfill | — | Celery workers |
| celery-beat | — | 每 60s 扫描到期 Topic |

---

## 工程文档

- `PRD.md` — 产品需求 v0.3
- `TaskRAG_AI_Development_Document.md` — 开发约定 v1.0
- `backend/` — FastAPI + Celery + LangChain
- `frontend/` — React 18 + TS + Ant Design

---

## 已知限制（Demo 范围）

- 不做生产级监控 / 备份 / HA
- 不做团队协作 / 知识库共享
- 单用户最多 5 个课题
- 首次回填固定 30 天
- Webhook 通知通道仅占位
