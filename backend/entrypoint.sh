#!/bin/sh
set -e

# 初始化数据库结构：有 Alembic 迁移则执行迁移，否则建表
python -m app.db_init

# 初始化角色与管理员账号
python -m app.seed

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
