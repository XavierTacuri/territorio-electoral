from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.territory import Sector
class SectorRepository:
    def __init__(self,db:Session):self.db=db
    def get(self,id:UUID):return self.db.get(Sector,id)
    def by_community(self,id:UUID):return list(self.db.scalars(select(Sector).where(Sector.community_id==id).order_by(Sector.name)))
