from sqlalchemy.orm import Session
from app.models.operational import Commitment

class CommitmentRepository:
    def __init__(self,db:Session):self.db=db
    def get(self,id):return self.db.get(Commitment,id)
    def add(self,obj):self.db.add(obj);return obj
