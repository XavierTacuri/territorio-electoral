from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.territory import Community
class CommunityRepository:
    def __init__(self,db:Session):self.db=db
    def get(self,id:UUID):return self.db.get(Community,id)
    def by_parish(self,id:int):return list(self.db.scalars(select(Community).where(Community.parish_id==id).order_by(Community.name)))
