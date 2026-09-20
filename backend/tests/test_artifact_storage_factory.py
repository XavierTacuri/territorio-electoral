from app.core.config import settings
from app.services.artifact_storage import LocalArtifactStorage, S3ArtifactStorage
from app.services.artifact_storage_factory import build_evidence_storage, build_report_storage
from app.services.s3_client import get_s3_client


def test_local_provider_builds_local_storage():
    assert settings.artifact_storage_provider == "local"
    assert isinstance(build_evidence_storage(), LocalArtifactStorage)
    assert isinstance(build_report_storage(), LocalArtifactStorage)


def test_s3_provider_builds_s3_storage_with_configured_bucket_and_prefixes(monkeypatch):
    get_s3_client.cache_clear()
    monkeypatch.setattr(settings, "artifact_storage_provider", "s3")
    monkeypatch.setattr(settings, "aws_region", "us-east-1")
    monkeypatch.setattr(settings, "s3_artifact_bucket", "campaign-artifacts")
    monkeypatch.setattr(settings, "s3_evidence_prefix", "evidence")
    monkeypatch.setattr(settings, "s3_report_prefix", "reports")
    try:
        evidence_storage = build_evidence_storage()
        report_storage = build_report_storage()
        assert isinstance(evidence_storage, S3ArtifactStorage)
        assert isinstance(report_storage, S3ArtifactStorage)
        assert evidence_storage.bucket == "campaign-artifacts" and evidence_storage.prefix == "evidence"
        assert report_storage.bucket == "campaign-artifacts" and report_storage.prefix == "reports"
    finally:
        get_s3_client.cache_clear()


def test_s3_provider_shares_a_single_boto3_client_across_storages(monkeypatch):
    get_s3_client.cache_clear()
    monkeypatch.setattr(settings, "artifact_storage_provider", "s3")
    monkeypatch.setattr(settings, "aws_region", "us-east-1")
    monkeypatch.setattr(settings, "s3_artifact_bucket", "campaign-artifacts")
    try:
        evidence_storage = build_evidence_storage()
        report_storage = build_report_storage()
        assert evidence_storage.client is report_storage.client
    finally:
        get_s3_client.cache_clear()
