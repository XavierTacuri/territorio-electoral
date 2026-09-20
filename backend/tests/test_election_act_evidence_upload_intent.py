"""§39/§40 Fase 4A: upload-intent + complete direct-to-S3 flow for
ElectionActEvidence. Uses an in-memory fake standing in for S3 (never
real AWS, never even botocore) so every idempotency/failure-mode scenario is
fast and deterministic; app/services/artifact_storage.py's own S3 semantics
are covered separately in test_artifact_storage_s3.py."""

import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models.election_day import ElectionActEvidence
from app.schemas.election_day import ElectionDayAdminSupportStartRequest, ElectionDayAssignmentCreate, ElectionDayCloseRequest
from app.services.artifact_storage import HeadResult, PresignedUpload, RemoteArtifactDownload, S3ArtifactStorage
from app.services.artifact_upload_token import create_artifact_upload_token
from app.services.election_act_service import ElectionActService
from app.services.election_day_admin_support_service import ElectionDayAdminSupportService
from app.services.election_day_service import ElectionDayService
from app.services.exceptions import BusinessRuleError

from tests.test_election_acts import _draft, _member, acts_ready  # noqa: F401
from tests.test_election_day import _board, _election_day_dataset, _polling_place


class SimulatedS3ChecksumRejection(Exception):
    """Stands in for the real S3 400 a presigned POST gets when the bytes it
    receives don't hash to the x-amz-checksum-sha256 the policy declared —
    the object is never stored server-side (§2/§3 Fase 4A audit)."""


class FakeS3EvidenceStorage(S3ArtifactStorage):
    """In-memory stand-in for S3ArtifactStorage — real network calls would
    make these tests flaky/slow/AWS-dependent for no benefit; the actual S3
    wire semantics (presigned POST fields, SSE, HEAD parsing, the native
    checksum request/response shape) are covered against botocore's Stubber
    in test_artifact_storage_s3.py. What this fake DOES faithfully model is
    the property that matters for these service-level tests: S3 computes
    the checksum from the real bytes it receives and refuses to store
    anything that doesn't match what the presigned policy declared — a test
    here can't silently "upload" mismatched bytes the way the old
    client-declared-metadata design could."""

    def __init__(self):
        super().__init__(client=None, bucket="test-bucket", prefix="evidence", max_file_mb=15, presign_expires_seconds=300)
        self.objects: dict[str, dict] = {}
        self._declared_checksums: dict[str, str] = {}

    def presign_upload(self, key, *, content_type, max_bytes, sha256_hex):
        self._declared_checksums[key] = sha256_hex
        return PresignedUpload(
            url="https://test-bucket.s3.amazonaws.com/",
            fields={"key": key, "Content-Type": content_type, "x-amz-checksum-sha256": sha256_hex},
            key=key, expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.presign_expires_seconds),
        )

    def simulate_browser_upload(self, key, *, data: bytes, content_type: str):
        """Test-only helper standing in for the real browser->S3 POST: like
        real S3, the checksum stored is computed from `data`, not trusted
        from any caller-supplied value — and the "upload" is refused if it
        doesn't match what presign_upload declared for this key."""
        actual_sha256 = hashlib.sha256(data).hexdigest()
        declared = self._declared_checksums.get(key)
        if declared is not None and actual_sha256 != declared:
            raise SimulatedS3ChecksumRejection(f"checksum mismatch for {key}")
        self.objects[key] = {"size": len(data), "content_type": content_type, "sha256": actual_sha256}

    def force_store_pending_object(self, key, *, size_bytes, content_type, sha256_hex):
        """Defense-in-depth test helper only: writes directly to the fake
        bucket bypassing checksum enforcement, standing in for "whatever
        ended up in the object" regardless of how — e.g. a non-AWS
        S3-compatible endpoint that doesn't enforce additional checksums as
        strictly. Real AWS S3 would already have refused this at POST time
        (see test_artifact_storage_s3.py); this exercises complete()'s own
        independent HEAD-vs-token comparison as a second layer."""
        self.objects[key] = {"size": size_bytes, "content_type": content_type, "sha256": sha256_hex}

    def store(self, source, extension):
        # API_PROXY-mode uploads (still exercised here alongside the direct
        # flow, e.g. to reach a SUBMITTED revision) go through this path too.
        data = source.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        key = self._new_key(extension)
        mime = {"jpg": "image/jpeg", "png": "image/png"}[extension.lower()]
        self.objects[key] = {"size": len(data), "content_type": mime, "sha256": digest}
        return key, len(data), digest

    def head_metadata(self, key):
        obj = self.objects.get(key)
        if not obj:
            return None
        return HeadResult(size_bytes=obj["size"], content_type=obj["content_type"], checksum_sha256_hex=obj["sha256"])

    def promote_pending(self, pending_key):
        obj = self.objects.pop(pending_key)
        final_key = pending_key.replace("/pending/", "/final/")
        self.objects[final_key] = obj
        return final_key

    def delete(self, key):
        return self.objects.pop(key, None) is not None

    def exists(self, key):
        return key in self.objects

    def download(self, key, *, filename=None, content_type=None):
        return RemoteArtifactDownload(url=f"https://test-bucket.s3.amazonaws.com/{key}", expires_at=datetime.now(timezone.utc) + timedelta(seconds=60))


JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 64
JPEG_SHA256 = hashlib.sha256(JPEG_BYTES).hexdigest()


def _intent_request(**overrides):
    values = dict(client_generated_id=None, original_filename="acta.jpg", mime_type="image/jpeg", size_bytes=len(JPEG_BYTES), sha256=JPEG_SHA256)
    values.update(overrides)
    return values


def _draft_act(db, ctx):
    service = ElectionActService(db, storage=FakeS3EvidenceStorage())
    act, revision = service.create_draft(ctx["campaign"].id, _draft(ctx), ctx["delegate"])
    return service, act, revision


def _complete_happy_path(db, ctx):
    service, act, revision = _draft_act(db, ctx)
    intent = service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], **_intent_request())
    assert intent.mode == "PRESIGNED_S3"
    pending_key = intent.fields["key"]
    service.storage.simulate_browser_upload(pending_key, data=JPEG_BYTES, content_type="image/jpeg")
    evidence = service.complete_upload(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], upload_token=intent.upload_token)
    return service, act, revision, evidence


# ---------- upload-intent (§39) ----------

def test_intent_mode_is_presigned_s3_when_storage_is_s3(db, acts_ready):
    ctx = acts_ready
    service, act, revision = _draft_act(db, ctx)
    intent = service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], **_intent_request())
    assert intent.mode == "PRESIGNED_S3" and intent.url and intent.fields and intent.upload_token


def test_intent_mode_is_api_proxy_when_storage_is_local(db, acts_ready):
    ctx = acts_ready
    service = ElectionActService(db)  # default factory-built storage: local in tests
    act, revision = service.create_draft(ctx["campaign"].id, _draft(ctx), ctx["delegate"])
    intent = service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], **_intent_request())
    assert intent.mode == "API_PROXY" and intent.url is None and intent.upload_token is None


def test_intent_delegate_correct_recinto_succeeds(db, acts_ready):
    ctx = acts_ready
    service, act, revision = _draft_act(db, ctx)
    intent = service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], **_intent_request())
    assert intent.mode == "PRESIGNED_S3"


def test_intent_rejected_for_delegate_of_another_recinto(db, admin, acts_ready):
    ctx = acts_ready
    other_place = _polling_place(db, ctx["process"], ctx["canton"], ctx["parish_b"], code="R99", name="Otro recinto")
    other_delegate = _member(db, admin, ctx["campaign"])
    ElectionDayService(db).create_assignment(
        ctx["campaign"].id, ElectionDayAssignmentCreate(user_id=other_delegate.id, assignment_role="POLLING_PLACE_DELEGATE", polling_place_id=other_place.id), ctx["executive"],
    )
    service, act, revision = _draft_act(db, ctx)
    with pytest.raises(PermissionError):
        service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, other_delegate, **_intent_request())


