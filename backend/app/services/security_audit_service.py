from datetime import date
from math import ceil
from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.security import SecurityAuditEvent
from app.schemas.security import SecurityAuditEventList, SecurityAuditEventRead


class SecurityAuditService:
    def __init__(self, db: Session):
        self.db = db

    def record(self, event_type: str, outcome: str, description: str, *, user_id: UUID | None = None,
               campaign_id: UUID | None = None, resource_type: str | None = None,
               resource_id: UUID | None = None, metadata: dict | None = None) -> SecurityAuditEvent:
        safe_metadata = {k: v for k, v in (metadata or {}).items() if k.lower() not in {
            "password", "token", "refresh_token", "csrf_token", "ip", "user_agent", "path",
            "submission_key", "hash"
        }}
        event = SecurityAuditEvent(event_type=event_type, outcome=outcome, event_date=date.today(),
            user_id=user_id, campaign_id=campaign_id, resource_type=resource_type,
            resource_id=resource_id, description=description, event_metadata=safe_metadata)
        self.db.add(event)
        return event

    def list(self, page: int, page_size: int, *, event_date: date | None = None,
             user_id: UUID | None = None, campaign_id: UUID | None = None,
             event_type: str | None = None, outcome: str | None = None,
             resource_type: str | None = None) -> SecurityAuditEventList:
        filters = []
        for column, value in ((SecurityAuditEvent.event_date, event_date), (SecurityAuditEvent.user_id, user_id),
                              (SecurityAuditEvent.campaign_id, campaign_id), (SecurityAuditEvent.event_type, event_type),
                              (SecurityAuditEvent.outcome, outcome), (SecurityAuditEvent.resource_type, resource_type)):
            if value is not None:
                filters.append(column == value)
        total = self.db.scalar(select(func.count()).select_from(SecurityAuditEvent).where(*filters)) or 0
        events = self.db.scalars(select(SecurityAuditEvent).where(*filters)
            .order_by(SecurityAuditEvent.event_date.desc(), SecurityAuditEvent.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size)).all()
        return SecurityAuditEventList(items=[SecurityAuditEventRead(
            id=e.id, event_type=e.event_type, outcome=e.outcome, event_date=e.event_date,
            user_id=e.user_id, campaign_id=e.campaign_id, resource_type=e.resource_type,
            resource_id=e.resource_id, description=e.description, metadata=e.event_metadata
        ) for e in events], page=page, page_size=page_size, total=total,
            total_pages=ceil(total / page_size) if total else 0)
