from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.jwt import create_access_token
from app.auth.security import verify_password
from app.database import get_db
from app.dependencies import UserPrincipal, get_principal
from app.models import User
from app.schemas import LoginRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    if user.status != "active":
        raise HTTPException(403, "账号已禁用")
    token = create_access_token(user.id, user.username, user.role)
    return TokenResponse(access_token=token, username=user.username, role=user.role)


@router.get("/me", response_model=UserOut)
def me(principal: UserPrincipal = Depends(get_principal), db: Session = Depends(get_db)):
    if principal.kind != "user":
        raise HTTPException(400, "该接口仅支持 Web 用户 JWT 认证")
    return db.get(User, principal.user_id)
