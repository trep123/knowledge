#!/usr/bin/env bash
# 从备份目录恢复。用法: ./deploy/restore.sh data/backups/<时间戳>
set -e
cd "$(dirname "$0")/.."

BACKUP_DIR="${1:?用法: ./deploy/restore.sh data/backups/<时间戳>}"
[ -d "$BACKUP_DIR" ] || { echo "备份目录不存在: $BACKUP_DIR"; exit 1; }
source .env

echo "停止服务..."
docker compose down

echo "1/4 恢复文档与配置..."
tar xzf "$BACKUP_DIR/files.tar.gz"

echo "2/4 启动 PostgreSQL..."
docker compose up -d postgres
until docker exec kb-postgres pg_isready -U "${POSTGRES_USER}" >/dev/null 2>&1; do sleep 2; done

echo "3/4 恢复数据库..."
gunzip -c "$BACKUP_DIR/postgres.sql.gz" | docker exec -i kb-postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -q

echo "4/4 恢复 Qdrant 快照..."
if ls "$BACKUP_DIR"/qdrant/*.snapshot >/dev/null 2>&1; then
    docker compose up -d qdrant
    sleep 5
    for snap in "$BACKUP_DIR"/qdrant/*.snapshot; do
        name=$(basename "$snap" .snapshot)
        docker cp "$snap" kb-qdrant:/tmp/"$name".snapshot
        curl -sf -X POST "http://127.0.0.1:6333/collections/$name/snapshots/recovery" \
            -H "Content-Type: application/json" \
            -d "{\"location\": \"file:///tmp/$name.snapshot\"}" 2>/dev/null \
            || echo "  警告: $name 快照恢复失败（可在服务启动后通过后端重建向量）"
    done
else
    echo "  备份中无 Qdrant 快照，跳过（可启动后对各文档执行重处理重建向量）"
fi

echo "启动全部服务..."
docker compose up -d
./deploy/status.sh
echo "恢复完成。建议执行检索测试验证。"
