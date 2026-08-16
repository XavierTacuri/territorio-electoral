from uuid import UUID

from fastapi import APIRouter,Depends,HTTPException,status
from sqlalchemy import func,select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.campaign import Campaign
from app.models.organization import OrganizationMembership
from app.models.security import SecurityAuditEvent
from app.models.user import User
from app.schemas.organization import MembershipRead,MembershipUpsert,OrganizationAuditRead,OrganizationCreate,OrganizationOnboarding,OrganizationOnboardingRead,OrganizationRead,OrganizationUpdate,OrganizationUsageRead,SubscriptionRead,SubscriptionUpsert
from app.schemas.entitlement import CampaignLicenseRead,FeatureCode
from app.services.feature_entitlement_service import FeatureEntitlementService
from app.api.routes.entitlements import read as entitlement_read
from app.schemas.organization import MembershipUpsert as OrgMembershipUpsert
from app.services.campaign_service import CampaignService
from app.services.exceptions import ConflictError,NotFoundError
from app.services.organization_service import OrganizationAccessService,OrganizationError,OrganizationService,PlanLimitService,SubscriptionService

router=APIRouter(prefix="/organizations",tags=["organizations"])
def fail(exc):
    if isinstance(exc,OrganizationError):return HTTPException(exc.status_code,detail={"code":exc.code,"message":exc.message})
    if isinstance(exc,NotFoundError):return HTTPException(404,str(exc))
    if isinstance(exc,ConflictError):return HTTPException(409,str(exc))
    return HTTPException(400,str(exc))
def organization_read(db,obj,actor):
    sub=SubscriptionService(db).get(obj.id)
    membership=db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id==obj.id,OrganizationMembership.user_id==actor.id,OrganizationMembership.status=="ACTIVE"))
    return OrganizationRead.model_validate({**{c.name:getattr(obj,c.name) for c in obj.__table__.columns},"campaign_count":db.scalar(select(func.count()).select_from(Campaign).where(Campaign.organization_id==obj.id)) or 0,"user_count":db.scalar(select(func.count()).select_from(OrganizationMembership).where(OrganizationMembership.organization_id==obj.id,OrganizationMembership.status=="ACTIVE")) or 0,"plan_code":sub.plan_code if sub else None,"subscription_status":sub.status if sub else None,"current_role":membership.organization_role if membership else None})
def subscription_read(service,obj):return SubscriptionRead.model_validate({**{c.name:getattr(obj,c.name) for c in obj.__table__.columns if c.name!="metadata"},"metadata":obj.config,"effective":service.effective(obj)})
def membership_read(db,obj):
    user=db.get(User,obj.user_id)
    return MembershipRead.model_validate({"id":obj.id,"organization_id":obj.organization_id,"user_id":obj.user_id,"organization_role":obj.organization_role,"status":obj.status,"created_at":obj.created_at,"username":user.username if user else None,"email":user.email if user else None,"display_name":f"{user.first_name} {user.last_name}" if user else None})

