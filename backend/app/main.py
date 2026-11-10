import time

import httpx
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, chat, documents, knowledge_bases, retrieval, tasks
from app.api.admin import api_keys, api_usage
from app.api.external import openai_compat
from app.config import settings
from app.dependencies import get_principal
from app.middleware import ApiUsageLogMiddleware

app = FastAPI(
    title="Local Knowledge Base Platform",
    version="1.0.0",
    description="本地私有化知识库平台：REST API + OpenAI Compatible API",
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
        checks["postgres"] = f"error: {exc}"

    await check("qdrant", f"{settings.qdrant_url}/healthz")
    await check("embedding", f"{settings.embedding_url}/health")
    await check("reranker", f"{settings.reranker_url}/health")
    await check("llm", f"{settings.llm_base_url}/models")

    from app.dependencies import get_redis

    try:
        get_redis().ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

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
def stats(principal=Depends(get_principal)):
    """Dashboard 统计。"""
    from app.database import SessionLocal
    from app.models import ApiUsageLog, Document, DocumentChunk, KnowledgeBase

    db = SessionLocal()
    try:
        return {
            "knowledge_bases": db.query(KnowledgeBase).count(),
            "documents": db.query(Document).count(),
            "documents_ready": db.query(Document).filter(Document.status == "ready").count(),
            "documents_failed": db.query(Document).filter(Document.status == "failed").count(),
            "chunks": db.query(DocumentChunk).count(),
            "api_calls_total": db.query(ApiUsageLog).count(),
        }
    finally:
        db.close()
