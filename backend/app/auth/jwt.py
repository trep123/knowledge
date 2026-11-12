import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings


def create_access_token(user_id: uuid.UUID, username: str, role: str, token_version: int = 0) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "ver": token_version,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def generate_api_key() -> str:
    return "kb-" + secrets.token_urlsafe(32)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()
