from sqlalchemy import select

from app.core.security import hash_password, verify_password
from app.models.security import AuthSession, SecurityAuditEvent
from app.models.user import User
from app.services.role_service import RoleService


def request(client, headers, current="AdminPass123", new="NuevaClave456", confirmation="NuevaClave456"):
    return client.post("/api/v1/auth/change-password", headers=headers, json={
        "current_password": current, "new_password": new,
        "new_password_confirmation": confirmation,
    })


def test_change_own_password_and_login_credentials(client, admin, admin_headers, db):
    response = request(client, admin_headers)
    assert response.status_code == 200
    assert response.json()["message"] == "Contraseña actualizada correctamente. Inicia sesión nuevamente."
    assert verify_password("NuevaClave456", admin.hashed_password)
    assert client.post("/api/v1/auth/login", data={"username": "admin", "password": "AdminPass123"}).status_code == 401
    assert client.post("/api/v1/auth/login", data={"username": "admin", "password": "NuevaClave456"}).status_code == 200
    event = db.scalar(select(SecurityAuditEvent).where(SecurityAuditEvent.event_type == "PASSWORD_CHANGED"))
    serialized = str(event.event_metadata).lower()
    assert "password" not in serialized and "nuevaclave" not in serialized
    assert event.event_metadata["actor_user_id"] == str(admin.id)


def test_change_own_password_validation(client, admin_headers):
    assert request(client, admin_headers, current="incorrecta").json()["detail"] == "La contraseña actual no es correcta."
    assert request(client, admin_headers, confirmation="OtraClave789").json()["detail"] == "Las nuevas contraseñas no coinciden."
    assert request(client, admin_headers, new="débil", confirmation="débil").json()["detail"] == "La nueva contraseña no cumple los requisitos de seguridad."
    assert request(client, admin_headers, new="AdminPass123", confirmation="AdminPass123").status_code == 400


def test_change_password_requires_authentication(client):
    assert request(client, {}).status_code == 401


def test_user_a_cannot_change_user_b(client, admin, db):
    role = RoleService(db).repository.get_by_code("CANDIDATE")
    user_a = User(email="a@example.com", username="user_a", first_name="A", last_name="Test",
        hashed_password=hash_password("UserPass123"), roles=[role])
    db.add(user_a); db.commit()
    token = client.post("/api/v1/auth/login", data={"username": "user_a", "password": "UserPass123"}).json()["access_token"]
    response = client.post(f"/api/v1/users/{admin.id}/change-password",
        headers={"Authorization": f"Bearer {token}"}, json={"new_password": "Changed123"})
    assert response.status_code == 403


def test_change_password_revokes_real_browser_session(client, admin, db):
    login = client.post("/api/v1/auth/browser/login", json={"identifier": "admin", "password": "AdminPass123"})
    assert login.status_code == 200
    access = login.json()["access_token"]
    old_refresh, old_csrf = client.cookies.get("te_refresh"), client.cookies.get("te_csrf")
    assert old_refresh and old_csrf
    changed = request(client, {"Authorization": f"Bearer {access}"})
    assert changed.status_code == 200
    db.refresh(admin)
    assert admin.token_version == 1
    assert not db.scalars(select(AuthSession).where(
        AuthSession.user_id == admin.id, AuthSession.revoked_at.is_(None))).all()
    client.cookies.set("te_refresh", old_refresh, path="/api/v1/auth/browser")
    client.cookies.set("te_csrf", old_csrf, path="/")
    refresh = client.post("/api/v1/auth/browser/refresh", headers={"X-CSRF-Token": old_csrf})
    assert refresh.status_code == 401
    assert client.post("/api/v1/auth/login", data={"username": "admin", "password": "AdminPass123"}).status_code == 401
    assert client.post("/api/v1/auth/login", data={"username": "admin", "password": "NuevaClave456"}).status_code == 200


def test_password_audit_contains_no_sensitive_fields(client, admin_headers, db):
    assert request(client, admin_headers).status_code == 200
    event = db.scalar(select(SecurityAuditEvent).where(SecurityAuditEvent.event_type == "PASSWORD_CHANGED"))
    serialized = str(event.event_metadata).lower()
    for forbidden in ("password", "current_password", "new_password", "token", "secret", "api_key", "hash"):
        assert forbidden not in serialized
