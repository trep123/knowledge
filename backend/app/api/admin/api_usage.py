import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_principal
from app.models import ApiUsageLog

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(principal) -> None:
    if principal.kind != "user" or not principal.is_admin:
        raise HTTPException(403, "仅管理员可访问")


@router.get("/api-usage")
def api_usage(
    principal=Depends(get_principal),
    db: Session = Depends(get_db),
    api_key_id: uuid.UUID | None = None,
    days: int = 7,
):
    _require_admin(principal)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    query = db.query(
        func.count(ApiUsageLog.id).label("total"),
        func.avg(ApiUsageLog.duration_ms).label("avg_duration_ms"),
        func.sum(case((ApiUsageLog.status_code >= 400, 1), else_=0)).label("errors"),
    ).filter(ApiUsageLog.created_at >= since)
    if api_key_id:
        query = query.filter(ApiUsageLog.api_key_id == api_key_id)
    row = query.one()
    return {
        "total_requests": row.total or 0,
        "avg_duration_ms": round(float(row.avg_duration_ms or 0), 1),
        "error_count": int(row.errors or 0),
        "error_rate": round((row.errors or 0) / row.total, 4) if row.total else 0,
        "days": days,
    }


@router.get("/api-usage/daily")
def api_usage_daily(principal=Depends(get_principal), db: Session = Depends(get_db), days: int = 30):
    _require_admin(principal)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(
            func.date_trunc("day", ApiUsageLog.created_at).label("day"),
            func.count(ApiUsageLog.id).label("count"),
            func.sum(case((ApiUsageLog.status_code >= 400, 1), else_=0)).label("errors"),
        )
        .filter(ApiUsageLog.created_at >= since)
        .group_by("day")
        .order_by("day")
        .all()
    )
    return [
        {"day": r.day.strftime("%Y-%m-%d"), "count": r.count, "errors": int(r.errors or 0)}
        for r in rows
    ]


@router.get("/api-logs")
def api_logs(principal=Depends(get_principal), db: Session = Depends(get_db), limit: int = 100):
    _require_admin(principal)
    rows = (
        db.query(ApiUsageLog)
        .order_by(ApiUsageLog.created_at.desc())
        .limit(min(limit, 500))
        .all()
    )
    return [
        {
            "id": str(r.id),
            "api_key_id": str(r.api_key_id) if r.api_key_id else None,
            "method": r.method,
            "path": r.path,
            "status_code": r.status_code,
            "duration_ms": r.duration_ms,
            "request_ip": r.request_ip,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
