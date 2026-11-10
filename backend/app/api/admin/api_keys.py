import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.jwt import generate_api_key, hash_api_key
from app.auth.permissions import ALL_SCOPES
from app.config import settings
from app.database import get_db
from app.dependencies import get_principal
from app.models import ApiKey, ApiKeyKnowledgeBase, KnowledgeBase
from app.schemas import ApiKeyCreate, ApiKeyOut, ApiKeyUpdate

router = APIRouter(prefix="/admin/api-keys", tags=["admin"])


def _require_admin(principal) -> None:
    if principal.kind != "user" or not principal.is_admin:
        raise HTTPException(403, "仅管理员可管理 API Key")


def _to_out(key: ApiKey, db: Session) -> dict:
    kb_ids = [str(b.knowledge_base_id) for b in key.knowledge_bases]
    data = ApiKeyOut.model_validate(
        {
            "id": key.id,
            "name": key.name,
            "key_prefix": key.key_prefix,
            "scopes": key.scopes,
            "knowledge_base_ids": kb_ids,
            "default_kb_ids": key.default_kb_ids,
            "rate_limit": key.rate_limit,
            "daily_limit": key.daily_limit,
            "status": key.status,
            "last_used_at": key.last_used_at,
            "expires_at": key.expires_at,
            "created_at": key.created_at,
        }
    ).model_dump()
    return data


def _validate_scopes(scopes: list[str]) -> None:
    invalid = [s for s in scopes if s not in ALL_SCOPES]
    if invalid:
        raise HTTPException(400, f"无效的权限范围: {invalid}，可选: {ALL_SCOPES}")


def _bind_kbs(db: Session, key: ApiKey, kb_ids: list[uuid.UUID]) -> None:
    db.query(ApiKeyKnowledgeBase).filter(ApiKeyKnowledgeBase.api_key_id == key.id).delete()
    for kb_id in kb_ids:
        if not db.get(KnowledgeBase, kb_id):
            raise HTTPException(400, f"知识库不存在: {kb_id}")
        db.add(ApiKeyKnowledgeBase(api_key_id=key.id, knowledge_base_id=kb_id))


@router.get("")
def list_api_keys(principal=Depends(get_principal), db: Session = Depends(get_db)):
    _require_admin(principal)
    keys = db.query(ApiKey).order_by(ApiKey.created_at.desc()).all()
    return [_to_out(k, db) for k in keys]


@router.post("", status_code=201)
def create_api_key(req: ApiKeyCreate, principal=Depends(get_principal), db: Session = Depends(get_db)):
    _require_admin(principal)
    _validate_scopes(req.scopes)
    plain_key = generate_api_key()
    key = ApiKey(
        name=req.name,
        key_prefix=plain_key[:10],
        key_hash=hash_api_key(plain_key),
        user_id=principal.user_id,
        scopes=req.scopes,
        rate_limit=req.rate_limit or settings.api_default_rate_limit,
        daily_limit=req.daily_limit,
        default_kb_ids=[str(k) for k in req.default_kb_ids],
        expires_at=datetime.now(timezone.utc) + timedelta(days=req.expires_in_days)
        if req.expires_in_days
        else None,
    )
    db.add(key)
    db.flush()
    _bind_kbs(db, key, req.knowledge_base_ids)
    db.commit()
    db.refresh(key)
    # 明文密钥只在创建时返回一次，数据库仅存哈希
    return _to_out(key, db) | {"api_key": plain_key}


@router.get("/{key_id}")
def get_api_key(key_id: uuid.UUID, principal=Depends(get_principal), db: Session = Depends(get_db)):
    _require_admin(principal)
    key = db.get(ApiKey, key_id)
    if not key:
        raise HTTPException(404, "API Key 不存在")
    return _to_out(key, db)


@router.put("/{key_id}")
def update_api_key(
    key_id: uuid.UUID, req: ApiKeyUpdate, principal=Depends(get_principal), db: Session = Depends(get_db)
):
    _require_admin(principal)
    key = db.get(ApiKey, key_id)
    if not key:
        raise HTTPException(404, "API Key 不存在")
    data = req.model_dump(exclude_unset=True)
    if "scopes" in data:
        _validate_scopes(data["scopes"])
    if "knowledge_base_ids" in data:
        _bind_kbs(db, key, data.pop("knowledge_base_ids"))
    if "default_kb_ids" in data and data["default_kb_ids"] is not None:
        key.default_kb_ids = [str(k) for k in data.pop("default_kb_ids")]
    if "expires_in_days" in data:
        days = data.pop("expires_in_days")
        key.expires_at = datetime.now(timezone.utc) + timedelta(days=days) if days else None
    for field, value in data.items():
        if value is not None:
            setattr(key, field, value)
    db.commit()
    db.refresh(key)
    return _to_out(key, db)


@router.post("/{key_id}/rotate")
def rotate_api_key(key_id: uuid.UUID, principal=Depends(get_principal), db: Session = Depends(get_db)):
    """轮换密钥：生成新明文，旧密钥立即失效。"""
    _require_admin(principal)
    key = db.get(ApiKey, key_id)
    if not key:
        raise HTTPException(404, "API Key 不存在")
    plain_key = generate_api_key()
    key.key_prefix = plain_key[:10]
    key.key_hash = hash_api_key(plain_key)
    db.commit()
    return {"success": True, "api_key": plain_key}


@router.delete("/{key_id}")
def delete_api_key(key_id: uuid.UUID, principal=Depends(get_principal), db: Session = Depends(get_db)):
    _require_admin(principal)
    key = db.get(ApiKey, key_id)
    if not key:
        raise HTTPException(404, "API Key 不存在")
    db.delete(key)
    db.commit()
    return {"success": True}
