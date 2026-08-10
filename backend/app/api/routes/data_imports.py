import json
from uuid import UUID
from fastapi import APIRouter,Depends,File,Form,HTTPException,Query,UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_active_user,require_admin
from app.db.session import get_db
from app.models.historical import DataImportError,DataImportJob
from app.models.user import User
from app.schemas.historical import *
from app.services.data_import_service import DataImportService
from app.services.data_source_service import DataSourceService
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
 job=await perform(source_id,dataset_type,file,mapping_profile,column_mapping_json,encoding,delimiter,force,user,db,False);SecurityAuditService(db).record("DATA_IMPORT_EXECUTED","SUCCESS","Importación de datos ejecutada",user_id=user.id,resource_type="DATA_IMPORT_JOB",resource_id=job.id,metadata={"dataset_type":dataset_type});db.commit();errors=list(db.scalars(select(DataImportError).where(DataImportError.import_job_id==job.id)));return {**DataImportJobRead.model_validate(job).model_dump(),'errors':errors}
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
