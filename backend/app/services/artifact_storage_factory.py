"""Builds the `ArtifactStorage` a service should use, based on
`settings.artifact_storage_provider`.

Every service that persists an artifact (evidence, election-day documents,
reports) takes an optional `storage=` constructor argument for tests/DI; when
omitted it calls one of these factories instead of constructing
`LocalEvidenceStorage`/`LocalReportStorage` directly, so a single setting
switches the whole application between the local filesystem and S3 without
touching service code.
"""

from app.core.config import settings
from app.services.artifact_storage import ArtifactStorage, LocalArtifactStorage, S3ArtifactStorage

# Deliberately NOT cached: constructing these wrapper objects is cheap (a
# handful of attribute assignments), and the one genuinely expensive/shared
# resource — the boto3 client itself — is already a process-wide singleton
# via app.services.s3_client.get_s3_client's own lru_cache. Not caching here
# keeps a settings change (or a test's monkeypatch) take effect immediately.


def _build_s3(prefix: str, max_file_mb: int) -> S3ArtifactStorage:
    from app.services.s3_client import get_s3_client

    return S3ArtifactStorage(
        get_s3_client(),
        bucket=settings.s3_artifact_bucket,
        prefix=prefix,
        max_file_mb=max_file_mb,
        sse_mode=settings.s3_sse_mode,
        kms_key_id=settings.s3_kms_key_id,
        presign_expires_seconds=settings.s3_presign_expires_seconds,
    )


def build_evidence_storage() -> ArtifactStorage:
    if settings.artifact_storage_provider == "s3":
        return _build_s3(settings.s3_evidence_prefix, settings.evidence_max_file_mb)
    return LocalArtifactStorage(settings.evidence_output_dir, settings.evidence_max_file_mb)


def build_report_storage() -> ArtifactStorage:
    if settings.artifact_storage_provider == "s3":
        return _build_s3(settings.s3_report_prefix, settings.report_max_file_mb)
    return LocalArtifactStorage(settings.report_output_dir, settings.report_max_file_mb)
