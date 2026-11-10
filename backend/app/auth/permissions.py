from fastapi import HTTPException

ALL_SCOPES = [
    "kb:read",
    "kb:search",
    "kb:chat",
    "kb:documents:read",
    "kb:documents:upload",
    "kb:documents:delete",
    "kb:admin",
]


def require_scope(principal, scope: str) -> None:
    """principal: UserPrincipal 拥有全部权限；ApiKeyPrincipal 检查 scopes。"""
    if principal.kind == "user":
        return
    if scope not in principal.scopes and "kb:admin" not in principal.scopes:
        raise HTTPException(403, f"API Key 缺少权限范围: {scope}")
