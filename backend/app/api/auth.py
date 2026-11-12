from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.jwt import create_access_token
from app.auth.security import hash_password, verify_password
from app.database import get_db
from app.dependencies import UserPrincipal, get_principal
from app.models import User
from app.schemas import LoginRequest, PasswordChange, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 15

# 用户不存在时也做一次 bcrypt 校验，避免通过响应时间枚举用户名
_DUMMY_HASH = hash_password("timing-equalizer-not-a-real-password")


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def issue_token(user: User) -> TokenResponse:
    token = create_access_token(user.id, user.username, user.role, user.token_version or 0)
    return TokenResponse(access_token=token, username=user.username, role=user.role)


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    user = db.query(User).filter(User.username == req.username).first()
    if not user:
        verify_password(req.password, _DUMMY_HASH)
        raise HTTPException(401, "用户名或密码错误")

    locked_until = _aware(user.locked_until)
    if locked_until and locked_until > now:
        minutes = max(1, int((locked_until - now).total_seconds() // 60) + 1)
        raise HTTPException(423, f"登录失败次数过多，账号已锁定，请 {minutes} 分钟后再试或联系管理员解锁")

    if not verify_password(req.password, user.password_hash):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
            user.failed_login_count = 0
        db.commit()
        raise HTTPException(401, "用户名或密码错误")

    if user.status != "active":
        raise HTTPException(403, "账号已禁用")

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    db.commit()
    return issue_token(user)


def _require_user(principal) -> None:
    if principal.kind != "user":
        raise HTTPException(400, "该接口仅支持 Web 用户 JWT 认证")


@router.get("/me", response_model=UserOut)
def me(principal: UserPrincipal = Depends(get_principal), db: Session = Depends(get_db)):
    _require_user(principal)
    return db.get(User, principal.user_id)


@router.put("/me/password", response_model=TokenResponse)
def change_my_password(
    req: PasswordChange, principal=Depends(get_principal), db: Session = Depends(get_db)
):
    """修改自己的密码。成功后旧 Token 全部失效，返回新 Token。"""
    _require_user(principal)
    user = db.get(User, principal.user_id)
    if not verify_password(req.old_password, user.password_hash):
        raise HTTPException(400, "原密码错误")
    if req.old_password == req.new_password:
        raise HTTPException(400, "新密码不能与原密码相同")
    user.password_hash = hash_password(req.new_password)
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    return issue_token(user)
