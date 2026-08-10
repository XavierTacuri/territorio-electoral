from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.territory import Province
class ProvinceRepository:
    def __init__(self,db:Session):self.db=db
    def get(self,id:int):return self.db.get(Province,id)
    def by_code(self,code:str):return self.db.scalar(select(Province).where(Province.code==code))
    def active(self):return list(self.db.scalars(select(Province).where(Province.is_active.is_(True)).order_by(Province.code)))
