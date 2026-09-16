import pytest
from pydantic import ValidationError

from app.core.config import Settings


def valid_production(**overrides):
    values = {
        "app_env": "production", "app_debug": False, "enable_api_docs": False,
        "secret_key": "s" * 40, "browser_refresh_token_hmac_secret": "r" * 40,
        "survey_submission_hmac_secret": "u" * 40, "browser_cookie_secure": True,
        "frontend_origins": "https://app.example.test", "browser_allowed_origins": "https://app.example.test",
        "trusted_hosts": "app.example.test", "territory_ai_provider": "unavailable",
        "postgres_password": "database-password-for-tests", "initial_admin_password": "AdminPasswordForTests123",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_production_rejects_debug():
    with pytest.raises(ValidationError): valid_production(app_debug=True)


def test_production_rejects_fake_provider():
    with pytest.raises(ValidationError): valid_production(territory_ai_provider="fake")


def test_production_rejects_missing_secret():
    with pytest.raises(ValidationError): valid_production(secret_key="")


def test_development_and_e2e_configs_are_valid():
    assert Settings(_env_file=None, app_env="development").app_env == "development"
    assert Settings(_env_file=None, app_env="e2e", app_debug=False).app_env == "e2e"


def test_production_accepts_database_url_with_default_postgres_password(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://render_user:render_pass@render-host/render_db")
    settings = valid_production(postgres_password="territorio_password")
    assert settings.database_url == "postgresql+psycopg://render_user:render_pass@render-host/render_db"


def test_production_rejects_missing_database_url_with_unsafe_postgres_password():
    with pytest.raises(ValidationError):
        valid_production(postgres_password="territorio_password")


def test_production_rejects_blank_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "   ")
    with pytest.raises(ValidationError):
        valid_production(postgres_password="territorio_password")


def test_production_accepts_database_url_override_alias(monkeypatch):
    monkeypatch.setenv("DATABASE_URL_OVERRIDE", "postgresql+psycopg://alias_user:alias_pass@alias-host/alias_db")
    settings = valid_production(postgres_password="territorio_password")
    assert settings.database_url == "postgresql+psycopg://alias_user:alias_pass@alias-host/alias_db"
