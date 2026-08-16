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
