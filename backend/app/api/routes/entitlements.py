from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_active_user,require_admin
from app.db.session import get_db
from app.models.campaign import Campaign
from app.models.user import User
from app.schemas.entitlement import CampaignLicenseRead,EntitlementRead,EntitlementUpsert,FeatureCode
from app.schemas.territory_ai import TerritoryAIConversationRead,TerritoryAIQueryRequest,TerritoryAIResponse
from app.services.campaign_access_service import CampaignAccessService
from app.services.feature_entitlement_service import FeatureEntitlementService
from app.services.territory_ai_service import TerritoryAiError,TerritoryAiService,get_ai_provider
from app.services.organization_service import OrganizationError
router=APIRouter(tags=["feature-entitlements"])
def read(service,obj):
    data={k:getattr(obj,k) for k in ("id","campaign_id","feature_code","enabled","entitlement_type","starts_at","expires_at","monthly_request_limit","monthly_token_limit","created_at","updated_at")};data["status"]=service.status(obj);return EntitlementRead(**data)
@router.get("/admin/feature-entitlements",response_model=list[CampaignLicenseRead])
def licenses(actor:User=Depends(require_admin),db:Session=Depends(get_db)):
    service=FeatureEntitlementService(db);result=[]
    for campaign in db.scalars(select(Campaign).order_by(Campaign.name)):
        feature=service.get(campaign.id,FeatureCode.TERRITORY_AI);features=[read(service,feature)] if feature else []
        result.append(CampaignLicenseRead(campaign_id=campaign.id,campaign_name=campaign.name,commercial_plan="PRO" if service.is_enabled(campaign.id,FeatureCode.TERRITORY_AI) else "STANDARD",features=features))
    return result
@router.put("/admin/campaigns/{campaign_id}/feature-entitlements/{feature_code}",response_model=EntitlementRead)
def upsert(campaign_id:UUID,feature_code:FeatureCode,data:EntitlementUpsert,actor:User=Depends(require_admin),db:Session=Depends(get_db)):
    if data.feature_code!=feature_code:raise HTTPException(422,detail={"code":"FEATURE_CODE_MISMATCH","message":"La funcionalidad no coincide"})
    if not db.get(Campaign,campaign_id):raise HTTPException(404,"Campaña no encontrada")
    service=FeatureEntitlementService(db);return read(service,service.upsert(campaign_id,data,actor))
@router.get("/campaigns/{campaign_id}/feature-entitlements/{feature_code}",response_model=EntitlementRead|None)
def campaign_feature(campaign_id:UUID,feature_code:FeatureCode,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:CampaignAccessService(db).require_access(campaign_id,actor)
    except PermissionError as e:raise HTTPException(403,str(e))
    service=FeatureEntitlementService(db);obj=service.get(campaign_id,feature_code);return read(service,obj) if obj else None
@router.post("/campaigns/{campaign_id}/territory-ai/query",response_model=TerritoryAIResponse)
def query(campaign_id:UUID,data:TerritoryAIQueryRequest,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db),provider=Depends(get_ai_provider)):
    try:return TerritoryAiService(db,provider).query(campaign_id,data,actor)
    except TerritoryAiError as e:raise HTTPException(e.status_code,detail={"code":e.code,"message":e.message,**e.extra})
    except OrganizationError as e:raise HTTPException(e.status_code,detail={"code":e.code,"message":e.message})
    except PermissionError as e:raise HTTPException(403,detail={"code":"CAMPAIGN_ACCESS_DENIED","message":str(e)})
@router.get("/campaigns/{campaign_id}/territory-ai/conversations",response_model=list[TerritoryAIConversationRead])
def conversations(campaign_id:UUID,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db),provider=Depends(get_ai_provider)):
    try:return TerritoryAiService(db,provider).list_conversations(campaign_id,actor)
    except OrganizationError as e:raise HTTPException(e.status_code,detail={"code":e.code,"message":e.message})
    except PermissionError as e:raise HTTPException(403,detail={"code":"CAMPAIGN_ACCESS_DENIED","message":str(e)})
@router.get("/campaigns/{campaign_id}/territory-ai/conversations/{conversation_id}",response_model=TerritoryAIConversationRead)
def conversation(campaign_id:UUID,conversation_id:UUID,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db),provider=Depends(get_ai_provider)):
    try:return TerritoryAiService(db,provider).conversation(campaign_id,conversation_id,actor)
    except TerritoryAiError as e:raise HTTPException(e.status_code,detail={"code":e.code,"message":e.message})
    except OrganizationError as e:raise HTTPException(e.status_code,detail={"code":e.code,"message":e.message})
    except PermissionError as e:raise HTTPException(403,detail={"code":"CAMPAIGN_ACCESS_DENIED","message":str(e)})
