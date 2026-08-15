from datetime import datetime
from enum import StrEnum
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

class FeatureCode(StrEnum): TERRITORY_AI = "TERRITORY_AI"
class EntitlementType(StrEnum): LICENSE="LICENSE"; TRIAL="TRIAL"; ADMIN_OVERRIDE="ADMIN_OVERRIDE"

class EntitlementUpsert(BaseModel):
    feature_code: FeatureCode
    enabled: bool = True
    entitlement_type: EntitlementType
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    monthly_request_limit: int | None = None
    monthly_token_limit: int | None = None
    @model_validator(mode="after")
    def validity(self):
        if self.starts_at and self.expires_at and self.starts_at >= self.expires_at: raise ValueError("La vigencia es inválida")
        if self.monthly_request_limit is not None and self.monthly_request_limit < 1: raise ValueError("El límite debe ser positivo")
        if self.monthly_token_limit is not None and self.monthly_token_limit < 1: raise ValueError("El límite debe ser positivo")
        return self

class EntitlementRead(BaseModel):
    id: UUID; campaign_id: UUID; feature_code: FeatureCode; enabled: bool; entitlement_type: EntitlementType
    starts_at: datetime|None; expires_at: datetime|None; monthly_request_limit:int|None; monthly_token_limit:int|None
    status: str; created_at:datetime; updated_at:datetime
    model_config=ConfigDict(from_attributes=True)

class CampaignLicenseRead(BaseModel):
    campaign_id:UUID; campaign_name:str; commercial_plan:str; features:list[EntitlementRead]

class TerritoryAiQuery(BaseModel):
    question:str = Field(min_length=2, max_length=4000)
    conversation_id:UUID|None=None

class AiCitation(BaseModel): id:UUID; title:str; url:str
class TerritoryAiResponse(BaseModel): answer:str; citations:list[AiCitation]; provider:str; model:str