def test_intent_rejected_for_validator(db, acts_ready):
    ctx = acts_ready
    service, act, revision = _draft_act(db, ctx)
    with pytest.raises(PermissionError):
        service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["validator"], **_intent_request())


def test_intent_rejected_for_candidate_manager(db, admin, acts_ready):
    ctx = acts_ready
    service, act, revision = _draft_act(db, ctx)
    with pytest.raises(PermissionError):
        service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["executive"], **_intent_request())
    manager = _member(db, admin, ctx["campaign"], "CAMPAIGN_MANAGER")
    with pytest.raises(PermissionError):
        service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, manager, **_intent_request())


def test_intent_rejected_for_admin_without_support(db, acts_ready):
    ctx = acts_ready
    service, act, revision = _draft_act(db, ctx)
    with pytest.raises(PermissionError):
        service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["admin"], **_intent_request())


def test_intent_rejected_for_admin_with_support_session(db, acts_ready):
    # §11/§19 Jornada Electoral: ADMIN Support is read/oversight-only — it
    # never creates evidence, even with an active support session.
    ctx = acts_ready
    ElectionDayAdminSupportService(db).start(ctx["campaign"].id, ElectionDayAdminSupportStartRequest(reason="Cobertura de emergencia"), ctx["admin"])
    service, act, revision = _draft_act(db, ctx)
    with pytest.raises(PermissionError):
        service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["admin"], **_intent_request())


def test_intent_rejected_when_operation_closed(db, acts_ready):
    ctx = acts_ready
    service, act, revision = _draft_act(db, ctx)
    ElectionDayService(db).close_operation(ctx["campaign"].id, ElectionDayCloseRequest(), ctx["executive"])
    with pytest.raises(BusinessRuleError):
        service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], **_intent_request())


def test_intent_rejected_when_revision_submitted(db, acts_ready):
    ctx = acts_ready
    service, act, revision = _draft_act(db, ctx)
    ev = service.upload_evidence(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], file_bytes=JPEG_BYTES, original_filename="a.jpg", client_generated_id=None)
    assert ev.id
    service.submit_revision(ctx["campaign"].id, act.id, revision.id, ctx["delegate"])
    with pytest.raises(BusinessRuleError):
        service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], **_intent_request())


def test_intent_rejects_invalid_mime(db, acts_ready):
    ctx = acts_ready
    service, act, revision = _draft_act(db, ctx)
    with pytest.raises(BusinessRuleError):
        service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], **_intent_request(mime_type="application/pdf"))


def test_intent_rejects_oversized_declared_size(db, acts_ready):
    ctx = acts_ready
    service, act, revision = _draft_act(db, ctx)
    with pytest.raises(BusinessRuleError):
        service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], **_intent_request(size_bytes=999_999_999))


def test_intent_rejects_malformed_sha256_at_schema_level():
    from pydantic import ValidationError

    from app.schemas.election_act import ElectionActEvidenceUploadIntentRequest
    with pytest.raises(ValidationError):
        ElectionActEvidenceUploadIntentRequest(original_filename="a.jpg", mime_type="image/jpeg", size_bytes=10, sha256="not-a-hash")


def test_intent_already_completed_returns_existing_evidence_id_without_new_presign(db, acts_ready):
    ctx = acts_ready
    cid = uuid4()
    service, act, revision = _draft_act(db, ctx)
    intent1 = service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], **_intent_request(client_generated_id=cid))
    service.storage.simulate_browser_upload(intent1.fields["key"], data=JPEG_BYTES, content_type="image/jpeg")
    created = service.complete_upload(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], upload_token=intent1.upload_token)
    intent2 = service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], **_intent_request(client_generated_id=cid))
    assert intent2.mode == "ALREADY_COMPLETED" and intent2.evidence_id == created.id and intent2.url is None


# ---------- complete (§40) ----------

