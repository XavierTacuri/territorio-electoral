from collections.abc import Callable
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.assignments import TerritorialAssignment
from app.models.campaign import Campaign
from app.models.operational import TerritorialActivity
from app.models.survey import SurveyResponse
from app.models.territory import Community, Parish, Sector
from app.models.user import User
from app.schemas.dashboard import DashboardFilters, DashboardPeriod, DashboardPeriodRead, DashboardScopeRead
from app.services.campaign_access_service import CampaignAccessService
from app.services.exceptions import BusinessRuleError, NotFoundError


class DashboardFilterService:
    def __init__(self, db: Session, today_provider: Callable[[], date] = date.today):
        self.db = db
        self.today_provider = today_provider
        self.access = CampaignAccessService(db)

    def resolve_period(self, campaign: Campaign, filters: DashboardFilters) -> DashboardPeriodRead:
        today = self.today_provider()
        period = filters.period or DashboardPeriod.LAST_30_DAYS
        if period == DashboardPeriod.CUSTOM:
            start, end = filters.date_from, filters.date_to
        elif period == DashboardPeriod.THIS_WEEK:
            start, end = today - timedelta(days=today.weekday()), today
        elif period == DashboardPeriod.LAST_7_DAYS:
            start, end = today - timedelta(days=6), today
        elif period == DashboardPeriod.CAMPAIGN_TO_DATE:
            minimums = [campaign.start_date]
            minimums += [self.db.scalar(select(func.min(TerritorialActivity.activity_date)).where(TerritorialActivity.campaign_id == campaign.id))]
            minimums += [self.db.scalar(select(func.min(SurveyResponse.response_date)).where(SurveyResponse.campaign_id == campaign.id))]
            start, end = min(x for x in minimums if x is not None) if any(minimums) else today, today
        else:
            start, end = today - timedelta(days=29), today
        if start is None or end is None or start > end:
            raise BusinessRuleError("Período inválido")
        previous_from = previous_to = None
        if filters.compare_previous_period:
            days = (end - start).days + 1
            previous_to = start - timedelta(days=1)
            previous_from = previous_to - timedelta(days=days - 1)
        return DashboardPeriodRead(date_from=start, date_to=end, previous_date_from=previous_from, previous_date_to=previous_to)

    def scope(self, campaign: Campaign, user: User, filters: DashboardFilters) -> DashboardScopeRead:
        roles = {r.code for r in user.roles}
        restricted = not self.access.admin(user) and "TERRITORIAL_COORDINATOR" in roles
        assignments = self.access.territorial_ids(campaign.id, user) if restricted else None
        parish_ids = sorted({a.parish_id for a in assignments or []}) if restricted else list(self.db.scalars(select(Parish.id).where(Parish.canton_id == campaign.canton_id, Parish.is_active.is_(True))))
        if filters.parish_id:
            parish = self.db.get(Parish, filters.parish_id)
            if not parish or parish.canton_id != campaign.canton_id:
                raise NotFoundError("Parroquia no encontrada")
            if filters.parish_id not in parish_ids:
                raise PermissionError("Territorio fuera del alcance")
            parish_ids = [filters.parish_id]
        community_ids = list(self.db.scalars(select(Community.id).where(Community.parish_id.in_(parish_ids), Community.is_active.is_(True)))) if parish_ids else []
        if restricted:
            explicit = {a.community_id for a in assignments or [] if a.community_id}
            whole = {a.parish_id for a in assignments or [] if a.community_id is None}
            community_ids = [cid for cid in community_ids if cid in explicit or self.db.get(Community, cid).parish_id in whole]
        if filters.community_id:
            community = self.db.get(Community, filters.community_id)
            if not community or community.parish_id not in parish_ids:
                raise BusinessRuleError("Jerarquía territorial inválida")
            if filters.community_id not in community_ids:
                raise PermissionError("Territorio fuera del alcance")
            community_ids = [filters.community_id]
        sector_ids = list(self.db.scalars(select(Sector.id).where(Sector.community_id.in_(community_ids), Sector.is_active.is_(True)))) if community_ids else []
        if restricted:
            explicit = {a.sector_id for a in assignments or [] if a.sector_id}
            broad_communities = {a.community_id for a in assignments or [] if a.community_id and a.sector_id is None}
            broad_parishes = {a.parish_id for a in assignments or [] if a.community_id is None}
            sector_ids = [sid for sid in sector_ids if sid in explicit or self.db.get(Sector, sid).community_id in broad_communities or self.db.get(Community, self.db.get(Sector, sid).community_id).parish_id in broad_parishes]
        if filters.sector_id:
            sector = self.db.get(Sector, filters.sector_id)
            if not sector or sector.community_id not in community_ids:
                raise BusinessRuleError("Jerarquía territorial inválida")
            if filters.sector_id not in sector_ids:
                raise PermissionError("Territorio fuera del alcance")
            sector_ids = [filters.sector_id]
        scope_type = "SECTOR" if filters.sector_id else "COMMUNITY" if filters.community_id else "PARISH" if filters.parish_id or restricted else "CAMPAIGN"
        return DashboardScopeRead(type=scope_type, parish_ids=parish_ids, community_ids=community_ids, sector_ids=sector_ids)
