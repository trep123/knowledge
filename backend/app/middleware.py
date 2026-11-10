"""API 调用日志中间件：仅记录外部 API Key 调用，不保存密钥明文。"""
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.database import SessionLocal
from app.models import ApiUsageLog


class ApiUsageLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        request.state.api_key_id = None
        response = await call_next(request)
        api_key_id = getattr(request.state, "api_key_id", None)
        if api_key_id is not None:
            duration_ms = int((time.perf_counter() - start) * 1000)
            db = SessionLocal()
            try:
                db.add(
                    ApiUsageLog(
                        api_key_id=api_key_id,
                        method=request.method,
                        path=str(request.url.path)[:500],
                        status_code=response.status_code,
                        duration_ms=duration_ms,
                        request_ip=request.client.host if request.client else None,
                        model=getattr(response, "kb_model", None),
                        retrieval_count=getattr(response, "kb_retrieval_count", None),
                        prompt_tokens=getattr(response, "kb_prompt_tokens", None),
                        completion_tokens=getattr(response, "kb_completion_tokens", None),
                    )
                )
                db.commit()
            except Exception:
                db.rollback()
            finally:
                db.close()
        return response
