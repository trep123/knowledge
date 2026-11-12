"""用户管理（仅管理员 JWT）：增删改查、重置密码、解锁。"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.auth.permissions import VALID_ROLES, VALID_USER_STATUSES
from app.auth.security import hash_password
from app.database import get_db
from app.dependencies import get_principal
from app.models import ApiKey, KnowledgeBase, KnowledgeBaseMember, User
from app.schemas import PasswordReset, UserCreate, UserListOut, UserOut, UserUpdate

router = APIRouter(prefix="/admin/users", tags=["admin"])


def _require_admin(principal) -> None:
    if principal.kind != "user" or not principal.is_admin:
        raise HTTPException(403, "仅管理员可管理用户")


def _get_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    return user


def _active_admin_count(db: Session) -> int:
    return db.query(func.count(User.id)).filter(User.role == "admin", User.status == "active").scalar()


def _ensure_not_last_admin(db: Session, user: User) -> None:
    if user.role == "admin" and user.status == "active" and _active_admin_count(db) <= 1:
        raise HTTPException(409, "不能移除最后一个可用的管理员")


def _bump_token(user: User) -> None:
    user.token_version = (user.token_version or 0) + 1


@router.get("", response_model=UserListOut)
def list_users(
    principal=Depends(get_principal),
    db: Session = Depends(get_db),
    q: str | None = None,
    role: str | None = None,
    status: str | None = None,
    skip: int = 0,
    limit: int = 50,
):
    _require_admin(principal)
    query = db.query(User)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(User.username.ilike(like), User.email.ilike(like)))
    if role:
        query = query.filter(User.role == role)
    if status:
        query = query.filter(User.status == status)
    total = query.count()
    items = query.order_by(User.created_at.desc()).offset(max(skip, 0)).limit(min(max(limit, 1), 200)).all()
    return UserListOut(total=total, items=[UserOut.model_validate(u) for u in items])


@router.post("", response_model=UserOut, status_code=201)
def create_user(req: UserCreate, principal=Depends(get_principal), db: Session = Depends(get_db)):
    _require_admin(principal)
    if req.role not in VALID_ROLES:
        raise HTTPException(400, f"无效角色: {req.role}，可选: {list(VALID_ROLES)}")
    if db.query(User).filter(func.lower(User.username) == req.username.lower()).first():
        raise HTTPException(409, "用户名已存在")
    user = User(
        username=req.username,
        password_hash=hash_password(req.password),
        email=req.email,
        role=req.role,
        status="active",
        token_version=0,
        failed_login_count=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: uuid.UUID, principal=Depends(get_principal), db: Session = Depends(get_db)):
    _require_admin(principal)
    return _get_user(db, user_id)


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID, req: UserUpdate, principal=Depends(get_principal), db: Session = Depends(get_db)
):
    _require_admin(principal)
    user = _get_user(db, user_id)
    data = req.model_dump(exclude_unset=True)

    if "role" in data and data["role"] is not None and data["role"] != user.role:
        if data["role"] not in VALID_ROLES:
            raise HTTPException(400, f"无效角色: {data['role']}，可选: {list(VALID_ROLES)}")
        if user.id == principal.user_id:
            raise HTTPException(409, "不能修改自己的角色")
        _ensure_not_last_admin(db, user)
        user.role = data["role"]
        _bump_token(user)

    if "status" in data and data["status"] is not None and data["status"] != user.status:
        if data["status"] not in VALID_USER_STATUSES:
            raise HTTPException(400, f"无效状态: {data['status']}，可选: {list(VALID_USER_STATUSES)}")
        if user.id == principal.user_id:
            raise HTTPException(409, "不能禁用自己")
        if data["status"] == "disabled":
            _ensure_not_last_admin(db, user)
        else:
            user.failed_login_count = 0
            user.locked_until = None
        user.status = data["status"]
        _bump_token(user)

    if "email" in data:
        user.email = data["email"]

    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: uuid.UUID, req: PasswordReset, principal=Depends(get_principal), db: Session = Depends(get_db)
):
    """管理员重置密码：同时解锁账号，并使该用户已登录的会话全部失效。"""
    _require_admin(principal)
    user = _get_user(db, user_id)
    user.password_hash = hash_password(req.new_password)
    user.failed_login_count = 0
    user.locked_until = None
    _bump_token(user)
    db.commit()
    return {"success": True}


@router.post("/{user_id}/unlock")
def unlock_user(user_id: uuid.UUID, principal=Depends(get_principal), db: Session = Depends(get_db)):
    _require_admin(principal)
    user = _get_user(db, user_id)
    user.failed_login_count = 0
    user.locked_until = None
    db.commit()
    return {"success": True}


@router.delete("/{user_id}")
def delete_user(user_id: uuid.UUID, principal=Depends(get_principal), db: Session = Depends(get_db)):
    _require_admin(principal)
    user = _get_user(db, user_id)
    if user.id == principal.user_id:
        raise HTTPException(409, "不能删除自己")
    _ensure_not_last_admin(db, user)
    owned_kbs = db.query(func.count(KnowledgeBase.id)).filter(KnowledgeBase.owner_id == user.id).scalar()
    owned_keys = db.query(func.count(ApiKey.id)).filter(ApiKey.user_id == user.id).scalar()
    if owned_kbs or owned_keys:
        raise HTTPException(
            409,
            f"该用户仍拥有 {owned_kbs} 个知识库、{owned_keys} 个 API Key，请先转移或删除，或改为禁用",
        )
    db.query(KnowledgeBaseMember).filter(KnowledgeBaseMember.user_id == user.id).delete()
    db.delete(user)
    db.commit()
    return {"success": True}
