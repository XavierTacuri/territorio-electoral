"""S3ArtifactStorage tests — never contact real AWS. store()/delete()/exists()
are verified with a botocore Stubber (deterministic, offline); download()
only computes a local presigned signature, so a plain fake-credentialed
client is enough."""

import hashlib

import boto3
import pytest
from botocore.stub import ANY, Stubber

from app.services.artifact_storage import RemoteArtifactDownload, S3ArtifactStorage, sha256_base64_to_hex, sha256_hex_to_base64


def _client():
    from botocore.config import Config

    return boto3.client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        aws_session_token="testing",
        config=Config(signature_version="s3v4"),
    )


def _storage(client, **overrides):
    kwargs = dict(bucket="test-bucket", prefix="evidence", max_file_mb=15, sse_mode="AES256", presign_expires_seconds=300)
    kwargs.update(overrides)
    return S3ArtifactStorage(client, **kwargs)


def test_store_uploads_with_aes256_encryption_and_randomized_key(tmp_path):
    client = _client()
    stubber = Stubber(client)
    source = tmp_path / "photo.jpg"
    source.write_bytes(b"jpeg-bytes")
    stubber.add_response(
        "put_object",
        {},
        {"Bucket": "test-bucket", "Key": ANY, "Body": ANY, "ServerSideEncryption": "AES256"},
    )
    with stubber:
        key, size, digest = _storage(client).store(source, "jpg")
    assert key.startswith("evidence/") and key.endswith(".jpg")
    assert size == len(b"jpeg-bytes")
    assert digest == hashlib.sha256(b"jpeg-bytes").hexdigest()
    # No PII (filename, username, ...) — just the fixed prefix and a UUID.
    assert "photo" not in key


def test_store_uses_kms_when_configured(tmp_path):
    client = _client()
    stubber = Stubber(client)
    source = tmp_path / "photo.jpg"
    source.write_bytes(b"jpeg-bytes")
    stubber.add_response(
        "put_object",
        {},
        {
            "Bucket": "test-bucket", "Key": ANY, "Body": ANY,
            "ServerSideEncryption": "aws:kms", "SSEKMSKeyId": "arn:aws:kms:us-east-1:000000000000:key/test",
        },
    )
    storage = _storage(client, sse_mode="aws:kms", kms_key_id="arn:aws:kms:us-east-1:000000000000:key/test")
    with stubber:
        storage.store(source, "jpg")


def test_store_rejects_oversized_file_without_calling_s3(tmp_path):
    client = _client()
    stubber = Stubber(client)  # no responses queued: any S3 call fails the test
    source = tmp_path / "big.jpg"
    source.write_bytes(b"x" * 2048)
    storage = S3ArtifactStorage(client, bucket="test-bucket", prefix="evidence", max_file_mb=0)
    with stubber:
        with pytest.raises(ValueError):
            storage.store(source, "jpg")


def test_delete_existing_object_returns_true():
    client = _client()
    stubber = Stubber(client)
    stubber.add_response("head_object", {}, {"Bucket": "test-bucket", "Key": "evidence/x.jpg"})
    stubber.add_response("delete_object", {}, {"Bucket": "test-bucket", "Key": "evidence/x.jpg"})
    with stubber:
        assert _storage(client).delete("evidence/x.jpg") is True


def test_delete_missing_object_returns_false():
    from botocore.exceptions import ClientError

    client = _client()
    stubber = Stubber(client)
    stubber.add_client_error("head_object", service_error_code="404", http_status_code=404)
    with stubber:
        assert _storage(client).delete("evidence/missing.jpg") is False


def test_exists_true_and_false():
    client = _client()
    stubber = Stubber(client)
    stubber.add_response("head_object", {}, {"Bucket": "test-bucket", "Key": "evidence/x.jpg"})
    stubber.add_client_error("head_object", service_error_code="404", http_status_code=404)
    with stubber:
        storage = _storage(client)
        assert storage.exists("evidence/x.jpg") is True
        assert storage.exists("evidence/missing.jpg") is False


def test_delete_reraises_unexpected_client_errors():
    client = _client()
    stubber = Stubber(client)
    stubber.add_client_error("head_object", service_error_code="AccessDenied", http_status_code=403)
    with stubber:
        with pytest.raises(Exception):
            _storage(client).delete("evidence/x.jpg")


def test_download_returns_short_lived_presigned_url_no_network_call():
    client = _client()
    download = _storage(client, presign_expires_seconds=120).download("evidence/x.jpg", filename="acta.jpg", content_type="image/jpeg")
    assert isinstance(download, RemoteArtifactDownload)
    assert download.url.startswith("https://")
    assert "test-bucket" in download.url
    assert "X-Amz-Signature" in download.url


def test_download_never_exceeds_configured_expiry():
    client = _client()
    download = _storage(client, presign_expires_seconds=60).download("evidence/x.jpg")
    assert "X-Amz-Expires=60" in download.url


def test_download_embeds_response_content_disposition_and_type():
    client = _client()
    download = _storage(client).download("evidence/x.jpg", filename="a b.jpg", content_type="image/jpeg")
    assert "response-content-disposition" in download.url.lower()
    assert "response-content-type" in download.url.lower()


def test_download_filename_is_sanitized_against_header_injection():
    # CR/LF and the quote/colon that would let a crafted filename break out
    # of the Content-Disposition value are stripped; whatever's left (plain
    # text) is inert — it can never reintroduce a header or query break.
    client = _client()
    download = _storage(client).download("evidence/x.jpg", filename='evil".jpg\r\nX-Injected: 1')
    assert "\r" not in download.url and "\n" not in download.url
    assert "%0d" not in download.url.lower() and "%0a" not in download.url.lower()
    assert '"' not in download.url.replace("%22", "")