def test_complete_success_creates_one_evidence(db, acts_ready):
    ctx = acts_ready
    service, act, revision, evidence = _complete_happy_path(db, ctx)
    assert evidence.mime_type == "image/jpeg" and evidence.size_bytes == len(JPEG_BYTES) and evidence.sha256 == JPEG_SHA256
    assert evidence.storage_key.startswith("evidence/final/")
    total = db.scalar(select(func.count()).select_from(ElectionActEvidence).where(ElectionActEvidence.revision_id == revision.id))
    assert total == 1


# ---------- original_filename preservation (§4 audit) ----------


def _complete_with_filename(db, ctx, original_filename):
    service, act, revision = _draft_act(db, ctx)
    intent = service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], **_intent_request(original_filename=original_filename))
    service.storage.simulate_browser_upload(intent.fields["key"], data=JPEG_BYTES, content_type="image/jpeg")
    return service.complete_upload(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], upload_token=intent.upload_token)


def test_original_filename_normal_is_preserved_sanitized(db, acts_ready):
    from app.services.evidence_security_service import safe_evidence_filename

    evidence = _complete_with_filename(db, acts_ready, "acta-recinto-12.jpg")
    assert evidence.original_filename == safe_evidence_filename("acta-recinto-12.jpg", "jpg")
    assert evidence.original_filename != "acta.jpg"  # not the generic fallback


def test_original_filename_unicode_is_preserved_reasonably(db, acts_ready):
    from app.services.evidence_security_service import safe_evidence_filename

    evidence = _complete_with_filename(db, acts_ready, "acta-junta-áéíóúñ.jpg")
    assert evidence.original_filename == safe_evidence_filename("acta-junta-áéíóúñ.jpg", "jpg")
    assert "á" in evidence.original_filename or "acta-junta" in evidence.original_filename


def test_original_filename_path_traversal_is_neutralized(db, acts_ready):
    evidence = _complete_with_filename(db, acts_ready, "../../etc/passwd.jpg")
    assert "/" not in evidence.original_filename and ".." not in evidence.original_filename
    assert evidence.original_filename.endswith(".jpg")


def test_original_filename_too_long_is_truncated(db, acts_ready):
    evidence = _complete_with_filename(db, acts_ready, ("a" * 500) + ".jpg")
    # safe_evidence_filename caps the normalized stem at 180 chars, plus ".jpg".
    assert len(evidence.original_filename) <= 185


def test_original_filename_blank_falls_back_to_generic_name(db, acts_ready):
    evidence = _complete_with_filename(db, acts_ready, " ")
    assert evidence.original_filename == "evidencia.jpg"


def test_original_filename_never_influences_storage_key(db, acts_ready):
    evidence = _complete_with_filename(db, acts_ready, "../../../secret-path.jpg")
    assert "secret" not in evidence.storage_key and ".." not in evidence.storage_key


def test_complete_object_missing_raises(db, acts_ready):
    ctx = acts_ready
    service, act, revision = _draft_act(db, ctx)
    intent = service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], **_intent_request())
    # Never actually "upload" anything — the pending object never exists.
    with pytest.raises(BusinessRuleError):
        service.complete_upload(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], upload_token=intent.upload_token)


def test_upload_rejected_by_s3_when_bytes_dont_match_declared_checksum(db, acts_ready):
    """§2 audit, escenario B: bytes distintos al checksum declarado. Real S3
    rechaza el POST antes de almacenar nada (nunca queda objeto en pending/);
    aquí lo simulamos rechazando en simulate_browser_upload, exactamente
    como haría la validación nativa x-amz-checksum-sha256 de S3."""
    ctx = acts_ready
    service, act, revision = _draft_act(db, ctx)
    intent = service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], **_intent_request())
    wrong_bytes = JPEG_BYTES + b"tampered"
    with pytest.raises(SimulatedS3ChecksumRejection):
        service.storage.simulate_browser_upload(intent.fields["key"], data=wrong_bytes, content_type="image/jpeg")
    # The rejected upload never created a pending object — complete() must
    # behave exactly like "nunca se subió nada" (already-covered path).
    with pytest.raises(BusinessRuleError):
        service.complete_upload(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], upload_token=intent.upload_token)
    assert not service.storage.exists(intent.fields["key"])