@router.get("",response_model=list[OrganizationRead])
def listing(actor:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return [organization_read(db,x,actor) for x in OrganizationService(db).list(actor)]
@router.post("",response_model=OrganizationRead,status_code=201)
def create(data:OrganizationCreate,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return organization_read(db,OrganizationService(db).create(data,actor),actor)
    except Exception as exc:raise fail(exc)
@router.post("/onboarding",response_model=OrganizationOnboardingRead,status_code=201)
def onboarding(data:OrganizationOnboarding,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:
        access=OrganizationAccessService(db)
        if not access.platform_admin(actor):raise OrganizationError("ORGANIZATION_ACCESS_DENIED","Solo administración de plataforma puede ejecutar onboarding")
        organizations=OrganizationService(db);organization=organizations.create(data.organization,actor)
        subscription_service=SubscriptionService(db);subscription=subscription_service.upsert(organization.id,data.subscription,actor)
        membership=organizations.add_member(organization.id,OrgMembershipUpsert(user_id=data.owner_user_id,organization_role="OWNER",status="ACTIVE"),actor)
        campaign_data=data.campaign.model_copy(update={"organization_id":organization.id})
        campaign=CampaignService(db).create(campaign_data,actor)
        return OrganizationOnboardingRead(organization=organization_read(db,organization,actor),subscription=subscription_read(subscription_service,subscription),membership=membership,campaign_id=campaign.id)
    except Exception as exc:raise fail(exc)
@router.get("/{organization_id}",response_model=OrganizationRead)
def detail(organization_id:UUID,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return organization_read(db,OrganizationAccessService(db).require_access(organization_id,actor,allow_suspended=True),actor)
    except Exception as exc:raise fail(exc)
@router.patch("/{organization_id}",response_model=OrganizationRead)
def update(organization_id:UUID,data:OrganizationUpdate,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return organization_read(db,OrganizationService(db).update(organization_id,data,actor),actor)
    except Exception as exc:raise fail(exc)
@router.get("/{organization_id}/memberships",response_model=list[MembershipRead])
def memberships(organization_id:UUID,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return [membership_read(db,item) for item in OrganizationService(db).members(organization_id,actor)]
    except Exception as exc:raise fail(exc)
@router.post("/{organization_id}/memberships",response_model=MembershipRead,status_code=201)
def add_membership(organization_id:UUID,data:MembershipUpsert,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return membership_read(db,OrganizationService(db).add_member(organization_id,data,actor))
    except Exception as exc:raise fail(exc)
@router.delete("/{organization_id}/memberships/{membership_id}",status_code=204)
def remove_membership(organization_id:UUID,membership_id:UUID,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:OrganizationService(db).remove_member(organization_id,membership_id,actor)
    except Exception as exc:raise fail(exc)
@router.get("/{organization_id}/subscription",response_model=SubscriptionRead)
def subscription(organization_id:UUID,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:
        OrganizationAccessService(db).require_access(organization_id,actor,allow_suspended=True);service=SubscriptionService(db);obj=service.get(organization_id)
        if not obj:raise NotFoundError("SuscripciÃ³n no encontrada")
        return subscription_read(service,obj)
    except Exception as exc:raise fail(exc)
@router.put("/{organization_id}/subscription",response_model=SubscriptionRead)
def update_subscription(organization_id:UUID,data:SubscriptionUpsert,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:
        access=OrganizationAccessService(db)
        if not access.platform_admin(actor):raise OrganizationError("ORGANIZATION_ACCESS_DENIED","Solo administraciÃ³n de plataforma puede cambiar el plan")
        access.require_access(organization_id,actor,allow_suspended=True);service=SubscriptionService(db);return subscription_read(service,service.upsert(organization_id,data,actor))
    except Exception as exc:raise fail(exc)
@router.get("/{organization_id}/usage",response_model=OrganizationUsageRead)
def usage(organization_id:UUID,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:OrganizationAccessService(db).require_access(organization_id,actor,allow_suspended=True);return PlanLimitService(db).usage(organization_id)
    except Exception as exc:raise fail(exc)
@router.get("/{organization_id}/users/search",response_model=list[dict])
def search_user(organization_id:UUID,query:str,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:
        OrganizationAccessService(db).require_admin(organization_id,actor);value=query.strip().lower()
        if len(value)<3:return []
        users=list(db.scalars(select(User).where((User.email==value)|(User.username==value),User.is_active.is_(True)).limit(5)))
        return [{"id":str(user.id),"username":user.username,"email":user.email,"display_name":f"{user.first_name} {user.last_name}"} for user in users]
    except Exception as exc:raise fail(exc)
@router.get("/{organization_id}/licenses",response_model=list[CampaignLicenseRead])
def licenses(organization_id:UUID,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:
        OrganizationAccessService(db).require_access(organization_id,actor,allow_suspended=True);service=FeatureEntitlementService(db);result=[]
        for campaign in db.scalars(select(Campaign).where(Campaign.organization_id==organization_id).order_by(Campaign.name)):
            feature=service.get(campaign.id,FeatureCode.TERRITORY_AI);features=[entitlement_read(service,feature)] if feature else []
            result.append(CampaignLicenseRead(campaign_id=campaign.id,campaign_name=campaign.name,commercial_plan="PRO" if service.is_enabled(campaign.id,FeatureCode.TERRITORY_AI) else "STANDARD",features=features))
        return result
    except Exception as exc:raise fail(exc)
@router.get("/{organization_id}/audit",response_model=list[OrganizationAuditRead])
def audit(organization_id:UUID,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:
        OrganizationAccessService(db).require_admin(organization_id,actor);campaign_ids=set(db.scalars(select(Campaign.id).where(Campaign.organization_id==organization_id)));items=[]
        for event in db.scalars(select(SecurityAuditEvent).order_by(SecurityAuditEvent.created_at.desc()).limit(300)):
            if event.campaign_id not in campaign_ids and str(event.event_metadata.get("organization_id",""))!=str(organization_id):continue
            user=db.get(User,event.user_id) if event.user_id else None
            items.append(OrganizationAuditRead(id=event.id,event_type=event.event_type,outcome=event.outcome,created_at=event.created_at,actor=user.username if user else None,description=event.description))
            if len(items)>=100:break
        return items
    except Exception as exc:raise fail(exc)
