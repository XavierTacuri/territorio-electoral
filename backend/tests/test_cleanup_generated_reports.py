"""Fase 4C.5 review: app/scripts/cleanup_generated_reports.py used to build
LocalReportStorage directly (bypassing artifact_storage_factory), so with
ARTIFACT_STORAGE_PROVIDER=s3 it never touched the real S3 object while still
marking the artifact unavailable. These tests prove the fix: the script now
goes through artifact_storage_factory.build_report_storage() — the same
single source of truth ReportService itself already used — for both
providers, and leaves a still-valid artifact untouched."""

from datetime import date

import boto3
import pytest
from botocore.config import Config
from botocore.stub import ANY, Stubber

from app.core.config import settings
from app.models.reports import ReportArtifact
from app.scripts import cleanup_generated_reports
from app.services.artifact_storage import LocalArtifactStorage, S3ArtifactStorage
from app.services.report_service import ReportService

from tests.test_report_center import _report_dataset, _request


def _s3_client():
    return boto3.client(
        "s3", region_name="us-east-1",
        aws_access_key_id="testing", aws_secret_access_key="testing", aws_session_token="testing",
        config=Config(signature_version="s3v4"),
    )


@pytest.fixture
def cleanup_dataset(db, admin):
    from app.services.activity_catalog_service import seed as seed_catalogs
    from app.scripts.seed_reports_and_alerts import seed as seed_report_templates

    seed_catalogs(db)
    seed_report_templates(db)
    db.commit()
    campaign, *_ = _report_dataset(db, admin, 701)
    return campaign


def test_cleanup_deletes_expired_report_via_local_provider(db, admin, cleanup_dataset, tmp_path, monkeypatch):
    assert settings.artifact_storage_provider == "local"
    monkeypatch.setattr(settings, "report_output_dir", str(tmp_path))
    storage = LocalArtifactStorage(str(tmp_path), settings.report_max_file_mb)
    service = ReportService(db, storage)
    run = service.generate(cleanup_dataset.id, _request(), admin)
    artifact = service.artifact(run)
    local_path = storage.resolve(artifact.storage_key)
    assert local_path.exists()

    artifact.expires_on = date(2000, 1, 1)
    db.commit()

    monkeypatch.setattr(cleanup_generated_reports, "SessionLocal", lambda: db)
    monkeypatch.setattr("sys.argv", ["cleanup_generated_reports.py"])
    cleanup_generated_reports.main()

    assert not local_path.exists()
    assert db.get(ReportArtifact, artifact.id).is_available is False


def test_cleanup_does_not_touch_report_still_within_retention_local_provider(db, admin, cleanup_dataset, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "report_output_dir", str(tmp_path))
    storage = LocalArtifactStorage(str(tmp_path), settings.report_max_file_mb)
    service = ReportService(db, storage)
    run = service.generate(cleanup_dataset.id, _request(report_date=date.today()), admin)
    artifact = service.artifact(run)
    local_path = storage.resolve(artifact.storage_key)
    assert local_path.exists()
    assert artifact.expires_on > date.today()

    monkeypatch.setattr(cleanup_generated_reports, "SessionLocal", lambda: db)
    monkeypatch.setattr("sys.argv", ["cleanup_generated_reports.py"])
    cleanup_generated_reports.main()

    assert local_path.exists()
    assert db.get(ReportArtifact, artifact.id).is_available is True


def test_cleanup_deletes_expired_report_via_s3_provider_not_local(db, admin, cleanup_dataset, monkeypatch):
    """§ this is the exact regression the audit found: with the old hardcoded
    LocalReportStorage, this test fails — no S3 call is ever made, so the
    Stubber below is left with unconsumed responses and
    assert_no_pending_responses() raises."""
    client = _s3_client()
    monkeypatch.setattr("app.services.s3_client.get_s3_client", lambda: client)

    gen_storage = S3ArtifactStorage(client, bucket="test-bucket", prefix="reports", max_file_mb=50)
    gen_service = ReportService(db, gen_storage)
    gen_stubber = Stubber(client)
    gen_stubber.add_response("put_object", {}, {"Bucket": "test-bucket", "Key": ANY, "Body": ANY, "ServerSideEncryption": "AES256"})
    with gen_stubber:
        run = gen_service.generate(cleanup_dataset.id, _request(), admin)
    artifact = gen_service.artifact(run)
    assert artifact.storage_key.startswith("reports/")

    artifact.expires_on = date(2000, 1, 1)
    db.commit()

    monkeypatch.setattr(settings, "artifact_storage_provider", "s3")
    monkeypatch.setattr(settings, "aws_region", "us-east-1")
    monkeypatch.setattr(settings, "s3_artifact_bucket", "test-bucket")
    monkeypatch.setattr(settings, "s3_report_prefix", "reports")
    monkeypatch.setattr(cleanup_generated_reports, "SessionLocal", lambda: db)
    monkeypatch.setattr("sys.argv", ["cleanup_generated_reports.py"])

    delete_stubber = Stubber(client)
    delete_stubber.add_response("head_object", {}, {"Bucket": "test-bucket", "Key": artifact.storage_key})
    delete_stubber.add_response("delete_object", {}, {"Bucket": "test-bucket", "Key": artifact.storage_key})
    with delete_stubber:
        cleanup_generated_reports.main()
    delete_stubber.assert_no_pending_responses()

    assert db.get(ReportArtifact, artifact.id).is_available is False


def test_cleanup_skips_and_continues_when_s3_delete_fails(db, admin, cleanup_dataset, monkeypatch):
    """§11: an unexpected S3 error (not a plain "already gone" 404) must not
    crash the whole batch silently losing every pending commit — it should
    be counted as skipped and logged, matching the existing
    ReportService.generate() orphan-cleanup convention (except Exception)."""
    client = _s3_client()
    monkeypatch.setattr("app.services.s3_client.get_s3_client", lambda: client)

    gen_storage = S3ArtifactStorage(client, bucket="test-bucket", prefix="reports", max_file_mb=50)
    gen_service = ReportService(db, gen_storage)
    gen_stubber = Stubber(client)
    gen_stubber.add_response("put_object", {}, {"Bucket": "test-bucket", "Key": ANY, "Body": ANY, "ServerSideEncryption": "AES256"})
    with gen_stubber:
        run = gen_service.generate(cleanup_dataset.id, _request(), admin)
    artifact = gen_service.artifact(run)

    artifact.expires_on = date(2000, 1, 1)
    db.commit()

    monkeypatch.setattr(settings, "artifact_storage_provider", "s3")
    monkeypatch.setattr(settings, "aws_region", "us-east-1")
    monkeypatch.setattr(settings, "s3_artifact_bucket", "test-bucket")
    monkeypatch.setattr(settings, "s3_report_prefix", "reports")
    monkeypatch.setattr(cleanup_generated_reports, "SessionLocal", lambda: db)
    monkeypatch.setattr("sys.argv", ["cleanup_generated_reports.py"])

    delete_stubber = Stubber(client)
    delete_stubber.add_client_error("head_object", service_error_code="AccessDenied", http_status_code=403)
    with delete_stubber:
        cleanup_generated_reports.main()  # must not raise ClientError uncaught
    delete_stubber.assert_no_pending_responses()

    assert db.get(ReportArtifact, artifact.id).is_available is True
