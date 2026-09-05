from uuid import UUID
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session
from app.models.alerts import AlertRule,OperationalAlert
class OperationalAlertRepository:
    def __init__(self,db:Session):self.db=db
    def by_id(self,id:UUID):return self.db.get(OperationalAlert,id)
    def by_fingerprint(self,campaign_id,fingerprint):return self.db.scalar(select(OperationalAlert).where(OperationalAlert.campaign_id==campaign_id,OperationalAlert.fingerprint==fingerprint))
    def list(self,campaign_id,page=1,page_size=20,status=None,severity=None,module=None):
        q=select(OperationalAlert).join(AlertRule).where(OperationalAlert.campaign_id==campaign_id,OperationalAlert.is_active.is_(True))
        if status:q=q.where(OperationalAlert.status==status)
        if severity:q=q.where(OperationalAlert.severity==severity)
        if module:q=q.where(AlertRule.module==module)
        severity_order=case((OperationalAlert.severity=="CRITICAL",1),(OperationalAlert.severity=="WARNING",2),else_=3)
        # Un tercer criterio determinista evita que dos alertas con la misma
        # severidad y fecha detectada (frecuente: varias condiciones evaluadas
        # el mismo día) queden en un orden indefinido entre sí.
        q=q.order_by(severity_order,OperationalAlert.detected_date.desc(),OperationalAlert.created_at.desc())
        total=self.db.scalar(select(func.count()).select_from(q.subquery())) or 0
        return list(self.db.scalars(q.offset((page-1)*page_size).limit(page_size))),total
