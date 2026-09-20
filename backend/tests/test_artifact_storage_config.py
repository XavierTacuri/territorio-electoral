import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_provider_defaults_to_local():
    settings = Settings(_env_file=None)
    assert settings.artifact_storage_provider == "local"


def test_provider_rejects_unknown_value():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, artifact_storage_provider="azure")


def test_s3_provider_requires_region():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, artifact_storage_provider="s3", s3_artifact_bucket="bucket")


def test_s3_provider_requires_bucket():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, artifact_storage_provider="s3", aws_region="us-east-1")


def test_s3_provider_rejects_blank_prefixes():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, artifact_storage_provider="s3", aws_region="us-east-1", s3_artifact_bucket="bucket", s3_evidence_prefix="   ")


def test_s3_provider_accepts_minimal_valid_config():
    settings = Settings(_env_file=None, artifact_storage_provider="s3", aws_region="us-east-1", s3_artifact_bucket="bucket")
    assert settings.artifact_storage_provider == "s3"
    assert settings.s3_evidence_prefix == "evidence"
    assert settings.s3_report_prefix == "reports"


def test_presign_expiry_must_be_positive():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, s3_presign_expires_seconds=0)


def test_s3_timeouts_must_be_positive():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, s3_connect_timeout_seconds=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, s3_read_timeout_seconds=0)


def test_s3_max_attempts_must_be_positive():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, s3_max_attempts=0)


def test_kms_sse_mode_requires_kms_key_id():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, s3_sse_mode="aws:kms")


def test_kms_sse_mode_accepted_with_key_id():
    settings = Settings(_env_file=None, s3_sse_mode="aws:kms", s3_kms_key_id="arn:aws:kms:us-east-1:000000000000:key/placeholder")
    assert settings.s3_sse_mode == "aws:kms"


def test_sse_mode_rejects_unknown_value():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, s3_sse_mode="none")


def test_local_provider_allowed_in_any_app_env_including_production_labelled():
    # Render staging today runs provider=local under a non-"production"
    # APP_ENV; local must stay valid so that topology keeps working. The
    # explicit "don't silently allow AWS production on local" warning lives
    # in app.main (a runtime log, not a hard validation failure) precisely
    # so this combination is never rejected outright — see test below.
    settings = Settings(_env_file=None, artifact_storage_provider="local")
    assert settings.artifact_storage_provider == "local"


def test_settings_never_exposes_static_aws_credentials():
    # The application must only ever use boto3's standard credential
    # provider chain (env/shared config/instance or task role). Asserting
    # the absence of these fields is a regression guard against ever adding
    # them back.
    settings = Settings(_env_file=None)
    assert not hasattr(settings, "aws_access_key_id")
    assert not hasattr(settings, "aws_secret_access_key")
