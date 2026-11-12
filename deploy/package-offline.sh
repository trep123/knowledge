#!/usr/bin/env bash
# 制作离线部署压缩包（含项目代码 + Docker 镜像，不含模型/运行数据）
# 用法：./deploy/package-offline.sh [--save] [输出目录，默认项目上级目录]
#   --save  先按 docker-compose.yml 中的镜像清单执行 docker save（需本机已 build/pull 好全部镜像）
# 产物：<输出目录>/knowledge-offline-<日期>.tar.zst
#
# 说明：
#   - 压缩包在项目目录之外生成，避免自包含递归。
#   - 排除：models/（模型）、data/（运行数据）、.env（机密）、.git、
#           node_modules/、frontend/dist/、.tools-venv/、__pycache__ 等。
#   - 使用 zstd -T0 多核并行压缩。
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)                 # 如 /kvm/knowledge
# shellcheck source=deploy/lib-images.sh
. "$ROOT/deploy/lib-images.sh"
SAVE=0
if [ "${1:-}" = "--save" ]; then SAVE=1; shift; fi
PARENT=$(dirname "$ROOT")   # /kvm
BASE=$(basename "$ROOT")    # knowledge
OUT_DIR="${1:-$PARENT}"
DATE=$(date +%Y%m%d)
ARCHIVE="$OUT_DIR/${BASE}-offline-${DATE}.tar.zst"

info() { echo -e "\033[32m[INFO]\033[0m $1"; }
err()  { echo -e "\033[31m[FAIL]\033[0m $1" >&2; }

command -v zstd >/dev/null 2>&1 || { err "未安装 zstd（apt install zstd）"; exit 1; }

# 1. 确保镜像已 save 到 offline/images/（每个镜像一个 tar）
IMAGES_DIR="$ROOT/offline/images"
mapfile -t IMAGES < <(compose_images "$ROOT/docker-compose.yml")
tar_name() { echo "$1" | tr '/:' '__'; }
if [ "$SAVE" -eq 1 ]; then
    mkdir -p "$IMAGES_DIR"
    for img in "${IMAGES[@]}"; do
        docker image inspect "$img" >/dev/null 2>&1 \
            || { err "本机没有镜像 $img，请先 docker compose build && docker compose pull"; exit 1; }
        info "docker save $img"
        docker save -o "$IMAGES_DIR/$(tar_name "$img").tar" "$img"
    done
fi
MISSING=0
for img in "${IMAGES[@]}"; do
    [ -f "$IMAGES_DIR/$(tar_name "$img").tar" ] || { err "缺少镜像包：$img（offline/images/$(tar_name "$img").tar）"; MISSING=1; }
done
if [ "$MISSING" -eq 1 ]; then
    err "请加 --save 参数重新执行，自动导出 docker-compose.yml 引用的全部镜像"
    exit 1
fi
info "镜像包："
ls -lh "$ROOT/offline/images/"*.tar | awk '{print "        "$9" ("$5")"}'

# 2. 打包（从上级目录以 BASE 为顶层目录名）
info "生成压缩包（多核 zstd 压缩，视镜像大小约需数分钟）..."
info "输出：$ARCHIVE"
tar \
    --exclude="${BASE}/models" \
    --exclude="${BASE}/data" \
    --exclude="${BASE}/.env" \
    --exclude="${BASE}/.git" \
    --exclude="${BASE}/node_modules" \
    --exclude="${BASE}/frontend/node_modules" \
    --exclude="${BASE}/frontend/dist" \
    --exclude="${BASE}/.tools-venv" \
    --exclude="${BASE}/**/__pycache__" \
    --exclude="${BASE}/**/*.pyc" \
    -cf - -C "$PARENT" "$BASE" | zstd -T0 -3 -o "$ARCHIVE"

info "完成。"
ls -lh "$ARCHIVE" | awk '{print "        "$9" ("$5")"}'
echo
echo "解压并部署："
echo "    zstd -d ${BASE}-offline-${DATE}.tar.zst -o ${BASE}-offline-${DATE}.tar"
echo "    tar xf ${BASE}-offline-${DATE}.tar"
echo "    cd ${BASE} && ./deploy/offline-deploy.sh"
echo
echo "注意：模型文件不在包内，需按 docs/MODELS.md 放入 models/ 后再部署。"
