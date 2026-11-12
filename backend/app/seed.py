"""初始化角色与管理员账号（幂等）。"""
from app.auth.permissions import ROLE_SCOPES
from app.auth.security import hash_password
from app.config import settings
from app.database import SessionLocal
from app.models import Role, User


def main() -> None:
    db = SessionLocal()
    try:
        # roles 表与 app.auth.permissions.ROLE_SCOPES 保持一致（权限判断以代码为准）
        for name, perms in ROLE_SCOPES.items():
            role = db.query(Role).filter(Role.name == name).first()
            if not role:
                db.add(Role(name=name, permissions={"scopes": perms}))
            elif (role.permissions or {}).get("scopes") != perms:
                role.permissions = {"scopes": perms}

        if settings.admin_password:
            admin = db.query(User).filter(User.username == settings.admin_username).first()
            if not admin:
                db.add(
                    User(
                        username=settings.admin_username,
                        password_hash=hash_password(settings.admin_password),
                        role="admin",
                        status="active",
                    )
                )
                print(f"admin user '{settings.admin_username}' created")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
