import json
from datetime import datetime,timedelta,timezone
from uuid import UUID
from fastapi import APIRouter,Depends,File,Form,HTTPException,Query,Response,UploadFile
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_active_user,require_admin
from app.db.session import get_db
from app.importers.mappings import DATASET_LABELS,DATASET_PROFILE,PROFILES
from app.models.historical import DataImportError,DataImportJob,DataSource
from app.models.user import User
from app.schemas.historical import *
from app.services.data_import_service import DataImportService
from app.services.data_source_service import DataSourceService
from app.services.dataset_version_service import DatasetVersionService,version_kind,version_kind_label
from app.services.electoral_milestone_service import ElectoralMilestoneService
from app.services.exceptions import ConflictError,NotFoundError
from app.services.security_audit_service import SecurityAuditService
router=APIRouter(tags=['official-data'])
def roles(u):return {r.code for r in u.roles}
def reader(u):
 if not (u.is_superuser or roles(u).intersection({'ADMIN','ANALYST'})):raise HTTPException(403,'Permisos insuficientes')
def fail(e):
 if isinstance(e,PermissionError):return HTTPException(403,str(e))
 if isinstance(e,NotFoundError):return HTTPException(404,str(e))
 if isinstance(e,ConflictError):return HTTPException(409,str(e))
 msg=str(e)
 if 'demasiado grande' in msg:return HTTPException(413,msg)
 if 'Solo se permiten' in msg:return HTTPException(415,msg)
 return HTTPException(400,msg)
def call(fn):
 try:return fn()
 except Exception as e:raise fail(e)
@router.post('/data-sources',response_model=DataSourceRead,status_code=201)
def create_source(data:DataSourceCreate,user:User=Depends(require_admin),db:Session=Depends(get_db)):return call(lambda:DataSourceService(db).create(data,user))
@router.get('/data-sources',response_model=list[DataSourceRead])
def sources(user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):reader(user);return DataSourceService(db).list()
@router.get('/data-sources/{id}',response_model=DataSourceRead)
def source(id:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):reader(user);return call(lambda:DataSourceService(db).get(id))
@router.patch('/data-sources/{id}',response_model=DataSourceRead)
def source_update(id:UUID,data:DataSourceUpdate,user:User=Depends(require_admin),db:Session=Depends(get_db)):return call(lambda:DataSourceService(db).update(id,data))
async def perform(source_id,dataset_type,file,mapping_profile,column_mapping_json,encoding,delimiter,force,user,db,validation):
 content=await file.read();mapping=json.loads(column_mapping_json) if column_mapping_json else None
 return call(lambda:DataImportService(db).run(source_id,dataset_type,file.filename or 'upload.csv',content,user,validation,mapping_profile,encoding,delimiter,mapping,force))
@router.post('/data-imports/validate',response_model=DataImportValidationResponse)
async def validate(source_id:UUID=Form(),dataset_type:str=Form(),file:UploadFile=File(),mapping_profile:str|None=Form(None),column_mapping_json:str|None=Form(None),encoding:str|None=Form(None),delimiter:str|None=Form(None),user:User=Depends(require_admin),db:Session=Depends(get_db)):
 job=await perform(source_id,dataset_type,file,mapping_profile,column_mapping_json,encoding,delimiter,False,user,db,True);errors=list(db.scalars(select(DataImportError).where(DataImportError.import_job_id==job.id)));return {**DataImportJobRead.model_validate(job).model_dump(),'errors':errors}
@router.post('/data-imports/execute',response_model=DataImportExecutionResponse)
async def execute(source_id:UUID=Form(),dataset_type:str=Form(),file:UploadFile=File(),mapping_profile:str|None=Form(None),column_mapping_json:str|None=Form(None),encoding:str|None=Form(None),delimiter:str|None=Form(None),force:bool=Form(False),user:User=Depends(require_admin),db:Session=Depends(get_db)):
 job=await perform(source_id,dataset_type,file,mapping_profile,column_mapping_json,encoding,delimiter,force,user,db,False);SecurityAuditService(db).record("DATA_IMPORT_EXECUTED","SUCCESS","Importación de datos ejecutada",user_id=user.id,resource_type="DATA_IMPORT_JOB",resource_id=job.id,metadata={"dataset_type":dataset_type});db.commit()
 if job.status=='COMPLETED':
  try:DatasetVersionService(db).create_from_job(job,DataSourceService(db).get(source_id))
  except ConflictError:db.rollback()
 errors=list(db.scalars(select(DataImportError).where(DataImportError.import_job_id==job.id)));return {**DataImportJobRead.model_validate(job).model_dump(),'errors':errors}
