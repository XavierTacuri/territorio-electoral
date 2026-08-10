from pydantic import BaseModel, ConfigDict


class RoleSummary(BaseModel):
    code: str
    name: str
    model_config = ConfigDict(from_attributes=True)


class RoleRead(RoleSummary):
    id: int
    description: str | None
    is_active: bool
