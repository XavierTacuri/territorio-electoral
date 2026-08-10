from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4
import jwt
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from app.core.config import settings

_password_hash = PasswordHash.recommended()


class TokenValidationError(ValueError):
    pass


def validate_password(password: str) -> None:
    if len(password) < 8 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise ValueError("La contraseña debe tener al menos 8 caracteres, una letra y un número")


def hash_password(password: str) -> str:
    validate_password(password)
    return _password_hash.hash(password)


def hash_local_development_password(password: str) -> str:
    """Hash an intentionally weak credential for an explicit local-only setup."""
    if settings.app_env.lower() != "development":
        raise ValueError("Las credenciales locales solo pueden configurarse en development")
    return _password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return _password_hash.verify(password, hashed_password)
    except Exception:
        return False


def create_access_token(subject: UUID | str, expires_delta: timedelta | None = None, *, token_version: int | None = None) -> str:
    now = datetime.now(timezone.utc)
    expires = now + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    payload: dict[str, Any] = {"sub": str(subject), "iat": now, "exp": expires, "type": "access", "jti": str(uuid4())}
    if token_version is not None:
        payload["ver"] = token_version
        payload["aud"] = "browser"
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm], options={"require": ["sub", "exp", "iat", "type"], "verify_aud": False})
        if payload.get("type") != "access":
            raise TokenValidationError("Token inválido")
        UUID(str(payload["sub"]))
        return payload
    except (InvalidTokenError, ValueError, TypeError, KeyError) as exc:
        raise TokenValidationError("Token inválido") from exc
