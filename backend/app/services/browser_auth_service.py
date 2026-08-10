import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, verify_password
from app.models.security import AuthSession
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import BrowserToken
from app.schemas.user import UserRead
from app.services.exceptions import AuthenticationError
from app.services.security_audit_service import SecurityAuditService


class BrowserAuthService:
    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db)
        self.audit = SecurityAuditService(db)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _random_token() -> str:
        return secrets.token_urlsafe(48)

    @staticmethod
    def _hash(value: str) -> str:
        return hmac.new(settings.browser_refresh_token_hmac_secret.encode(), value.encode(), hashlib.sha256).hexdigest()

    def _access(self, user: User) -> BrowserToken:
        return BrowserToken(access_token=create_access_token(
            user.id, timedelta(minutes=settings.browser_access_token_minutes), token_version=user.token_version
        ), expires_in=settings.browser_access_token_minutes * 60, user=UserRead.model_validate(user))

    def _new_session(self, user: User, family_id: UUID | None = None) -> tuple[AuthSession, str, str]:
        refresh, csrf = self._random_token(), self._random_token()
        session = AuthSession(user_id=user.id, family_id=family_id or uuid4(),
            refresh_token_hash=self._hash(refresh), csrf_token_hash=self._hash(csrf),
            expires_at=self._now() + timedelta(days=settings.browser_refresh_token_days))
        self.db.add(session)
        return session, refresh, csrf

    def login(self, identifier: str, password: str) -> tuple[BrowserToken, str, str]:
        user = self.users.get_by_identifier(identifier)
        if not user or not verify_password(password, user.hashed_password) or not user.is_active:
            self.audit.record("LOGIN_FAILURE", "FAILURE", "Intento de inicio de sesión rechazado")
            self.db.commit()
            raise AuthenticationError("Las credenciales ingresadas no son válidas.")
        active = self.db.scalars(select(AuthSession).where(AuthSession.user_id == user.id,
            AuthSession.revoked_at.is_(None), AuthSession.expires_at > self._now())
            .order_by(AuthSession.created_at.asc())).all()
        for old in active[:max(0, len(active) - settings.browser_max_active_sessions + 1)]:
            old.revoked_at, old.revocation_reason = self._now(), "SESSION_LIMIT"
        _, refresh, csrf = self._new_session(user)
        user.last_login_at = self._now()
        self.audit.record("LOGIN_SUCCESS", "SUCCESS", "Inicio de sesión de navegador exitoso", user_id=user.id)
        self.db.commit()
        return self._access(user), refresh, csrf

    def refresh(self, refresh: str, csrf: str) -> tuple[BrowserToken, str, str]:
        token_hash = self._hash(refresh)
        session = self.db.scalar(select(AuthSession).where(AuthSession.refresh_token_hash == token_hash))
        if not session:
            raise AuthenticationError("Sesión no válida")
        if session.revoked_at is not None:
            self.db.execute(update(AuthSession).where(AuthSession.family_id == session.family_id,
                AuthSession.revoked_at.is_(None)).values(revoked_at=self._now(), revocation_reason="TOKEN_REUSE"))
            self.audit.record("REFRESH_TOKEN_REUSE", "FAILURE", "Se revocó una familia por reutilización",
                user_id=session.user_id)
            self.db.commit()
            raise AuthenticationError("Sesión no válida")
        now = self._now()
        expires = session.expires_at if session.expires_at.tzinfo else session.expires_at.replace(tzinfo=timezone.utc)
        if expires <= now or not hmac.compare_digest(session.csrf_token_hash, self._hash(csrf)):
            raise AuthenticationError("Sesión no válida")
        user = self.users.get_by_id(session.user_id)
        if not user or not user.is_active:
            session.revoked_at, session.revocation_reason = now, "USER_INACTIVE"
            self.db.commit()
            raise AuthenticationError("Sesión no válida")
        replacement, new_refresh, new_csrf = self._new_session(user, session.family_id)
        self.db.flush()
        session.revoked_at, session.last_used_at = now, now
        session.revocation_reason, session.replaced_by_session_id = "ROTATED", replacement.id
        self.audit.record("TOKEN_REFRESH", "SUCCESS", "Token de navegador renovado", user_id=user.id)
        self.db.commit()
        return self._access(user), new_refresh, new_csrf

    def session(self, refresh: str) -> User:
        session = self.db.scalar(select(AuthSession).where(AuthSession.refresh_token_hash == self._hash(refresh)))
        if not session or session.revoked_at is not None:
            raise AuthenticationError("Sesión no válida")
        expires = session.expires_at if session.expires_at.tzinfo else session.expires_at.replace(tzinfo=timezone.utc)
        user = self.users.get_by_id(session.user_id)
        if expires <= self._now() or not user or not user.is_active:
            raise AuthenticationError("Sesión no válida")
        return user

    def logout(self, refresh: str | None) -> None:
        if refresh:
            session = self.db.scalar(select(AuthSession).where(AuthSession.refresh_token_hash == self._hash(refresh)))
            if session and session.revoked_at is None:
                session.revoked_at, session.revocation_reason = self._now(), "LOGOUT"
                self.audit.record("LOGOUT", "SUCCESS", "Sesión de navegador cerrada", user_id=session.user_id)
        self.db.commit()

    def revoke_user_sessions(self, user: User, reason: str) -> None:
        user.token_version += 1
        self.db.execute(update(AuthSession).where(AuthSession.user_id == user.id,
            AuthSession.revoked_at.is_(None)).values(revoked_at=self._now(), revocation_reason=reason))
