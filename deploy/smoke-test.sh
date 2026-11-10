#!/usr/bin/env bash
# 端到端冒烟测试：登录 -> 建库 -> 上传 -> 等待处理 -> 检索 -> 问答 -> API Key -> OpenAI 兼容接口
set -e
cd "$(dirname "$0")/.."
source .env

BASE="http://127.0.0.1:${GATEWAY_PORT:-8080}"
PASS=0; FAIL=0
ok()  { echo -e "  [PASS] $1"; PASS=$((PASS+1)); }
bad() { echo -e "  [FAIL] $1"; FAIL=$((FAIL+1)); }

echo "== 1. 健康检查 =="
curl -sf "$BASE/api/health" >/dev/null && ok "/api/health" || bad "/api/health"
DEPS=$(curl -sf "$BASE/api/health/dependencies" || echo '{}')
echo "$DEPS" | python3 -c "import json,sys;d=json.load(sys.stdin);[print(f'    {k}: {v}') for k,v in d.get('checks',{}).items()]"

echo "== 2. 登录 =="
TOKEN=$(curl -sf -X POST "$BASE/api/v1/auth/login" -H "Content-Type: application/json" \
  -d "{\"username\":\"$ADMIN_USERNAME\",\"password\":\"$ADMIN_PASSWORD\"}" | python3 -c "import json,sys;print(json.load(sys.stdin)['access_token'])")
[ -n "$TOKEN" ] && ok "JWT 登录成功" || { bad "登录失败"; exit 1; }
AUTH="Authorization: Bearer $TOKEN"

