#!/bin/sh
set -e

# 初始化数据库结构：有 Alembic 迁移则执行迁移，否则建表
python -m app.db_init

# 初始化角色与管理员账号
python -m app.seed

# 后端只在容器网络内被 nginx 访问，信任其 X-Forwarded-For 以记录真实客户端 IP
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2 \
    --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-*}"
