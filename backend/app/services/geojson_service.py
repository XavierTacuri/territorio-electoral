import json
from app.core.config import settings
class GeoJSONService:
 @staticmethod
 def geometry(value):return json.loads(value) if isinstance(value,str) else value
 @staticmethod
 def feature(resource_id,geometry,properties):return {"type":"Feature","id":str(resource_id),"geometry":GeoJSONService.geometry(geometry),"properties":properties}
 @staticmethod
 def collection(features,bbox=None,status="AVAILABLE",unmapped=0,warnings=None,metadata=None):
  payload={"type":"FeatureCollection","bbox":bbox,"features":features,"data_status":status,"unmapped_count":unmapped,"warnings":warnings or [],"metadata":metadata or {}}
  if len(json.dumps(payload,default=str).encode())>settings.map_max_geojson_bytes:raise OverflowError("La consulta geográfica supera el límite permitido. Reduzca el área, utilice clustering o aumente el nivel de zoom.")
  return payload
