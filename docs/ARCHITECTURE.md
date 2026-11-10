# 架构说明（Architecture）

本文描述 Local Knowledge Base Platform 的系统组成、数据流、检索/RAG 流水线、数据模型与关键技术决策。部署与运维见 [DEPLOYMENT.md](DEPLOYMENT.md)，接口细节见 [API.md](API.md)。

## 1. 组件与职责

| 组件 | 容器 | 技术 | 职责 |
|------|------|------|------|
| 网关 | kb-nginx | Nginx 1.27 | 唯一对外入口（:8080）；路由分发、SSE 透传、静态前端、安全响应头 |
| Web 前端 | （构建进 nginx） | React 18 + TS + Vite + AntD 5 + zustand | 管理端 SPA：登录、看板、知识库、文档、检索、问答、API Key、用量 |
| 后端 | kb-backend | FastAPI + SQLAlchemy 2 | REST/OpenAI 兼容 API、认证鉴权、检索编排、RAG |
| 异步 worker | kb-worker | Celery 5 | 文档解析/OCR/切片/向量化/入库（CPU 密集与 IO 任务） |
| 关系库 | kb-postgres | PostgreSQL 16 | 用户、知识库、文档、切片、任务、API Key、用量日志 |
| 向量库 | kb-qdrant | Qdrant v1.19.2 | 稠密 + 稀疏向量存储与检索，每知识库一个 Collection |
| 缓存/队列 | kb-redis | Redis 7 | Celery broker/backend、限流计数桶 |
| Embedding | kb-embedding | bge-m3（GPU0） | 文本 → 1024 维稠密向量 |
| Reranker | kb-reranker | bge-reranker-v2-m3（GPU0） | (query, 候选片段) 交叉编码精排 |
| LLM | kb-llm | llama.cpp + Qwen3-8B Q4_K_M（GPU1） | 生成回答，OpenAI 兼容服务端 |

> Embedding 与 Reranker 共用同一镜像 `kb-model-server:local`（源码 `services/model-server/`），通过环境变量 `MODEL_TYPE` 决定加载哪种模型、暴露 `/embed` 或 `/rerank`。

## 2. 网关路由

Nginx 使用 **变量式 `proxy_pass` + Docker 内置 DNS（`resolver 127.0.0.11 valid=10s`）**，避免 upstream 缓存容器 IP 导致后端重启后 502。

| 路径 | 目标 | 说明 |
|------|------|------|
| `/` | 前端静态资源 | SPA，`try_files … /index.html` |
| `/api/` | kb-backend | REST API |
| `/v1/` | kb-backend | OpenAI 兼容 API，**关闭缓冲**以支持 SSE |
| `= /api/v1/chat/completions` | kb-backend | Web 流式问答，SSE 专用 location |
| `/docs` `/redoc` `/openapi.json` | kb-backend | 交互式 API 文档 |
| `/nginx_status` | 内置 | 仅内网可访问 |

SSE location 关键配置：`proxy_buffering off; proxy_cache off; proxy_read_timeout 3600s; chunked_transfer_encoding on;`，并透传 `X-Accel-Buffering`。

## 3. 文档处理流水线

上传后同步落库、异步处理，状态机：`pending → processing → ready | failed`。

```
上传 (POST /knowledge-bases/{kb}/documents[/batch])
  └─ document_service.save_and_enqueue()
       · 安全文件名（防路径穿越）+ 扩展名白名单
       · 大小上限（默认 200MB）+ 头部魔数校验（PDF/DOCX/PNG/JPG/TIFF）
       · SHA256 去重（同一知识库内，命中返回 action=duplicate）
       · 原始文件移动到 data/documents/<collection>/<doc_id>/
       · 建 Document + Task 记录 → process_document.delay()
                                    │
Celery worker: process_document ◄──┘
  1. 解析 parse_document()（按页返回 [(page_no, text), …]）
       · PDF：PyMuPDF 提取；单页文本 < 50 字 → 200dpi 渲染 + OCR
       · 图片：pytesseract（chi_sim + eng）
       · DOCX：段落 + 表格；Markdown：保留原文；TXT：直读
  2. 清洗 clean_text() + 切片 chunk_text()
       · 递归按分隔符切分（\n\n、\n、。！？；…），单位为“字符”
       · 默认 chunk_size=800、overlap=120（每知识库可配）
       · 片段最短 20 字符，过短文档会得到“未提取到文本”而 failed
  3. 确保 Qdrant Collection 存在 → 清理旧向量/切片（重处理场景）
  4. 批量 Embedding（每批 32）→ 稠密向量
  5. 稀疏编码 encode_sparse()（jieba 分词 → CRC32 索引 + 词频）
  6. 写 Qdrant（PointStruct: {dense, sparse} + 完整 payload，每批 256 upsert）
  7. 写 DocumentChunk 行；解析文本存 data/extracted/<doc_id>.txt
  8. status=ready，chunk_count 落库
失败任一步 → Document/Task 置 failed 并记录 error_message
```

