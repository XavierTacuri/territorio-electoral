import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.security import hash_password
from app.models.user import User
from app.services.role_service import RoleService


def production(**overrides):
    values = {"app_env": "production", "app_debug": False, "enable_api_docs": False,
        "secret_key": "s" * 40, "browser_refresh_token_hmac_secret": "r" * 40,
        "survey_submission_hmac_secret": "u" * 40, "browser_cookie_secure": True,
        "frontend_origins": "https://app.example.test", "browser_allowed_origins": "https://app.example.test",
        "trusted_hosts": "app.example.test", "postgres_password": "safe-database-password",
        "initial_admin_password": "SafeAdminPassword123"}
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_openai_production_requires_key_and_model():
    with pytest.raises(ValidationError): production(territory_ai_provider="openai", territory_ai_model="gpt-5")
    with pytest.raises(ValidationError): production(territory_ai_provider="openai", openai_api_key="secret")
    assert production(territory_ai_provider="openai", openai_api_key="secret", territory_ai_model="gpt-5").territory_ai_provider == "openai"


def test_ai_configuration_never_contains_secret(client, admin_headers):
    payload = client.get("/api/v1/admin/ai-provider", headers=admin_headers).json()
    assert set(payload) == {"provider", "provider_label", "model", "status", "api_key_configured"}
    assert "api_key" not in payload


def test_ai_admin_endpoints_rbac(client, admin_headers, db):
    assert client.get("/api/v1/admin/ai-provider", headers=admin_headers).status_code == 200
    role = RoleService(db).repository.get_by_code("CANDIDATE")
    user = User(email="candidate@example.com", username="candidate", first_name="C", last_name="D",
        hashed_password=hash_password("Candidate123"), roles=[role])
    db.add(user); db.commit()
    token = client.post("/api/v1/auth/login", data={"username": "candidate", "password": "Candidate123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/admin/ai-provider", headers=headers).status_code == 403
    assert client.post("/api/v1/admin/ai-provider/test", headers=headers).status_code == 403


@pytest.mark.parametrize("role_code", ["CANDIDATE", "CAMPAIGN_MANAGER", "ANALYST", "TERRITORIAL_COORDINATOR"])
def test_ai_admin_endpoints_deny_every_non_global_admin(client, db, role_code):
    role = RoleService(db).repository.get_by_code(role_code)
    username = role_code.lower()
    user = User(email=f"{username}@example.com", username=username, first_name="Usuario", last_name="Prueba",
        hashed_password=hash_password("RolePass123"), roles=[role])
    db.add(user); db.commit()
    token = client.post("/api/v1/auth/login", data={"username": username, "password": "RolePass123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/admin/ai-provider", headers=headers).status_code == 403
    assert client.post("/api/v1/admin/ai-provider/test", headers=headers).status_code == 403
