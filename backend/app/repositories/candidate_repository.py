from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.candidate import Candidate
class CandidateRepository:
    def __init__(self,db:Session):self.db=db
    def by_campaign(self,id:UUID):return self.db.scalar(select(Candidate).where(Candidate.campaign_id==id))
    def by_user(self,id:UUID):return self.db.scalar(select(Candidate).where(Candidate.user_id==id))
