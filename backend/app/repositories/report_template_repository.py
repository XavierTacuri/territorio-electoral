from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models.reports import ReportTemplate

class ReportTemplateRepository:
    def __init__(self, db: Session): self.db = db
    def by_id(self, template_id: UUID): return self.db.get(ReportTemplate, template_id)
    def by_code(self, code: str): return self.db.scalar(select(ReportTemplate).where(ReportTemplate.code == code.upper()))
    def list(self, include_inactive=False):
        query=select(ReportTemplate).order_by(ReportTemplate.name)
        if not include_inactive: query=query.where(ReportTemplate.is_active.is_(True))
        return list(self.db.scalars(query))
    def add(self, item): self.db.add(item); self.db.flush(); return item