# ---------- Direct browser-to-S3 upload (§12-18) ----------


def test_new_pending_key_is_randomized_and_under_pending_prefix():
    client = _client()
    storage = _storage(client)
    key = storage.new_pending_key("jpg")
    assert key.startswith("evidence/pending/") and key.endswith(".jpg")


def test_presign_upload_returns_url_fields_and_exact_key_condition():
    client = _client()
    storage = _storage(client)
    key = storage.new_pending_key("jpg")
    presigned = storage.presign_upload(key, content_type="image/jpeg", max_bytes=1024, sha256_hex="a" * 64)
    assert presigned.key == key
    assert presigned.fields["key"] == key
    assert presigned.fields["Content-Type"] == "image/jpeg"
    # S3's native additional-checksum field (base64), not x-amz-meta-* —
    # this is what makes S3 itself validate the uploaded bytes (§2 audit).
    assert presigned.fields["x-amz-checksum-sha256"] == sha256_hex_to_base64("a" * 64)
    assert presigned.fields["x-amz-server-side-encryption"] == "AES256"
    assert "policy" in presigned.fields and "x-amz-signature" in presigned.fields


def test_presign_upload_never_exceeds_configured_expiry():
    client = _client()
    storage = _storage(client, presign_expires_seconds=90)
    key = storage.new_pending_key("jpg")
    presigned = storage.presign_upload(key, content_type="image/jpeg", max_bytes=1024, sha256_hex="a" * 64)
    from datetime import datetime, timezone

    assert presigned.expires_at > datetime.now(timezone.utc)
    assert (presigned.expires_at - datetime.now(timezone.utc)).total_seconds() <= 91


def test_presign_upload_includes_kms_condition_when_configured():
    client = _client()
    storage = _storage(client, sse_mode="aws:kms", kms_key_id="arn:aws:kms:us-east-1:000000000000:key/test")
    key = storage.new_pending_key("jpg")
    presigned = storage.presign_upload(key, content_type="image/jpeg", max_bytes=1024, sha256_hex="a" * 64)
    assert presigned.fields["x-amz-server-side-encryption"] == "aws:kms"
    assert presigned.fields["x-amz-server-side-encryption-aws-kms-key-id"] == "arn:aws:kms:us-east-1:000000000000:key/test"


def test_head_metadata_returns_none_when_object_missing():
    client = _client()
    stubber = Stubber(client)
    stubber.add_client_error("head_object", service_error_code="404", http_status_code=404)
    with stubber:
        assert _storage(client).head_metadata("evidence/pending/missing.jpg") is None


def test_head_metadata_reports_size_content_type_and_native_s3_checksum():
    client = _client()
    stubber = Stubber(client)
    stubber.add_response(
        "head_object",
        {"ContentLength": 2048, "ContentType": "image/jpeg", "ChecksumSHA256": sha256_hex_to_base64("b" * 64)},
        {"Bucket": "test-bucket", "Key": "evidence/pending/x.jpg", "ChecksumMode": "ENABLED"},
    )
    with stubber:
        head = _storage(client).head_metadata("evidence/pending/x.jpg")
    assert head.size_bytes == 2048
    assert head.content_type == "image/jpeg"
    # Confirms head_metadata asked for (and read back) S3's own computed
    # checksum, not client-supplied metadata — the exact request params
    # above (ChecksumMode="ENABLED") is what the Stubber enforces.
    assert head.checksum_sha256_hex == "b" * 64


def test_head_metadata_returns_none_checksum_when_object_has_none():
    # An object uploaded without a checksum (shouldn't happen via this
    # class, but defensive): head_metadata must not crash decoding it.
    client = _client()
    stubber = Stubber(client)
    stubber.add_response(
        "head_object",
        {"ContentLength": 10, "ContentType": "image/jpeg"},
        {"Bucket": "test-bucket", "Key": "evidence/pending/x.jpg", "ChecksumMode": "ENABLED"},
    )
    with stubber:
        head = _storage(client).head_metadata("evidence/pending/x.jpg")
    assert head.checksum_sha256_hex is None


def test_promote_pending_copies_then_deletes_and_rejects_wrong_prefix():
    client = _client()
    stubber = Stubber(client)
    pending_key = "evidence/pending/abc123.jpg"
    final_key = "evidence/final/abc123.jpg"
    stubber.add_response(
        "copy_object",
        {},
        {"Bucket": "test-bucket", "Key": final_key, "CopySource": {"Bucket": "test-bucket", "Key": pending_key}, "ServerSideEncryption": "AES256"},
    )
    stubber.add_response("delete_object", {}, {"Bucket": "test-bucket", "Key": pending_key})
    storage = _storage(client)
    with stubber:
        assert storage.promote_pending(pending_key) == final_key
    with pytest.raises(ValueError):
        storage.promote_pending("evidence/final/already-there.jpg")


# ---------- sha256 hex <-> S3 checksum base64 conversion ----------


def test_sha256_hex_to_base64_and_back_round_trips():
    digest = hashlib.sha256(b"acta electoral fixture").hexdigest()
    assert sha256_base64_to_hex(sha256_hex_to_base64(digest)) == digest


def test_sha256_hex_to_base64_matches_known_vector():
    # sha256("") = e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
    empty_digest_hex = hashlib.sha256(b"").hexdigest()
    assert sha256_hex_to_base64(empty_digest_hex) == "47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU="
