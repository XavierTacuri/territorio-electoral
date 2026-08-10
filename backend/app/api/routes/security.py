from datetime import date
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.api.dependencies import require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.security import SecurityAuditEventList
from app.services.security_audit_service import SecurityAuditService

router = APIRouter(prefix="/security", tags=["security"])


@router.get("/audit-events", response_model=SecurityAuditEventList)
def audit_events(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                 event_date: date | None = None, user_id: UUID | None = None,
                 campaign_id: UUID | None = None, event_type: str | None = None,
                 outcome: str | None = None, resource_type: str | None = None,
                 _: User = Depends(require_admin), db: Session = Depends(get_db)) -> SecurityAuditEventList:
    return SecurityAuditService(db).list(page, page_size, event_date=event_date, user_id=user_id,
        campaign_id=campaign_id, event_type=event_type, outcome=outcome, resource_type=resource_type)
