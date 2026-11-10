"""初始化角色与管理员账号（幂等）。"""
from app.auth.security import hash_password
from app.config import settings
from app.database import SessionLocal
from app.models import Role, User


def main() -> None:
    db = SessionLocal()
    try:
        for name, perms in {
            "admin": ["*"],
            "user": ["kb:read", "kb:search", "kb:chat", "kb:documents:read", "kb:documents:upload"],
        }.items():
            if not db.query(Role).filter(Role.name == name).first():
                db.add(Role(name=name, permissions={"scopes": perms}))

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
