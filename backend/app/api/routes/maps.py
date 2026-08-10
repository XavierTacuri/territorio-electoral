from datetime import date
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter,Depends,File,Form,HTTPException,Query,Response,UploadFile
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_active_user,require_admin
from app.db.session import get_db
from app.models.historical import DataImportError,DataImportJob
from app.models.user import User
from app.schemas.dashboard import DashboardPeriod
from app.schemas.historical import DataImportErrorRead,DataImportJobRead
from app.schemas.maps import *
from app.services.exceptions import BusinessRuleError,ConflictError,NotFoundError
from app.services.geometry_import_service import GeometryImportService
from app.services.map_service import MapService

router=APIRouter(prefix='/campaigns/{campaign_id}/map',tags=['maps']);geometry_router=APIRouter(prefix='/geometry-imports',tags=['geometry-imports'])
def filters(date_from:date|None=None,date_to:date|None=None,period:DashboardPeriod|None=None,parish_id:int|None=None,community_id:UUID|None=None,sector_id:UUID|None=None,bbox:str|None=None,zoom:int=Query(12,ge=0,le=22),simplify:bool=True,simplify_tolerance:float|None=Query(None,ge=0),include_geometry:bool=True,limit:int|None=Query(None,ge=1)):
 try:return MapFilters(date_from=date_from,date_to=date_to,period=period,parish_id=parish_id,community_id=community_id,sector_id=sector_id,bbox=bbox,zoom=zoom,simplify=simplify,simplify_tolerance=simplify_tolerance,include_geometry=include_geometry,limit=limit)
 except ValidationError as exc:raise HTTPException(422,'Filtros geográficos inválidos') from exc
def call(fn):
 try:return fn()
 except PermissionError as e:raise HTTPException(403,str(e)) from e
 except NotFoundError as e:raise HTTPException(404,str(e)) from e
 except ConflictError as e:raise HTTPException(409,str(e)) from e
 except OverflowError as e:raise HTTPException(413,str(e)) from e
 except BusinessRuleError as e:
  code=415 if 'Solo se permiten' in str(e) else 413 if 'demasiado grande' in str(e) else 400
  raise HTTPException(code,str(e)) from e
