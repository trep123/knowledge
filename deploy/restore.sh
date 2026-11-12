#!/usr/bin/env bash
# 从备份目录恢复。用法: ./deploy/restore.sh data/backups/<时间戳> [--yes]
#
# 会覆盖当前数据库、向量库与文档文件；当前 .env 保持不变（备份中的副本为 env.backup）。
set -euo pipefail
cd "$(dirname "$0")/.."

BACKUP_DIR="${1:?用法: ./deploy/restore.sh data/backups/<时间戳> [--yes]}"
[ -d "$BACKUP_DIR" ] || { echo "备份目录不存在: $BACKUP_DIR"; exit 1; }
set -a; source .env; set +a

echo "校验备份完整性..."
(cd "$BACKUP_DIR" && sha256sum -c --quiet SHA256SUMS) || { echo "SHA256 校验失败，已中止"; exit 1; }

if [ "${2:-}" != "--yes" ]; then
    read -r -p "将用 $BACKUP_DIR 覆盖当前全部数据，输入 yes 继续: " ans
    [ "$ans" = "yes" ] || { echo "已取消"; exit 1; }
fi

echo "停止服务..."
docker compose down

echo "1/4 恢复文档与配置..."
rm -rf data/documents data/extracted
tar xzf "$BACKUP_DIR/files.tar.gz"
if [ -f "$BACKUP_DIR/env.backup" ] && ! cmp -s "$BACKUP_DIR/env.backup" .env; then
    echo "  提示: 备份时的 .env 与当前不同，未覆盖；如需使用请手动对比 $BACKUP_DIR/env.backup"
fi

echo "2/4 启动数据服务..."
docker compose up -d postgres qdrant redis
until docker exec kb-postgres pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; do sleep 2; done

echo "3/4 恢复数据库..."
# 先清空 schema，确保恢复结果与备份完全一致（也兼容不含 DROP 语句的旧版备份）
docker exec kb-postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -q -v ON_ERROR_STOP=1 \
    -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
gunzip -c "$BACKUP_DIR/postgres.sql.gz" \
    | docker exec -i kb-postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -q -v ON_ERROR_STOP=1

echo "4/4 恢复 Qdrant 快照..."
FAILED=0
if ls "$BACKUP_DIR"/qdrant/*.snapshot >/dev/null 2>&1; then
    # 通过一次性 backend 容器在容器网络内上传快照（Qdrant 不对宿主机暴露端口）
    for i in $(seq 1 30); do
        docker compose run --rm --no-deps -T --entrypoint curl backend -fsS http://qdrant:6333/healthz >/dev/null 2>&1 && break
        sleep 2
    done
    for snap in "$BACKUP_DIR"/qdrant/*.snapshot; do
        name=$(basename "$snap" .snapshot)
        if docker compose run --rm --no-deps -T --entrypoint curl backend -fsS -X POST \
            "http://qdrant:6333/collections/$name/snapshots/upload?priority=snapshot&wait=true" \
            -F "snapshot=@-;filename=$name.snapshot" < "$snap" >/dev/null; then
            echo "  [OK]   $name"
        else
            echo "  [FAIL] $name 快照恢复失败（服务启动后可对该知识库文档执行重处理重建向量）"
            FAILED=$((FAILED+1))
        fi
    done
else
    echo "  备份中无 Qdrant 快照，跳过（启动后可对各文档执行重处理重建向量）"
fi

echo "启动全部服务..."
docker compose up -d
./deploy/status.sh
[ "$FAILED" -eq 0 ] && echo "恢复完成。建议执行检索测试验证。" || { echo "恢复完成，但有 $FAILED 个向量集合失败"; exit 2; }