@router.get('/data-imports',response_model=list[DataImportJobRead])
def jobs(status:str|None=None,dataset_type:str|None=None,source_id:UUID|None=None,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
 reader(user);q=select(DataImportJob)
 if status:q=q.where(DataImportJob.status==status)
 if dataset_type:q=q.where(DataImportJob.dataset_type==dataset_type)
 if source_id:q=q.where(DataImportJob.source_id==source_id)
 return list(db.scalars(q.order_by(DataImportJob.started_at.desc())))
@router.get('/data-imports/{id}',response_model=DataImportJobRead)
def job(id:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
 reader(user);o=db.get(DataImportJob,id)
 if not o:raise HTTPException(404,'Importación inexistente')
 return o
@router.get('/data-imports/{id}/errors',response_model=list[DataImportErrorRead])
def errors(id:UUID,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):reader(user);return list(db.scalars(select(DataImportError).where(DataImportError.import_job_id==id).offset((page-1)*page_size).limit(page_size)))
def _dataset_types(db):return sorted({t for (t,) in db.execute(select(DataSource.dataset_type).distinct())})
@router.get('/data-hub/catalog',response_model=DataHubCatalogResponse)
def data_hub_catalog(user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
 reader(user);dvs=DatasetVersionService(db);entries=[];without_active=0;active_sources=0
 for dtype in _dataset_types(db):
  sources=list(db.scalars(select(DataSource).where(DataSource.dataset_type==dtype).order_by(DataSource.code)))
  active_sources+=sum(1 for s in sources if s.is_active)
  active_version=next((v for s in sources if (v:=dvs.active_for(s.id,dtype))),None)
  if not active_version:without_active+=1
  last_job=db.scalar(select(DataImportJob).where(DataImportJob.dataset_type==dtype).order_by(DataImportJob.started_at.desc()))
  entries.append(DataHubCatalogEntry(dataset_type=dtype,dataset_label=DATASET_LABELS.get(dtype,dtype),version_kind=version_kind(dtype),version_kind_label=version_kind_label(dtype),sources=sources,active_version=active_version,last_job=last_job,versions_count=len(dvs.list(dataset_type=dtype))))
 cutoff=datetime.now(timezone.utc)-timedelta(days=30)
 recent_imports=db.scalar(select(func.count()).select_from(DataImportJob).where(DataImportJob.started_at>=cutoff)) or 0
 imports_with_errors=db.scalar(select(func.count()).select_from(DataImportJob).where(DataImportJob.started_at>=cutoff,DataImportJob.status.in_(('FAILED','REJECTED')))) or 0
 return DataHubCatalogResponse(summary=DataHubSummary(active_sources=active_sources,datasets=len(entries),recent_imports=recent_imports,imports_with_errors=imports_with_errors,datasets_without_active_version=without_active),entries=entries)
@router.get('/data-hub/datasets/{dataset_type}',response_model=DatasetDetailResponse)
def data_hub_dataset(dataset_type:str,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
 reader(user);sources=list(db.scalars(select(DataSource).where(DataSource.dataset_type==dataset_type).order_by(DataSource.code)))
 versions=DatasetVersionService(db).list(dataset_type=dataset_type);active=next((v for v in versions if v.status=='ACTIVE'),None)
 jobs=list(db.scalars(select(DataImportJob).where(DataImportJob.dataset_type==dataset_type).order_by(DataImportJob.started_at.desc()).limit(50)))
 return DatasetDetailResponse(dataset_type=dataset_type,dataset_label=DATASET_LABELS.get(dataset_type,dataset_type),version_kind=version_kind(dataset_type),version_kind_label=version_kind_label(dataset_type),sources=sources,active_version=active,versions=versions,jobs=jobs)
@router.get('/data-hub/versions',response_model=list[DatasetVersionRead])
def data_hub_versions(dataset_type:str|None=None,source_id:UUID|None=None,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):reader(user);return DatasetVersionService(db).list(dataset_type=dataset_type,data_source_id=source_id)
@router.post('/data-hub/versions/{id}/activate',response_model=DatasetVersionRead)
def activate_version(id:UUID,user:User=Depends(require_admin),db:Session=Depends(get_db)):return call(lambda:DatasetVersionService(db).activate(id,user))
@router.post('/data-hub/versions/{id}/archive',response_model=DatasetVersionRead)
def archive_version(id:UUID,user:User=Depends(require_admin),db:Session=Depends(get_db)):return call(lambda:DatasetVersionService(db).archive(id,user))
@router.get('/data-hub/versions/{id}/diff',response_model=DatasetVersionDiff)
def diff_version(id:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):reader(user);return call(lambda:DatasetVersionService(db).diff(id))
@router.get('/data-import-profiles/{dataset_type}/template')
def import_template(dataset_type:str,user:User=Depends(require_admin),db:Session=Depends(get_db)):
 profile=DATASET_PROFILE.get(dataset_type)
 if not profile or profile not in PROFILES:raise HTTPException(404,'No existe plantilla para este tipo de conjunto')
 csv_body=','.join(PROFILES[profile])+'\n'
 return Response(content=csv_body,media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename=plantilla_{dataset_type.lower()}.csv'})
@router.get('/electoral-milestones',response_model=list[ElectoralMilestoneRead])
def milestones(electoral_process_id:UUID|None=None,status:str|None=None,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):reader(user);return ElectoralMilestoneService(db).list(electoral_process_id,status)
@router.post('/electoral-milestones',response_model=ElectoralMilestoneRead,status_code=201)
def milestone_create(data:ElectoralMilestoneCreate,user:User=Depends(require_admin),db:Session=Depends(get_db)):return call(lambda:ElectoralMilestoneService(db).create(data,user))
@router.get('/electoral-milestones/{id}',response_model=ElectoralMilestoneRead)
def milestone(id:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):reader(user);return call(lambda:ElectoralMilestoneService(db).get(id))
@router.patch('/electoral-milestones/{id}',response_model=ElectoralMilestoneRead)
def milestone_update(id:UUID,data:ElectoralMilestoneUpdate,user:User=Depends(require_admin),db:Session=Depends(get_db)):return call(lambda:ElectoralMilestoneService(db).update(id,data,user))
@router.post('/electoral-milestones/{id}/activate',response_model=ElectoralMilestoneRead)
def milestone_activate(id:UUID,user:User=Depends(require_admin),db:Session=Depends(get_db)):return call(lambda:ElectoralMilestoneService(db).set_status(id,'ACTIVE',user))
@router.post('/electoral-milestones/{id}/archive',response_model=ElectoralMilestoneRead)
def milestone_archive(id:UUID,user:User=Depends(require_admin),db:Session=Depends(get_db)):return call(lambda:ElectoralMilestoneService(db).set_status(id,'ARCHIVED',user))
