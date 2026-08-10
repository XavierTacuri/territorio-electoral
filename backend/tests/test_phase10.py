from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.core.security import decode_access_token
from app.models.security import AuthSession, SecurityAuditEvent


def browser_login(client, username="admin", password="AdminPass123"):
    return client.post("/api/v1/auth/browser/login", json={"identifier": username, "password": password})


def test_browser_login_sets_secure_cookie_contract(client, admin):
    response = browser_login(client)
    assert response.status_code == 200
    assert response.json()["user"]["id"] == str(admin.id)
    assert "access_token" in response.json()
    cookies = response.headers.get_list("set-cookie")
    assert any("te_refresh=" in value and "HttpOnly" in value and "SameSite=lax" in value for value in cookies)
    assert any("te_csrf=" in value and "HttpOnly" not in value for value in cookies)
    payload = decode_access_token(response.json()["access_token"])
    assert payload["ver"] == 0 and payload["aud"] == "browser"


def test_browser_login_failure_is_neutral_and_audited(client, db):
    response = browser_login(client, password="wrong")
    assert response.status_code == 401
    assert response.json()["detail"] == "Las credenciales ingresadas no son válidas."
    event = db.scalar(select(SecurityAuditEvent).where(SecurityAuditEvent.event_type == "LOGIN_FAILURE"))
    assert event and "token" not in event.event_metadata and "ip" not in event.event_metadata


def test_refresh_requires_csrf_and_rotates(client, db, admin):
    assert browser_login(client).status_code == 200
    csrf = client.cookies.get("te_csrf")
    old_refresh = client.cookies.get("te_refresh")
    missing = client.post("/api/v1/auth/browser/refresh")
    assert missing.status_code == 403
    refreshed = client.post("/api/v1/auth/browser/refresh", headers={"X-CSRF-Token": csrf})
    assert refreshed.status_code == 200
    assert client.cookies.get("te_refresh") != old_refresh
    sessions = db.scalars(select(AuthSession).where(AuthSession.user_id == admin.id)).all()
    assert len(sessions) == 2
    assert sum(item.revoked_at is None for item in sessions) == 1


def test_reuse_revokes_family(client, db, admin):
    browser_login(client)
    old_refresh, old_csrf = client.cookies.get("te_refresh"), client.cookies.get("te_csrf")
    client.post("/api/v1/auth/browser/refresh", headers={"X-CSRF-Token": old_csrf})
    client.cookies.set("te_refresh", old_refresh, path="/api/v1/auth/browser")
    client.cookies.set("te_csrf", old_csrf, path="/")
    response = client.post("/api/v1/auth/browser/refresh", headers={"X-CSRF-Token": old_csrf})
    assert response.status_code == 401
    active = db.scalars(select(AuthSession).where(AuthSession.user_id == admin.id, AuthSession.revoked_at.is_(None))).all()
    assert active == []
    assert db.scalar(select(SecurityAuditEvent).where(SecurityAuditEvent.event_type == "REFRESH_TOKEN_REUSE"))


def test_logout_is_idempotent(client, db, admin):
    browser_login(client)
    csrf = client.cookies.get("te_csrf")
    assert client.post("/api/v1/auth/browser/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.post("/api/v1/auth/browser/logout").status_code == 204
    assert not db.scalars(select(AuthSession).where(AuthSession.user_id == admin.id, AuthSession.revoked_at.is_(None))).all()


def test_expired_session_is_rejected(client, db, admin):
    assert browser_login(client).status_code == 200
    session = db.scalar(select(AuthSession))
    session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert client.get("/api/v1/auth/browser/session").status_code == 401


def test_password_change_increments_version_and_revokes(client, db, admin, admin_headers):
    browser_login(client)
    response = client.post("/api/v1/users/" + str(admin.id) + "/change-password",
        json={"new_password": "ChangedPass123"}, headers=admin_headers)
    assert response.status_code == 200
    db.refresh(admin)
    assert admin.token_version == 1
    assert not db.scalars(select(AuthSession).where(AuthSession.user_id == admin.id, AuthSession.revoked_at.is_(None))).all()


def test_audit_is_admin_only_and_uses_date(client, db, admin_headers):
    browser_login(client)
    response = client.get("/api/v1/security/audit-events", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["items"]
    assert len(response.json()["items"][0]["event_date"]) == 10
    assert "created_at" not in response.json()["items"][0]


def test_security_headers_and_request_id(client):
    response = client.get("/api/v1/health", headers={"X-Request-ID": "test-request"})
    assert response.headers["X-Request-ID"] == "test-request"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
