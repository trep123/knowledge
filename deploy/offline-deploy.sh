#!/usr/bin/env bash
# 一键离线部署脚本
# 用法：解压离线包后，在项目根目录执行  ./deploy/offline-deploy.sh
# 说明：从 offline/images/ 加载全部 Docker 镜像（无需联网 build/pull），
#       自动生成 .env（随机密钥），启动全部服务并等待健康检查。
#       模型文件（models/）不在离线包内，需另行准备，详见 docs/MODELS.md。
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)

info() { echo -e "\033[32m[INFO]\033[0m $1"; }
warn() { echo -e "\033[33m[WARN]\033[0m $1"; }
err()  { echo -e "\033[31m[FAIL]\033[0m $1" >&2; }

# ---------- 1. 前置检查 ----------
info "检查 Docker 环境..."
command -v docker >/dev/null 2>&1 || { err "未安装 docker"; exit 1; }
docker compose version >/dev/null 2>&1 || { err "docker compose 不可用（需 v2 插件）"; exit 1; }
docker info >/dev/null 2>&1 || { err "docker 守护进程不可用，请先启动 docker 服务"; exit 1; }
docker info 2>/dev/null | grep -qi nvidia \
    && info "NVIDIA runtime 已注册（GPU 可用）" \
    || warn "未检测到 NVIDIA runtime，GPU 服务可能无法启动（详见 docs/DEPLOYMENT.md）"

# ---------- 2. 加载镜像 ----------
IMAGES_DIR="$ROOT/offline/images"
if [ ! -d "$IMAGES_DIR" ] || ! ls "$IMAGES_DIR"/*.tar >/dev/null 2>&1; then
    err "未找到离线镜像目录 $IMAGES_DIR/*.tar"
    exit 1
fi
info "从离线包加载 Docker 镜像（首次约需数分钟）..."
for f in "$IMAGES_DIR"/*.tar; do
    info "  docker load <- $(basename "$f")"
    docker load -i "$f"
done
info "镜像加载完成。"

# ---------- 3. 生成 .env ----------
gen_secret() { openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
gen_pass()   { openssl rand -base64 18 2>/dev/null | tr -d '/+=' | cut -c1-16 || head -c 12 /dev/urandom | od -An -tx1 | tr -d ' \n'; }

if [ -f "$ROOT/.env" ]; then
    info "检测到已有 .env，保留不变。"
else
    info "生成 .env（随机密钥与管理员密码）..."
    cp "$ROOT/.env.example" "$ROOT/.env"
    APP_SECRET=$(gen_secret); JWT_SECRET=$(gen_secret)
    PG_PASS=$(gen_pass); REDIS_PASS=$(gen_pass); ADMIN_PASS=$(gen_pass)
    LLM_KEY=$(gen_secret)
    sed -i \
        -e "s|^APP_SECRET_KEY=.*|APP_SECRET_KEY=${APP_SECRET}|" \
        -e "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=${JWT_SECRET}|" \
        -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${PG_PASS}|" \
        -e "s|^REDIS_PASSWORD=.*|REDIS_PASSWORD=${REDIS_PASS}|" \
        -e "s|^LLM_API_KEY=.*|LLM_API_KEY=${LLM_KEY}|" \
        -e "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=${ADMIN_PASS}|" \
        "$ROOT/.env"
    chmod 600 "$ROOT/.env"
    warn "已生成管理员账号，请立即记录："
    echo "        ADMIN_USERNAME=$(grep -E '^ADMIN_USERNAME=' "$ROOT/.env" | cut -d= -f2)"
    echo "        ADMIN_PASSWORD=${ADMIN_PASS}"
    echo "        （后续也可在 .env 中查看/修改，管理员密码仅首次启动时生效）"
fi

# ---------- 4. 模型检查 ----------
info "检查模型文件..."
MISSING=0
for m in \
    "models/embedding/bge-m3/pytorch_model.bin" \
    "models/reranker/bge-reranker-v2-m3/model.safetensors" \
    "models/llm/Qwen3-8B-Q4_K_M.gguf"; do
    if [ -e "$ROOT/$m" ]; then
        info "  [OK] $m"
    else
        warn "  [缺失] $m"
        MISSING=1
    fi
done
if [ $MISSING -eq 1 ]; then
    warn "离线包不含模型文件。缺失模型会导致 embedding/reranker/llm 服务无法就绪。"
    warn "请按 docs/MODELS.md 下载模型放入 models/ 对应目录后重试。"
    read -r -p "仍要继续启动（仅数据库/后端等基础服务可用）？[y/N] " ans
    case "$ans" in y|Y|yes|YES) ;; *) info "已取消。补齐模型后重新运行本脚本。"; exit 1;; esac
fi

# ---------- 5. 数据目录 ----------
for d in postgres qdrant redis documents extracted logs backups temporary; do
    mkdir -p "$ROOT/data/$d"
done

# ---------- 6. 启动服务 ----------
GATEWAY_PORT=$(grep -E '^GATEWAY_PORT=' "$ROOT/.env" | cut -d= -f2); GATEWAY_PORT=${GATEWAY_PORT:-8080}
info "启动全部服务（镜像已预加载，无需 build）..."
docker compose up -d --no-build

# ---------- 7. 健康检查 ----------
info "等待服务就绪（最长 5 分钟）..."
HOST_IP=$(hostname -I 2>/dev/null | awk '{print $1}'); HOST_IP=${HOST_IP:-127.0.0.1}
for i in $(seq 1 60); do
    if curl -sf "http://127.0.0.1:${GATEWAY_PORT}/api/health" >/dev/null 2>&1; then
        echo
        info "部署成功！"
        echo "        Web 控制台 : http://${HOST_IP}:${GATEWAY_PORT}"
        echo "        API 文档   : http://${HOST_IP}:${GATEWAY_PORT}/docs"
        echo "        健康检查   : curl http://127.0.0.1:${GATEWAY_PORT}/api/health/dependencies"
        echo
        ./deploy/status.sh || true
        exit 0
    fi
    sleep 5
done

warn "健康检查超时。基础服务可能仍在启动（模型服务加载权重需 1-3 分钟）。"
echo "        查看日志 : ./deploy/logs.sh backend"
echo "        服务状态 : ./deploy/status.sh"
./deploy/status.sh || true
exit 1
