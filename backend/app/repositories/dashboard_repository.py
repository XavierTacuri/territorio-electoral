from datetime import date
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.operational import ActivityParticipantSummary, CitizenNeed, Commitment, TerritorialActivity


class DashboardRepository:
    def __init__(self, db: Session):
        self.db = db

    def operational_counts(self, campaign_id: UUID, start: date, end: date, parish_ids: list[int]):
        territorial = TerritorialActivity.parish_id.in_(parish_ids) if parish_ids else False
        activity = self.db.execute(select(
            func.count().filter(TerritorialActivity.status == "COMPLETED"),
            func.count().filter(TerritorialActivity.status == "PLANNED"),
            func.count().filter(TerritorialActivity.status == "CANCELLED"),
            func.count(func.distinct(TerritorialActivity.parish_id)).filter(TerritorialActivity.status == "COMPLETED"),
        ).where(TerritorialActivity.campaign_id == campaign_id, TerritorialActivity.is_active.is_(True), TerritorialActivity.activity_date.between(start, end), territorial)).one()
        attendees = self.db.scalar(select(func.coalesce(func.sum(ActivityParticipantSummary.estimated_attendees), 0)).join(TerritorialActivity, TerritorialActivity.id == ActivityParticipantSummary.activity_id).where(TerritorialActivity.campaign_id == campaign_id, TerritorialActivity.is_active.is_(True), TerritorialActivity.status == "COMPLETED", TerritorialActivity.activity_date.between(start, end), territorial)) or 0
        needs = self.db.execute(select(func.count(CitizenNeed.id), func.coalesce(func.sum(CitizenNeed.mentions_count), 0)).join(TerritorialActivity, TerritorialActivity.id == CitizenNeed.activity_id).where(CitizenNeed.campaign_id == campaign_id, CitizenNeed.is_active.is_(True), TerritorialActivity.activity_date.between(start, end), CitizenNeed.parish_id.in_(parish_ids) if parish_ids else False)).one()
        return {"completed": activity[0], "planned": activity[1], "cancelled": activity[2], "covered": activity[3], "attendees": attendees, "needs": needs[0], "mentions": needs[1]}

    def commitment_counts(self, campaign_id: UUID, cutoff: date, parish_ids: list[int]):
        row = self.db.execute(select(
            func.count(Commitment.id),
            func.count().filter(Commitment.status == "PENDING"),
            func.count().filter(Commitment.status == "IN_PROGRESS"),
            func.count().filter(Commitment.status == "COMPLETED"),
            func.count().filter(Commitment.status == "CANCELLED"),
            func.count().filter(Commitment.due_date < cutoff, Commitment.status.in_(["PENDING", "IN_PROGRESS"])),
            func.count().filter(Commitment.responsible_user_id.is_(None)),
            func.count().filter(Commitment.due_date.is_(None)),
        ).where(Commitment.campaign_id == campaign_id, Commitment.is_active.is_(True), Commitment.parish_id.in_(parish_ids) if parish_ids else False)).one()
        return dict(zip(("total", "pending", "in_progress", "completed", "cancelled", "overdue", "without_responsible", "without_due_date"), row))
