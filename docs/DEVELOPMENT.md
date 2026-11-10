# 开发指南（Development）

面向想二次开发或本地调试的工程师。生产部署请看 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 1. 代码结构

```
backend/app/
├── main.py              # FastAPI 应用、路由挂载、CORS、健康检查、用量中间件
├── config.py            # pydantic-settings 配置（读取环境变量）
├── database.py          # SQLAlchemy engine / SessionLocal / Base
├── db_init.py           # 启动建表：有 Alembic 迁移则 upgrade，否则 create_all
├── seed.py              # 初始化角色与管理员账号
├── dependencies.py      # get_principal（JWT/API Key）、鉴权、限流
├── middleware.py        # ApiUsageLogMiddleware（仅记录 API Key 请求）
├── api/                 # 路由层（见下）
│   ├── auth.py  knowledge_bases.py  documents.py  retrieval.py  chat.py  tasks.py
│   ├── admin/           # api_keys.py、api_usage.py
│   └── external/        # openai_compat.py（/v1/*）
├── services/            # 业务编排：retrieval / rag / document / embedding / reranker / llm
├── rag/                 # chunker、sparse（jieba→稀疏）、rrf、context_builder
├── parsers/             # pdf / docx / markdown / txt / image / ocr + parse_document 分发
├── vector/              # collection_manager（Qdrant Collection 生命周期）
├── workers/             # celery_app、document_tasks（process_document）
├── models/              # SQLAlchemy ORM 模型
├── schemas/             # Pydantic 请求/响应模型
└── auth/                # jwt、security（bcrypt）、permissions（scope）

frontend/src/
├── main.tsx  App.tsx           # 入口与路由
├── api/client.ts               # axios 实例（注入 JWT，401→/login）
├── store/auth.ts               # zustand（localStorage: kb_token/kb_username/kb_role）
├── layouts/MainLayout.tsx      # 侧边栏布局
└── pages/                      # Login/Dashboard/KnowledgeBases/Documents/Retrieval/Chat/ApiKeys/ApiUsage

services/model-server/          # Embedding/Reranker 共用服务（MODEL_TYPE 区分）
```

## 2. 本地开发（不重建镜像）

推荐：**基础设施用 Docker，应用代码在本机跑热重载**。

```bash
# 1) 只起依赖（数据库/向量库/队列/模型服务）
docker compose up -d postgres qdrant redis embedding reranker llm

# 2) 后端热重载（需本机 Python 3.12 虚拟环境）
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
# 让本机后端能连到容器：把 .env 里的主机名换成 127.0.0.1，端口按需映射，
# 或临时用环境变量覆盖，例如：
export DATABASE_URL="postgresql+psycopg2://kbuser:<pw>@127.0.0.1:5432/knowledge_base"
export REDIS_URL="redis://:<pw>@127.0.0.1:6379/0"
export QDRANT_URL="http://127.0.0.1:6333"
export EMBEDDING_URL="http://127.0.0.1:8001" RERANKER_URL="http://127.0.0.1:8002"
export LLM_BASE_URL="http://127.0.0.1:8080/v1"
python -m app.db_init && python -m app.seed     # 首次初始化
uvicorn app.main:app --reload --port 8000        # 后端
celery -A app.workers.celery_app worker -l info  # 另开一个终端跑 worker

# 3) 前端热重载（Node 22）
cd ../frontend
npm install        # 建议 registry: npm config set registry https://registry.npmmirror.com
npm run dev        # http://localhost:5173，已配置 /api 与 /v1 代理到 :8080
```

> 注意：`vite.config.ts` 的 dev 代理默认指向 `http://127.0.0.1:8080`（即 nginx 网关）。若后端直接跑在 `:8000`，把代理 target 改成 `http://127.0.0.1:8000` 即可绕过网关。
> 依赖服务若要在本机直连，需要在 `docker-compose.yml` 为对应服务临时加 `ports` 映射（生产配置默认不暴露）。

## 3. 全量容器内开发

改动后端/前端源码后重建对应镜像：

```bash
docker compose build backend          # 后端（worker 复用同镜像）
docker compose build nginx            # 前端（构建进 nginx 镜像）
docker compose up -d backend worker nginx
```

## 4. 数据库迁移

项目用 **Alembic**，但首次部署若无迁移脚本会走 `Base.metadata.create_all` 直接建表（见 `db_init.py`）。改了 ORM 模型后生成迁移：

```bash
cd backend
alembic revision --autogenerate -m "add xxx column"
alembic upgrade head            # 本地验证
# 容器内：docker compose exec backend alembic upgrade head
```

`migrations/versions/*.py` 存在时，容器启动会自动 `upgrade head`。

## 5. 常用调试

```bash
./deploy/logs.sh backend          # 跟踪后端日志
./deploy/logs.sh worker           # 文档处理日志（解析/向量化错误都在这里）
docker compose exec postgres psql -U kbuser -d knowledge_base
docker compose exec qdrant sh     # 向量库容器
curl -s localhost:8080/api/health/dependencies | python3 -m json.tool
```

- 文档一直 `processing`：看 worker 日志，通常是 embedding 服务未就绪或某页解析异常。
- 文档 `failed: 未能从文档中提取到任何文本`：内容清洗后不足最短片长（20 字符），属正常保护。
- 检索为空：确认文档 `ready`、`/api/health/dependencies` 全 ok、请求的知识库 ID 在授权范围内。

## 6. 冒烟测试

`deploy/smoke-test.sh` 覆盖 13 项端到端：健康检查 → 登录 → 建库 → 上传 → 等待 ready → 混合检索 → RAG 问答（含引用）→ 创建 API Key → OpenAI 兼容调用 → 401/无效 Key 拒绝 → 清理。

```bash
./deploy/smoke-test.sh
```

## 7. 代码约定

- **切片单位统一为字符**，不要引入 token 计量造成混用。
- **鉴权永远在服务端**：不要信任客户端传入的 `knowledge_base_ids`，一律经 `get_authorized_knowledge_bases` / `authorized_kb_id_set` 求交集。
- **批量接口逐项容错**：单个失败 `db.rollback()` 后继续，返回 `{ok, error}`，不让整批 500。
- **API Key 明文不落库**：只存 SHA256 哈希与 prefix；用量日志不记录明文密钥。
- 新增路由后在 `main.py` 挂载；OpenAI 兼容类接口放 `api/external/`。
- 提交前确保 `cd frontend && npm run build`（含 `tsc -b`）无类型错误。

## 8. 提交到 GitHub

仓库已配置 `.gitignore`，排除 `.env`、`data/`、`models/*`、`.tools-venv/`、`node_modules/`、`frontend/dist/`、`__pycache__/`、`*.log` 等。首次推送：

```bash
git init
git add .
git status                      # ★ 确认没有 .env / data / models / *.gguf 被纳入
git commit -m "init: Local Knowledge Base Platform"
git branch -M main
git remote add origin <your-repo-url>
git push -u origin main
```

> 模型与运行数据都不入库；克隆方按 [MODELS.md](MODELS.md) 下载模型、按 [DEPLOYMENT.md](DEPLOYMENT.md) 部署。
