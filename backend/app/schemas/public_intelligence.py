from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID
from urllib.parse import urlparse
from pydantic import BaseModel, ConfigDict, Field, field_validator

class SourceType(StrEnum):
    OFFICIAL_WEBSITE="OFFICIAL_WEBSITE";OFFICIAL_API="OFFICIAL_API";OPEN_DATA="OPEN_DATA";RSS="RSS";NEWS="NEWS";PUBLIC_DOCUMENT_REPOSITORY="PUBLIC_DOCUMENT_REPOSITORY";OTHER="OTHER"
class RetrievalMethod(StrEnum):MANUAL="MANUAL";RSS="RSS";API="API";WEB_PAGE="WEB_PAGE";FILE_DOWNLOAD="FILE_DOWNLOAD"
class SourceBase(BaseModel):
    model_config=ConfigDict(extra="forbid")
    code:str=Field(min_length=2,max_length=80);name:str=Field(min_length=2,max_length=180);publisher:str=Field(min_length=2,max_length=180);source_type:SourceType;base_url:str;feed_url:str|None=None;api_url:str|None=None;jurisdiction:str|None=None;country:str="EC";province:str|None=None;canton:str|None=None;official:bool=False;active:bool=True;retrieval_method:RetrievalMethod;refresh_interval_minutes:int|None=Field(None,ge=15,le=43200);terms_notes:str|None=None;license_notes:str|None=None;credential_reference:str|None=None;adapter_config:dict[str,Any]=Field(default_factory=dict)
    @field_validator("base_url","feed_url","api_url")
    @classmethod
    def safe_scheme(cls,v):
        if v is None:return v
        p=urlparse(v)
        if p.scheme not in {"http","https"} or not p.hostname or p.username or p.password:raise ValueError("URL pública inválida; use http/https sin credenciales")
        return v
class PublicSourceCreate(SourceBase):pass
class PublicSourceUpdate(BaseModel):
    model_config=ConfigDict(extra="forbid")
    name:str|None=None;publisher:str|None=None;source_type:SourceType|None=None;base_url:str|None=None;feed_url:str|None=None;api_url:str|None=None;jurisdiction:str|None=None;official:bool|None=None;active:bool|None=None;retrieval_method:RetrievalMethod|None=None;refresh_interval_minutes:int|None=None;terms_notes:str|None=None;license_notes:str|None=None;adapter_config:dict[str,Any]|None=None
class PublicSourceRead(SourceBase):
    model_config=ConfigDict(from_attributes=True)
    id:UUID;campaign_id:UUID;last_fetch_at:datetime|None;last_success_at:datetime|None;consecutive_failures:int;items_last_fetch:int
    freshness_status:str|None=None;next_refresh_at:datetime|None=None;stale_after_at:datetime|None=None
class ItemRead(BaseModel):
    id:UUID;source_id:UUID;source_name:str;source_url:str;publisher:str;official:bool;title:str;summary:str|None;item_type:str;url:str;canonical_url:str;published_at:datetime|None;fetched_at:datetime;author:str|None;content_excerpt:str|None;language:str;content_hash:str;status:str;topics:list[dict]=[];territories:list[dict]=[];revisions:list[dict]=[]
class ItemPage(BaseModel):items:list[ItemRead];page:int;page_size:int;total:int;total_pages:int
class FetchRunRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:UUID;source_id:UUID;started_at:datetime;finished_at:datetime|None;status:str;items_discovered:int;items_created:int;items_updated:int;items_unchanged:int;items_failed:int;error_summary:str|None;trigger_type:str
class SummaryRead(BaseModel):active_sources:int;official_sources:int;items_last_24h:int;items_last_7_days:int;new_documents:int;sources_with_error:int;last_update:datetime|None;latest_items:list[ItemRead]
class MapMetricRead(BaseModel):parish_id:int;dpa_code:str;name:str;value:int
class NeedLinkCreate(BaseModel):need_id:UUID