echo "== 3. 创建知识库 =="
KB_RESP=$(curl -sf -X POST "$BASE/api/v1/knowledge-bases" -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name":"冒烟测试库","description":"smoke test","chunk_size":500,"chunk_overlap":80}')
KB_ID=$(echo "$KB_RESP" | python3 -c "import json,sys;print(json.load(sys.stdin)['id'])")
[ -n "$KB_ID" ] && ok "知识库 $KB_ID" || bad "创建知识库失败"

echo "== 4. 上传测试文档 =="
TMPDOC=$(mktemp /tmp/smoke_XXXX.txt)
cat > "$TMPDOC" <<'DOC'
本地知识库平台安全规范

第一章 访问控制
所有外部调用必须经过 API Gateway 统一鉴权，禁止直接访问 PostgreSQL 和 Qdrant 数据库端口。
API Key 采用 SHA256 哈希存储，明文仅在创建时展示一次。每个 API Key 必须绑定授权知识库。

第二章 危险操作确认
删除知识库、删除文档、轮换密钥等危险操作必须执行二次确认。删除文档时必须同步删除对应的向量数据。

第三章 审计要求
系统必须记录所有 API 调用的时间、来源 IP、状态码和耗时，日志中不得保存明文密钥。
备份采用 PostgreSQL 逻辑备份加 Qdrant 快照的一致性流程，恢复后必须执行检索测试验证。
DOC
UP_RESP=$(curl -sf -X POST "$BASE/api/v1/knowledge-bases/$KB_ID/documents" -H "$AUTH" -F "file=@$TMPDOC")
DOC_ID=$(echo "$UP_RESP" | python3 -c "import json,sys;print(json.load(sys.stdin)['document']['id'])")
[ -n "$DOC_ID" ] && ok "文档已上传 $DOC_ID" || bad "上传失败"

echo "== 5. 等待文档处理完成 =="
for i in $(seq 1 36); do
    STATUS=$(curl -sf "$BASE/api/v1/documents/$DOC_ID" -H "$AUTH" | python3 -c "import json,sys;print(json.load(sys.stdin)['status'])")
    [ "$STATUS" = "ready" ] && break
    [ "$STATUS" = "failed" ] && break
    sleep 5
done
[ "$STATUS" = "ready" ] && ok "文档处理完成（切片数: $(curl -sf "$BASE/api/v1/documents/$DOC_ID" -H "$AUTH" | python3 -c "import json,sys;print(json.load(sys.stdin)['chunk_count'])")）" || bad "文档处理状态: $STATUS"

echo "== 6. 混合检索 =="
SEARCH_RESP=$(curl -sf -X POST "$BASE/api/v1/search/hybrid" -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"knowledge_base_ids\":[\"$KB_ID\"],\"query\":\"API Key 是如何存储的？\",\"top_k\":3,\"rerank\":true}")
N=$(echo "$SEARCH_RESP" | python3 -c "import json,sys;print(json.load(sys.stdin)['total'])")
[ "$N" -ge 1 ] && ok "检索到 $N 条结果" || bad "检索无结果"
echo "$SEARCH_RESP" | python3 -c "import json,sys;d=json.load(sys.stdin);r=d['results'][0] if d['results'] else {};print(f\"    top1: score={r.get('score')} content={r.get('content','')[:60]}...\")"

echo "== 7. RAG 问答（含引用） =="
CHAT_RESP=$(curl -sf -X POST "$BASE/api/v1/chat/completions" -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"knowledge_base_ids\":[\"$KB_ID\"],\"query\":\"删除文档时有什么要求？\",\"top_k\":3,\"return_citations\":true}")
ANSWER=$(echo "$CHAT_RESP" | python3 -c "import json,sys;print(json.load(sys.stdin)['answer'][:100])")
CITES=$(echo "$CHAT_RESP" | python3 -c "import json,sys;print(len(json.load(sys.stdin)['citations']))")
[ -n "$ANSWER" ] && ok "回答: $ANSWER…" || bad "问答失败"
[ "$CITES" -ge 1 ] && ok "引用 $CITES 条" || bad "无引用"

echo "== 8. 创建 API Key 并验证 OpenAI 兼容接口 =="
KEY_RESP=$(curl -sf -X POST "$BASE/api/v1/admin/api-keys" -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"name\":\"smoke-test\",\"scopes\":[\"kb:read\",\"kb:search\",\"kb:chat\"],\"knowledge_base_ids\":[\"$KB_ID\"]}")
API_KEY=$(echo "$KEY_RESP" | python3 -c "import json,sys;print(json.load(sys.stdin)['api_key'])")
[ -n "$API_KEY" ] && ok "API Key 已创建" || bad "API Key 创建失败"

OA_RESP=$(curl -sf -X POST "$BASE/v1/chat/completions" -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"knowledge-base\",\"messages\":[{\"role\":\"user\",\"content\":\"备份采用什么流程？\"}]}")
OA_TEXT=$(echo "$OA_RESP" | python3 -c "import json,sys;print(json.load(sys.stdin)['choices'][0]['message']['content'][:80])")
[ -n "$OA_TEXT" ] && ok "OpenAI 兼容接口: $OA_TEXT…" || bad "OpenAI 兼容接口失败"

echo "== 9. 权限验证 =="
UNAUTH=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/v1/search" -H "Content-Type: application/json" -d '{"query":"test"}')
[ "$UNAUTH" = "401" ] || [ "$UNAUTH" = "403" ] && ok "未授权请求被拒绝 ($UNAUTH)" || bad "未授权请求返回 $UNAUTH"
BADKEY=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/v1/chat/completions" -H "Authorization: Bearer kb-invalidkey" -H "Content-Type: application/json" -d '{"model":"knowledge-base","messages":[{"role":"user","content":"hi"}]}')
[ "$BADKEY" = "401" ] && ok "无效 API Key 被拒绝" || bad "无效 API Key 返回 $BADKEY"

echo "== 10. 清理 =="
curl -sf -X DELETE "$BASE/api/v1/knowledge-bases/$KB_ID" -H "$AUTH" >/dev/null && ok "测试知识库已删除" || bad "清理失败"
rm -f "$TMPDOC"

echo
echo "结果: PASS=$PASS FAIL=$FAIL"
[ $FAIL -eq 0 ] && echo "冒烟测试全部通过" || { echo "存在失败项"; exit 1; }
