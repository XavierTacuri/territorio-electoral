from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.role_repository import RoleRepository
from app.schemas.role import RoleRead

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("", response_model=list[RoleRead])
def list_roles(include_inactive: bool = Query(False), user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if include_inactive and not user.is_superuser and "ADMIN" not in {r.code for r in user.roles}:
        raise HTTPException(status_code=403, detail="Permisos insuficientes")
    return RoleRepository(db).list(active_only=not include_inactive)
