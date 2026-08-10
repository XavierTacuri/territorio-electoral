from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models.reports import ReportRun

class ReportRunRepository:
    def __init__(self, db: Session): self.db=db
    def by_id(self, run_id: UUID): return self.db.get(ReportRun, run_id)
    def add(self,item): self.db.add(item); self.db.flush(); return item
    def list(self,campaign_id,page=1,page_size=20):
        q=select(ReportRun).where(ReportRun.campaign_id==campaign_id).order_by(ReportRun.report_date.desc(),ReportRun.id)
        total=self.db.scalar(select(func.count()).select_from(q.subquery())) or 0
        return list(self.db.scalars(q.offset((page-1)*page_size).limit(page_size))),total
