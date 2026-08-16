from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.entitlement import AiUsageEvent
from app.models.organization import Organization, OrganizationMembership, OrganizationSubscription
from app.models.user import User
from app.schemas.organization import MembershipUpsert, OrganizationCreate, OrganizationUpdate, SubscriptionUpsert
from app.services.exceptions import ConflictError, NotFoundError
from app.services.security_audit_service import SecurityAuditService


class OrganizationError(PermissionError):
    def __init__(self,code,message,status_code=403):self.code=code;self.message=message;self.status_code=status_code;super().__init__(message)


class OrganizationAccessService:
    def __init__(self,db:Session):self.db=db
    @staticmethod
    def platform_admin(user:User):return user.is_superuser or "ADMIN" in {r.code for r in user.roles}
    def memberships(self,user:User):return list(self.db.scalars(select(OrganizationMembership).where(OrganizationMembership.user_id==user.id,OrganizationMembership.status=="ACTIVE")))
    def accessible_ids(self,user:User):
        if self.platform_admin(user):return set(self.db.scalars(select(Organization.id)))
        return {m.organization_id for m in self.memberships(user)}
    def require_access(self,organization_id:UUID,user:User,allow_suspended=False):
        obj=self.db.get(Organization,organization_id)
        if not obj:raise NotFoundError("OrganizaciÃ³n no encontrada")
        if not self.platform_admin(user) and organization_id not in self.accessible_ids(user):raise OrganizationError("ORGANIZATION_ACCESS_DENIED","Sin acceso a la organizaciÃ³n")
        if obj.status=="SUSPENDED" and not allow_suspended and not self.platform_admin(user):raise OrganizationError("ORGANIZATION_SUSPENDED","La organizaciÃ³n estÃ¡ suspendida")
        if obj.status=="ARCHIVED" and not self.platform_admin(user):raise OrganizationError("ORGANIZATION_ACCESS_DENIED","OrganizaciÃ³n no disponible")
        return obj
    def require_admin(self,organization_id:UUID,user:User):
        obj=self.require_access(organization_id,user,allow_suspended=True)
        if self.platform_admin(user):return obj
        membership=self.db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id==organization_id,OrganizationMembership.user_id==user.id,OrganizationMembership.status=="ACTIVE"))
        if not membership or membership.organization_role not in {"OWNER","ADMIN"}:raise OrganizationError("ORGANIZATION_ACCESS_DENIED","Se requiere administraciÃ³n de la organizaciÃ³n")
        return obj


class SubscriptionService:
    ACTIVE={"ACTIVE","TRIAL"}
    def __init__(self,db:Session,now_provider=lambda:datetime.now(timezone.utc)):self.db=db;self.now_provider=now_provider
    def get(self,organization_id):return self.db.scalar(select(OrganizationSubscription).where(OrganizationSubscription.organization_id==organization_id))
    def effective(self,subscription):
        if not subscription or subscription.status not in self.ACTIVE:return False
        now=self.now_provider();now=now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now
        for value,valid in ((subscription.starts_at,lambda x:now>=x),(subscription.expires_at,lambda x:now<x),(subscription.trial_ends_at,lambda x:subscription.status!="TRIAL" or now<x)):
            if value:
                value=value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
                if not valid(value):return False
        return True
    def require_active(self,organization_id):
        obj=self.get(organization_id)
        if not self.effective(obj):raise OrganizationError("SUBSCRIPTION_INACTIVE","La suscripciÃ³n de la organizaciÃ³n no estÃ¡ activa")
        return obj
    def upsert(self,organization_id,data:SubscriptionUpsert,actor):
        obj=self.get(organization_id);created=obj is None
        if not obj:obj=OrganizationSubscription(organization_id=organization_id);self.db.add(obj)
        previous_limits=(obj.max_campaigns,obj.max_users) if not created else (None,None)
        values=data.model_dump();values["config"]=values.pop("metadata")
        for key,value in values.items():setattr(obj,key,value)
        if previous_limits!=(obj.max_campaigns,obj.max_users):SecurityAuditService(self.db).record("PLAN_LIMIT_CHANGED","SUCCESS","Limites organizacionales actualizados",user_id=actor.id,resource_type="ORGANIZATION_SUBSCRIPTION",resource_id=obj.id,metadata={"organization_id":str(organization_id),"max_campaigns":obj.max_campaigns,"max_users":obj.max_users})
        self.db.flush();SecurityAuditService(self.db).record("SUBSCRIPTION_CHANGED" if not created else "SUBSCRIPTION_CHANGED","SUCCESS","SuscripciÃ³n organizacional actualizada",user_id=actor.id,resource_type="ORGANIZATION_SUBSCRIPTION",resource_id=obj.id,metadata={"organization_id":str(organization_id),"plan_code":obj.plan_code,"status":obj.status});self.db.commit();self.db.refresh(obj);return obj


