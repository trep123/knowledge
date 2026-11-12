from tests.conftest import ADMIN_PASSWORD, auth, login

USERS = "/api/v1/admin/users"


def create_user(client, admin_headers, username="alice", password="Alice12345", role="user"):
    resp = client.post(USERS, json={"username": username, "password": password, "role": role}, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def user_headers(client, username="alice", password="Alice12345"):
    resp = login(client, username, password)
    assert resp.status_code == 200, resp.text
    return auth(resp.json()["access_token"])


def test_admin_crud(client, admin_headers):
    u = create_user(client, admin_headers)
    assert u["role"] == "user" and u["status"] == "active"

    dup = client.post(USERS, json={"username": "ALICE", "password": "Alice12345"}, headers=admin_headers)
    assert dup.status_code == 409

    weak = client.post(USERS, json={"username": "bob", "password": "short"}, headers=admin_headers)
    assert weak.status_code == 422

    bad_role = client.post(USERS, json={"username": "bob", "password": "Bob123456", "role": "root"}, headers=admin_headers)
    assert bad_role.status_code == 400

    listing = client.get(USERS, params={"q": "ali"}, headers=admin_headers).json()
    assert listing["total"] == 1 and listing["items"][0]["username"] == "alice"

    upd = client.put(f"{USERS}/{u['id']}", json={"email": "a@example.com"}, headers=admin_headers)
    assert upd.status_code == 200 and upd.json()["email"] == "a@example.com"

    assert client.delete(f"{USERS}/{u['id']}", headers=admin_headers).status_code == 200
    assert client.get(f"{USERS}/{u['id']}", headers=admin_headers).status_code == 404


def test_non_admin_is_restricted(client, admin_headers):
    create_user(client, admin_headers)
    h = user_headers(client)
    assert client.get(USERS, headers=h).status_code == 403
    assert client.get("/api/v1/admin/api-keys", headers=h).status_code == 403
    # 普通用户角色没有 kb:admin，不能建库
    assert client.post("/api/v1/knowledge-bases", json={"name": "x"}, headers=h).status_code == 403
    # 没有任何授权时列表为空而不是报错
    resp = client.get("/api/v1/knowledge-bases", headers=h)
    assert resp.status_code == 200 and resp.json() == []


def test_kb_membership_grants_access(client, admin_headers):
    u = create_user(client, admin_headers)
    kb = client.post("/api/v1/knowledge-bases", json={"name": "运维"}, headers=admin_headers).json()
    h = user_headers(client)
    assert client.get(f"/api/v1/knowledge-bases/{kb['id']}", headers=h).status_code == 403

    resp = client.put(f"/api/v1/knowledge-bases/{kb['id']}/members", json={"user_ids": [u["id"]]}, headers=admin_headers)
    assert resp.status_code == 200 and [m["username"] for m in resp.json()] == ["alice"]

    assert client.get(f"/api/v1/knowledge-bases/{kb['id']}", headers=h).status_code == 200
    assert [k["id"] for k in client.get("/api/v1/knowledge-bases", headers=h).json()] == [kb["id"]]
    # 被授权用户不能管理授权
    assert client.get(f"/api/v1/knowledge-bases/{kb['id']}/members", headers=h).status_code == 403

    client.put(f"/api/v1/knowledge-bases/{kb['id']}/members", json={"user_ids": []}, headers=admin_headers)
    assert client.get(f"/api/v1/knowledge-bases/{kb['id']}", headers=h).status_code == 403


def test_change_password_revokes_old_token(client, admin_headers):
    create_user(client, admin_headers)
    h = user_headers(client)
    wrong = client.put("/api/v1/auth/me/password", json={"old_password": "nope", "new_password": "Newpass123"}, headers=h)
    assert wrong.status_code == 400
    ok = client.put("/api/v1/auth/me/password", json={"old_password": "Alice12345", "new_password": "Newpass123"}, headers=h)
    assert ok.status_code == 200
    assert client.get("/api/v1/auth/me", headers=h).status_code == 401
    assert client.get("/api/v1/auth/me", headers=auth(ok.json()["access_token"])).status_code == 200
    assert login(client, "alice", "Newpass123").status_code == 200


def test_reset_and_disable_revoke_sessions(client, admin_headers):
    u = create_user(client, admin_headers)
    h = user_headers(client)
    assert client.post(f"{USERS}/{u['id']}/reset-password", json={"new_password": "Reset12345"}, headers=admin_headers).status_code == 200
    assert client.get("/api/v1/auth/me", headers=h).status_code == 401

    h = user_headers(client, password="Reset12345")
    assert client.put(f"{USERS}/{u['id']}", json={"status": "disabled"}, headers=admin_headers).status_code == 200
    assert client.get("/api/v1/auth/me", headers=h).status_code == 401
    assert login(client, "alice", "Reset12345").status_code == 403

    assert client.put(f"{USERS}/{u['id']}", json={"status": "bogus"}, headers=admin_headers).status_code == 400


def test_admin_self_protection(client, admin_headers):
    me = client.get("/api/v1/auth/me", headers=admin_headers).json()
    assert client.put(f"{USERS}/{me['id']}", json={"status": "disabled"}, headers=admin_headers).status_code == 409
    assert client.put(f"{USERS}/{me['id']}", json={"role": "user"}, headers=admin_headers).status_code == 409
    assert client.delete(f"{USERS}/{me['id']}", headers=admin_headers).status_code == 409

    # 第二个管理员可以被降级，但最后一个管理员不行
    other = create_user(client, admin_headers, username="root2", password="Root123456", role="admin")
    assert client.put(f"{USERS}/{other['id']}", json={"role": "user"}, headers=admin_headers).status_code == 200


def test_delete_user_owning_kb_is_blocked(client, admin_headers):
    other = create_user(client, admin_headers, username="root2", password="Root123456", role="admin")
    h2 = user_headers(client, "root2", "Root123456")
    client.post("/api/v1/knowledge-bases", json={"name": "k"}, headers=h2)
    resp = client.delete(f"{USERS}/{other['id']}", headers=admin_headers)
    assert resp.status_code == 409 and "知识库" in resp.json()["detail"]


def test_login_lockout_and_unlock(client, admin_headers):
    u = create_user(client, admin_headers)
    for _ in range(5):
        assert login(client, "alice", "wrong-pass1").status_code == 401
    locked = login(client, "alice", "Alice12345")
    assert locked.status_code == 423
    assert client.post(f"{USERS}/{u['id']}/unlock", headers=admin_headers).status_code == 200
    assert login(client, "alice", "Alice12345").status_code == 200


def test_unknown_user_login(client):
    assert login(client, "ghost", ADMIN_PASSWORD).status_code == 401
