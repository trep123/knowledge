#!/usr/bin/env bash
# 制作离线部署压缩包（含项目代码 + Docker 镜像，不含模型/运行数据）
# 用法：./deploy/package-offline.sh [输出目录，默认项目上级目录]
# 产物：<输出目录>/knowledge-offline-<日期>.tar.zst
#
# 说明：
#   - 压缩包在项目目录之外生成，避免自包含递归。
#   - 排除：models/（模型）、data/（运行数据）、.env（机密）、.git、
#           node_modules/、frontend/dist/、.tools-venv/、__pycache__ 等。
#   - 使用 zstd -T0 多核并行压缩。
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)                 # /kvm/knowledge
PARENT=$(dirname "$ROOT")   # /kvm
BASE=$(basename "$ROOT")    # knowledge
OUT_DIR="${1:-$PARENT}"
DATE=$(date +%Y%m%d)
ARCHIVE="$OUT_DIR/${BASE}-offline-${DATE}.tar.zst"

info() { echo -e "\033[32m[INFO]\033[0m $1"; }
err()  { echo -e "\033[31m[FAIL]\033[0m $1" >&2; }

command -v zstd >/dev/null 2>&1 || { err "未安装 zstd（apt install zstd）"; exit 1; }

# 1. 确保镜像已 save 到 offline/images/
if ! ls "$ROOT/offline/images/"*.tar >/dev/null 2>&1; then
    err "offline/images/ 中没有镜像 tar，请先执行 docker save（见脚本末尾注释）"
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