def test_complete_rejects_size_mismatch_defense_in_depth(db, acts_ready):
    """§2 audit, escenario C: aunque S3 ya habría rechazado esto en la
    subida real, complete() verifica independientemente contra lo que HEAD
    reporta — segunda capa, no la única, para un endpoint S3-compatible que
    no aplicara el checksum nativo tan estrictamente."""
    ctx = acts_ready
    service, act, revision = _draft_act(db, ctx)
    intent = service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], **_intent_request())
    service.storage.force_store_pending_object(intent.fields["key"], size_bytes=999, content_type="image/jpeg", sha256_hex=JPEG_SHA256)
    with pytest.raises(BusinessRuleError):
        service.complete_upload(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], upload_token=intent.upload_token)


def test_complete_rejects_mime_mismatch_defense_in_depth(db, acts_ready):
    ctx = acts_ready
    service, act, revision = _draft_act(db, ctx)
    intent = service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], **_intent_request())
    service.storage.force_store_pending_object(intent.fields["key"], size_bytes=len(JPEG_BYTES), content_type="image/png", sha256_hex=JPEG_SHA256)
    with pytest.raises(BusinessRuleError):
        service.complete_upload(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], upload_token=intent.upload_token)


def test_complete_rejects_checksum_mismatch_defense_in_depth(db, acts_ready):
    ctx = acts_ready
    service, act, revision = _draft_act(db, ctx)
    intent = service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], **_intent_request())
    service.storage.force_store_pending_object(intent.fields["key"], size_bytes=len(JPEG_BYTES), content_type="image/jpeg", sha256_hex="b" * 64)
    with pytest.raises(BusinessRuleError):
        service.complete_upload(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], upload_token=intent.upload_token)
    # A rejected checksum must never promote the pending object nor create evidence.
    assert not service.storage.exists(f"evidence/final/{intent.fields['key'].rsplit('/', 1)[-1]}")
    total = db.scalar(select(func.count()).select_from(ElectionActEvidence).where(ElectionActEvidence.revision_id == revision.id))
    assert total == 0


def test_complete_rejects_expired_token(db, acts_ready):
    ctx = acts_ready
    service, act, revision = _draft_act(db, ctx)
    op = ElectionDayService(db)._require_operation(ctx["campaign"].id)
    token = create_artifact_upload_token(
        campaign_id=ctx["campaign"].id, operation_id=op.id, act_id=act.id, revision_id=revision.id, user_id=ctx["delegate"].id,
        client_generated_id=None, pending_key="evidence/pending/x.jpg", size_bytes=1, mime_type="image/jpeg", sha256="a" * 64,
        original_filename="acta.jpg", expires_in_seconds=-10,
    )
    with pytest.raises(BusinessRuleError):
        service.complete_upload(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], upload_token=token)


def test_complete_rejects_manipulated_token(db, acts_ready):
    ctx = acts_ready
    service, act, revision = _draft_act(db, ctx)
    intent = service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], **_intent_request())
    with pytest.raises(BusinessRuleError):
        service.complete_upload(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], upload_token=intent.upload_token + "tampered")


def test_complete_rejects_token_issued_for_another_user(db, admin, acts_ready):
    ctx = acts_ready
    service, act, revision = _draft_act(db, ctx)
    intent = service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], **_intent_request())
    service.storage.simulate_browser_upload(intent.fields["key"], data=JPEG_BYTES, content_type="image/jpeg")
    other_delegate = _member(db, admin, ctx["campaign"])
    with pytest.raises(PermissionError):
        service.complete_upload(ctx["campaign"].id, act.id, revision.id, other_delegate, upload_token=intent.upload_token)


def test_complete_rejects_token_issued_for_another_campaign(db, admin, acts_ready):
    ctx = acts_ready
    other_campaign, *_ = _election_day_dataset(db, admin, 81)
    service, act, revision = _draft_act(db, ctx)
    intent = service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], **_intent_request())
    with pytest.raises(PermissionError):
        service.complete_upload(other_campaign.id, act.id, revision.id, ctx["delegate"], upload_token=intent.upload_token)


