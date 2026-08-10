from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.assignments import CampaignUser, TerritorialAssignment
from app.models.campaign import Campaign
from app.models.user import User
from app.services.exceptions import NotFoundError


class CampaignAccessService:
    def __init__(self,db:Session):self.db=db
    @staticmethod
    def admin(user:User)->bool:return user.is_superuser or "ADMIN" in {r.code for r in user.roles}
    def accessible_ids(self,user:User)->set[UUID]:
        if self.admin(user):return set(self.db.scalars(select(Campaign.id)))
        return set(self.db.scalars(select(CampaignUser.campaign_id).where(CampaignUser.user_id==user.id,CampaignUser.is_active.is_(True))))
    def require_access(self,campaign_id:UUID,user:User)->Campaign:
        campaign=self.db.get(Campaign,campaign_id)
        if not campaign:raise NotFoundError("Campaña no encontrada")
        if not self.admin(user) and campaign_id not in self.accessible_ids(user):raise PermissionError("Sin acceso a la campaña")
        return campaign
    def require_management(self,campaign_id:UUID,user:User)->Campaign:
        campaign=self.require_access(campaign_id,user)
        if not self.admin(user) and "CAMPAIGN_MANAGER" not in {r.code for r in user.roles}:raise PermissionError("Sin permisos de gestión")
        return campaign
    def territorial_ids(self,campaign_id:UUID,user:User):
        if self.admin(user) or "CANDIDATE" in {r.code for r in user.roles}:return None
        return list(self.db.scalars(select(TerritorialAssignment).where(TerritorialAssignment.campaign_id==campaign_id,TerritorialAssignment.user_id==user.id,TerritorialAssignment.is_active.is_(True))))
