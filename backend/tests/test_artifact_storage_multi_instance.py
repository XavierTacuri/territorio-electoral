"""§35/§36 Fase 4A: with provider=s3, an artifact generated/uploaded by one
API instance must be servable by a completely different instance — the only
thing they share is the bucket, never a filesystem or Python process state.

Each `S3ArtifactStorage` here is built from its own boto3 client/Stubber
pair, deliberately standing in for two unrelated processes (e.g. ECS tasks
API-1 and API-2 in the Fase 4B target). "Instance B" never sees "instance
A"'s in-memory object — only the `storage_key` a real deployment would have
persisted to Postgres, which is the actual contract this test protects."""

import boto3
from botocore.stub import ANY, Stubber

from app.services.artifact_storage import RemoteArtifactDownload, S3ArtifactStorage


def _independent_client():
    from botocore.config import Config

    return boto3.client(
        "s3", region_name="us-east-1",
        aws_access_key_id="testing", aws_secret_access_key="testing", aws_session_token="testing",
        config=Config(signature_version="s3v4"),
    )


def test_report_stored_by_one_instance_is_downloadable_from_another(tmp_path):
    bucket, prefix = "shared-bucket", "reports"
    source = tmp_path / "informe.pdf"
    source.write_bytes(b"%PDF-1.4 fixture report bytes")

    instance_a_client = _independent_client()
    instance_a_stubber = Stubber(instance_a_client)
    instance_a_stubber.add_response("put_object", {}, {"Bucket": bucket, "Key": ANY, "Body": ANY, "ServerSideEncryption": "AES256"})
    instance_a_storage = S3ArtifactStorage(instance_a_client, bucket=bucket, prefix=prefix, max_file_mb=50)
    with instance_a_stubber:
        storage_key, size, digest = instance_a_storage.store(source, "pdf")

    # Nothing but `storage_key` (what Postgres would hold) crosses over —
    # instance B is a fresh client, fresh Stubber, fresh Python object.
    instance_b_client = _independent_client()
    instance_b_stubber = Stubber(instance_b_client)
    instance_b_stubber.add_response("head_object", {}, {"Bucket": bucket, "Key": storage_key})
    instance_b_storage = S3ArtifactStorage(instance_b_client, bucket=bucket, prefix=prefix, max_file_mb=50)
    with instance_b_stubber:
        assert instance_b_storage.exists(storage_key) is True
        download = instance_b_storage.download(storage_key, filename="informe.pdf", content_type="application/pdf")
    assert isinstance(download, RemoteArtifactDownload)
    assert storage_key.startswith(f"{prefix}/")


def test_evidence_completed_by_one_instance_is_viewable_from_another():
    bucket, prefix = "shared-bucket", "evidence"
    storage_key = f"{prefix}/already-uploaded-by-instance-a.jpg"

    instance_b_client = _independent_client()
    instance_b_stubber = Stubber(instance_b_client)
    instance_b_stubber.add_response("head_object", {}, {"Bucket": bucket, "Key": storage_key})
    instance_b_storage = S3ArtifactStorage(instance_b_client, bucket=bucket, prefix=prefix, max_file_mb=15)
    with instance_b_stubber:
        assert instance_b_storage.exists(storage_key) is True
        download = instance_b_storage.download(storage_key, filename="acta.jpg", content_type="image/jpeg")
    assert isinstance(download, RemoteArtifactDownload)
