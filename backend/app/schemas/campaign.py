from datetime import date
from enum import StrEnum
from uuid import UUID
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, field_validator, model_validator
from app.schemas.user import UserSummary
class OfficeType(StrEnum): MAYOR="MAYOR"; URBAN_COUNCILOR="URBAN_COUNCILOR"; RURAL_COUNCILOR="RURAL_COUNCILOR"; PARISH_BOARD="PARISH_BOARD"
class CampaignStatus(StrEnum): DRAFT="DRAFT"; ACTIVE="ACTIVE"; COMPLETED="COMPLETED"; ARCHIVED="ARCHIVED"
def clean(v:str)->str:
    v=" ".join(v.split())
    if not v: raise ValueError("El valor no puede estar vacío")
    return v
class CampaignCreate(BaseModel):
    name:str; slug:str; canton_id:int; office_type:OfficeType; election_name:str; election_date:date; start_date:date|None=None; end_date:date|None=None; status:CampaignStatus=CampaignStatus.DRAFT; description:str|None=None; is_active:bool=True
    model_config=ConfigDict(extra="forbid")
    _names=field_validator("name","election_name")(clean)
    @field_validator("slug")
    @classmethod
    def slug_valid(cls,v:str)->str:
        v=v.strip().lower()
        if not v or " " in v: raise ValueError("Slug inválido")
        return v
    @model_validator(mode="after")
    def dates(self):
        if self.start_date and self.end_date and self.start_date>self.end_date: raise ValueError("La fecha inicial no puede ser posterior a la final")
        if self.start_date and self.election_date<self.start_date: raise ValueError("La elección no puede ser anterior al inicio")
        return self
class CampaignUpdate(BaseModel):
    name:str|None=None; slug:str|None=None; office_type:OfficeType|None=None; election_name:str|None=None; election_date:date|None=None; start_date:date|None=None; end_date:date|None=None; status:CampaignStatus|None=None; description:str|None=None; is_active:bool|None=None
    model_config=ConfigDict(extra="forbid")
class CampaignSummary(BaseModel):
    id:UUID; name:str; slug:str; canton_id:int; canton_name:str|None=None; province_id:int|None=None; province_name:str|None=None; office_type:OfficeType; election_name:str; election_date:date; status:CampaignStatus; is_active:bool
    model_config=ConfigDict(from_attributes=True)
class CampaignRead(CampaignSummary):
    start_date:date|None; end_date:date|None; description:str|None; candidate:"CandidateRead|None"=None
class CampaignListResponse(BaseModel): items:list[CampaignSummary]; page:int; page_size:int; total:int; total_pages:int
class CandidateCreate(BaseModel):
    user_id:UUID|None=None; first_name:str; last_name:str; display_name:str; birth_date:date|None=None; political_organization:str|None=None; list_number:int|None=None; biography:str|None=None; photo_url:AnyHttpUrl|None=None; is_active:bool=True
    model_config=ConfigDict(extra="forbid")
    @model_validator(mode="after")
    def birth(self):
        if self.birth_date and self.birth_date>date.today(): raise ValueError("La fecha de nacimiento no puede estar en el futuro")
        return self
class CandidateUpdate(BaseModel):
    user_id:UUID|None=None; first_name:str|None=None; last_name:str|None=None; display_name:str|None=None; birth_date:date|None=None; political_organization:str|None=None; list_number:int|None=None; biography:str|None=None; photo_url:AnyHttpUrl|None=None; is_active:bool|None=None
    model_config=ConfigDict(extra="forbid")
class CandidateRead(BaseModel):
    id:UUID; campaign_id:UUID; user_id:UUID|None; first_name:str; last_name:str; display_name:str; birth_date:date|None; political_organization:str|None; list_number:int|None; biography:str|None; photo_url:str|None; is_active:bool
    model_config=ConfigDict(from_attributes=True)
class CampaignUserAssign(BaseModel): user_id:UUID
class CampaignUserRead(BaseModel): id:UUID; campaign_id:UUID; user_id:UUID; is_active:bool
class TerritorialAssignmentCreate(BaseModel): user_id:UUID; parish_id:int; community_id:UUID|None=None; sector_id:UUID|None=None
class TerritorialAssignmentRead(BaseModel): id:UUID; campaign_id:UUID; user_id:UUID; parish_id:int; community_id:UUID|None; sector_id:UUID|None; is_active:bool
