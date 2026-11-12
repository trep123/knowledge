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

# Web 用户角色 -> 权限范围。seed 会把同一份定义写入 roles 表。
ROLE_SCOPES: dict[str, list[str]] = {
    "admin": list(ALL_SCOPES),
    "user": ["kb:read", "kb:search", "kb:chat", "kb:documents:read", "kb:documents:upload"],
}
VALID_ROLES = tuple(ROLE_SCOPES)
VALID_USER_STATUSES = ("active", "disabled")


def scopes_for_role(role: str) -> list[str]:
    return ROLE_SCOPES.get(role, [])


def require_scope(principal, scope: str) -> None:
    """Web 用户按角色检查，API Key 按创建时勾选的 scopes 检查；kb:admin 视为超集。"""
    scopes = principal.scopes
    if scope not in scopes and "kb:admin" not in scopes:
        who = "当前用户角色" if principal.kind == "user" else "API Key"
        raise HTTPException(403, f"{who}缺少权限范围: {scope}")
