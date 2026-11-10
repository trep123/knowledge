# Local Knowledge Base Platform

> 本地私有化、可完全离线运行的统一知识库与 RAG 问答平台。一个网关同时对外提供 **Web 管理端**、**REST API** 与 **OpenAI 兼容 API**，所有数据与依赖都收敛在项目目录内，不污染系统环境。

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Backend](https://img.shields.io/badge/backend-FastAPI-009688.svg)](backend)
[![Frontend](https://img.shields.io/badge/frontend-React%2018%20%2B%20AntD-61dafb.svg)](frontend)
[![Deploy](https://img.shields.io/badge/deploy-Docker%20Compose-2496ed.svg)](docker-compose.yml)

---

## ✨ 核心特性

- **混合检索（Hybrid Retrieval）**：稠密向量（bge-m3，1024 维）+ 稀疏向量（jieba 分词 → Qdrant 服务端 IDF）→ **RRF 融合** → **bge-reranker-v2-m3 精排**，多知识库并行召回后统一融合。
- **RAG 智能问答**：基于检索证据生成回答，**禁止编造**，附带**引用溯源**（文件名 + 页码 + 命中片段），支持 **SSE 流式**输出。
- **完整文档流水线**：PDF / DOCX / Markdown / TXT / 图片，扫描版 PDF 与图片自动 **OCR**（中英文），按**字符**切片、SHA256 去重、Celery 异步处理、失败可重试、支持重处理与版本递增。
- **两套对外接口**：面向 Web 的 REST API（JWT 鉴权）+ 面向第三方程序的 **OpenAI 兼容 API**（`/v1/chat/completions`，API Key 鉴权），可直接被 LangChain、OpenAI SDK 等生态复用。
- **企业级权限与计量**：API Key 细粒度 scope、按知识库授权、每分钟/每日限流、调用日志与用量统计。
- **批量操作**：知识库批量删除；文档批量上传 / 批量删除 / 批量重处理，逐项返回成败。
- **GPU 加速、可离线**：Embedding / Reranker / LLM 全部本地推理（Tesla P4 实测可用），模型只读挂载，无任何外部 API 依赖。
- **数据与环境隔离**：PostgreSQL、Qdrant、Redis、上传文件、日志、备份全部落在项目 `data/` 目录；宿主机不安装任何 pip/npm 包。

## 🧱 架构总览

```
                         ┌──────────────────────────────────────────┐
   浏览器 / 第三方程序  →  │  Nginx 网关  (唯一对外端口 :8080)          │
                         │  · /            → Web 前端 (React SPA)     │
                         │  · /api/*       → 后端 REST API            │
                         │  · /v1/*        → OpenAI 兼容 API (SSE)    │
                         │  · /docs        → Swagger                  │
                         └───────────────┬──────────────────────────┘
                                         │
                         ┌───────────────▼───────────────┐
                         │   FastAPI 后端 (kb-backend)    │
                         │  认证/鉴权 · 知识库 · 文档 ·    │
                         │  检索 · RAG · API Key · 用量    │
                         └──┬─────────┬─────────┬─────────┘
             异步任务        │         │         │  推理调用
        ┌───────────────────▼──┐   ┌──▼──────┐ ┌▼─────────────────────────────┐
        │ Celery Worker        │   │ 数据层  │ │ 模型服务 (本地 GPU)           │
        │ 解析/OCR/切片/向量化 │   │ PG ·    │ │ · Embedding  bge-m3   (GPU0) │
        └──────────┬───────────┘   │ Qdrant ·│ │ · Reranker   v2-m3    (GPU0) │
                   │               │ Redis   │ │ · LLM  Qwen3-8B llama.cpp(GPU1)│
                   └───────────────┴─────────┘ └──────────────────────────────┘
```

检索链路：`query → [Dense 召回 + Sparse 召回] → RRF 融合(k=60) → Reranker 精排 → Top-K 证据 → LLM 生成 + 引用`

## 🚀 快速开始

### 1. 前置要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Linux（Ubuntu 22.04+ 实测；macOS 可 CPU 模式） |
| Docker | 20.10+ 与 Docker Compose v2 |
| GPU（可选） | NVIDIA GPU + 驱动 + `nvidia-container-toolkit`；无 GPU 可回退 CPU（见下） |
| 内存 | ≥ 16 GB（模型加载峰值） |
| 磁盘 | ≥ 30 GB（模型约 9 GB + 数据） |

### 2. 获取代码与模型

```bash
git clone <your-repo-url> knowledge && cd knowledge

# 模型文件不入库（体积大），需单独下载到 models/ 下：
#   models/embedding/bge-m3/            (BAAI/bge-m3)
#   models/reranker/bge-reranker-v2-m3/ (BAAI/bge-reranker-v2-m3)
#   models/llm/Qwen3-8B-Q4_K_M.gguf     (Qwen3-8B GGUF 量化)
# 详细下载方式（含国内镜像）见 docs/MODELS.md
```

### 3. 配置

```bash
cp .env.example .env
# 编辑 .env：把所有 change-this-* 替换为随机强密码/密钥，设置 ADMIN_PASSWORD
chmod 600 .env
```

### 4. 启动

```bash
./deploy/check-environment.sh   # 环境自检（Docker/GPU/模型/端口/.env）
./deploy/start.sh               # 构建镜像 + 启动 + 等待健康检查（首次较慢）
./deploy/status.sh              # 查看服务状态
./deploy/smoke-test.sh          # 端到端冒烟测试（13 项）
```

启动后访问 **`http://<服务器IP>:8080`**，用 `.env` 中的 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 登录。

> 无 GPU 时：将 `docker-compose.yml` 中 embedding/reranker/llm 的 `deploy.resources.reservations.devices` 段删除，并把 llm 的 `-ngl 99` 改为 `-ngl 0`（CPU 推理）。详见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

## 📁 目录结构

```
knowledge/
├── docker-compose.yml        # 服务编排（10 个容器）
├── .env.example              # 配置模板（复制为 .env）
├── Makefile                  # make check/build/start/stop/status/logs/backup
├── backend/                  # FastAPI 后端 + Celery worker
│   └── app/
│       ├── api/              # 路由：auth / knowledge_bases / documents / retrieval / chat / tasks / admin / external
│       ├── services/         # 检索、RAG、文档、embedding、reranker、llm 服务
│       ├── rag/              # 切片器、稀疏编码、RRF、上下文构建
│       ├── parsers/          # pdf / docx / markdown / txt / image / ocr
│       ├── vector/           # Qdrant collection 管理
│       ├── workers/          # Celery 文档处理任务
│       ├── models/           # SQLAlchemy 数据模型
│       ├── auth/             # JWT、API Key、权限 scope
│       └── main.py
├── frontend/                 # React 18 + TS + Vite + AntD 5（构建进 nginx 镜像）
├── services/model-server/    # Embedding / Reranker 共用推理服务
├── configs/nginx/            # 网关路由配置
├── models/                   # ★ 模型文件（gitignore，需自行下载）
├── data/                     # ★ 全部运行时数据（gitignore）
├── deploy/                   # 运维脚本 + systemd 单元
├── examples/                 # 客户端调用示例（cURL / Python / JS / Java）
├── offline/manifests/        # 模型 SHA256 清单
└── docs/                     # 详细文档
```

## 📖 文档

| 文档 | 内容 |
|------|------|
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | 部署、GPU 分工、运维脚本、备份恢复、故障排查 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 系统架构、数据流、检索/RAG 流水线、数据模型 |
| [docs/API.md](docs/API.md) | REST 与 OpenAI 兼容 API 完整参考、鉴权、限流、错误码 |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | 全部环境变量、检索/切片参数、端口与 GPU 配置 |
| [docs/MODELS.md](docs/MODELS.md) | 三个模型的下载方式、镜像、SHA256 校验 |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 本地开发、热重载、数据库迁移、代码约定 |
| [docs/知识库部署方案.md](docs/知识库部署方案.md) | 原始设计规格说明书（完整需求与方案设计） |
| [examples/](examples/) | 可直接运行的客户端调用示例：cURL / Python / JavaScript / Java |

## 🔌 对外 API 速览

| 协议 | 地址 | 认证 |
|------|------|------|
| REST API | `/api/v1/*`（知识库、文档、检索、问答、任务、管理） | JWT（Web）或 API Key |
| OpenAI 兼容 | `GET /v1/models`、`POST /v1/chat/completions`（支持 SSE 流式） | `Authorization: Bearer <API_KEY>` |
| 健康检查 | `GET /api/health`、`/api/health/dependencies`、`/api/health/ready` | 无 |
| 交互式文档 | `GET /docs`（Swagger）、`GET /redoc` | 无 |

第三方程序调用示例：

```bash
curl http://<服务器IP>:8080/v1/chat/completions \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
        "model": "knowledge-base",
        "messages": [{"role": "user", "content": "删除文档时需要注意什么？"}],
        "knowledge_base_ids": ["<kb-uuid>"],
        "stream": true
      }'
```

API Key 在 Web 管理端「API Key 管理」创建，**明文只展示一次**，可绑定知识库、权限范围（scope）、限流与有效期。完整字段与端点见 [docs/API.md](docs/API.md)。

## 🧩 服务一览

| 容器 | 作用 | 镜像 | 对外端口 |
|------|------|------|----------|
| kb-nginx | 网关 + Web 前端 | `kb-frontend:local` | **8080**（唯一） |
| kb-backend | FastAPI（REST / OpenAI 兼容） | `kb-backend:local` | 内部 |
| kb-worker | Celery 文档处理 | `kb-backend:local` | 内部 |
| kb-postgres | 关系数据 | `postgres:16-alpine` | 内部 |
| kb-qdrant | 向量库 | `qdrant/qdrant:v1.19.2` | 内部 |
| kb-redis | 队列 + 限流 | `redis:7-alpine` | 内部 |
| kb-embedding | bge-m3 向量服务（GPU0） | `kb-model-server:local` | 内部 |
| kb-reranker | bge-reranker-v2-m3（GPU0） | `kb-model-server:local` | 内部 |
| kb-llm | llama.cpp + Qwen3-8B（GPU1） | `ghcr.io/ggml-org/llama.cpp:server-cuda` | 内部 |

## 🛠️ 常用运维

```bash
make status          # 或 ./deploy/status.sh
make logs            # ./deploy/logs.sh [服务名]
make restart         # ./deploy/restart.sh
make backup          # ./deploy/backup.sh → data/backups/<时间戳>/
./deploy/restore.sh data/backups/<时间戳>
./deploy/smoke-test.sh
```

## 🔒 数据与环境隔离

所有运行数据、依赖环境都保存在项目目录内，宿主机唯一的系统级变更是 `nvidia-container-toolkit`（GPU 支持必需）与 Docker 自身的镜像存储。完整数据布局表见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#2-安装位置与数据布局)。

## 🗺️ Roadmap

已交付：基础设施、文档流水线、混合检索、RAG 问答、REST/OpenAI 兼容 API、API Key 与用量、Web 管理端、批量操作、一键部署。

规划中（后续迭代）：MCP Server、Python / JavaScript SDK、Webhooks、对话历史持久化、增量索引与定时任务。

## 📄 License

本项目基于 [Apache License 2.0](LICENSE) 开源。所使用的模型权重（bge-m3、bge-reranker-v2-m3、Qwen3-8B）各自遵循其原始许可证，请自行确认合规使用。
