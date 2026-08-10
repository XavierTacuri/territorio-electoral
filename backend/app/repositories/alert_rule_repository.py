from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.alerts import AlertRule
class AlertRuleRepository:
    def __init__(self,db:Session):self.db=db
    def active(self,codes=None):
        q=select(AlertRule).where(AlertRule.is_active.is_(True)).order_by(AlertRule.code)
        if codes:q=q.where(AlertRule.code.in_([c.upper() for c in codes]))
        return list(self.db.scalars(q))
    def by_code(self,code):return self.db.scalar(select(AlertRule).where(AlertRule.code==code.upper()))
