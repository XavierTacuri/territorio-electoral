"""Signed, opaque token binding a presigned S3 upload to exactly the request
that authorized it (§15 Fase 4A).

This is NOT a login/access token reused for a new purpose: it uses its own
`type`/`aud` claims (PyJWT rejects a mismatched `aud` on decode) and carries
a completely different payload — every fact `complete()` needs to
re-authorize the request without trusting anything the client could tamper
with (campaign/operation/act/revision/user identity, the exact pending S3
key, the declared size/mime/sha256). It borrows the same crypto primitives
and secret as `app.core.security` (PyJWT + `settings.secret_key`) because
introducing a second signing mechanism for this would be needless, not
because this token IS a login token.

Never persisted (DB or logs) — it exists only in the intent response and the
immediate complete request that follows it.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import jwt
from jwt import InvalidTokenError

from app.core.config import settings
from app.core.security import TokenValidationError

_AUDIENCE = "artifact-upload"
_TYPE = "artifact_upload"
_REQUIRED_CLAIMS = [
    "sub", "iat", "exp", "type", "aud", "jti",
    "campaign_id", "operation_id", "act_id", "revision_id", "user_id",
    "pending_key", "size_bytes", "mime_type", "sha256", "original_filename",
]


def create_artifact_upload_token(
    *,
    campaign_id: UUID,
    operation_id: UUID,
    act_id: UUID,
    revision_id: UUID,
    user_id: UUID,
    client_generated_id: UUID | None,
    pending_key: str,
    size_bytes: int,
    mime_type: str,
    sha256: str,
    original_filename: str,
    expires_in_seconds: int,
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id), "iat": now, "exp": now + timedelta(seconds=expires_in_seconds),
        "type": _TYPE, "aud": _AUDIENCE, "jti": str(uuid4()),
        "campaign_id": str(campaign_id), "operation_id": str(operation_id), "act_id": str(act_id),
        "revision_id": str(revision_id), "user_id": str(user_id),
        "client_generated_id": str(client_generated_id) if client_generated_id else None,
        "pending_key": pending_key, "size_bytes": size_bytes, "mime_type": mime_type, "sha256": sha256,
        # Already sanitized (safe_evidence_filename) by the caller at intent
        # time — never the raw client-supplied string, and never used to
        # derive a path/key, only stored back as ElectionActEvidence
        # metadata by complete() (§4 audit).
        "original_filename": original_filename,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_artifact_upload_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.jwt_algorithm],
            audience=_AUDIENCE, options={"require": _REQUIRED_CLAIMS},
        )
        if payload.get("type") != _TYPE:
            raise TokenValidationError("Token de carga inválido")
        for key in ("campaign_id", "operation_id", "act_id", "revision_id", "user_id"):
            UUID(str(payload[key]))
        if payload.get("client_generated_id") is not None:
            UUID(str(payload["client_generated_id"]))
        return payload
    except (InvalidTokenError, ValueError, TypeError, KeyError) as exc:
        raise TokenValidationError("Token de carga inválido") from exc
