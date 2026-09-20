"""§12 audit Fase 4A: the ArtifactStorage unification (evidence + reports
sharing one class hierarchy) must not regress ReportService. Exercises the
full generate -> download -> deactivate lifecycle against BOTH backends —
provider=local (already covered elsewhere, repeated here for symmetry) and
provider=s3 (via a real S3ArtifactStorage + botocore Stubber, never real
AWS) — to prove the refactor is transparent to report generation."""

from datetime import date

import boto3
import pytest
from botocore.config import Config
from botocore.stub import ANY, Stubber

from app.services.artifact_storage import LocalArtifactStorage, RemoteArtifactDownload, S3ArtifactStorage
from app.services.exceptions import BusinessRuleError
from app.services.report_service import ReportService

from tests.test_report_center import _report_dataset, _request


def _s3_client():
    return boto3.client(
        "s3", region_name="us-east-1",
        aws_access_key_id="testing", aws_secret_access_key="testing", aws_session_token="testing",
        config=Config(signature_version="s3v4"),
    )


@pytest.fixture
def rc_regression(db, admin):
    from app.services.activity_catalog_service import seed as seed_catalogs
    from app.scripts.seed_reports_and_alerts import seed as seed_report_templates

    seed_catalogs(db)
    seed_report_templates(db)
    db.commit()
    campaign, canton, parish_a, parish_b = _report_dataset(db, admin, 501)
    return campaign, canton, parish_a, parish_b


def test_report_lifecycle_with_local_provider(db, admin, rc_regression, tmp_path):
    campaign, *_ = rc_regression
    storage = LocalArtifactStorage(str(tmp_path), 10)
    service = ReportService(db, storage)
    run = service.generate(campaign.id, _request(), admin)
    assert run.status == "COMPLETED"
    artifact = service.artifact(run)
    assert artifact is not None and artifact.is_available
    download, _ = service.download(campaign.id, run.id, admin, date(2026, 8, 20))
    assert download.path.exists()
    service.deactivate(campaign.id, run.id, admin)
    assert not download.path.exists()


def test_report_lifecycle_with_s3_provider(db, admin, rc_regression):
    campaign, *_ = rc_regression
    client = _s3_client()
    storage = S3ArtifactStorage(client, bucket="test-bucket", prefix="reports", max_file_mb=50)
    service = ReportService(db, storage)

    generate_stubber = Stubber(client)
    generate_stubber.add_response("put_object", {}, {"Bucket": "test-bucket", "Key": ANY, "Body": ANY, "ServerSideEncryption": "AES256"})
    with generate_stubber:
        run = service.generate(campaign.id, _request(), admin)
    assert run.status == "COMPLETED"
    artifact = service.artifact(run)
    assert artifact is not None and artifact.storage_key.startswith("reports/")

    download_stubber = Stubber(client)
    download_stubber.add_response("head_object", {}, {"Bucket": "test-bucket", "Key": artifact.storage_key})
    with download_stubber:
        download, downloaded_artifact = service.download(campaign.id, run.id, admin, date(2026, 8, 20))
    assert isinstance(download, RemoteArtifactDownload)
    assert downloaded_artifact.id == artifact.id
    assert download.url.startswith("https://") and "X-Amz-Signature" in download.url

    deactivate_stubber = Stubber(client)
    deactivate_stubber.add_response("head_object", {}, {"Bucket": "test-bucket", "Key": artifact.storage_key})
    deactivate_stubber.add_response("delete_object", {}, {"Bucket": "test-bucket", "Key": artifact.storage_key})
    with deactivate_stubber:
        service.deactivate(campaign.id, run.id, admin)
    db.refresh(artifact)
    assert artifact.is_available is False and artifact.is_active is False


def test_report_generation_cleans_up_s3_object_on_db_failure(db, admin, rc_regression, monkeypatch):
    """§12/§18: same orphan-cleanup guarantee as the evidence paths, now
    proven against the S3 backend specifically (store() succeeds, then the
    DB transaction fails before the artifact row commits)."""
    campaign, *_ = rc_regression
    client = _s3_client()
    storage = S3ArtifactStorage(client, bucket="test-bucket", prefix="reports", max_file_mb=50)
    service = ReportService(db, storage)

    stubber = Stubber(client)
    stubber.add_response("put_object", {}, {"Bucket": "test-bucket", "Key": ANY, "Body": ANY, "ServerSideEncryption": "AES256"})
    stubber.add_response("head_object", {}, {"Bucket": "test-bucket", "Key": ANY})
    stubber.add_response("delete_object", {}, {"Bucket": "test-bucket", "Key": ANY})

    # generate() commits twice: once to persist the GENERATING run (before
    # storage.store() is ever called), and once after the artifact row is
    # built (right after storage.store() succeeded) — the second call is
    # the one that must fail here to exercise the post-S3-write cleanup path.
    original_commit = db.commit
    calls = {"n": 0}

    def failing_commit():
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("fallo simulado de base de datos")
        return original_commit()

    monkeypatch.setattr(db, "commit", failing_commit)
    with stubber, pytest.raises(BusinessRuleError):
        service.generate(campaign.id, _request(), admin)
    monkeypatch.undo()
    stubber.assert_no_pending_responses()
