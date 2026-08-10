from math import ceil
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.security import hash_password
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserListResponse, UserRead, UserUpdate
from app.services.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.services.role_service import RoleService
from app.services.browser_auth_service import BrowserAuthService
from app.services.security_audit_service import SecurityAuditService


class UserService:
    def __init__(self, db: Session):
        self.db, self.repository, self.roles = db, UserRepository(db), RoleService(db)

    def _duplicates(self, email: str | None, username: str | None, exclude_id: UUID | None = None) -> None:
        if email:
            found = self.repository.get_by_email(email)
            if found and found.id != exclude_id: raise ConflictError("El email ya está registrado")
        if username:
            found = self.repository.get_by_username(username)
            if found and found.id != exclude_id: raise ConflictError("El username ya está registrado")

    def create(self, data: UserCreate, *, is_superuser: bool = False) -> User:
        self._duplicates(str(data.email), data.username)
        roles = self.roles.get_active_roles(data.role_codes)
        user = self.repository.create(email=str(data.email), username=data.username, first_name=data.first_name, last_name=data.last_name, hashed_password=hash_password(data.password), roles=roles, is_superuser=is_superuser)
        try:
            self.db.commit(); self.db.refresh(user)
        except IntegrityError as exc:
            self.db.rollback(); raise ConflictError("Email o username ya registrado") from exc
        return self.repository.get_by_id(user.id) or user

    def get(self, user_id: UUID) -> User:
        user = self.repository.get_by_id(user_id)
        if not user: raise NotFoundError("Usuario no encontrado")
        return user

    def list(self, page: int, page_size: int, search: str | None, is_active: bool | None, role_code: str | None) -> UserListResponse:
        items, total = self.repository.list(page, page_size, search, is_active, role_code)
        return UserListResponse(items=[UserRead.model_validate(x) for x in items], page=page, page_size=page_size, total=total, total_pages=ceil(total / page_size) if total else 0)

    def update(self, user_id: UUID, data: UserUpdate, actor: User) -> User:
        user = self.get(user_id); changes = data.model_dump(exclude_unset=True)
        self._duplicates(str(changes["email"]) if changes.get("email") else None, changes.get("username"), user.id)
        if "role_codes" in changes and changes["role_codes"] is None: raise BusinessRuleError("role_codes no puede ser null")
        new_roles = self.roles.get_active_roles(changes.pop("role_codes")) if "role_codes" in changes else None
        remains_admin = user.is_superuser or (new_roles is None and any(r.code == "ADMIN" for r in user.roles)) or (new_roles is not None and any(r.code == "ADMIN" for r in new_roles))
        remains_active = changes.get("is_active", user.is_active)
        if user.id == actor.id and self.repository.count_active_admins() == 1 and (not remains_admin or not remains_active):
            raise BusinessRuleError("No se puede desactivar o quitar el rol al único administrador activo")
        for field, value in changes.items():
            if value is None: raise BusinessRuleError(f"{field} no puede ser null")
            setattr(user, field, value)
        critical_change = (new_roles is not None and {r.code for r in new_roles} != {r.code for r in user.roles}) or (
            "is_active" in changes and not changes["is_active"])
        if new_roles is not None: user.roles = new_roles
        if critical_change:
            BrowserAuthService(self.db).revoke_user_sessions(user, "PERMISSIONS_CHANGED")
            SecurityAuditService(self.db).record("ROLE_CHANGED" if new_roles is not None else "USER_DISABLED",
                "SUCCESS", "Se actualizaron permisos críticos", user_id=user.id)
        try: self.db.commit(); self.db.refresh(user)
        except IntegrityError as exc: self.db.rollback(); raise ConflictError("Email o username ya registrado") from exc
        return self.repository.get_by_id(user.id) or user

    def change_password(self, user_id: UUID, new_password: str) -> None:
        user = self.get(user_id)
        user.hashed_password = hash_password(new_password)
        BrowserAuthService(self.db).revoke_user_sessions(user, "PASSWORD_CHANGED")
        SecurityAuditService(self.db).record("PASSWORD_CHANGED", "SUCCESS",
            "Contraseña actualizada y sesiones revocadas", user_id=user.id)
        self.db.commit()
