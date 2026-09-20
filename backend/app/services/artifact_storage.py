"""Storage abstraction for persistent artifacts (evidence photos, election-day
documents, generated reports).

Two backends implement the same `ArtifactStorage` contract:

- `LocalArtifactStorage` writes to a local directory. Used by development,
  the isolated E2E stack, and the current Render staging topology (a single
  container's uvicorn workers share one filesystem, so this is safe there).
- `S3ArtifactStorage` writes to an S3-compatible bucket. Required whenever
  more than one API instance may serve the same campaign without a shared
  filesystem (Fase 4A/4B AWS target) — see `app/services/s3_client.py` for
  how the boto3 client is built (IAM credential provider chain, never static
  keys) and `app/services/artifact_storage_factory.py` for how a service
  picks one or the other based on `settings.artifact_storage_provider`.

Neither backend leaks its details past this module: services and routes only
see `store()/delete()/exists()/download()` and the `ArtifactDownload` result
of the latter — never a bucket name, boto3 client, or `s3://` URL construct.
"""

import base64
import hashlib
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4


def sha256_hex_to_base64(hex_digest: str) -> str:
    """S3's native checksum fields (`x-amz-checksum-sha256`, and the
    `ChecksumSHA256` HEAD/GetObjectAttributes response) use base64, while
    this codebase stores/compares sha256 as hex everywhere else (DB column,
    API payloads, the upload token). Convert at the S3 boundary only."""
    return base64.b64encode(bytes.fromhex(hex_digest)).decode("ascii")


def sha256_base64_to_hex(b64_digest: str) -> str:
    return base64.b64decode(b64_digest).hex()


@dataclass(frozen=True)
class LocalArtifactDownload:
    """A file already present on this instance's local filesystem."""

    path: Path


@dataclass(frozen=True)
class RemoteArtifactDownload:
    """A short-lived, pre-authorized URL the client fetches directly from
    object storage — FastAPI never streams the bytes."""

    url: str
    expires_at: datetime


ArtifactDownload = LocalArtifactDownload | RemoteArtifactDownload


@dataclass(frozen=True)
class PresignedUpload:
    """A browser-direct upload authorization: POST `fields` (plus the file
    as `file`) to `url`. Only `S3ArtifactStorage` produces these — the local
    backend has no equivalent, so callers branch on
    `isinstance(storage, S3ArtifactStorage)` before ever requesting one."""

    url: str
    fields: dict
    key: str
    expires_at: datetime


@dataclass(frozen=True)
class HeadResult:
    """What actually landed in the bucket, as reported by S3 itself.

    `checksum_sha256_hex` is NOT client-declared metadata — it is S3's own
    additional-checksum feature (`x-amz-checksum-sha256` required as a
    presigned-POST condition at upload time, `ChecksumMode=ENABLED` read back
    here): S3 computes it server-side from the actual bytes it received and
    rejects the upload outright if the client's declared checksum didn't
    match what it actually got. Reading it back and comparing against the
    expected value is therefore a real integrity check, not trust in
    something the client could have lied about independently of the bytes it
    sent. `None` means the object was never uploaded with a checksum
    (shouldn't happen for anything this class wrote itself)."""

    size_bytes: int
    content_type: str | None
    checksum_sha256_hex: str | None


class ArtifactStorage(ABC):
    """Storage abstraction for persistent, generated/uploaded artifacts.

    `store()` keeps its historical (key, size_bytes, sha256) tuple return so
    every existing call site (evidence/report services) is unaffected by
    which backend is configured. `download()` is the capability that differs
    by backend: local resolves to a `Path` FastAPI can stream with
    `FileResponse`; S3 resolves to a presigned GET the caller redirects to.
    """

    @abstractmethod
    def store(self, source: Path, extension: str) -> tuple[str, int, str]: ...

    @abstractmethod
    def delete(self, key: str) -> bool: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def download(self, key: str, *, filename: str | None = None, content_type: str | None = None) -> ArtifactDownload: ...


