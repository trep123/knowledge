#!/usr/bin/env bash
# 一致性备份：PostgreSQL dump + Qdrant snapshot + 文档/配置
#
# Qdrant 未对宿主机暴露端口，且官方镜像不含 curl/wget，
# 因此通过 kb-backend 容器（已安装 curl）在容器网络内访问 http://qdrant:6333。
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a

TS=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="data/backups/$TS"
umask 077                       # 备份含数据库与密钥，仅属主可读
mkdir -p "$BACKUP_DIR/qdrant"

qdrant() { docker exec kb-backend curl -fsS "$@"; }

echo "1/4 备份 PostgreSQL..."
docker exec kb-postgres pg_dump -U "${POSTGRES_USER}" --clean --if-exists "${POSTGRES_DB}" | gzip > "$BACKUP_DIR/postgres.sql.gz"

echo "2/4 备份 Qdrant (snapshot)..."
COLLECTIONS=$(qdrant http://qdrant:6333/collections \
    | python3 -c "import json,sys; print(' '.join(c['name'] for c in json.load(sys.stdin)['result']['collections']))")
SNAP_OK=0; SNAP_FAIL=0
for c in $COLLECTIONS; do
    SNAP=$(qdrant -X POST "http://qdrant:6333/collections/$c/snapshots?wait=true" \
        | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['name'])") || { echo "  [FAIL] $c 创建快照失败"; SNAP_FAIL=$((SNAP_FAIL+1)); continue; }
    if qdrant "http://qdrant:6333/collections/$c/snapshots/$SNAP" > "$BACKUP_DIR/qdrant/${c}.snapshot"; then
        # 下载后删除服务端快照，避免占满 data/qdrant
        qdrant -X DELETE "http://qdrant:6333/collections/$c/snapshots/$SNAP" >/dev/null || true
        SNAP_OK=$((SNAP_OK+1))
    else
        echo "  [FAIL] $c 下载快照失败"; rm -f "$BACKUP_DIR/qdrant/${c}.snapshot"; SNAP_FAIL=$((SNAP_FAIL+1))
    fi
done
echo "  Qdrant 快照：成功 $SNAP_OK 个，失败 $SNAP_FAIL 个"

echo "3/4 备份文档与配置..."
tar czf "$BACKUP_DIR/files.tar.gz" data/documents data/extracted configs
cp .env "$BACKUP_DIR/env.backup"   # 单独存放，恢复时不会自动覆盖当前 .env

echo "4/4 记录清单..."
(cd "$BACKUP_DIR" && find . -type f ! -name SHA256SUMS -exec sha256sum {} + > SHA256SUMS)
du -sh "$BACKUP_DIR"
echo "备份完成: $BACKUP_DIR"
[ "$SNAP_FAIL" -eq 0 ] || { echo "警告: 有 $SNAP_FAIL 个向量集合未能备份，恢复后需对相关文档重处理"; exit 2; }
echo "注意: 模型文件体积大且不可变，未纳入备份；可用 offline/manifests/models.sha256 校验后重新下载。"
