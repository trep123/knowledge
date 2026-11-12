#!/usr/bin/env bash
# 一键离线部署脚本
# 用法：解压离线包后，在项目根目录执行
#     ./deploy/offline-deploy.sh [-y|--yes] [--skip-sha]
#   -y, --yes     非交互模式：模型缺失时也继续启动基础服务（适用于 ssh 远程/自动化）
#   --skip-sha    跳过模型 SHA256 校验（大文件校验约需数十秒）
# 环境变量：HEALTH_TIMEOUT=秒数（默认 600，等待全部依赖就绪的上限）
# 说明：从 offline/images/ 加载 Docker 镜像（无需联网 build/pull），
#       自动生成 .env（随机密钥）、按 GPU 数量分配显卡，启动并等待全部依赖就绪。
#       模型文件（models/）不在离线包内，需另行准备，详见 docs/MODELS.md。
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
# shellcheck source=deploy/lib-images.sh
. "$ROOT/deploy/lib-images.sh"

ASSUME_YES=0; SKIP_SHA=0
for arg in "$@"; do
    case "$arg" in
        -y|--yes) ASSUME_YES=1 ;;
        --skip-sha) SKIP_SHA=1 ;;
        -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
        *) echo "未知参数：$arg（-h 查看用法）" >&2; exit 2 ;;
    esac
done
HEALTH_TIMEOUT=${HEALTH_TIMEOUT:-600}

