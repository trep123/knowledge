#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."

./deploy/check-environment.sh

echo "构建镜像..."
docker compose build

echo "启动服务..."
docker compose up -d

echo "等待健康检查..."
for i in $(seq 1 60); do
    if curl -sf "http://127.0.0.1:$(grep -E '^GATEWAY_PORT=' .env | cut -d= -f2 || echo 8080)/api/health" >/dev/null 2>&1; then
        echo "服务已启动: http://$(hostname -I | awk '{print $1}'):$(grep -E '^GATEWAY_PORT=' .env | cut -d= -f2)"
        ./deploy/status.sh
        exit 0
    fi
    sleep 5
done

echo "健康检查超时，请查看日志: ./deploy/logs.sh"
./deploy/status.sh
exit 1
