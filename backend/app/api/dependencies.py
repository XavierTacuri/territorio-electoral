from collections.abc import Callable
from uuid import UUID
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.security import TokenValidationError, decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
_CREDENTIALS = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No se pudieron validar las credenciales", headers={"WWW-Authenticate": "Bearer"})


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    try:
        payload = decode_access_token(token)
        user_id = UUID(str(payload["sub"]))
    except (TokenValidationError, ValueError): raise _CREDENTIALS
    user = UserRepository(db).get_by_id(user_id)
    if not user: raise _CREDENTIALS
    if payload.get("aud") == "browser" and payload.get("ver") != user.token_version:
        raise _CREDENTIALS
    return user


def get_current_active_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_active: raise HTTPException(status_code=403, detail="Usuario inactivo")
    return user


def require_roles(*codes: str) -> Callable[..., User]:
    accepted = {code.upper() for code in codes}
    def dependency(user: User = Depends(get_current_active_user)) -> User:
        if not user.is_superuser and not accepted.intersection(role.code for role in user.roles):
            raise HTTPException(status_code=403, detail="Permisos insuficientes")
        return user
    return dependency


require_admin = require_roles("ADMIN")
