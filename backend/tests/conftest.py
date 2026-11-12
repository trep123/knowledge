"""测试使用 SQLite 与内存替身，不依赖 PostgreSQL / Qdrant / Redis / 模型服务。"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

_TMP = tempfile.mkdtemp(prefix="kb-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP}/test.db")
os.environ.setdefault("DATA_DIR", _TMP)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests-only")
os.environ.setdefault("APP_SECRET_KEY", "test-app-secret-for-unit-tests-only")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402,F401
from app.auth.security import hash_password  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import User  # noqa: E402
from app.vector import collection_manager  # noqa: E402

ADMIN_PASSWORD = "Admin12345"


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    # 向量库操作替换为空实现
    monkeypatch.setattr(collection_manager, "create_collection", lambda *a, **k: "x")
    monkeypatch.setattr(collection_manager, "delete_collection", lambda *a, **k: None)
    monkeypatch.setattr(collection_manager, "delete_document_points", lambda *a, **k: None)
    db = SessionLocal()
    db.add(User(username="admin", password_hash=hash_password(ADMIN_PASSWORD), role="admin", status="active"))
    db.commit()
    db.close()
    yield


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


def login(client, username, password):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(client):
    resp = login(client, "admin", ADMIN_PASSWORD)
    assert resp.status_code == 200, resp.text
    return auth(resp.json()["access_token"])