**幂等性**：worker 在写向量前调用 `collection_manager.create_collection()`（已存在则跳过），保证即使知识库创建时集合缺失、或数据漂移，重新处理也能自愈。

## 4. 混合检索流水线

`retrieval_service.hybrid_search(kbs, query, top_k, rerank, filters)`：

```
query
 ├─ Dense：bge-m3 编码 → 每个知识库 Collection 的 Prefetch 查询（top 30）
 └─ Sparse：jieba 编码 → 稀疏查询，Qdrant 服务端 Modifier.IDF 加权（top 30）
        │  （稀疏命中若缺 payload，用 qdrant.retrieve 回捞）
        ▼
   RRF 融合（rrf.py，k=60，score = Σ 1/(k+rank)）→ 取 top 40
        ▼
   Reranker 精排（bge-reranker-v2-m3，对最多 reranker_top_k*4 个候选打分）
        ▼
   最终 Top-K（默认 5）→ RetrievedChunk[]（含 filename/page/content/score）
```

默认检索参数（见 [CONFIGURATION.md](CONFIGURATION.md)）：`dense_top_k=30`、`sparse_top_k=30`、`rrf_top_k=40`、`reranker_top_k=10`、`final_top_k=5`。

**多知识库**：对每个授权知识库分别发起 Qdrant prefetch，再在应用层做跨库 RRF 融合；知识库授权在服务端完成，绝不信任客户端传入的 KB ID。

## 5. RAG 问答

`rag_service.answer()` / `answer_stream()`：

1. 混合检索得到 Top-K 证据片段。
2. `context_builder` 组装系统提示词（**明确禁止编造**，无依据时回答固定兜底语「知识库中未找到足够依据…」）+ 编号资料（含文件名/页码）。
3. 调用 llama.cpp（Qwen3-8B）生成；`--reasoning-budget 0` 关闭思考链以保证正文非空。
4. 流式模式按 SSE 产出事件：`citations`（引用）→ 多个 `delta`（增量文本）→ `done`；OpenAI 兼容端产出标准 `chat.completion.chunk`，可选附带 `kb_citations`。

两个问答入口：
- `POST /api/v1/chat/completions`：Web 端，入参 `{query, history?, knowledge_base_ids?, stream?, return_citations?, top_k?, rerank?}`，SSE 事件为自定义 `citations/delta/done`。
- `POST /v1/chat/completions`：OpenAI 兼容，入参标准 `messages`（最后一条 user 作为 query，其余作为 history），扩展参数 `knowledge_base_ids/top_k/rerank/return_citations`；未传知识库时回退到 API Key 的 `default_kb_ids`。

## 6. 认证与鉴权

统一入口 `get_principal`（HTTPBearer）：

- **JWT**（Web 用户）：PyJWT 签发，默认 12h；`UserPrincipal`，`admin` 角色拥有全部权限。
- **API Key**（外部程序）：格式 `kb-` + `token_urlsafe(32)`；数据库只存 **SHA256 哈希** 与 `key_prefix`，明文仅创建时返回一次；`ApiKeyPrincipal` 携带 `scopes` 与绑定知识库。

权限模型：
- `require_scope(principal, scope)`：用户直接放行；API Key 校验 scope（`kb:admin` 视为超集）。
- Scope 列表：`kb:read`、`kb:search`、`kb:chat`、`kb:documents:read`、`kb:documents:upload`、`kb:documents:delete`、`kb:admin`。
- `get_authorized_knowledge_bases()`：把请求的 KB ID 与主体授权范围求交集，越权返回 403 并列出被拒 ID。
- `authorized_kb_id_set()`：批量操作使用，返回主体可见的全部 active 知识库 ID 集合，**逐项**鉴权（越权项标记为「无权访问」而非整体失败）。