class PlanLimitService:
    def __init__(self,db):self.db=db;self.subscriptions=SubscriptionService(db)
    def campaign_count(self,organization_id):return self.db.scalar(select(func.count()).select_from(Campaign).where(Campaign.organization_id==organization_id,Campaign.status!="ARCHIVED",Campaign.is_active.is_(True))) or 0
    def user_count(self,organization_id):return self.db.scalar(select(func.count()).select_from(OrganizationMembership).where(OrganizationMembership.organization_id==organization_id,OrganizationMembership.status=="ACTIVE")) or 0
    def require_campaign_slot(self,organization_id):
        sub=self.subscriptions.require_active(organization_id)
        if sub.max_campaigns is not None and self.campaign_count(organization_id)>=sub.max_campaigns:raise OrganizationError("PLAN_CAMPAIGN_LIMIT_REACHED",f"Has alcanzado el lÃ­mite de {sub.max_campaigns} campaÃ±as de tu plan",409)
    def require_user_slot(self,organization_id,user_id):
        existing=self.db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id==organization_id,OrganizationMembership.user_id==user_id,OrganizationMembership.status=="ACTIVE"))
        if existing:return
        sub=self.subscriptions.require_active(organization_id)
        if sub.max_users is not None and self.user_count(organization_id)>=sub.max_users:raise OrganizationError("PLAN_USER_LIMIT_REACHED",f"Has alcanzado el lÃ­mite de {sub.max_users} usuarios de tu plan",409)
    def usage(self,organization_id):
        sub=self.subscriptions.get(organization_id);requests=self.db.scalar(select(func.coalesce(func.sum(AiUsageEvent.request_count),0)).join(Campaign,Campaign.id==AiUsageEvent.campaign_id).where(Campaign.organization_id==organization_id)) or 0
        return {"campaigns_used":self.campaign_count(organization_id),"campaigns_limit":sub.max_campaigns if sub else None,"users_used":self.user_count(organization_id),"users_limit":sub.max_users if sub else None,"ai_requests_used":requests,"ai_requests_limit":None}


class OrganizationService:
    def __init__(self,db):self.db=db;self.access=OrganizationAccessService(db);self.audit=SecurityAuditService(db)
    def list(self,user):
        ids=self.access.accessible_ids(user);q=select(Organization).where(Organization.id.in_(ids)).order_by(Organization.name) if not self.access.platform_admin(user) else select(Organization).order_by(Organization.name)
        return list(self.db.scalars(q))
    def create(self,data:OrganizationCreate,actor):
        if not self.access.platform_admin(actor):raise OrganizationError("ORGANIZATION_ACCESS_DENIED","Solo administraciÃ³n de plataforma puede crear organizaciones")
        obj=Organization(**data.model_dump());self.db.add(obj)
        try:self.db.flush()
        except IntegrityError as exc:self.db.rollback();raise ConflictError("El slug de organizaciÃ³n ya existe") from exc
        self.audit.record("ORGANIZATION_CREATED","SUCCESS","OrganizaciÃ³n creada",user_id=actor.id,resource_type="ORGANIZATION",resource_id=obj.id);self.db.commit();self.db.refresh(obj);return obj
    def update(self,id,data:OrganizationUpdate,actor):
        obj=self.access.require_access(id,actor,allow_suspended=True)
        if not self.access.platform_admin(actor):raise OrganizationError("ORGANIZATION_ACCESS_DENIED","Solo administraciÃ³n de plataforma puede modificar la organizaciÃ³n")
        old=obj.status
        for key,value in data.model_dump(exclude_unset=True).items():setattr(obj,key,value)
        event="ORGANIZATION_SUSPENDED" if old!="SUSPENDED" and obj.status=="SUSPENDED" else "ORGANIZATION_REACTIVATED" if old=="SUSPENDED" and obj.status=="ACTIVE" else "ORGANIZATION_UPDATED"
        self.audit.record(event,"SUCCESS","OrganizaciÃ³n actualizada",user_id=actor.id,resource_type="ORGANIZATION",resource_id=obj.id);self.db.commit();self.db.refresh(obj);return obj
    def add_member(self,id,data:MembershipUpsert,actor):
        self.access.require_admin(id,actor);PlanLimitService(self.db).require_user_slot(id,data.user_id)
        if not self.db.get(User,data.user_id):raise NotFoundError("Usuario no encontrado")
        obj=self.db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id==id,OrganizationMembership.user_id==data.user_id))
        if not obj:obj=OrganizationMembership(organization_id=id,user_id=data.user_id);self.db.add(obj)
        obj.organization_role=data.organization_role;obj.status=data.status;self.db.flush();self.audit.record("ORG_MEMBER_ADDED","SUCCESS","Miembro organizacional actualizado",user_id=actor.id,resource_type="ORGANIZATION_MEMBERSHIP",resource_id=obj.id,metadata={"organization_id":str(id),"organization_role":obj.organization_role});self.db.commit();self.db.refresh(obj);return obj
    def members(self,id,actor):
        self.access.require_admin(id,actor);return list(self.db.scalars(select(OrganizationMembership).where(OrganizationMembership.organization_id==id).order_by(OrganizationMembership.created_at)))
    def remove_member(self,id,membership_id,actor):
        self.access.require_admin(id,actor);obj=self.db.get(OrganizationMembership,membership_id)
        if not obj or obj.organization_id!=id:raise NotFoundError("MembresÃ­a no encontrada")
        obj.status="INACTIVE";self.audit.record("ORG_MEMBER_REMOVED","SUCCESS","Miembro organizacional removido",user_id=actor.id,resource_type="ORGANIZATION_MEMBERSHIP",resource_id=obj.id,metadata={"organization_id":str(id)});self.db.commit()
