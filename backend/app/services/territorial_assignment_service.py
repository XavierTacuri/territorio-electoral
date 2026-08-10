from uuid import UUID
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.assignments import CampaignUser,TerritorialAssignment
from app.models.candidate import Candidate
from app.models.territory import Community,Parish,Sector
from app.models.user import User
from app.schemas.campaign import CampaignUserAssign,TerritorialAssignmentCreate
from app.services.campaign_access_service import CampaignAccessService
from app.services.exceptions import BusinessRuleError,ConflictError,NotFoundError

class TerritorialAssignmentService:
    ALLOWED={"TERRITORIAL_COORDINATOR","CAMPAIGN_MANAGER","ANALYST"}
    def __init__(self,db:Session):self.db=db;self.access=CampaignAccessService(db)
    def assign_user(self,campaign_id:UUID,data:CampaignUserAssign,actor:User):
        campaign=self.access.require_management(campaign_id,actor)
        if campaign.status=="ARCHIVED":raise BusinessRuleError("Campaña archivada")
        user=self.db.get(User,data.user_id)
        if not user or not user.is_active:raise BusinessRuleError("Usuario inactivo o inexistente")
        if not self.access.admin(actor) and (user.is_superuser or "ADMIN" in {r.code for r in user.roles}):raise BusinessRuleError("Un director no puede asignar administradores")
        obj=CampaignUser(campaign_id=campaign_id,user_id=user.id,assigned_by_user_id=actor.id);self.db.add(obj)
        try:self.db.commit();self.db.refresh(obj)
        except IntegrityError as e:self.db.rollback();raise ConflictError("Usuario ya asignado") from e
        return obj
    def users(self,campaign_id:UUID,actor:User):
        self.access.require_management(campaign_id,actor)
        return list(self.db.scalars(select(CampaignUser).where(CampaignUser.campaign_id==campaign_id,CampaignUser.is_active.is_(True))))
    def remove_user(self,campaign_id:UUID,user_id:UUID,actor:User):
        self.access.require_management(campaign_id,actor)
        if self.db.scalar(select(Candidate).where(Candidate.campaign_id==campaign_id,Candidate.user_id==user_id)):raise BusinessRuleError("Desvincule primero el candidato")
        obj=self.db.scalar(select(CampaignUser).where(CampaignUser.campaign_id==campaign_id,CampaignUser.user_id==user_id,CampaignUser.is_active.is_(True)))
        if not obj:raise NotFoundError("Usuario no asignado")
        obj.is_active=False
        for item in self.db.scalars(select(TerritorialAssignment).where(TerritorialAssignment.campaign_id==campaign_id,TerritorialAssignment.user_id==user_id)):item.is_active=False
        self.db.commit()
    def create(self,campaign_id:UUID,data:TerritorialAssignmentCreate,actor:User):
        campaign=self.access.require_management(campaign_id,actor)
        if campaign.status not in {"DRAFT","ACTIVE"}:raise BusinessRuleError("La campaña no acepta asignaciones")
        user=self.db.get(User,data.user_id)
        member=self.db.scalar(select(CampaignUser).where(CampaignUser.campaign_id==campaign_id,CampaignUser.user_id==data.user_id,CampaignUser.is_active.is_(True)))
        if not user or not user.is_active or not member:raise BusinessRuleError("Usuario no asignado a la campaña")
        if not self.ALLOWED.intersection(r.code for r in user.roles):raise BusinessRuleError("Rol incompatible")
        parish=self.db.get(Parish,data.parish_id)
        if not parish or parish.canton_id!=campaign.canton_id:raise BusinessRuleError("Parroquia fuera del cantón de campaña")
        community=self.db.get(Community,data.community_id) if data.community_id else None
        if data.community_id and (not community or community.parish_id!=parish.id):raise BusinessRuleError("Comunidad fuera de la parroquia")
        sector=self.db.get(Sector,data.sector_id) if data.sector_id else None
        if data.sector_id and not data.community_id:raise BusinessRuleError("Un sector requiere comunidad")
        if data.sector_id and (not sector or sector.community_id!=community.id):raise BusinessRuleError("Sector fuera de la comunidad")
        existing=self.db.scalar(select(TerritorialAssignment).where(TerritorialAssignment.campaign_id==campaign_id,TerritorialAssignment.user_id==data.user_id,TerritorialAssignment.parish_id==data.parish_id,TerritorialAssignment.community_id==data.community_id,TerritorialAssignment.sector_id==data.sector_id).order_by(TerritorialAssignment.is_active.desc()))
        if existing and existing.is_active:raise ConflictError("Asignación territorial duplicada")
        if existing:
            existing.is_active=True;existing.assigned_by_user_id=actor.id;self.db.commit();self.db.refresh(existing);return existing
        obj=TerritorialAssignment(campaign_id=campaign_id,assigned_by_user_id=actor.id,**data.model_dump());self.db.add(obj);self.db.commit();self.db.refresh(obj);return obj
    def list(self,campaign_id:UUID,actor:User):
        self.access.require_access(campaign_id,actor);q=select(TerritorialAssignment).where(TerritorialAssignment.campaign_id==campaign_id,TerritorialAssignment.is_active.is_(True))
        if not self.access.admin(actor) and "CAMPAIGN_MANAGER" not in {r.code for r in actor.roles}:q=q.where(TerritorialAssignment.user_id==actor.id)
        return list(self.db.scalars(q))
    def remove(self,campaign_id:UUID,id:UUID,actor:User):
        self.access.require_management(campaign_id,actor);obj=self.db.get(TerritorialAssignment,id)
        if not obj or obj.campaign_id!=campaign_id:raise NotFoundError("Asignación no encontrada")
        obj.is_active=False;self.db.commit()