限流：API Key 请求经 `_check_rate_limit`，用 Redis 维护「每分钟桶」与「每日桶」，超限返回 429。中间件 `ApiUsageLogMiddleware` 仅对 API Key 请求写用量日志（方法/路径/状态码/耗时/IP，**不记录明文密钥**）。

## 7. 向量存储设计

- Collection 命名：`kb_{kb_id.hex[:16]}`，每知识库独立。
- 稠密向量：`vectors_config={"dense": VectorParams(size=1024, distance=COSINE, hnsw m=16 ef=200)}`。
- 稀疏向量：`sparse_vectors_config={"sparse": SparseVectorParams(modifier=Modifier.IDF)}`（服务端 IDF 加权）。
- Payload 索引：`document_id`、`knowledge_base_id`、`file_type`、`page_number`、`document_version`。
- Point payload：`chunk_id, document_id, knowledge_base_id, filename, content, page_number, chunk_index, file_type, document_version`。
- 删除文档：按 `document_id` filter 删除对应 points，并删除磁盘文件与 extracted 文本。

## 8. 数据模型（PostgreSQL）

| 表 | 关键字段 | 说明 |
|----|----------|------|
| `roles` | name, permissions(JSON) | 角色（预留） |
| `users` | username, password_hash, role, status | 用户；`admin`/`user` |
| `knowledge_bases` | name, owner_id, embedding_model, embedding_dimension, vector_collection(unique), chunk_size, chunk_overlap, status | 知识库 |
| `documents` | knowledge_base_id, filename, file_path, file_type, file_hash, file_size, page_count, chunk_count, status, version, error_message | 文档；`(kb_id, file_hash)` 唯一约束用于去重 |
| `document_chunks` | document_id, knowledge_base_id, chunk_index, content, page_number, metadata, qdrant_point_id | 切片（PG 侧留档，检索以 Qdrant 为主） |
| `tasks` | task_type, document_id, status, progress, error_message, finished_at | 异步处理任务 |
| `api_keys` | name, key_prefix, key_hash(unique), user_id, scopes(JSON), rate_limit, daily_limit, default_kb_ids(JSON), expires_at, last_used_at, status | API Key |
| `api_key_knowledge_bases` | api_key_id, knowledge_base_id | Key ↔ 知识库多对多授权 |
| `api_usage_logs` | api_key_id, method, path, status_code, duration_ms, request_ip, prompt_tokens, completion_tokens | 调用用量 |

> 级联：`documents`/`document_chunks`/`api_key_knowledge_bases` 对父记录 `ON DELETE CASCADE`；`tasks.document_id`、`api_usage_logs.api_key_id` 为 `SET NULL`（保留历史）。
> 说明：对话/消息、Webhook 等表本期未纳入（问答为无状态设计），属后续迭代。

## 9. GPU 分工与 Pascal 注意事项

| 设备 | 负载 | 显存 |
|------|------|------|
| GPU 0 | kb-embedding + kb-reranker（PyTorch 2.6.0 **cu124**） | 约 2.3 GB |
| GPU 1 | kb-llm（llama.cpp `server-cuda`，`-ngl 99 -c 8192`） | 约 5.8 GB |

Tesla P4 为 Pascal（sm_61）：
- PyTorch 必须用 **cu124** 轮子（cu128 起不再编译 Pascal 支持）；PyPI 的 `torch==2.6.0` linux 轮子即 cu124 构建。
- llama.cpp 用 `ghcr.io/ggml-org/llama.cpp:server-cuda`；若不兼容可 `-ngl 0` 回退 CPU。
- Qwen3 为混合思考模型，服务需加 `--reasoning-budget 0`，否则正文可能为空（token 被思考链占用）。

无 GPU 部署：移除各服务的 `deploy.resources.reservations.devices` 段，llm 改 `-ngl 0`。

## 10. 关键技术决策

- **字符为切片单位**：全系统统一用字符数计量 `chunk_size`，不混用 token，避免中英文计量歧义。
- **稀疏向量用 CRC32 索引 + 服务端 IDF**：jieba 词 → `CRC32 & 0x7FFFFFFF` 作为 u32 索引，值为词频；IDF 交给 Qdrant 计算，省去自维护词表。
- **应用层 RRF 而非库内融合**：便于跨多个 Collection/知识库统一融合，逻辑透明可调。
- **变量式 proxy_pass**：解决容器 IP 漂移导致的 502。
- **数据全部 bind mount 到项目内**：满足「不污染系统环境、可整体打包迁移」的硬约束。
- **哈希存储 API Key**：明文不落库，降低泄露风险。
