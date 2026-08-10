from datetime import date
from enum import StrEnum
from math import isfinite
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.schemas.dashboard import DashboardPeriod


ALLOWED_PROPERTIES={"resource_id","resource_type","name","code","territory_level","campaign_id","metric_code","metric_label","metric_value","metric_unit","data_status","suppressed","geometry_source","geometry_quality"}

class GeoJSONGeometry(BaseModel):
    type:str
    coordinates:Any
class GeoJSONPoint(GeoJSONGeometry):
    type:Literal["Point"]="Point"
    coordinates:list[float]
class GeoJSONMultiPolygon(GeoJSONGeometry):
    type:Literal["MultiPolygon"]="MultiPolygon"
    coordinates:list
class GeoJSONFeature(BaseModel):
    type:Literal["Feature"]="Feature";id:str|int|UUID;geometry:GeoJSONGeometry|None;properties:dict[str,Any]
class GeoJSONFeatureCollectionRead(BaseModel):
    type:Literal["FeatureCollection"]="FeatureCollection";bbox:list[float]|None=None;features:list[GeoJSONFeature]=[];data_status:str="AVAILABLE";unmapped_count:int=0;warnings:list[str]=[];metadata:dict[str,Any]={}
class GeoJSONBoundingBox(BaseModel):
    min_lon:float;min_lat:float;max_lon:float;max_lat:float
    @model_validator(mode="after")
    def valid(self):
        vals=(self.min_lon,self.min_lat,self.max_lon,self.max_lat)
        if not all(isfinite(v) for v in vals) or not(-180<=self.min_lon<self.max_lon<=180) or not(-90<=self.min_lat<self.max_lat<=90):raise ValueError("Bounding box inválido")
        return self
    def as_list(self):return [self.min_lon,self.min_lat,self.max_lon,self.max_lat]
class MapFilters(BaseModel):
    model_config=ConfigDict(extra="forbid")
    date_from:date|None=None;date_to:date|None=None;period:DashboardPeriod|None=None;parish_id:int|None=None;community_id:UUID|None=None;sector_id:UUID|None=None;bbox:GeoJSONBoundingBox|None=None;zoom:int=Field(12,ge=0,le=22);simplify:bool=True;simplify_tolerance:float|None=Field(None,ge=0);include_geometry:bool=True;limit:int|None=Field(None,ge=1)
    @field_validator("bbox",mode="before")
    @classmethod
    def parse_bbox(cls,v):
        if v is None or isinstance(v,GeoJSONBoundingBox):return v
        try:
            values=[float(x) for x in v.split(",")]
            if len(values)!=4:raise ValueError
            return GeoJSONBoundingBox(min_lon=values[0],min_lat=values[1],max_lon=values[2],max_lat=values[3])
        except Exception as exc:raise ValueError("bbox debe contener cuatro coordenadas válidas") from exc
    @model_validator(mode="after")
    def hierarchy(self):
        if self.community_id and not self.parish_id:raise ValueError("community_id requiere parish_id")
        if self.sector_id and not self.community_id:raise ValueError("sector_id requiere community_id")
        if self.date_from and self.date_to and self.date_from>self.date_to:raise ValueError("Rango de fechas inválido")
        return self
class MapLayerRead(BaseModel):code:str;name:str;description:str;geometry_type:str;territory_levels:list[str];metrics:list[str];filters:list[str];min_zoom:int;max_zoom:int;available:bool;data_status:str;unavailable_reason:str|None=None
class MapLayerCatalogRead(BaseModel):layers:list[MapLayerRead]
class MapBoundsRead(BaseModel):canton_bbox:list[float]|None;accessible_bbox:list[float]|None;center:list[float]|None;recommended_zoom:int;geometry_available:bool;territories_without_geometry:int
class MapFeatureDetailRead(BaseModel):resource_type:str;resource_id:str;geometry:GeoJSONGeometry|None;properties:dict[str,Any];summary:dict[str,Any]
class MapActivityMetadataRead(BaseModel):activities_without_location:int;clustered:bool;returned_features:int
class MapClusterPropertiesRead(BaseModel):cluster_id:str;point_count:int;completed:int;planned:int;cancelled:int;estimated_attendees:int;cluster_bbox:list[float]|None;is_cluster:bool=True
class MapDataQualityIssue(BaseModel):code:str;description:str;count:int;resource_type:str;status:str;technical_action:str|None=None
class MapDataQualityRead(BaseModel):status:str;issues:list[MapDataQualityIssue]
class GeometryImportValidationRead(BaseModel):job_id:UUID;status:str;features_read:int;features_valid:int;features_updated:int;features_rejected:int;file_sha256:str;errors:list[dict[str,Any]]=[]
class GeometryImportExecutionRead(GeometryImportValidationRead):pass
