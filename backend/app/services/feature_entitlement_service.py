from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models.entitlement import AiUsageEvent, CampaignFeatureEntitlement
from app.models.user import User
from app.schemas.entitlement import EntitlementUpsert, FeatureCode
from app.services.security_audit_service import SecurityAuditService

def utcnow(): return datetime.now(timezone.utc)
def aware(value): return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value

class FeatureEntitlementService:
    def __init__(self, db:Session, now_provider=utcnow): self.db=db; self.now_provider=now_provider; self.audit=SecurityAuditService(db)
    def get(self, campaign_id:UUID, feature_code:FeatureCode|str):
        return self.db.scalar(select(CampaignFeatureEntitlement).where(CampaignFeatureEntitlement.campaign_id==campaign_id, CampaignFeatureEntitlement.feature_code==str(feature_code)))
    def status(self, entitlement):
        if not entitlement or not entitlement.enabled: return "DISABLED"
        now=aware(self.now_provider()); starts=aware(entitlement.starts_at); expires=aware(entitlement.expires_at)
        if starts and now < starts:return "SCHEDULED"
        if expires and now >= expires:return "EXPIRED"
        return "TRIAL" if entitlement.entitlement_type=="TRIAL" else "ENABLED"
    def is_enabled(self,campaign_id:UUID,feature_code:FeatureCode|str)->bool:return self.status(self.get(campaign_id,feature_code)) in {"ENABLED","TRIAL"}
    def upsert(self,campaign_id:UUID,data:EntitlementUpsert,actor:User):
        obj=self.get(campaign_id,data.feature_code); created=obj is None
        if created:
            obj=CampaignFeatureEntitlement(campaign_id=campaign_id,created_by_user_id=actor.id,updated_by_user_id=actor.id)
            self.db.add(obj)
        old_enabled=obj.enabled if not created else None
        for key,value in data.model_dump().items():setattr(obj,key,value)
        obj.updated_by_user_id=actor.id;self.db.flush()
        event="FEATURE_ENTITLEMENT_CREATED" if created else "FEATURE_ENTITLEMENT_DISABLED" if old_enabled and not obj.enabled else "FEATURE_ENTITLEMENT_UPDATED"
        self.audit.record(event,"SUCCESS","Licencia de funcionalidad actualizada",user_id=actor.id,campaign_id=campaign_id,resource_type="FEATURE_ENTITLEMENT",resource_id=obj.id,metadata={"feature_code":obj.feature_code,"entitlement_type":obj.entitlement_type})
        self.db.commit();self.db.refresh(obj);return obj
    def quota_available(self, entitlement)->bool:
        if entitlement.monthly_request_limit is None and entitlement.monthly_token_limit is None:return True
        now=aware(self.now_provider()); month=datetime(now.year,now.month,1,tzinfo=timezone.utc)
        requests,tokens=self.db.execute(select(func.coalesce(func.sum(AiUsageEvent.request_count),0),func.coalesce(func.sum(AiUsageEvent.input_tokens),0)+func.coalesce(func.sum(AiUsageEvent.output_tokens),0)).where(AiUsageEvent.campaign_id==entitlement.campaign_id,AiUsageEvent.timestamp>=month)).one()
        return (entitlement.monthly_request_limit is None or requests < entitlement.monthly_request_limit) and (entitlement.monthly_token_limit is None or tokens < entitlement.monthly_token_limit)
