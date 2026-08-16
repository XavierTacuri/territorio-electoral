from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.schemas.campaign import CampaignCreate


class OrganizationStatus(StrEnum): ACTIVE="ACTIVE";SUSPENDED="SUSPENDED";ARCHIVED="ARCHIVED"
class OrganizationRole(StrEnum): OWNER="OWNER";ADMIN="ADMIN";MEMBER="MEMBER"
class MembershipStatus(StrEnum): ACTIVE="ACTIVE";INACTIVE="INACTIVE";INVITED="INVITED"
class PlanCode(StrEnum): STANDARD="STANDARD";PRO="PRO"
class SubscriptionStatus(StrEnum): TRIAL="TRIAL";ACTIVE="ACTIVE";PAST_DUE="PAST_DUE";SUSPENDED="SUSPENDED";EXPIRED="EXPIRED";CANCELLED="CANCELLED"

class OrganizationCreate(BaseModel):
    name:str;slug:str;status:OrganizationStatus=OrganizationStatus.ACTIVE;legal_name:str|None=None;contact_email:str|None=None;contact_phone:str|None=None;country:str="EC";timezone:str="America/Guayaquil"
    @field_validator("slug")
    @classmethod
    def slug_value(cls,v):return v.strip().lower()
class OrganizationUpdate(BaseModel):
    name:str|None=None;status:OrganizationStatus|None=None;legal_name:str|None=None;contact_email:str|None=None;contact_phone:str|None=None;country:str|None=None;timezone:str|None=None
class OrganizationRead(BaseModel):
    id:UUID;name:str;slug:str;status:OrganizationStatus;legal_name:str|None;contact_email:str|None;contact_phone:str|None;country:str;timezone:str;created_at:datetime;updated_at:datetime;campaign_count:int=0;user_count:int=0;plan_code:PlanCode|None=None;subscription_status:SubscriptionStatus|None=None;current_role:OrganizationRole|None=None
    model_config=ConfigDict(from_attributes=True)
class MembershipUpsert(BaseModel):
    user_id:UUID;organization_role:OrganizationRole=OrganizationRole.MEMBER;status:MembershipStatus=MembershipStatus.ACTIVE
class MembershipRead(BaseModel):
    id:UUID;organization_id:UUID;user_id:UUID;organization_role:OrganizationRole;status:MembershipStatus;created_at:datetime;username:str|None=None;email:str|None=None;display_name:str|None=None
    model_config=ConfigDict(from_attributes=True)
class SubscriptionUpsert(BaseModel):
    plan_code:PlanCode;status:SubscriptionStatus;starts_at:datetime|None=None;expires_at:datetime|None=None;trial_ends_at:datetime|None=None;max_campaigns:int|None=Field(None,gt=0);max_users:int|None=Field(None,gt=0);metadata:dict=Field(default_factory=dict);external_customer_id:str|None=None;external_subscription_id:str|None=None
class SubscriptionRead(BaseModel):
    id:UUID;organization_id:UUID;plan_code:PlanCode;status:SubscriptionStatus;starts_at:datetime|None;expires_at:datetime|None;trial_ends_at:datetime|None;max_campaigns:int|None;max_users:int|None;metadata:dict;external_customer_id:str|None;external_subscription_id:str|None;created_at:datetime;updated_at:datetime;effective:bool
    model_config=ConfigDict(from_attributes=True)
class OrganizationUsageRead(BaseModel):
    campaigns_used:int;campaigns_limit:int|None;users_used:int;users_limit:int|None;ai_requests_used:int;ai_requests_limit:int|None=None
class OrganizationOnboarding(BaseModel):
    organization:OrganizationCreate;owner_user_id:UUID;subscription:SubscriptionUpsert;campaign:CampaignCreate
class OrganizationOnboardingRead(BaseModel):
    organization:OrganizationRead;subscription:SubscriptionRead;membership:MembershipRead;campaign_id:UUID
class OrganizationAuditRead(BaseModel):
    id:UUID;event_type:str;outcome:str;event_date:datetime|None=None;created_at:datetime;actor:str|None=None;description:str
