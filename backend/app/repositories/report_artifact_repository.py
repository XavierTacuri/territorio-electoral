from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.reports import ReportArtifact

class ReportArtifactRepository:
    def __init__(self,db:Session):self.db=db
    def by_run(self,run_id:UUID):return self.db.scalar(select(ReportArtifact).where(ReportArtifact.report_run_id==run_id))
    def add(self,item):self.db.add(item);self.db.flush();return item