def test_complete_rejects_token_issued_for_another_revision(db, acts_ready):
    ctx = acts_ready
    service, act, revision = _draft_act(db, ctx)
    intent = service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], **_intent_request())
    other_board = _board(db, ctx["place"], code="J02", number=2)
    other_draft = _draft(ctx)
    other_draft.electoral_board_id = other_board.id
    act2, revision2 = service.create_draft(ctx["campaign"].id, other_draft, ctx["delegate"])
    with pytest.raises(PermissionError):
        service.complete_upload(ctx["campaign"].id, act2.id, revision2.id, ctx["delegate"], upload_token=intent.upload_token)


def test_complete_retry_with_same_client_generated_id_does_not_duplicate(db, acts_ready):
    ctx = acts_ready
    cid = uuid4()
    service, act, revision = _draft_act(db, ctx)
    intent = service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], **_intent_request(client_generated_id=cid))
    service.storage.simulate_browser_upload(intent.fields["key"], data=JPEG_BYTES, content_type="image/jpeg")
    first = service.complete_upload(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], upload_token=intent.upload_token)
    second = service.complete_upload(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], upload_token=intent.upload_token)
    assert first.id == second.id
    total = db.scalar(select(func.count()).select_from(ElectionActEvidence).where(ElectionActEvidence.revision_id == revision.id))
    assert total == 1


# ---------- Observabilidad (§20/§33): nunca loggear el token/URL ----------

def test_upload_token_and_presigned_fields_never_appear_in_logs(db, acts_ready, caplog):
    ctx = acts_ready
    with caplog.at_level("INFO", logger="territorio.storage"):
        service, act, revision = _draft_act(db, ctx)
        intent = service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], **_intent_request())
        service.storage.simulate_browser_upload(intent.fields["key"], data=JPEG_BYTES, content_type="image/jpeg")
        service.complete_upload(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], upload_token=intent.upload_token)
    secret_field_markers = ("signature", "policy", "credential", "security-token")
    secret_field_values = [v for k, v in (intent.fields or {}).items() if any(m in k.lower() for m in secret_field_markers)]
    sensitive_values = [intent.upload_token, intent.url, *secret_field_values]
    for record in caplog.records:
        rendered = record.getMessage() + str(getattr(record, "__dict__", {}))
        for value in sensitive_values:
            if value:
                assert value not in rendered
    # And the fixed set of extra keys the JSON formatter ever serializes
    # doesn't include a token/url/signature field in the first place.
    from app.core.observability import JsonFormatter

    formatter = JsonFormatter()
    for record in caplog.records:
        payload = formatter.format(record)
        for forbidden in ("upload_token", "presigned", "signature", "x-amz", intent.upload_token or "<none>"):
            assert forbidden not in payload


# ---------- Token isolation from login/access tokens (§5 audit) ----------


def test_login_access_token_cannot_be_used_as_upload_token(db, acts_ready):
    from app.core.security import create_access_token
    from app.services.artifact_upload_token import decode_artifact_upload_token
    from app.core.security import TokenValidationError as CoreTokenValidationError

    ctx = acts_ready
    login_token = create_access_token(ctx["delegate"].id)
    with pytest.raises(CoreTokenValidationError):
        decode_artifact_upload_token(login_token)


def test_upload_token_cannot_be_used_as_login_access_token(db, acts_ready):
    from app.core.security import TokenValidationError as CoreTokenValidationError, decode_access_token

    ctx = acts_ready
    service, act, revision = _draft_act(db, ctx)
    intent = service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], **_intent_request())
    with pytest.raises(CoreTokenValidationError):
        decode_access_token(intent.upload_token)


def test_upload_token_has_short_expiry_bound_to_presign_config(db, acts_ready):
    ctx = acts_ready
    service, act, revision = _draft_act(db, ctx)
    from app.core.config import settings as app_settings

    intent = service.create_upload_intent(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], **_intent_request())
    ttl = (intent.expires_at - datetime.now(timezone.utc)).total_seconds()
    assert 0 < ttl <= app_settings.s3_presign_expires_seconds + 1
