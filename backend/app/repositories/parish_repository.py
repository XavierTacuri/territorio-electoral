from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.territory import Parish
class ParishRepository:
    def __init__(self,db:Session):self.db=db
    def get(self,id:int):return self.db.get(Parish,id)
    def by_dpa(self,code:str):return self.db.scalar(select(Parish).where(Parish.dpa_code==code))
    def by_canton(self,id:int):return list(self.db.scalars(select(Parish).where(Parish.canton_id==id).order_by(Parish.dpa_code)))
