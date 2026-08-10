from enum import StrEnum
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class ParishType(StrEnum): URBAN="URBAN"; RURAL="RURAL"
def clean(v: str) -> str:
    v=" ".join(v.split())
    if not v: raise ValueError("El valor no puede estar vacío")
    return v
class ProvinceRead(BaseModel):
    id:int; code:str; name:str; is_active:bool
    model_config=ConfigDict(from_attributes=True)
class CantonBase(BaseModel):
    province_id:int; code:str; dpa_code:str; name:str; is_active:bool=True
    model_config=ConfigDict(extra="forbid")
    _name=field_validator("name")(clean)
class CantonCreate(CantonBase): pass
class CantonUpdate(BaseModel):
    code:str|None=None; dpa_code:str|None=None; name:str|None=None; is_active:bool|None=None
    model_config=ConfigDict(extra="forbid")
class CantonRead(CantonBase):
    id:int
    model_config=ConfigDict(from_attributes=True)
class ParishBase(BaseModel):
    canton_id:int; code:str; dpa_code:str; name:str; parish_type:ParishType; is_active:bool=True
    model_config=ConfigDict(extra="forbid")
    _name=field_validator("name")(clean)
class ParishCreate(ParishBase): pass
class ParishUpdate(BaseModel):
    code:str|None=None; dpa_code:str|None=None; name:str|None=None; parish_type:ParishType|None=None; is_active:bool|None=None
    model_config=ConfigDict(extra="forbid")
class ParishRead(ParishBase):
    id:int
    model_config=ConfigDict(from_attributes=True)
class PlaceBase(BaseModel):
    name:str; code:str|None=None; description:str|None=None; latitude:float|None=Field(None,ge=-90,le=90); longitude:float|None=Field(None,ge=-180,le=180); is_active:bool=True
    model_config=ConfigDict(extra="forbid")
    _name=field_validator("name")(clean)
    @model_validator(mode="after")
    def coordinate_pair(self):
        if (self.latitude is None)!=(self.longitude is None): raise ValueError("Latitud y longitud deben enviarse juntas")
        return self
class CommunityCreate(PlaceBase):
    parish_id:int; is_official:bool=False
class CommunityUpdate(PlaceBase):
    name:str|None=None; is_official:bool|None=None
class CommunityRead(PlaceBase):
    id:UUID; parish_id:int; is_official:bool
    model_config=ConfigDict(from_attributes=True)
class SectorCreate(PlaceBase): community_id:UUID
class SectorUpdate(PlaceBase): name:str|None=None
class SectorRead(PlaceBase):
    id:UUID; community_id:UUID
    model_config=ConfigDict(from_attributes=True)
class CommunityListResponse(BaseModel): items:list[CommunityRead]; page:int; page_size:int; total:int; total_pages:int
class SectorListResponse(BaseModel): items:list[SectorRead]; page:int; page_size:int; total:int; total_pages:int
