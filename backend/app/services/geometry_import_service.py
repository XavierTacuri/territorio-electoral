import hashlib,json,tempfile
from datetime import datetime,timezone
from pathlib import Path
from uuid import UUID
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.importers.geojson_utils import parse_feature_collection,validate_geometry
from app.models.historical import DataImportError,DataImportJob
from app.models.territory import Canton,Community,Parish,Sector
from app.services.data_source_service import DataSourceService
from app.services.exceptions import BusinessRuleError,ConflictError

class GeometryImportService:
 def __init__(self,db:Session):self.db=db
 def run(self,source_id:UUID,filename:str,content:bytes,user,territory_level:str,dpa_code_property="dpa_code",name_property="name",validation_only=False,force=False,allow_make_valid=False):
  source=DataSourceService(self.db).get(source_id)
  if not source.is_active:raise BusinessRuleError("Fuente inactiva")
  suffix=Path(filename).suffix.lower()
  if suffix not in {'.geojson','.json'}:raise BusinessRuleError("Solo se permiten archivos GeoJSON o JSON")
  if len(content)>settings.map_geometry_import_max_file_mb*1024*1024:raise BusinessRuleError("Archivo geográfico demasiado grande")
  sha=hashlib.sha256(content).hexdigest();existing=self.db.scalar(select(DataImportJob).where(DataImportJob.source_id==source_id,DataImportJob.dataset_type=='OTHER_AGGREGATED_OFFICIAL',DataImportJob.file_sha256==sha,DataImportJob.mapping_profile=='TERRITORIAL_GEOJSON',DataImportJob.status=='COMPLETED'))
  if existing and not force:raise ConflictError("El archivo ya fue importado")
  job=DataImportJob(source_id=source_id,dataset_type='OTHER_AGGREGATED_OFFICIAL',original_filename=Path(filename).name[:255],file_sha256=sha,file_size_bytes=len(content),status='VALIDATING',validation_only=validation_only,mapping_profile='TERRITORIAL_GEOJSON',executed_by_user_id=user.id);self.db.add(job);self.db.commit();self.db.refresh(job);temp=None
  try:
   with tempfile.NamedTemporaryFile(prefix='te-geometry-',suffix=suffix,delete=False) as handle:handle.write(content);temp=Path(handle.name)
   data=parse_feature_collection(temp.read_bytes());level=territory_level.upper()
   if level not in {'CANTON','PARISH','COMMUNITY','SECTOR'}:raise BusinessRuleError("Nivel territorial inválido")
   expected='MULTIPOLYGON' if level in {'CANTON','PARISH'} else 'POINT';valid=[];errors=[];seen=set()
   for number,feature in enumerate(data['features'],1):
    try:
     if not isinstance(feature,dict) or feature.get('type')!='Feature':raise BusinessRuleError('Feature inválida')
     props=feature.get('properties') or {};key=str(props.get(dpa_code_property) or feature.get('id') or '').strip()
     if not key:raise BusinessRuleError('Identificador territorial faltante')
     if key in seen:raise BusinessRuleError('Recurso duplicado dentro del archivo')
     seen.add(key);geometry=validate_geometry(feature.get('geometry'),expected);obj=self.lookup(level,key,props.get(name_property))
     if not obj:raise BusinessRuleError('Código o recurso territorial inexistente')
     warning=None
     if self.db.bind.dialect.name=='postgresql':
      geom=func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(geometry)),4326);is_valid=self.db.scalar(select(func.ST_IsValid(geom)))
      if not is_valid:
       if not allow_make_valid:raise BusinessRuleError('Geometría inválida')
       geom=func.ST_MakeValid(geom);warning='Geometría reparada mediante ST_MakeValid'
      final_type=self.db.scalar(select(func.GeometryType(geom)))
      if expected=='MULTIPOLYGON' and final_type not in {'POLYGON','MULTIPOLYGON'}:raise BusinessRuleError('La reparación cambió el tipo geométrico')
     valid.append((obj,geometry,warning))
    except BusinessRuleError as exc:errors.append((number,str(exc)))
   job.rows_read=len(data['features']);job.rows_valid=len(valid);job.rows_failed=len(errors)
   for number,message in errors[:settings.data_import_max_errors]:self.db.add(DataImportError(import_job_id=job.id,row_number=number,column_name='geometry',error_code='INVALID_GEOMETRY_FEATURE',message=message[:500],rejected_value_preview=None))
   if errors:job.status='REJECTED';job.error_summary=f'{len(errors)} features rechazadas';job.finished_at=datetime.now(timezone.utc);self.db.commit();return job
   if validation_only:job.status='VALIDATED';job.finished_at=datetime.now(timezone.utc);self.db.commit();return job
   job.status='IMPORTING';self.db.commit();updated=0
   for obj,geometry,warning in valid:
    geom=func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(geometry)),4326)
    if warning:geom=func.ST_MakeValid(geom)
    if level in {'CANTON','PARISH'}:geom=func.ST_Multi(geom);obj.geometry=geom
    else:obj.location=geom
    updated+=1
   self.db.flush();job.rows_updated=updated;job.status='COMPLETED';job.finished_at=datetime.now(timezone.utc);self.db.commit();return job
  except Exception:
   self.db.rollback();job=self.db.get(DataImportJob,job.id);job.status='FAILED';job.error_summary='La importación geográfica no pudo completarse';job.finished_at=datetime.now(timezone.utc);self.db.commit();raise
  finally:
   if temp and temp.exists():temp.unlink()
 def lookup(self,level,key,name=None):
  if level=='CANTON':return self.db.scalar(select(Canton).where(Canton.dpa_code==key))
  if level=='PARISH':return self.db.scalar(select(Parish).where(Parish.dpa_code==key))
  model=Community if level=='COMMUNITY' else Sector
  try:return self.db.get(model,UUID(key))
  except ValueError:
   return self.db.scalar(select(model).where(func.lower(model.name)==str(name or key).strip().lower()))
