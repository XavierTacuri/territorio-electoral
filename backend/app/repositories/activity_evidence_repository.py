from sqlalchemy.orm import Session
from app.models.operational import ActivityEvidence

class ActivityEvidenceRepository:
    def __init__(self,db:Session):self.db=db
    def get(self,id):return self.db.get(ActivityEvidence,id)
    def add(self,obj):self.db.add(obj);return obj
