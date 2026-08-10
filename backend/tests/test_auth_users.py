from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.core.security import create_access_token, hash_password
from app.models.user import User
from app.services.role_service import RoleService


def test_login_username_email_and_last_login(client: TestClient, admin: User):
    for identifier in ("admin", "ADMIN@EXAMPLE.COM"):
        response = client.post("/api/v1/auth/login", data={"username": identifier, "password": "AdminPass123"})
        assert response.status_code == 200
        assert set(response.json()) == {"access_token", "token_type", "expires_in"}
    assert admin.last_login_at is not None

@pytest.mark.parametrize("identifier,password", [("admin", "Wrong123"), ("missing", "Wrong123")])
def test_bad_login_is_generic(client, admin, identifier, password):
    response = client.post("/api/v1/auth/login", data={"username": identifier, "password": password})
    assert response.status_code == 401 and response.json() == {"detail": "Credenciales incorrectas"}


def test_inactive_login(client, admin, db):
    admin.is_active = False; db.commit()
    assert client.post("/api/v1/auth/login", data={"username": "admin", "password": "AdminPass123"}).status_code == 403


def test_me_authentication(client, admin, admin_headers, db):
    response = client.get("/api/v1/auth/me", headers=admin_headers)
    assert response.status_code == 200 and response.json()["username"] == "admin"
    assert "hashed_password" not in response.text and "created_at" not in response.text
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer bad"}).status_code == 401
    admin.is_active = False; db.commit()
    assert client.get("/api/v1/auth/me", headers=admin_headers).status_code == 403


def test_roles_require_auth(client, admin_headers):
    assert client.get("/api/v1/roles").status_code == 401
    response = client.get("/api/v1/roles", headers=admin_headers)
    assert response.status_code == 200 and len(response.json()) == 5


def test_non_admin_forbidden(client, db):
    role = RoleService(db).repository.get_by_code("ANALYST")
    user = User(email="analyst@example.com", username="analyst", first_name="Ana", last_name="Lista", hashed_password=hash_password("Analyst123"), roles=[role])
    db.add(user); db.commit()
    token = create_access_token(user.id)
    assert client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"}).status_code == 403
    assert client.get("/api/v1/users").status_code == 401


def payload(**changes):
    data = {"email": "person@example.com", "username": "person", "first_name": "Test", "last_name": "Person", "password": "Person123", "role_codes": ["ANALYST", "CANDIDATE"]}
    data.update(changes); return data


def test_user_crud_filters_and_password(client, admin_headers):
    created = client.post("/api/v1/users", json=payload(), headers=admin_headers)
    assert created.status_code == 201
    body = created.json(); user_id = body["id"]
    assert len(body["roles"]) == 2 and "hashed_password" not in created.text
    assert client.get(f"/api/v1/users/{user_id}", headers=admin_headers).status_code == 200
    listing = client.get("/api/v1/users?search=person&role_code=ANALYST&is_active=true&page=1&page_size=1", headers=admin_headers)
    assert listing.status_code == 200 and listing.json()["total"] == 1
    updated = client.patch(f"/api/v1/users/{user_id}", json={"first_name": "Nuevo", "role_codes": ["ANALYST"]}, headers=admin_headers)
    assert updated.status_code == 200 and updated.json()["first_name"] == "Nuevo"
    changed = client.post(f"/api/v1/users/{user_id}/change-password", json={"new_password": "Changed123"}, headers=admin_headers)
    assert changed.status_code == 200 and "hashed_password" not in changed.text

@pytest.mark.parametrize("changes", [{"email": "ADMIN@example.com"}, {"username": "ADMIN"}])
def test_duplicate_identifiers_case_insensitive(client, admin, admin_headers, changes):
    assert client.post("/api/v1/users", json=payload(**changes), headers=admin_headers).status_code == 409

@pytest.mark.parametrize("codes", [["MISSING"], ["ANALYST", "ANALYST"]])
def test_invalid_roles(client, admin_headers, codes):
    response = client.post("/api/v1/users", json=payload(role_codes=codes), headers=admin_headers)
    assert response.status_code in (400, 422)


def test_inactive_role_and_not_found(client, db, admin_headers):
    role = RoleService(db).repository.get_by_code("ANALYST"); role.is_active = False; db.commit()
    assert client.post("/api/v1/users", json=payload(role_codes=["ANALYST"]), headers=admin_headers).status_code == 400
    assert client.get(f"/api/v1/users/{uuid4()}", headers=admin_headers).status_code == 404


def test_cannot_disable_only_admin(client, admin, admin_headers):
    response = client.patch(f"/api/v1/users/{admin.id}", json={"is_active": False}, headers=admin_headers)
    assert response.status_code == 400
