import json
from math import isfinite
from app.services.exceptions import BusinessRuleError

def parse_feature_collection(content:bytes)->dict:
    try:data=json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError,json.JSONDecodeError) as exc:raise BusinessRuleError("GeoJSON inválido") from exc
    if not isinstance(data,dict) or data.get("type")!="FeatureCollection" or not isinstance(data.get("features"),list):raise BusinessRuleError("Se requiere un FeatureCollection")
    if "crs" in data:raise BusinessRuleError("No se acepta CRS declarado; convierta previamente a EPSG:4326")
    return data
def walk_coordinates(value):
    if isinstance(value,(int,float)):
        if not isfinite(value):raise BusinessRuleError("Coordenada no finita")
        return
    if not isinstance(value,list) or not value:raise BusinessRuleError("Coordenadas inválidas")
    for item in value:walk_coordinates(item)
def validate_geometry(geometry:dict,expected:str):
    if not isinstance(geometry,dict) or geometry.get("type") in {None,"GeometryCollection"}:raise BusinessRuleError("Tipo geométrico no permitido")
    kind=geometry["type"]
    allowed={"MULTIPOLYGON":{"Polygon","MultiPolygon"},"POINT":{"Point"}}[expected]
    if kind not in allowed:raise BusinessRuleError(f"Se esperaba {expected}")
    coordinates=geometry.get("coordinates");walk_coordinates(coordinates)
    if kind=="Point":
        if len(coordinates)!=2 or not(-180<=coordinates[0]<=180 and -90<=coordinates[1]<=90):raise BusinessRuleError("Punto fuera de EPSG:4326")
    return {"type":"MultiPolygon","coordinates":[coordinates]} if kind=="Polygon" else geometry
