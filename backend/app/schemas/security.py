from datetime import date
from uuid import UUID
from pydantic import BaseModel


class SecurityAuditEventRead(BaseModel):
    id: UUID
    event_type: str
    outcome: str
    event_date: date
    user_id: UUID | None
    campaign_id: UUID | None
    resource_type: str | None
    resource_id: UUID | None
    description: str
    metadata: dict


class SecurityAuditEventList(BaseModel):
    items: list[SecurityAuditEventRead]
    page: int
    page_size: int
    total: int
    total_pages: int
