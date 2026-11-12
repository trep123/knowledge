# 配置说明（Configuration）

所有配置通过项目根目录的 `.env` 注入（`docker compose` 自动读取）。模板见 [.env.example](../.env.example)。后端读取逻辑见 [backend/app/config.py](../backend/app/config.py)。

> ⚠️ `.env` 含机密，权限应为 `600`，且已在 `.gitignore` 中排除，**切勿提交到版本库**。

## 1. 环境变量

### 应用与密钥

| 变量 | 默认 | 说明 |
|------|------|------|
| `APP_ENV` | `production` | 运行环境标识 |
| `APP_SECRET_KEY` | — | 应用通用密钥，**必须改为随机值** |
| `JWT_SECRET_KEY` | — | JWT 签名密钥，**必须改为随机值** |
| `JWT_EXPIRE_HOURS` | `12` | JWT 有效期（小时，代码内默认） |

生成随机密钥：`openssl rand -hex 32`。

`APP_ENV=production` 时，若 `APP_SECRET_KEY` / `JWT_SECRET_KEY` 仍以 `change-this` 开头或短于 16 位，后端会**拒绝启动**。

| 变量 | 默认 | 说明 |
|------|------|------|
| `ENABLE_API_DOCS` | 生产环境 `false`，其他 `true` | 是否开放 `/docs`、`/redoc`、`/openapi.json` |
| `FORWARDED_ALLOW_IPS` | `*` | uvicorn 信任哪些代理的 `X-Forwarded-For`（后端只在容器网络内被 nginx 访问） |
| `HISTORY_MAX_MESSAGES` | `10` | 问答时最多带入的历史消息条数（仅 user/assistant，system 会被丢弃） |
| `HISTORY_MAX_CHARS` | `4000` | 历史消息总字符上限 |

### 数据存储

| 变量 | 默认 | 说明 |
|------|------|------|
| `POSTGRES_DB` | `knowledge_base` | 数据库名 |
| `POSTGRES_USER` | `kbuser` | 数据库用户 |
| `POSTGRES_PASSWORD` | — | 数据库密码，**必须改** |
| `REDIS_PASSWORD` | — | Redis 密码，**必须改** |
| `QDRANT_URL` | `http://qdrant:6333` | 向量库地址（容器网络内） |

> `DATABASE_URL` / `REDIS_URL` 由 compose 依据上述变量拼装，一般无需单独设置。

### 模型服务

| 变量 | 默认 | 说明 |
|------|------|------|
| `EMBEDDING_URL` | `http://embedding:8001` | Embedding 服务地址 |
| `RERANKER_URL` | `http://reranker:8002` | Reranker 服务地址 |
| `LLM_BASE_URL` | `http://llm:8080/v1` | llama.cpp OpenAI 兼容地址 |
| `LLM_API_KEY` | — | 调用 llama.cpp 的内部密钥（compose 传给 llm 与 backend） |
| `LLM_MODEL` | `qwen3-8b` | 模型别名（llama.cpp `--alias`） |

### 网关与限流

| 变量 | 默认 | 说明 |
|------|------|------|
| `GATEWAY_PORT` | `8080` | **唯一对外端口**；宿主机 80/443/5432/8000 被占用时改成其它空闲端口 |
| `API_DEFAULT_RATE_LIMIT` | `60` | API Key 默认每分钟请求数 |

### 离线与初始管理员

| 变量 | 默认 | 说明 |
|------|------|------|
| `HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE` / `HF_DATASETS_OFFLINE` | `1` | 强制离线，禁止模型服务联网拉取 |
| `ADMIN_USERNAME` | `admin` | 初始管理员用户名 |
| `ADMIN_PASSWORD` | — | 初始管理员密码，**必须改**；仅首次启动创建，之后改此值不生效 |

> 修改初始管理员密码：改 `.env` 后需删除 `users` 表中旧记录再重启，或直接在 postgres 容器内更新（见 [DEPLOYMENT.md](DEPLOYMENT.md#7-故障排查)）。

## 2. 检索与切片参数

这些是后端代码内默认值（`config.py`），一般无需通过环境变量覆盖；如需调整可在此处修改后重建 backend/worker 镜像。

### 切片（单位为**字符**）

| 参数 | 默认 | 说明 |
|------|------|------|
| `chunk_size` | `800` | 每片目标字符数（建库时可逐库覆盖，范围 100–4000） |
| `chunk_overlap` | `120` | 相邻片重叠字符数（范围 0–1000） |
| 最短片长 | `20` | 低于此长度的片被丢弃（`rag/chunker.py`）；过短文档会因无有效片而 `failed` |

### 检索

| 参数 | 默认 | 说明 |
|------|------|------|
| `dense_top_k` | `30` | 稠密向量召回条数 |
| `sparse_top_k` | `30` | 稀疏向量召回条数 |
| `rrf_top_k` | `40` | RRF 融合后保留条数 |
| `reranker_top_k` | `10` | 精排后保留条数（实际对最多 `reranker_top_k*4` 个候选打分） |
| `final_top_k` | `5` | 最终送入 LLM 的证据条数 |

### 向量与上传

| 参数 | 默认 | 说明 |
|------|------|------|
| `embedding_model_name` | `bge-m3` | 记录在建库元数据 |
| `embedding_dimension` | `1024` | 稠密向量维度（须与模型一致） |
| `max_upload_mb` | `200` | 单文件上传上限 |
| `allowed_extensions` | `.pdf .docx .md .markdown .txt .png .jpg .jpeg .tiff .tif` | 允许的文件类型 |

## 3. 端口与网络

- 仅 nginx 发布 `${GATEWAY_PORT}:80`，其余容器都在内部网络 `kb-network`，不对宿主机暴露端口。
- 容器间通过服务名互访（`postgres`/`redis`/`qdrant`/`embedding`/`reranker`/`llm`/`backend`）。
- Nginx 用 `resolver 127.0.0.11`（Docker 内置 DNS）+ 变量式 `proxy_pass`，后端重启后自动跟随新 IP。

## 4. GPU 设备分配

在 `docker-compose.yml` 中通过 `deploy.resources.reservations.devices` 指定：

| 服务 | `device_ids` | 说明 |
|------|--------------|------|
| embedding / reranker | `["0"]` | GPU0 |
| llm | `["1"]` | GPU1 |

- 单 GPU 或无 GPU：把相关服务的 `devices` 段合并到同一 `device_ids`，或整段删除并把 llm 命令的 `-ngl 99` 改为 `-ngl 0`（CPU 推理）。
- LLM 关键启动参数：`-ngl 99 -c 8192 -b 2048 --reasoning-budget 0`。`--reasoning-budget 0` 对 Qwen3 必需，否则正文可能为空。

## 5. 修改配置后的生效方式

| 改动 | 生效方式 |
|------|----------|
| `.env` 中的密码/端口/密钥 | `./deploy/restart.sh`（或 `docker compose up -d`） |
| `config.py` 检索/切片默认值 | `docker compose build backend && docker compose up -d backend worker` |
| `docker-compose.yml`（GPU/命令/镜像） | `docker compose up -d`（必要时 `--force-recreate`） |
| nginx 配置 `configs/nginx/kb-gateway.conf` | `docker restart kb-nginx` |
| 前端源码 | `docker compose build nginx && docker compose up -d nginx` |