def private(response:Response):response.headers['Cache-Control']='private, max-age=60'
@router.get('/layers',response_model=MapLayerCatalogRead)
def layers(campaign_id:UUID,response:Response,f:MapFilters=Depends(filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):private(response);return call(lambda:MapService(db).layers(campaign_id,user,f))
@router.get('/bounds',response_model=MapBoundsRead)
def bounds(campaign_id:UUID,response:Response,f:MapFilters=Depends(filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):private(response);return call(lambda:MapService(db).bounds(campaign_id,user,f))
@router.get('/boundaries',response_model=GeoJSONFeatureCollectionRead)
def boundaries(campaign_id:UUID,response:Response,level:str=Query('PARISH',pattern='^(CANTON|PARISH)$'),include_metrics:bool=False,metric:str|None=None,f:MapFilters=Depends(filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):private(response);return call(lambda:MapService(db).boundaries(campaign_id,user,f,level,include_metrics,metric))
@router.get('/communities',response_model=GeoJSONFeatureCollectionRead)
def communities(campaign_id:UUID,response:Response,f:MapFilters=Depends(filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):private(response);return call(lambda:MapService(db).points(campaign_id,user,f,'COMMUNITY'))
@router.get('/sectors',response_model=GeoJSONFeatureCollectionRead)
def sectors(campaign_id:UUID,response:Response,f:MapFilters=Depends(filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):private(response);return call(lambda:MapService(db).points(campaign_id,user,f,'SECTOR'))
@router.get('/activities',response_model=GeoJSONFeatureCollectionRead)
def activities(campaign_id:UUID,response:Response,cluster:bool=True,f:MapFilters=Depends(filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):private(response);return call(lambda:MapService(db).activities(campaign_id,user,f,cluster))
@router.get('/operational-coverage',response_model=GeoJSONFeatureCollectionRead)
def coverage(campaign_id:UUID,response:Response,metric:str=Query('COMPLETED_ACTIVITIES'),f:MapFilters=Depends(filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):private(response);return call(lambda:MapService(db).thematic(campaign_id,user,f,'OPERATIONAL_COVERAGE',metric))
@router.get('/needs',response_model=GeoJSONFeatureCollectionRead)
def needs(campaign_id:UUID,response:Response,metric:str=Query('NEED_COUNT'),f:MapFilters=Depends(filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):private(response);return call(lambda:MapService(db).thematic(campaign_id,user,f,'NEEDS',metric))
@router.get('/commitments',response_model=GeoJSONFeatureCollectionRead)
def commitments(campaign_id:UUID,response:Response,metric:str=Query('PENDING_COMMITMENTS'),f:MapFilters=Depends(filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):private(response);return call(lambda:MapService(db).thematic(campaign_id,user,f,'COMMITMENTS',metric))
@router.get('/surveys',response_model=GeoJSONFeatureCollectionRead)
def surveys(campaign_id:UUID,response:Response,survey_id:UUID|None=None,question_code:str|None=None,metric:str=Query('VALID_RESPONSES'),f:MapFilters=Depends(filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):private(response);return call(lambda:MapService(db).surveys(campaign_id,user,f,survey_id,metric))
@router.get('/electoral-history',response_model=GeoJSONFeatureCollectionRead)
def electoral(campaign_id:UUID,response:Response,process_id:UUID,contest_id:UUID,metric:str=Query('PARTICIPATION_RATE'),is_final:bool=True,f:MapFilters=Depends(filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):private(response);return call(lambda:MapService(db).electoral(campaign_id,user,f,process_id,contest_id,metric,is_final))
@router.get('/participation-projection',response_model=GeoJSONFeatureCollectionRead)
def participation_projection(campaign_id:UUID,response:Response,metric:str=Query('TURNOUT_RATE_CENTRAL'),f:MapFilters=Depends(filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):private(response);return call(lambda:MapService(db).participation_projection(campaign_id,user,f,metric))
@router.get('/demographics',response_model=GeoJSONFeatureCollectionRead)
def demographics(campaign_id:UUID,response:Response,indicator_code:str,reference_year:int|None=None,source_id:UUID|None=None,f:MapFilters=Depends(filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):private(response);return call(lambda:MapService(db).demographics(campaign_id,user,f,indicator_code,reference_year,source_id))
@router.get('/features/{resource_type}/{resource_id}',response_model=MapFeatureDetailRead)
def feature(campaign_id:UUID,resource_type:str,resource_id:str,f:MapFilters=Depends(filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):
 try:rid=int(resource_id) if resource_type=='PARISH' else UUID(resource_id)
 except ValueError:raise HTTPException(422,'Identificador inválido')
 return call(lambda:MapService(db).detail(campaign_id,user,f,resource_type,rid))
@router.get('/data-quality',response_model=MapDataQualityRead)
def quality(campaign_id:UUID,f:MapFilters=Depends(filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):return call(lambda:MapService(db).quality(campaign_id,user,f))

async def run_import(source_id,file,territory_level,dpa_code_property,name_property,force,allow_make_valid,user,db,validation):
 content=await file.read();return call(lambda:GeometryImportService(db).run(source_id,file.filename or 'geometry.geojson',content,user,territory_level,dpa_code_property,name_property,validation,force,allow_make_valid))
def import_response(job,db):
 errors=list(db.scalars(select(DataImportError).where(DataImportError.import_job_id==job.id)));return {'job_id':job.id,'status':job.status,'features_read':job.rows_read,'features_valid':job.rows_valid,'features_updated':job.rows_updated,'features_rejected':job.rows_failed,'file_sha256':job.file_sha256,'errors':[DataImportErrorRead.model_validate(x).model_dump() for x in errors]}
@geometry_router.post('/validate',response_model=GeometryImportValidationRead)
async def validate_geometry(source_id:UUID=Form(),file:UploadFile=File(),territory_level:str=Form(),dpa_code_property:str=Form('dpa_code'),name_property:str=Form('name'),allow_make_valid:bool=Form(False),user:User=Depends(require_admin),db:Session=Depends(get_db)):return import_response(await run_import(source_id,file,territory_level,dpa_code_property,name_property,False,allow_make_valid,user,db,True),db)
@geometry_router.post('/execute',response_model=GeometryImportExecutionRead)
async def execute_geometry(source_id:UUID=Form(),file:UploadFile=File(),territory_level:str=Form(),dpa_code_property:str=Form('dpa_code'),name_property:str=Form('name'),force:bool=Form(False),allow_make_valid:bool=Form(False),user:User=Depends(require_admin),db:Session=Depends(get_db)):return import_response(await run_import(source_id,file,territory_level,dpa_code_property,name_property,force,allow_make_valid,user,db,False),db)
def geometry_reader(user):
 if not(user.is_superuser or {r.code for r in user.roles}.intersection({'ADMIN','ANALYST'})):raise HTTPException(403,'Permisos insuficientes')
@geometry_router.get('',response_model=list[DataImportJobRead])
def geometry_jobs(user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):geometry_reader(user);return list(db.scalars(select(DataImportJob).where(DataImportJob.mapping_profile=='TERRITORIAL_GEOJSON').order_by(DataImportJob.started_at.desc())))
@geometry_router.get('/{job_id}',response_model=DataImportJobRead)
def geometry_job(job_id:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):geometry_reader(user);job=db.get(DataImportJob,job_id);return job if job and job.mapping_profile=='TERRITORIAL_GEOJSON' else (_ for _ in ()).throw(HTTPException(404,'Importación inexistente'))
@geometry_router.get('/{job_id}/errors',response_model=list[DataImportErrorRead])
def geometry_errors(job_id:UUID,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):geometry_reader(user);return list(db.scalars(select(DataImportError).join(DataImportJob).where(DataImportError.import_job_id==job_id,DataImportJob.mapping_profile=='TERRITORIAL_GEOJSON').offset((page-1)*page_size).limit(page_size)))
