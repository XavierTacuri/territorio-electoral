from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class TerritoryAIIntent(StrEnum):
    TERRITORY_SUMMARY="TERRITORY_SUMMARY"; ELECTORAL_REGISTER="ELECTORAL_REGISTER"; HISTORICAL_TURNOUT="HISTORICAL_TURNOUT"; TURNOUT_PROJECTION="TURNOUT_PROJECTION"; DEMOGRAPHICS="DEMOGRAPHICS"; SURVEY_STUDIES="SURVEY_STUDIES"; OPERATIONS="OPERATIONS"; NEEDS="NEEDS"; COMMITMENTS="COMMITMENTS"; PUBLIC_INTELLIGENCE="PUBLIC_INTELLIGENCE"; SOURCE_LOOKUP="SOURCE_LOOKUP"; GENERAL_GROUNDED_SEARCH="GENERAL_GROUNDED_SEARCH"
class TerritoryAISourceKind(StrEnum):
    CNE="CNE"; TURNOUT_MODEL="TURNOUT_MODEL"; INEC="INEC"; SURVEY_STUDY="SURVEY_STUDY"; TERRITORIAL_ACTIVITY="TERRITORIAL_ACTIVITY"; CITIZEN_NEED="CITIZEN_NEED"; COMMITMENT="COMMITMENT"; PUBLIC_INTELLIGENCE="PUBLIC_INTELLIGENCE"; SYSTEM_METADATA="SYSTEM_METADATA"
class PoliticalSafetyCategory(StrEnum):
    DESCRIPTIVE="DESCRIPTIVE"; OPERATIONAL="OPERATIONAL"; METHODOLOGY="METHODOLOGY"; PUBLIC_INFORMATION="PUBLIC_INFORMATION"; AGGREGATE_STUDY="AGGREGATE_STUDY"; MICROTARGETING="MICROTARGETING"; PERSUASION="PERSUASION"; INDIVIDUAL_POLITICAL_PROFILING="INDIVIDUAL_POLITICAL_PROFILING"; WIN_PREDICTION="WIN_PREDICTION"; SECRET_EXTRACTION="SECRET_EXTRACTION"

class TerritoryReference(BaseModel):
    id:int
    name:str
    dpa_code:str
    level:str
    campaign_id:UUID|None=None
    canton_id:int
class TerritoryAIEvidence(BaseModel):
    evidence_id:str; source_kind:TerritoryAISourceKind; title:str; structured_data:dict[str,Any]=Field(default_factory=dict); excerpt:str|None=None; source_name:str; source_url:str|None=None; record_date:date|datetime|None=None; data_cutoff:date|datetime|None=None; territory:TerritoryReference|None=None; campaign_id:UUID; freshness:str="UNKNOWN"; internal_path:str|None=None; metadata:dict[str,Any]=Field(default_factory=dict); trust_level:str="TRUSTED"
class TerritoryAICitation(BaseModel):
    id:str; source_type:TerritoryAISourceKind; title:str; source_name:str; reference_date:date|datetime|None=None; data_cutoff:date|datetime|None=None; territory:TerritoryReference|None=None; excerpt:str|None=None; internal_path:str|None=None; external_url:str|None=None; freshness:str
class ProviderStructuredOutput(BaseModel): answer:str=Field(min_length=1,max_length=12000);citation_ids:list[str]=Field(default_factory=list,max_length=30);limitations:list[str]=Field(default_factory=list,max_length=20)
class TerritoryAIQueryPlan(BaseModel): intent:TerritoryAIIntent; intents:list[TerritoryAIIntent]=Field(default_factory=list); source_kinds:list[TerritoryAISourceKind]; territory:TerritoryReference|None=None; context_ids:dict[str,str]=Field(default_factory=dict)
class TerritoryAIQueryRequest(BaseModel):
    question:str=Field(min_length=2,max_length=4000);conversation_id:UUID|None=None;parish_id:int|None=None;study_id:UUID|None=None;activity_id:UUID|None=None;need_id:UUID|None=None;public_item_id:UUID|None=None
class TerritoryAIResponse(BaseModel):
    answer:str; citations:list[TerritoryAICitation]; limitations:list[str]=Field(default_factory=list); intent:TerritoryAIIntent; territory:TerritoryReference|None=None; conversation_id:UUID|None=None; message_id:UUID|None=None; provider:str|None=None; model:str|None=None; status:str="ANSWERED"
class TerritoryAIMessageRead(BaseModel): id:UUID;role:str;content:str;citations:list[dict];created_at:datetime;model_config=ConfigDict(from_attributes=True)
class TerritoryAIConversationRead(BaseModel): id:UUID;campaign_id:UUID;user_id:UUID;title:str;created_at:datetime;updated_at:datetime;messages:list[TerritoryAIMessageRead]=Field(default_factory=list);model_config=ConfigDict(from_attributes=True)
