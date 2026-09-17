from uuid import UUID
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session
from app.models.alerts import AlertRule,OperationalAlert
class OperationalAlertRepository:
    def __init__(self,db:Session):self.db=db
    def by_id(self,id:UUID):return self.db.get(OperationalAlert,id)
    def by_fingerprint(self,campaign_id,fingerprint):return self.db.scalar(select(OperationalAlert).where(OperationalAlert.campaign_id==campaign_id,OperationalAlert.fingerprint==fingerprint))
    def list(self,campaign_id,page=1,page_size=20,status=None,severity=None,module=None,condition_type=None,condition_types=None,statuses=None):
        q=select(OperationalAlert).join(AlertRule).where(OperationalAlert.campaign_id==campaign_id,OperationalAlert.is_active.is_(True))
        if status:q=q.where(OperationalAlert.status==status)
        # `statuses` groups several literal statuses under one semantic filter
        # (e.g. ACTIVE = OPEN+ACKNOWLEDGED, RESOLVED = RESOLVED+DISMISSED) for
        # the Centro de Alertas' Estado filter and the summary counters, so
        # the DB does the grouping instead of the caller filtering a page
        # after the fact.
        if statuses is not None:q=q.where(OperationalAlert.status.in_(statuses))
        if severity:q=q.where(OperationalAlert.severity==severity)
        if module:q=q.where(AlertRule.module==module)
        if condition_type:q=q.where(AlertRule.condition_type==condition_type)
        # A role-level family restriction (e.g. Candidate/Manager) is applied
        # at query time rather than filtering the page afterwards, so alerts
        # outside those families are never even fetched (§64).
        if condition_types is not None:q=q.where(AlertRule.condition_type.in_(condition_types))
        severity_order=case((OperationalAlert.severity=="CRITICAL",1),(OperationalAlert.severity=="WARNING",2),else_=3)
        # Most-recent-first is the primary order the Centro de Alertas asks
        # for; severity/id only break ties between alerts detected the same
        # day so the order stays fully deterministic.
        q=q.order_by(OperationalAlert.detected_date.desc(),severity_order,OperationalAlert.created_at.desc())
        total=self.db.scalar(select(func.count()).select_from(q.subquery())) or 0
        return list(self.db.scalars(q.offset((page-1)*page_size).limit(page_size))),total
