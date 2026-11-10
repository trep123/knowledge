#!/usr/bin/env bash
# 一致性备份：PostgreSQL dump + Qdrant snapshot + 文档/模型/配置
set -e
cd "$(dirname "$0")/.."
source .env 2>/dev/null || true

TS=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="data/backups/$TS"
mkdir -p "$BACKUP_DIR"

echo "1/4 备份 PostgreSQL..."
docker exec kb-postgres pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" | gzip > "$BACKUP_DIR/postgres.sql.gz"

echo "2/4 备份 Qdrant (snapshot)..."
mkdir -p "$BACKUP_DIR/qdrant"
COLLECTIONS=$(curl -s http://127.0.0.1:$(grep -E '^GATEWAY_PORT=' .env | cut -d= -f2 || echo 8080)/api/health >/dev/null 2>&1; docker exec kb-qdrant sh -c 'wget -qO- http://localhost:6333/collections' 2>/dev/null | python3 -c "import json,sys; print(' '.join(c['name'] for c in json.load(sys.stdin)['result']['collections']))" 2>/dev/null || true)
for c in $COLLECTIONS; do
    docker exec kb-qdrant sh -c "wget -qO- --post-data='' http://localhost:6333/collections/$c/snapshots" >/dev/null 2>&1 || true
    SNAP=$(docker exec kb-qdrant sh -c "ls -t /qdrant/storage/snapshots/$c 2>/dev/null | head -1")
    if [ -n "$SNAP" ]; then
        cp "data/qdrant/snapshots/$c/$SNAP" "$BACKUP_DIR/qdrant/${c}.snapshot" 2>/dev/null || true
    fi
done

echo "3/4 备份文档与配置..."
tar czf "$BACKUP_DIR/files.tar.gz" data/documents data/extracted configs .env 2>/dev/null || true

echo "4/4 记录清单..."
sha256sum "$BACKUP_DIR"/* > "$BACKUP_DIR/SHA256SUMS" 2>/dev/null || true
du -sh "$BACKUP_DIR"
echo "备份完成: $BACKUP_DIR"
echo "注意: 模型文件体积大且不可变，未纳入备份；可用 offline/manifests/models.sha256 校验后重新下载。"
