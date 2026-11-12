# API 参考（API Reference）

网关基址：`http://<服务器IP>:8080`。交互式文档：`/docs`（Swagger）、`/redoc`。

- [1. 认证](#1-认证)
- [2. 权限范围（Scope）](#2-权限范围scope)
- [3. 健康检查](#3-健康检查)
- [4. 认证接口](#4-认证接口)
- [5. 知识库](#5-知识库)
- [6. 文档](#6-文档)
- [7. 批量操作](#7-批量操作)
- [8. 检索](#8-检索)
- [9. 问答（Web）](#9-问答web)
- [10. OpenAI 兼容接口](#10-openai-兼容接口)
- [11. 任务](#11-任务)
- [12. 管理：API Key 与用量](#12-管理api-key-与用量)
- [13. 限流与错误码](#13-限流与错误码)

所有 `/api/v1/*` 与 `/v1/*` 接口都需要 `Authorization: Bearer <JWT 或 API Key>`（健康检查除外）。

## 1. 认证

两种凭证，二选一放入 `Authorization: Bearer`：

| 凭证 | 来源 | 适用 |
|------|------|------|
| JWT | `POST /api/v1/auth/login` 获取，默认有效期 12h | Web 前端、临时脚本 |
| API Key | Web「API Key 管理」创建，格式 `kb-xxxxxxxx...` | 第三方程序长期集成 |

API Key 特性：明文**仅创建时返回一次**（数据库只存 SHA256 哈希）；可绑定知识库、scope、每分钟/每日限流、有效期；可 rotate（轮换）、禁用、删除。不能传扩展参数的 OpenAI 客户端可在 Key 上设置 `default_kb_ids`。

> 📦 可直接运行的客户端示例（cURL / Python / JavaScript / Java）见 [`examples/`](../examples/)，全部使用 API Key 鉴权、无需登录。

```bash
# 获取 JWT
curl -X POST http://<IP>:8080/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<ADMIN_PASSWORD>"}'
# → {"access_token":"<jwt>","token_type":"bearer","username":"admin","role":"admin"}
```

## 2. 权限范围（Scope）

| Scope | 含义 |
|-------|------|
| `kb:read` | 读取知识库列表/详情 |
| `kb:search` | 检索 |
| `kb:chat` | 问答（含 OpenAI 兼容） |
| `kb:documents:read` | 读取文档/切片 |
| `kb:documents:upload` | 上传/重处理文档 |
| `kb:documents:delete` | 删除文档 |
| `kb:admin` | 管理（建库/删库/API Key 管理），视为全部权限超集 |

Web 用户（JWT）按角色校验：

| 角色 | 权限范围 | 可访问的知识库 |
|------|----------|----------------|
| `admin` 管理员 | 全部（含 `kb:admin`） | 全部 |
| `user` 普通用户 | `kb:read` `kb:search` `kb:chat` `kb:documents:read` `kb:documents:upload` | 自己拥有的 + 被授权的 |

API Key 按创建时勾选的 scope 校验，缺少则 `403`；API Key 所属用户被禁用后该 Key 同时失效。

## 3. 健康检查

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 存活探针，`{"status":"ok"}` |
| GET | `/api/health/dependencies` | 检查 postgres/qdrant/embedding/reranker/llm/redis，全 ok 返回 `status:ok`，否则 `degraded` |
| GET | `/api/health/ready` | 就绪探针 |

## 4. 认证接口

| 方法 | 路径 | Scope | 说明 |
|------|------|-------|------|
| POST | `/api/v1/auth/login` | 无 | 登录，返回 JWT。连续 5 次密码错误锁定 15 分钟（返回 `423`） |
| GET | `/api/v1/auth/me` | 登录 | 当前用户信息 |
| PUT | `/api/v1/auth/me/password` | 登录 | 修改自己的密码 `{old_password, new_password}`，返回新 JWT，旧 JWT 全部失效 |

密码规则：8-128 位，同时包含字母和数字。修改/重置密码、禁用账号、修改角色后，该用户已签发的 JWT 立即失效。

## 5. 知识库

| 方法 | 路径 | Scope | 说明 |
|------|------|-------|------|
| GET | `/api/v1/knowledge-bases` | `kb:read` | 列表（含 `document_count`） |
| POST | `/api/v1/knowledge-bases` | `kb:admin` | 创建（同时建 Qdrant Collection） |
| GET | `/api/v1/knowledge-bases/{kb_id}` | `kb:read` | 详情 |
| PUT | `/api/v1/knowledge-bases/{kb_id}` | `kb:admin` | 更新 name/description/chunk_size/chunk_overlap |
| DELETE | `/api/v1/knowledge-bases/{kb_id}` | `kb:admin` | 删除（含全部文档、向量、文件） |
| GET | `/api/v1/knowledge-bases/{kb_id}/members` | 管理员或所有者 | 已授权用户列表 |
| PUT | `/api/v1/knowledge-bases/{kb_id}/members` | 管理员或所有者 | 整体替换授权用户 `{"user_ids": [...]}` |

创建请求体：

```json
{ "name": "运维知识库", "description": "可选", "chunk_size": 800, "chunk_overlap": 120 }
```

- `chunk_size`：100–4000（字符），默认 800
- `chunk_overlap`：0–1000（字符），默认 120

## 6. 文档

| 方法 | 路径 | Scope | 说明 |
|------|------|-------|------|
| POST | `/api/v1/knowledge-bases/{kb_id}/documents` | `kb:documents:upload` | 单文件上传（multipart 字段 `file`） |
| GET | `/api/v1/knowledge-bases/{kb_id}/documents` | `kb:documents:read` | 文档列表（`skip`/`limit`，limit ≤ 200） |
| GET | `/api/v1/documents/{doc_id}` | `kb:documents:read` | 文档详情 |
| DELETE | `/api/v1/documents/{doc_id}` | `kb:documents:delete` | 删除（含向量与文件） |
| POST | `/api/v1/documents/{doc_id}/reprocess` | `kb:documents:upload` | 重新处理（version+1） |
| GET | `/api/v1/documents/{doc_id}/chunks` | `kb:documents:read` | 切片列表（`skip`/`limit`，limit ≤ 500） |

支持类型：`.pdf .docx .md .markdown .txt .png .jpg .jpeg .tiff .tif`；单文件上限默认 200MB；扫描版 PDF/图片自动 OCR。上传返回：

```json
{ "success": true, "action": "created", "document": { "id": "...", "status": "pending", "...": "..." } }
```

`action` 为 `created` 或 `duplicate`（同一知识库内 SHA256 命中去重）。文档状态：`pending → processing → ready | failed`。

```bash
curl -X POST http://<IP>:8080/api/v1/knowledge-bases/<KB_ID>/documents \
  -H "Authorization: Bearer <TOKEN>" -F "file=@/path/to/doc.pdf"
```

## 7. 批量操作

所有批量接口返回统一结构，**逐项成败互不影响**：

```json
{
  "success": true,
  "total": 3, "succeeded": 2, "failed": 1,
  "results": [
    { "id": "...", "ok": true, "action": "created" },
    { "id": "...", "ok": false, "error": "文档不存在" }
  ]
}
```

| 方法 | 路径 | Scope | 请求体 | 说明 |
|------|------|-------|--------|------|
| POST | `/api/v1/knowledge-bases/{kb_id}/documents/batch` | `kb:documents:upload` | multipart，多个 `files` 字段 | 批量上传，逐项校验/去重/入队 |
| POST | `/api/v1/documents/batch-delete` | `kb:documents:delete` | `{"ids": ["<uuid>", ...]}` | 批量删除 |
| POST | `/api/v1/documents/batch-reprocess` | `kb:documents:upload` | `{"ids": ["<uuid>", ...]}` | 批量重新处理 |
| POST | `/api/v1/knowledge-bases/batch-delete` | `kb:admin` | `{"ids": ["<uuid>", ...]}` | 批量删除知识库（含文档/向量/文件） |

- `ids` 长度 1–1000。
- 服务端**逐项鉴权**：越权项返回 `{"ok": false, "error": "无权访问"}`，不存在的 ID 返回 `"…不存在"`，不会整体 403。
- 批量上传结果项字段：`filename`、`ok`、`action`(`created`/`duplicate`)、`document_id` 或 `error`。

```bash
# 批量上传
curl -X POST http://<IP>:8080/api/v1/knowledge-bases/<KB_ID>/documents/batch \
  -H "Authorization: Bearer <TOKEN>" -F "files=@a.pdf" -F "files=@b.docx"

# 批量删除文档
curl -X POST http://<IP>:8080/api/v1/documents/batch-delete \
  -H "Authorization: Bearer <TOKEN>" -H 'Content-Type: application/json' \
  -d '{"ids":["<doc-uuid-1>","<doc-uuid-2>"]}'
```

## 8. 检索

| 方法 | 路径 | Scope | 说明 |
|------|------|-------|------|
| POST | `/api/v1/search` | `kb:search` | 混合检索 |
| POST | `/api/v1/search/hybrid` | `kb:search` | 同上（别名） |

请求体：

```json
{
  "query": "删除文档要注意什么",
  "knowledge_base_ids": ["<kb-uuid>"],   // 省略则用主体授权的全部知识库
  "top_k": 5,                              // 1–50，默认 5
  "rerank": true,                          // 是否精排，默认 true
  "filters": null                          // 可选，按 payload 过滤（file_type/page_number 等）
}
```

响应：

```json
{
  "success": true,
  "query": "...",
  "total": 5,
  "results": [
    { "chunk_id": "...", "document_id": "...", "filename": "a.pdf",
      "page_number": 3, "content": "...", "score": 0.9055 }
  ]
}
```

检索内部流程（Dense + Sparse → RRF → Rerank）见 [ARCHITECTURE.md](ARCHITECTURE.md#4-混合检索流水线)。

## 9. 问答（Web）

| 方法 | 路径 | Scope | 说明 |
|------|------|-------|------|
| POST | `/api/v1/chat/completions` | `kb:chat` | RAG 问答，支持 SSE 流式 |

请求体：

```json
{
  "query": "问题",
  "knowledge_base_ids": ["<kb-uuid>"],
  "top_k": 5, "rerank": true,
  "return_citations": true,
  "stream": false,
  "history": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
}
```

- 非流式：返回 `{answer, citations}`。
- 流式（`stream:true`，`Content-Type: text/event-stream`）：依次产出
  - `data: {"event":"citations","citations":[...]}`
  - `data: {"event":"delta","content":"增量文本"}`（多条）
  - `data: {"event":"done"}`
  - `data: [DONE]`

无足够证据时返回固定兜底语：「知识库中未找到足够依据来回答该问题。请补充相关文档后重试。」

## 10. OpenAI 兼容接口

供 OpenAI SDK / LangChain 等直接接入。`model` 固定填 `knowledge-base`。

| 方法 | 路径 | Scope | 说明 |
|------|------|-------|------|
| GET | `/v1/models` | `kb:chat` | 返回单个模型 `knowledge-base` |
| POST | `/v1/chat/completions` | `kb:chat` | 对话补全，支持 `stream` |

请求体在标准 OpenAI 字段（`model`/`messages`/`stream`/`temperature`/`max_tokens`）基础上扩展：

| 扩展字段 | 类型 | 默认 | 说明 |
|----------|------|------|------|
| `knowledge_base_ids` | uuid[] | 无 | 检索范围；省略时回退到 API Key 的 `default_kb_ids`，再省略则用授权的全部知识库 |
| `top_k` | int | 5 | 检索条数（1–50） |
| `rerank` | bool | true | 是否精排 |
| `return_citations` | bool | false | 是否在响应附带 `kb_citations` |

`messages` 中**最后一条 user 消息**作为检索问题，其之前的消息作为对话历史。

```bash
# 非流式
curl http://<IP>:8080/v1/chat/completions \
  -H "Authorization: Bearer <API_KEY>" -H 'Content-Type: application/json' \
  -d '{"model":"knowledge-base","messages":[{"role":"user","content":"问题"}],
       "knowledge_base_ids":["<kb-uuid>"],"return_citations":true}'

# 流式（SSE，标准 chat.completion.chunk；return_citations 时首个 chunk 带 kb_citations）
curl -N http://<IP>:8080/v1/chat/completions \
  -H "Authorization: Bearer <API_KEY>" -H 'Content-Type: application/json' \
  -d '{"model":"knowledge-base","stream":true,"messages":[{"role":"user","content":"问题"}]}'
```

Python（OpenAI SDK）：

```python
from openai import OpenAI
client = OpenAI(base_url="http://<IP>:8080/v1", api_key="<API_KEY>")
resp = client.chat.completions.create(
    model="knowledge-base",
    messages=[{"role": "user", "content": "删除文档要注意什么？"}],
    extra_body={"knowledge_base_ids": ["<kb-uuid>"], "top_k": 5, "return_citations": True},
)
print(resp.choices[0].message.content)
```

## 11. 任务

| 方法 | 路径 | Scope | 说明 |
|------|------|-------|------|
| GET | `/api/v1/tasks` | 登录 | 任务列表（可按状态过滤） |
| GET | `/api/v1/tasks/{task_id}` | 登录 | 任务详情（含 progress） |
| POST | `/api/v1/tasks/{task_id}/retry` | 登录 | 重试（仅 `failed` 任务） |

## 12. 管理：API Key 与用量

| 方法 | 路径 | Scope | 说明 |
|------|------|-------|------|
| GET | `/api/v1/admin/api-keys` | `kb:admin` | Key 列表（不含明文/哈希） |
| POST | `/api/v1/admin/api-keys` | `kb:admin` | 创建，**响应含明文 key，仅此一次** |
| GET | `/api/v1/admin/api-keys/{key_id}` | `kb:admin` | 详情 |
| PUT | `/api/v1/admin/api-keys/{key_id}` | `kb:admin` | 更新（scopes/绑定/限流/status/有效期） |
| DELETE | `/api/v1/admin/api-keys/{key_id}` | `kb:admin` | 删除 |
| POST | `/api/v1/admin/api-keys/{key_id}/rotate` | `kb:admin` | 轮换密钥，返回新明文（仅一次） |
| GET | `/api/v1/admin/api-usage` | `kb:admin` | 用量汇总 |
| GET | `/api/v1/admin/api-usage/daily` | `kb:admin` | 按日统计 |
| GET | `/api/v1/admin/api-logs` | `kb:admin` | 调用日志明细 |

创建 Key 请求体：

```json
{
  "name": "prod-integration",
  "scopes": ["kb:search", "kb:chat"],
  "knowledge_base_ids": ["<kb-uuid>"],
  "default_kb_ids": ["<kb-uuid>"],
  "rate_limit": 60,
  "daily_limit": 10000,
  "expires_in_days": 90
}
```

其它：`GET /api/v1/stats`（登录）返回平台统计（知识库数、文档数、切片数等）。

## 13. 管理：用户

仅管理员 JWT 可调用，API Key 一律 `403`。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/admin/users?q=&role=&status=&skip=0&limit=50` | 列表，返回 `{total, items}`；`q` 模糊匹配用户名/邮箱 |
| POST | `/api/v1/admin/users` | 创建 `{username, password, email?, role}`，用户名 3-50 位字母数字 `_ . -`，不区分大小写唯一 |
| GET | `/api/v1/admin/users/{id}` | 详情 |
| PUT | `/api/v1/admin/users/{id}` | 修改 `email` / `role`（admin\|user）/ `status`（active\|disabled） |
| POST | `/api/v1/admin/users/{id}/reset-password` | 重置密码 `{new_password}`，同时解锁并使其会话失效 |
| POST | `/api/v1/admin/users/{id}/unlock` | 解除登录锁定 |
| DELETE | `/api/v1/admin/users/{id}` | 删除；仍拥有知识库或 API Key 时返回 `409`，可改为禁用 |

保护规则：不能禁用、降级或删除自己；不能移除最后一个可用管理员（`409`）。

## 14. 限流与错误码

限流仅作用于 API Key 请求，用 Redis 维护每分钟桶与每日桶（阈值取 Key 的 `rate_limit`/`daily_limit`）。

| 状态码 | 场景 |
|--------|------|
| 400 | 参数错误 / 不支持的文件类型 / 魔数校验失败 / 没有可用知识库 |
| 401 | 缺少或无效的 Bearer 凭证 / 用户被禁用 / 改密等操作后旧 JWT 失效 |
| 403 | scope 不足 / API Key 禁用或过期 / 无权访问指定知识库 |
| 404 | 资源不存在 |
| 409 | 用户名重复 / 不能操作自己或最后一个管理员 / 删除仍有资源的用户 |
| 413 | 文件超过大小限制 |
| 423 | 登录失败次数过多，账号临时锁定 |
| 422 | 请求体校验失败（FastAPI 自动） |
| 429 | 超出每分钟或每日调用限制 |
| 500 | 服务端异常 |

错误响应统一为 `{"detail": "错误描述"}`（422 为 FastAPI 校验数组）。
