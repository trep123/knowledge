#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
docker compose down
echo "已停止（数据保留在 ./data 目录）"