class LocalArtifactStorage(ArtifactStorage):
    def __init__(self, root: str, max_file_mb: int = 15):
        if not root.strip():
            raise ValueError("El directorio de almacenamiento no puede estar vacío")
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_file_mb * 1024 * 1024

    def resolve(self, key: str) -> Path:
        if Path(key).is_absolute() or ".." in Path(key).parts:
            raise ValueError("Ruta de artefacto insegura")
        raw = self.root / key
        if raw.is_symlink():
            raise ValueError("Ruta de artefacto insegura")
        target = raw.resolve(strict=False)
        if target.parent != self.root:
            raise ValueError("Ruta de artefacto insegura")
        return target

    def store(self, source: Path, extension: str) -> tuple[str, int, str]:
        size = source.stat().st_size
        if size > self.max_bytes:
            raise ValueError("El archivo supera el tamaño permitido")
        key = f"{uuid4().hex}.{extension.lower()}"
        target = self.resolve(key)
        shutil.move(str(source), target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        return key, size, digest

    def delete(self, key: str) -> bool:
        target = self.resolve(key)
        if not target.exists():
            return False
        if target.is_symlink():
            raise ValueError("Ruta de artefacto insegura")
        target.unlink()
        return True

    def exists(self, key: str) -> bool:
        return self.resolve(key).exists()

    def download(self, key: str, *, filename: str | None = None, content_type: str | None = None) -> LocalArtifactDownload:
        return LocalArtifactDownload(path=self.resolve(key))


class S3ArtifactStorage(ArtifactStorage):
    """Object-storage-backed implementation. The bucket is never a database:
    Postgres remains the source of truth for which key exists, its size,
    mime type and sha256 — this class only moves/authorizes bytes."""

    def __init__(
        self,
        client,
        *,
        bucket: str,
        prefix: str,
        max_file_mb: int,
        sse_mode: str = "AES256",
        kms_key_id: str | None = None,
        presign_expires_seconds: int = 300,
    ):
        if not bucket.strip():
            raise ValueError("El bucket S3 no puede estar vacío")
        if not prefix.strip():
            raise ValueError("El prefijo S3 no puede estar vacío")
        self.client = client
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.max_bytes = max_file_mb * 1024 * 1024
        self.sse_mode = sse_mode
        self.kms_key_id = kms_key_id
        self.presign_expires_seconds = presign_expires_seconds

    def _new_key(self, extension: str) -> str:
        # Randomized, PII-free key: no username, filename, or other user
        # data ever becomes part of the object key.
        return f"{self.prefix}/{uuid4().hex}.{extension.lower()}"

    def _encryption_args(self) -> dict:
        args: dict = {"ServerSideEncryption": self.sse_mode}
        if self.sse_mode == "aws:kms" and self.kms_key_id:
            args["SSEKMSKeyId"] = self.kms_key_id
        return args

    def store(self, source: Path, extension: str) -> tuple[str, int, str]:
        size = source.stat().st_size
        if size > self.max_bytes:
            raise ValueError("El archivo supera el tamaño permitido")
        data = source.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        key = self._new_key(extension)
        # put_object (not the upload_file/TransferManager helper): these
        # artifacts are always well under S3's single-PUT limit, and a
        # direct call keeps this deterministic and easy to test against a
        # botocore Stubber instead of the multipart-capable transfer manager.
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, **self._encryption_args())
        return key, size, digest

    def delete(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if _is_not_found(exc):
                return False
            raise
        self.client.delete_object(Bucket=self.bucket, Key=key)
        return True

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            if _is_not_found(exc):
                return False
            raise

    def download(self, key: str, *, filename: str | None = None, content_type: str | None = None) -> RemoteArtifactDownload:
        params: dict = {"Bucket": self.bucket, "Key": key}
        if filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{_safe_header_filename(filename)}"'
        if content_type:
            params["ResponseContentType"] = content_type
        params["ResponseCacheControl"] = "private, no-store"
        url = self.client.generate_presigned_url("get_object", Params=params, ExpiresIn=self.presign_expires_seconds)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.presign_expires_seconds)
        return RemoteArtifactDownload(url=url, expires_at=expires_at)

    # ---------- Direct browser-to-S3 upload (§12-18 Fase 4A) ----------

    def new_pending_key(self, extension: str) -> str:
        """A key under `{prefix}/pending/` — never referenced by any
        persisted row. Only `promote_pending` (called from a verified
        `complete()`) ever moves an object out of this prefix, so a leaked
        presigned POST that's never completed leaves an orphan confined to
        `pending/`, safe for a Fase 4B lifecycle rule to expire (§17)."""
        return f"{self.prefix}/pending/{uuid4().hex}.{extension.lower()}"

    def presign_upload(self, key: str, *, content_type: str, max_bytes: int, sha256_hex: str) -> PresignedUpload:
        # x-amz-checksum-sha256 (S3's native additional-checksum field, not
        # x-amz-meta-*) makes S3 itself compute the SHA-256 of the bytes it
        # receives and reject the upload (400, before it's ever written) if
        # they don't match this declared value — the client cannot upload
        # different bytes than the checksum it authorized here.
        checksum_b64 = sha256_hex_to_base64(sha256_hex)
        conditions: list = [
            {"key": key},
            {"Content-Type": content_type},
            {"x-amz-checksum-sha256": checksum_b64},
            ["content-length-range", 1, max_bytes],
        ]
        fields: dict = {"Content-Type": content_type, "x-amz-checksum-sha256": checksum_b64}
        encryption = self._encryption_args()
        conditions.append({"x-amz-server-side-encryption": encryption["ServerSideEncryption"]})
        fields["x-amz-server-side-encryption"] = encryption["ServerSideEncryption"]
        if "SSEKMSKeyId" in encryption:
            conditions.append({"x-amz-server-side-encryption-aws-kms-key-id": encryption["SSEKMSKeyId"]})
            fields["x-amz-server-side-encryption-aws-kms-key-id"] = encryption["SSEKMSKeyId"]
        response = self.client.generate_presigned_post(
            Bucket=self.bucket, Key=key, Fields=fields, Conditions=conditions, ExpiresIn=self.presign_expires_seconds,
        )
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.presign_expires_seconds)
        return PresignedUpload(url=response["url"], fields=response["fields"], key=key, expires_at=expires_at)

    def head_metadata(self, key: str) -> HeadResult | None:
        from botocore.exceptions import ClientError

        try:
            # ChecksumMode="ENABLED" is what makes HEAD return the
            # server-computed ChecksumSHA256 — omitting it returns size/type
            # only, silently losing the one field that actually matters here.
            head = self.client.head_object(Bucket=self.bucket, Key=key, ChecksumMode="ENABLED")
        except ClientError as exc:
            if _is_not_found(exc):
                return None
            raise
        checksum_b64 = head.get("ChecksumSHA256")
        return HeadResult(
            size_bytes=head.get("ContentLength", 0),
            content_type=head.get("ContentType"),
            checksum_sha256_hex=sha256_base64_to_hex(checksum_b64) if checksum_b64 else None,
        )

    def promote_pending(self, pending_key: str) -> str:
        """Server-side copy from `{prefix}/pending/` to `{prefix}/final/`,
        then delete the pending object — never the other way around, and
        never a delete without a prior successful copy (§17/§18)."""
        pending_marker = f"{self.prefix}/pending/"
        if not pending_key.startswith(pending_marker):
            raise ValueError("La clave pendiente no pertenece a este prefijo")
        final_key = f"{self.prefix}/final/{pending_key[len(pending_marker):]}"
        self.client.copy_object(
            Bucket=self.bucket, Key=final_key, CopySource={"Bucket": self.bucket, "Key": pending_key}, **self._encryption_args(),
        )
        self.client.delete_object(Bucket=self.bucket, Key=pending_key)
        return final_key


def _is_not_found(exc) -> bool:
    code = exc.response.get("Error", {}).get("Code", "")
    return code in {"404", "NoSuchKey", "NotFound"}


def _safe_header_filename(filename: str) -> str:
    # Response-Content-Disposition rides inside a presigned query string;
    # keep it to a conservative ASCII subset so no header/query injection is
    # possible regardless of what original_filename historically contained.
    return "".join(c for c in filename if c.isalnum() or c in "._- ") or "artefacto"
