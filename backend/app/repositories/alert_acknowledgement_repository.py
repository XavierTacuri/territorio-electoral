from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.alerts import AlertAcknowledgement
class AlertAcknowledgementRepository:
    def __init__(self,db:Session):self.db=db
    def for_alert(self,alert_id):return list(self.db.scalars(select(AlertAcknowledgement).where(AlertAcknowledgement.alert_id==alert_id).order_by(AlertAcknowledgement.action_date,AlertAcknowledgement.id)))
