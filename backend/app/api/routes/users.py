from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.api.dependencies import require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import MessageResponse, PasswordChange, UserCreate, UserListResponse, UserRead, UserUpdate
from app.services.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"], dependencies=[])


def translate(exc: Exception) -> HTTPException:
    if isinstance(exc, ConflictError): return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, NotFoundError): return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreate, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    try: return UserService(db).create(data)
    except (ConflictError, BusinessRuleError) as exc: raise translate(exc)


@router.get("", response_model=UserListResponse)
def list_users(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), search: str | None = None, is_active: bool | None = None, role_code: str | None = None, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return UserService(db).list(page, page_size, search, is_active, role_code)


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: UUID, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    try: return UserService(db).get(user_id)
    except NotFoundError as exc: raise translate(exc)


@router.patch("/{user_id}", response_model=UserRead)
def update_user(user_id: UUID, data: UserUpdate, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    try: return UserService(db).update(user_id, data, actor)
    except (ConflictError, BusinessRuleError, NotFoundError) as exc: raise translate(exc)


@router.post("/{user_id}/change-password", response_model=MessageResponse)
def change_password(user_id: UUID, data: PasswordChange, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    try: UserService(db).change_password(user_id, data.new_password, actor=actor)
    except NotFoundError as exc: raise translate(exc)
    return MessageResponse(message="Contraseña actualizada correctamente")
