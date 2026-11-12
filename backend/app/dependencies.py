import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import redis as redis_lib
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from sqlalchemy import or_, select

from app.auth.jwt import decode_access_token, hash_api_key
from app.auth.permissions import scopes_for_role
from app.config import settings
from app.database import get_db
from app.models import ApiKey, ApiKeyKnowledgeBase, KnowledgeBase, KnowledgeBaseMember, User

bearer_scheme = HTTPBearer(auto_error=False)

_redis: redis_lib.Redis | None = None


def get_redis() -> redis_lib.Redis:
    global _redis
    if _redis is None:
        _redis = redis_lib.from_url(settings.redis_url, decode_responses=True)
    return _redis


@dataclass
class UserPrincipal:
    kind: str = "user"
    user_id: uuid.UUID = None
    username: str = ""
    role: str = "user"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def scopes(self) -> list[str]:
        return scopes_for_role(self.role)


@dataclass
class ApiKeyPrincipal:
    kind: str = "api_key"
    api_key: ApiKey = None
    user_id: uuid.UUID = None
    scopes: list[str] = field(default_factory=list)
    allowed_kb_ids: list[uuid.UUID] = field(default_factory=list)

    @property
    def is_admin(self) -> bool:
        return "kb:admin" in self.scopes


def _aware(dt: datetime) -> datetime:
    """部分数据库驱动返回不带时区的时间，统一按 UTC 处理。"""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _user_kb_filter(user_id: uuid.UUID):
    """非管理员可访问：自己拥有的 + 被授权的知识库。"""
    granted = KnowledgeBaseMember.__table__.c
    return or_(
        KnowledgeBase.owner_id == user_id,
        KnowledgeBase.id.in_(select(granted.knowledge_base_id).where(granted.user_id == user_id)),
    )


def _check_rate_limit(key_id: uuid.UUID, rate_limit: int, daily_limit: int) -> None:
    r = get_redis()
    now = time.time()
    minute_bucket = f"rl:{key_id}:{int(now // 60)}"
    day_bucket = f"dl:{key_id}:{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    pipe = r.pipeline()
    pipe.incr(minute_bucket)
    pipe.expire(minute_bucket, 120)
    pipe.incr(day_bucket)
    pipe.expire(day_bucket, 86400 * 2)
    minute_count, _, day_count, _ = pipe.execute()
    if minute_count > rate_limit:
        raise HTTPException(429, "超出每分钟请求限制")
    if day_count > daily_limit:
        raise HTTPException(429, "超出每日调用限制")


def get_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    """统一认证入口：JWT（Web 用户）或 API Key（外部程序）。"""
    if credentials is None:
        raise HTTPException(401, "缺少 Authorization: Bearer 凭证")
    token = credentials.credentials

    payload = decode_access_token(token)
    if payload and payload.get("type") == "access":
        try:
            user = db.get(User, uuid.UUID(payload["sub"]))
        except (KeyError, ValueError):
            user = None
        if not user or user.status != "active":
            raise HTTPException(401, "用户不存在或已禁用")
        if payload.get("ver", 0) != (user.token_version or 0):
            raise HTTPException(401, "登录已失效，请重新登录")
        # 角色以数据库为准，不信任 Token 中的 role
        return UserPrincipal(user_id=user.id, username=user.username, role=user.role)

    key_hash = hash_api_key(token)
    api_key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()
    if not api_key:
        raise HTTPException(401, "无效的凭证")
    if api_key.status != "active":
        raise HTTPException(403, "API Key 已禁用")
    if api_key.expires_at and _aware(api_key.expires_at) < datetime.now(timezone.utc):
        raise HTTPException(403, "API Key 已过期")
    owner = db.get(User, api_key.user_id)
    if not owner or owner.status != "active":
        raise HTTPException(403, "API Key 所属用户已禁用")

    _check_rate_limit(api_key.id, api_key.rate_limit, api_key.daily_limit)

    api_key.last_used_at = datetime.now(timezone.utc)
    db.commit()

    kb_ids = [
        row[0]
        for row in db.query(ApiKeyKnowledgeBase.knowledge_base_id)
        .filter(ApiKeyKnowledgeBase.api_key_id == api_key.id)
        .all()
    ]
    principal = ApiKeyPrincipal(
        api_key=api_key,
        user_id=api_key.user_id,
        scopes=list(api_key.scopes or []),
        allowed_kb_ids=kb_ids,
    )
    request.state.api_key_id = api_key.id
    return principal


def authorized_kb_id_set(principal, db: Session) -> set[uuid.UUID]:
    """返回主体当前可访问的全部 active 知识库 ID 集合（批量操作用于逐项鉴权）。

    与 get_authorized_knowledge_bases 不同：不抛异常，无授权时返回空集合。
    """
    query = db.query(KnowledgeBase.id).filter(KnowledgeBase.status == "active")
    if principal.kind == "api_key":
        if not principal.allowed_kb_ids:
            return set()
        query = query.filter(KnowledgeBase.id.in_(principal.allowed_kb_ids))
    elif not principal.is_admin:
        query = query.filter(_user_kb_filter(principal.user_id))
    return {row[0] for row in query.all()}


def get_authorized_knowledge_bases(
    principal, requested_kb_ids: list[uuid.UUID] | None, db: Session
) -> list[KnowledgeBase]:
    """服务端权限过滤：返回本次请求实际可访问的知识库列表。

    不信任客户端传入的知识库 ID，必须与主体的授权范围求交集。
    """
    query = db.query(KnowledgeBase).filter(KnowledgeBase.status == "active")
    if principal.kind == "api_key":
        if not principal.allowed_kb_ids:
            raise HTTPException(403, "该 API Key 未绑定任何知识库")
        query = query.filter(KnowledgeBase.id.in_(principal.allowed_kb_ids))
    else:
        if not principal.is_admin:
            query = query.filter(_user_kb_filter(principal.user_id))

    if requested_kb_ids:
        query = query.filter(KnowledgeBase.id.in_(requested_kb_ids))
    kbs = query.all()

    if requested_kb_ids and len(kbs) != len(set(requested_kb_ids)):
        found = {kb.id for kb in kbs}
        denied = [str(k) for k in requested_kb_ids if k not in found]
        raise HTTPException(403, f"无权访问知识库: {denied}")
    if not kbs:
        raise HTTPException(400, "没有可用的知识库")
    return kbs
