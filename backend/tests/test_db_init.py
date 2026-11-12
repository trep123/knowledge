from sqlalchemy import create_engine, inspect, text

from app.db_init import ensure_columns


def test_ensure_columns_upgrades_old_users_table(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/old.db")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id CHAR(32) PRIMARY KEY, username VARCHAR(100), password_hash TEXT)"))
        conn.execute(text("INSERT INTO users VALUES ('a', 'admin', 'x')"))
    added = ensure_columns(engine)
    assert set(added) == {"users.token_version", "users.failed_login_count", "users.locked_until", "users.last_login_at"}
    cols = {c["name"] for c in inspect(engine).get_columns("users")}
    assert {"token_version", "locked_until"} <= cols
    with engine.connect() as conn:
        assert conn.execute(text("SELECT token_version FROM users")).scalar() == 0
    assert ensure_columns(engine) == []  # 幂等
