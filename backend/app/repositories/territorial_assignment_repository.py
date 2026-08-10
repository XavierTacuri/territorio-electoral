from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.assignments import TerritorialAssignment
class TerritorialAssignmentRepository:
    def __init__(self,db:Session):self.db=db
    def get(self,id:UUID):return self.db.get(TerritorialAssignment,id)
    def by_campaign(self,id:UUID):return list(self.db.scalars(select(TerritorialAssignment).where(TerritorialAssignment.campaign_id==id,TerritorialAssignment.is_active.is_(True))))
    def by_user(self,campaign_id:UUID,user_id:UUID):return list(self.db.scalars(select(TerritorialAssignment).where(TerritorialAssignment.campaign_id==campaign_id,TerritorialAssignment.user_id==user_id,TerritorialAssignment.is_active.is_(True))))
