from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.territory import Canton
class CantonRepository:
    def __init__(self,db:Session):self.db=db
    def get(self,id:int):return self.db.get(Canton,id)
    def by_dpa(self,code:str):return self.db.scalar(select(Canton).where(Canton.dpa_code==code))
    def list(self,province_id:int|None=None):
        q=select(Canton).order_by(Canton.dpa_code);return list(self.db.scalars(q.where(Canton.province_id==province_id) if province_id else q))
