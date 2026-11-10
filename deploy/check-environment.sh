#!/usr/bin/env bash
# 环境检查：Docker、GPU、模型文件、端口、.env
set -u
cd "$(dirname "$0")/.."
ROOT=$(pwd)
FAIL=0

ok()   { echo -e "  [OK]   $1"; }
bad()  { echo -e "  [FAIL] $1"; FAIL=1; }
warn() { echo -e "  [WARN] $1"; }

echo "== Docker =="
command -v docker >/dev/null && ok "docker $(docker --version | awk '{print $3}' | tr -d ',')" || bad "docker 未安装"
docker compose version >/dev/null 2>&1 && ok "docker compose 可用" || bad "docker compose 不可用"
docker info 2>/dev/null | grep -q nvidia && ok "NVIDIA runtime 已注册" || warn "NVIDIA runtime 未注册（模型服务将回退 CPU）"

echo "== GPU =="
if command -v nvidia-smi >/dev/null; then
    GPU_COUNT=$(nvidia-smi -L | wc -l)
    ok "检测到 ${GPU_COUNT} 张 GPU"
    nvidia-smi -L | sed 's/^/        /'
else
    warn "nvidia-smi 不可用"
fi

echo "== .env =="
if [ -f "$ROOT/.env" ]; then
    ok ".env 存在"
    grep -q "change-this" "$ROOT/.env" && bad ".env 中仍有默认密码 (change-this)" || ok "无默认密码残留"
else
    bad ".env 不存在（复制 .env.example 并填写）"
fi

echo "== 模型文件 =="
check_model() {
    local path="$1" name="$2"
    if [ -e "$path" ]; then ok "$name: $(du -sh "$path" 2>/dev/null | awk '{print $1}')"; else bad "$name 缺失: $path"; fi
}
check_model "$ROOT/models/embedding/bge-m3/pytorch_model.bin" "Embedding bge-m3"
check_model "$ROOT/models/reranker/bge-reranker-v2-m3/model.safetensors" "Reranker bge-reranker-v2-m3"
check_model "$ROOT/models/llm/Qwen3-8B-Q4_K_M.gguf" "LLM Qwen3-8B Q4_K_M"

echo "== 端口 =="
PORT=$(grep -E "^GATEWAY_PORT=" "$ROOT/.env" 2>/dev/null | cut -d= -f2)
PORT=${PORT:-8080}
if ss -tln 2>/dev/null | grep -q ":${PORT} "; then
    docker ps --format '{{.Names}} {{.Ports}}' | grep -q ":${PORT}->" \
        && ok "端口 ${PORT} 由本平台容器占用" \
        || bad "端口 ${PORT} 被其他进程占用"
else
    ok "端口 ${PORT} 空闲"
fi

echo "== 数据目录 =="
for d in postgres qdrant redis documents extracted logs backups temporary; do
    [ -d "$ROOT/data/$d" ] || mkdir -p "$ROOT/data/$d"
done
ok "data/ 目录就绪（所有运行数据均保存在 $ROOT/data 内）"

echo
[ $FAIL -eq 0 ] && echo "环境检查通过" || { echo "环境检查存在失败项，请处理后重试"; exit 1; }
