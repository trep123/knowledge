"""数据库结构初始化：优先执行 Alembic 迁移；无迁移脚本时直接建表。"""
from pathlib import Path


def main() -> None:
    versions = Path(__file__).resolve().parent.parent / "migrations" / "versions"
    has_migrations = versions.exists() and any(versions.glob("*.py"))
    if has_migrations:
        from alembic import command
        from alembic.config import Config

        cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
        command.upgrade(cfg, "head")
        print("alembic upgrade head: done")
    else:
        from app import models  # noqa: F401
        from app.database import Base, engine

        Base.metadata.create_all(engine)
        print("no migrations found, create_all: done")


if __name__ == "__main__":
    main()
