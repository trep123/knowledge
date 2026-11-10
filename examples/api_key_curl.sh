#!/usr/bin/env bash
#
# 外部 API 调用示例（使用 API Key，无需登录账户）
#
# 用法:
#   export KB_API_KEY="kb-你的APIKey"
#   ./examples/api_key_curl.sh [models|chat|stream|search|all]
#
# 可选环境变量:
#   KB_BASE_URL   网关地址，默认 http://localhost:8080
#   KB_API_KEY    必填，Web「API Key 管理」创建，明文只展示一次
#   KB_ID         知识库 UUID；不填则用 API Key 绑定的默认知识库/授权范围
#   KB_QUERY      提问内容，默认「删除文档时需要注意什么？」
#
# 说明: 所有请求都用 `Authorization: Bearer <API Key>` 鉴权，不涉及账号密码登录。
#
set -euo pipefail

BASE_URL="${KB_BASE_URL:-http://localhost:8080}"
API_KEY="${KB_API_KEY:-}"
KB_ID="${KB_ID:-}"
QUERY="${KB_QUERY:-删除文档时需要注意什么？}"

if [[ -z "$API_KEY" ]]; then
  echo "错误: 请先设置环境变量 KB_API_KEY，例如:" >&2
  echo '  export KB_API_KEY="kb-xxxxxxxx..."' >&2
  exit 1
fi

AUTH="Authorization: Bearer ${API_KEY}"
JSON_H="Content-Type: application/json"

# 组装可选的 knowledge_base_ids 片段（KB_ID 为空则省略，走 Key 的默认知识库）
kb_ids_field() {
  if [[ -n "$KB_ID" ]]; then
    printf '"knowledge_base_ids": ["%s"],' "$KB_ID"
  fi
}

hr() { printf '\n\033[1;36m== %s ==\033[0m\n' "$1"; }
# 有 python3 就美化 JSON，否则原样输出
pretty() { if command -v python3 >/dev/null 2>&1; then python3 -m json.tool 2>/dev/null || cat; else cat; fi; }

demo_models() {
  hr "1) GET /v1/models —— 列出可用模型"
  curl -sS "$BASE_URL/v1/models" -H "$AUTH" | pretty
}

demo_chat() {
  hr "2) POST /v1/chat/completions —— 非流式问答（OpenAI 兼容）"
  curl -sS "$BASE_URL/v1/chat/completions" \
    -H "$AUTH" -H "$JSON_H" \
    -d "{
          \"model\": \"knowledge-base\",
          \"messages\": [{\"role\": \"user\", \"content\": \"$QUERY\"}],
          $(kb_ids_field)
          \"top_k\": 5,
          \"rerank\": true,
          \"return_citations\": true
        }" | pretty
}

demo_stream() {
  hr "3) POST /v1/chat/completions —— SSE 流式问答（逐字返回）"
  echo "(原始 SSE 事件流，以 data: [DONE] 结束)"
  curl -sS -N "$BASE_URL/v1/chat/completions" \
    -H "$AUTH" -H "$JSON_H" \
    -d "{
          \"model\": \"knowledge-base\",
          \"stream\": true,
          \"messages\": [{\"role\": \"user\", \"content\": \"$QUERY\"}],
          $(kb_ids_field)
          \"return_citations\": true
        }"
  echo
}

demo_search() {
  hr "4) POST /api/v1/search —— 混合检索（只返回证据片段，不生成）"
  curl -sS "$BASE_URL/api/v1/search" \
    -H "$AUTH" -H "$JSON_H" \
    -d "{
          \"query\": \"$QUERY\",
          $(kb_ids_field)
          \"top_k\": 5,
          \"rerank\": true
        }" | pretty
}

case "${1:-all}" in
  models)  demo_models ;;
  chat)    demo_chat ;;
  stream)  demo_stream ;;
  search)  demo_search ;;
  all)     demo_models; demo_chat; demo_stream; demo_search ;;
  *)
    echo "未知子命令: $1" >&2
    echo "可用: models | chat | stream | search | all" >&2
    exit 2 ;;
esac

hr "完成"
echo "基址: $BASE_URL"
echo "提示: 401=Key 无效/缺失, 403=scope 不足或无权访问该知识库, 429=触发限流"