info() { echo -e "\033[32m[INFO]\033[0m $1"; }
warn() { echo -e "\033[33m[WARN]\033[0m $1"; }
err()  { echo -e "\033[31m[FAIL]\033[0m $1" >&2; }
env_get() { { grep -E "^$1=" "$ROOT/.env" || true; } | tail -n1 | cut -d= -f2-; }
env_set() {
    if grep -qE "^$1=" "$ROOT/.env"; then
        sed -i "s|^$1=.*|$1=$2|" "$ROOT/.env"
    else
        echo "$1=$2" >> "$ROOT/.env"
    fi
}
confirm() {   # confirm "问题" ：-y 时直接通过；非交互终端且无 -y 时视为拒绝
    [ "$ASSUME_YES" -eq 1 ] && return 0
    if [ ! -t 0 ]; then
        err "当前为非交互环境，无法确认：$1（如需继续请加 -y）"
        return 1
    fi
    local ans; read -r -p "$1 [y/N] " ans || return 1
    case "$ans" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

# ---------- 1. 前置检查 ----------
info "检查 Docker 环境..."
command -v docker >/dev/null 2>&1 || { err "未安装 docker"; exit 1; }
docker compose version >/dev/null 2>&1 || { err "docker compose 不可用（需 v2 插件）"; exit 1; }
DOCKER_INFO=$(docker info 2>/dev/null) || { err "docker 守护进程不可用，请先启动 docker 服务"; exit 1; }
command -v curl >/dev/null 2>&1 || { err "未安装 curl（健康检查需要）"; exit 1; }

# GPU：本平台的 embedding/reranker/llm 均依赖 NVIDIA GPU（离线包中的 llama.cpp 为 CUDA 版）
grep -qi nvidia <<<"$DOCKER_INFO" || {
    err "Docker 未注册 NVIDIA runtime，GPU 服务无法启动。请安装 nvidia-container-toolkit 后重启 docker（见 docs/DEPLOYMENT.md）"
    exit 1
}
GPU_COUNT=0
if command -v nvidia-smi >/dev/null 2>&1; then
    GPU_COUNT=$(nvidia-smi -L 2>/dev/null | grep -c '^GPU' || true)
fi
if [ "$GPU_COUNT" -lt 1 ]; then
    err "未检测到可用 GPU（nvidia-smi -L 无输出）。离线包仅支持 GPU 部署。"
    exit 1
fi
info "检测到 ${GPU_COUNT} 张 GPU"

# ---------- 2. 生成或校验 .env ----------
gen_secret() { openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
gen_pass()   { openssl rand -base64 18 2>/dev/null | tr -d '/+=' | cut -c1-16 || head -c 12 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
fill_defaults() {   # 只替换仍为 change-this 的项
    local k
    for k in APP_SECRET_KEY JWT_SECRET_KEY LLM_API_KEY; do
        env_get "$k" | grep -q '^change-this' && env_set "$k" "$(gen_secret)"
    done
    for k in POSTGRES_PASSWORD REDIS_PASSWORD ADMIN_PASSWORD; do
        env_get "$k" | grep -q '^change-this' && env_set "$k" "$(gen_pass)"
    done
    return 0
}
pg_initialized() { [ -n "$(ls -A "$ROOT/data/postgres" 2>/dev/null)" ]; }

NEW_ADMIN=0
if [ ! -f "$ROOT/.env" ]; then
    info "生成 .env（随机密钥与管理员密码）..."
    cp "$ROOT/.env.example" "$ROOT/.env"
    chmod 600 "$ROOT/.env"
    fill_defaults
    NEW_ADMIN=1
elif grep -qE '=change-this' "$ROOT/.env"; then
    DEFAULT_KEYS=$(grep -E '=change-this' "$ROOT/.env" | cut -d= -f1 | tr '\n' ' ')
    if pg_initialized; then
        if env_get POSTGRES_PASSWORD | grep -q '^change-this'; then
            err ".env 中仍有默认值：${DEFAULT_KEYS}"
            err "数据库已用默认密码初始化，自动修改 POSTGRES_PASSWORD 会导致后端连不上数据库。"
            err "请先在 postgres 中 ALTER USER 修改密码，再同步修改 .env 后重试。"
            exit 1
        fi
        if env_get ADMIN_PASSWORD | grep -q '^change-this'; then
            warn "管理员账号已按默认密码创建，修改 .env 不会生效，请登录后在右上角立即修改密码。"
        fi
        warn ".env 中存在默认值（${DEFAULT_KEYS}），自动替换为随机值（已登录用户需重新登录）。"
        fill_defaults
    else
        warn ".env 中存在默认值（${DEFAULT_KEYS}），全新安装，自动替换为随机值。"
        fill_defaults
        NEW_ADMIN=1
    fi
    chmod 600 "$ROOT/.env"
else
    info "使用已有 .env。"
fi

# 按 GPU 数量分配显卡（仅在用户未改过默认分配时调整）
if [ "$GPU_COUNT" -eq 1 ] && [ "$(env_get LLM_GPU)" != "0" ]; then
    warn "单 GPU 机器：embedding/reranker/llm 共用 GPU0，需显存 >= 16GB，否则 LLM 可能因显存不足启动失败。"
    env_set EMBED_GPU 0
    env_set LLM_GPU 0
fi
for k in EMBED_GPU LLM_GPU; do
    v=$(env_get "$k"); v=${v:-0}
    if [ "$v" -ge "$GPU_COUNT" ] 2>/dev/null; then
        err "$k=$v 超出 GPU 编号范围（共 ${GPU_COUNT} 张，编号 0-$((GPU_COUNT-1))），请修改 .env"
        exit 1
    fi
done

# ---------- 3. 端口检查 ----------
GATEWAY_PORT=$(env_get GATEWAY_PORT); GATEWAY_PORT=${GATEWAY_PORT:-8080}
if command -v ss >/dev/null 2>&1 && ss -tln 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${GATEWAY_PORT}$"; then
    if ! docker ps --format '{{.Names}} {{.Ports}}' | grep -q "^kb-nginx .*:${GATEWAY_PORT}->"; then
        err "端口 ${GATEWAY_PORT} 已被其他进程占用，请修改 .env 中的 GATEWAY_PORT"
        exit 1
    fi
fi

# ---------- 4. 加载并校验镜像 ----------
mapfile -t IMAGES < <(compose_images "$ROOT/docker-compose.yml")
missing_images() {
    local img
    for img in "${IMAGES[@]}"; do
        docker image inspect "$img" >/dev/null 2>&1 || echo "$img"
    done
}
MISSING_IMGS=$(missing_images)
if [ -z "$MISSING_IMGS" ]; then
    info "所需镜像已全部存在，跳过 docker load。"
else
    IMAGES_DIR="$ROOT/offline/images"
    if ! ls "$IMAGES_DIR"/*.tar >/dev/null 2>&1; then
        err "缺少镜像且未找到离线镜像 $IMAGES_DIR/*.tar："
        echo "$MISSING_IMGS" | sed 's/^/        /' >&2
        exit 1
    fi
    info "从离线包加载 Docker 镜像（首次约需数分钟）..."
    for f in "$IMAGES_DIR"/*.tar; do
        info "  docker load <- $(basename "$f")"
        docker load -i "$f"
    done
    MISSING_IMGS=$(missing_images)
    if [ -n "$MISSING_IMGS" ]; then
        err "离线包中缺少以下镜像（请用 package-offline.sh 重新打包）："
        echo "$MISSING_IMGS" | sed 's/^/        /' >&2
        exit 1
    fi
    info "镜像加载完成。"
fi

# ---------- 5. 模型检查 ----------
info "检查模型文件..."
MANIFEST="$ROOT/offline/manifests/models.sha256"
MODEL_PROBLEM=0
while read -r _ path; do
    [ -z "$path" ] && continue
    if [ -e "$ROOT/$path" ]; then
        info "  [OK] $path"
    else
        warn "  [缺失] $path"
        MODEL_PROBLEM=1
    fi
done < "$MANIFEST"
if [ "$MODEL_PROBLEM" -eq 0 ] && [ "$SKIP_SHA" -eq 0 ]; then
    info "校验模型 SHA256（约需数十秒，--skip-sha 可跳过）..."
    if ! sha256sum --quiet -c "$MANIFEST"; then
        warn "模型文件校验失败（可能下载不完整或版本不符），请按 docs/MODELS.md 重新下载。"
        MODEL_PROBLEM=1
    fi
fi
if [ "$MODEL_PROBLEM" -eq 1 ]; then
    warn "模型缺失或损坏会导致 embedding/reranker/llm 服务无法就绪。"
    if ! confirm "仍要继续启动（仅数据库/后端等基础服务可用）？"; then
        info "已取消。补齐模型后重新运行本脚本。"
        exit 1
    fi
fi

# ---------- 6. 数据目录 ----------
for d in postgres qdrant redis documents extracted logs backups temporary; do
    mkdir -p "$ROOT/data/$d"
done

# ---------- 7. 启动服务 ----------
info "启动全部服务（镜像已预加载，无需 build）..."
docker compose up -d --no-build

# ---------- 8. 健康检查（等待全部依赖就绪） ----------
info "等待服务就绪（最长 ${HEALTH_TIMEOUT} 秒，模型加载权重通常需 1-3 分钟）..."
HOST_IP=$(hostname -I 2>/dev/null | awk '{print $1}'); HOST_IP=${HOST_IP:-127.0.0.1}
GATEWAY_BIND=$(env_get GATEWAY_BIND); GATEWAY_BIND=${GATEWAY_BIND:-0.0.0.0}
case "$GATEWAY_BIND" in 0.0.0.0|"") PROBE_HOST=127.0.0.1; SHOW_HOST=$HOST_IP ;; *) PROBE_HOST=$GATEWAY_BIND; SHOW_HOST=$GATEWAY_BIND ;; esac
DEPS_URL="http://${PROBE_HOST}:${GATEWAY_PORT}/api/health/dependencies"
DEADLINE=$(( $(date +%s) + HEALTH_TIMEOUT ))
LAST=""
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
    LAST=$(curl -sf --max-time 30 "$DEPS_URL" 2>/dev/null || true)
    if grep -q '"status":"ok"' <<<"$LAST"; then
        echo
        info "部署成功，全部依赖就绪！"
        echo "        Web 控制台 : http://${SHOW_HOST}:${GATEWAY_PORT}"
        [ "$(env_get ENABLE_API_DOCS)" = "true" ] && echo "        API 文档   : http://${SHOW_HOST}:${GATEWAY_PORT}/docs"
        echo "        依赖状态   : curl http://${PROBE_HOST}:${GATEWAY_PORT}/api/health/dependencies"
        if [ "$NEW_ADMIN" -eq 1 ]; then
            echo "        管理员账号 : $(env_get ADMIN_USERNAME)"
            echo "        初始密码   : 已写入 .env 的 ADMIN_PASSWORD（查看：grep ADMIN_PASSWORD .env），登录后请在右上角修改密码"
        fi
        echo
        ./deploy/status.sh || true
        exit 0
    fi
    sleep 5
done

warn "在 ${HEALTH_TIMEOUT} 秒内未全部就绪。"
if [ -n "$LAST" ]; then
    echo "        各依赖状态：$LAST"
    echo "        未就绪的服务可用 ./deploy/logs.sh <服务名> 查看日志（如 llm、embedding）"
else
    echo "        后端未响应，查看日志：./deploy/logs.sh backend"
fi
echo "        服务状态：./deploy/status.sh"
./deploy/status.sh || true
exit 1
