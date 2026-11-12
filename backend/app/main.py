import time

import httpx
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, chat, documents, knowledge_bases, retrieval, tasks
from app.api.admin import api_keys, api_usage, users
from app.api.external import openai_compat
from app.config import settings
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import authorized_kb_id_set, get_principal
from app.middleware import ApiUsageLogMiddleware

if settings.app_env == "production" and (weak := settings.insecure_settings()):
    raise RuntimeError(
        f"生产环境拒绝启动：{', '.join(weak)} 仍为默认值或过短（至少 16 位），请在 .env 中设置随机值"
        "（openssl rand -hex 32）"
    )

app = FastAPI(
    title="Local Knowledge Base Platform",
    version="1.0.0",
    description="本地私有化知识库平台：REST API + OpenAI Compatible API",
    docs_url="/docs" if settings.api_docs_enabled else None,
    redoc_url="/redoc" if settings.api_docs_enabled else None,
    openapi_url="/openapi.json" if settings.api_docs_enabled else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ApiUsageLogMiddleware)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(knowledge_bases.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(retrieval.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(api_keys.router, prefix="/api/v1")
app.include_router(api_usage.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(openai_compat.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "time": time.time()}


@app.get("/api/health/dependencies")
async def health_dependencies():
    checks = {}

    async def check(name, url, method="GET"):
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.request(method, url)
                checks[name] = "ok" if resp.status_code < 500 else f"http {resp.status_code}"
        except Exception as exc:
            checks[name] = f"error: {type(exc).__name__}"

    from app.database import engine
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {type(exc).__name__}"

    await check("qdrant", f"{settings.qdrant_url}/healthz")
    await check("embedding", f"{settings.embedding_url}/health")
    await check("reranker", f"{settings.reranker_url}/health")
    await check("llm", f"{settings.llm_base_url}/models")

    from app.dependencies import get_redis

    try:
        get_redis().ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {type(exc).__name__}"

    all_ok = all(v == "ok" for v in checks.values())
    return {"status": "ok" if all_ok else "degraded", "checks": checks}


@app.get("/api/health/ready")
async def health_ready():
    from sqlalchemy import text

    from app.database import engine

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content={"status": "not ready"})


@app.get("/api/v1/stats")
def stats(principal=Depends(get_principal), db: Session = Depends(get_db)):
    """Dashboard 统计：只统计当前主体可访问的知识库；调用总数仅管理员可见。"""
    from app.models import ApiUsageLog, Document, DocumentChunk

    allowed = authorized_kb_id_set(principal, db)
    docs = db.query(Document).filter(Document.knowledge_base_id.in_(allowed))
    result = {
        "knowledge_bases": len(allowed),
        "documents": docs.count(),
        "documents_ready": docs.filter(Document.status == "ready").count(),
        "documents_failed": docs.filter(Document.status == "failed").count(),
        "chunks": db.query(DocumentChunk).filter(DocumentChunk.knowledge_base_id.in_(allowed)).count(),
    }
    if principal.kind == "user" and principal.is_admin:
        result["api_calls_total"] = db.query(ApiUsageLog).count()
    return result
