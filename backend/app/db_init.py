"""数据库结构初始化：优先执行 Alembic 迁移；无迁移脚本时直接建表。

create_all 只会创建缺失的表，不会给已有表加列。为兼容早期版本已部署的库，
这里对新增列做一次幂等补齐（ADD COLUMN），新表由 create_all 自动创建。
"""
from pathlib import Path

from sqlalchemy import inspect, text

# 表名 -> [(列名, DDL 类型片段)]
_ADDED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "users": [
        ("token_version", "INTEGER NOT NULL DEFAULT 0"),
        ("failed_login_count", "INTEGER NOT NULL DEFAULT 0"),
        ("locked_until", "TIMESTAMP WITH TIME ZONE"),
        ("last_login_at", "TIMESTAMP WITH TIME ZONE"),
    ],
}


def ensure_columns(engine) -> list[str]:
    added = []
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns:
                if name not in present:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                    added.append(f"{table}.{name}")
    return added


def main() -> None:
    from app import models  # noqa: F401
    from app.database import Base, engine

    versions = Path(__file__).resolve().parent.parent / "migrations" / "versions"
    has_migrations = versions.exists() and any(versions.glob("*.py"))
    if has_migrations:
        from alembic import command
        from alembic.config import Config

        cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
        command.upgrade(cfg, "head")
        print("alembic upgrade head: done")
    else:
        Base.metadata.create_all(engine)
        added = ensure_columns(engine)
        print(f"no migrations found, create_all: done; added columns: {added or 'none'}")


if __name__ == "__main__":
    main()
