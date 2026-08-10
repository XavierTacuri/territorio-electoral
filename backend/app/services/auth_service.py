from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.security import create_access_token, verify_password
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import Token
from app.services.exceptions import AuthenticationError, InactiveUserError


class AuthService:
    def __init__(self, db: Session): self.db, self.repository = db, UserRepository(db)
    def authenticate(self, identifier: str, password: str) -> tuple[User, Token]:
        user = self.repository.get_by_identifier(identifier)
        if not user or not verify_password(password, user.hashed_password): raise AuthenticationError("Credenciales incorrectas")
        if not user.is_active: raise InactiveUserError("Usuario inactivo")
        user.last_login_at = datetime.now(timezone.utc); self.db.commit()
        return user, Token(access_token=create_access_token(user.id), expires_in=settings.access_token_expire_minutes * 60)
