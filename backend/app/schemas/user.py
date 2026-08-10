import re
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from app.core.security import validate_password
from app.schemas.role import RoleSummary


def normalize_username(value: str) -> str:
    value = value.strip().lower()
    if not value or re.search(r"\s", value):
        raise ValueError("El username no puede estar vacío ni contener espacios")
    return value


def clean_name(value: str) -> str:
    value = " ".join(value.split())
    if not value:
        raise ValueError("El nombre no puede estar vacío")
    return value


def normalize_roles(values: list[str]) -> list[str]:
    normalized = [value.strip().upper() for value in values]
    if not normalized:
        raise ValueError("Se requiere al menos un rol")
    if len(normalized) != len(set(normalized)):
        raise ValueError("No se permiten roles repetidos")
    return normalized


class UserCreate(BaseModel):
    email: EmailStr
    username: str
    first_name: str
    last_name: str
    password: str
    role_codes: list[str]
    model_config = ConfigDict(extra="forbid")

    @field_validator("email", mode="before")
    @classmethod
    def email_lower(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("username")
    @classmethod
    def username_valid(cls, value: str) -> str:
        return normalize_username(value)

    @field_validator("first_name", "last_name")
    @classmethod
    def names_valid(cls, value: str) -> str:
        return clean_name(value)

    @field_validator("password")
    @classmethod
    def password_valid(cls, value: str) -> str:
        validate_password(value)
        return value

    @field_validator("role_codes")
    @classmethod
    def roles_valid(cls, value: list[str]) -> list[str]:
        return normalize_roles(value)


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    is_active: bool | None = None
    role_codes: list[str] | None = None
    model_config = ConfigDict(extra="forbid")

    @field_validator("email", mode="before")
    @classmethod
    def email_lower(cls, value: str | None) -> str | None:
        return value.strip().lower() if value is not None else None

    @field_validator("username")
    @classmethod
    def username_valid(cls, value: str | None) -> str | None:
        return normalize_username(value) if value is not None else None

    @field_validator("first_name", "last_name")
    @classmethod
    def names_valid(cls, value: str | None) -> str | None:
        return clean_name(value) if value is not None else None

    @field_validator("role_codes")
    @classmethod
    def roles_valid(cls, value: list[str] | None) -> list[str] | None:
        return normalize_roles(value) if value is not None else None


class UserSummary(BaseModel):
    id: UUID
    email: str
    username: str
    first_name: str
    last_name: str
    model_config = ConfigDict(from_attributes=True)


class UserRead(UserSummary):
    is_active: bool
    is_superuser: bool
    roles: list[RoleSummary]


class UserListResponse(BaseModel):
    items: list[UserRead]
    page: int
    page_size: int
    total: int
    total_pages: int


class PasswordChange(BaseModel):
    new_password: str
    model_config = ConfigDict(extra="forbid")

    @field_validator("new_password")
    @classmethod
    def password_valid(cls, value: str) -> str:
        validate_password(value)
        return value


class MessageResponse(BaseModel):
    message: str
