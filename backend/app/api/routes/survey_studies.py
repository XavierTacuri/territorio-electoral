from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query,Response,UploadFile,File
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.survey_study import *
from app.services.exceptions import ConflictError,NotFoundError
from app.services.survey_study_service import SurveyStudyService

router=APIRouter(tags=["survey-studies"])
def run(fn):
    try:return fn()
    except PermissionError as e:raise HTTPException(403,str(e))
    except NotFoundError as e:raise HTTPException(404,str(e))
    except ConflictError as e:raise HTTPException(409,str(e))
    except Exception as e:raise HTTPException(400,str(e))

@router.get("/campaigns/{campaign_id}/survey-studies",response_model=StudyList)
def list_studies(campaign_id:UUID,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),status:StudyStatus|None=None,study_type:StudyType|None=None,parish_id:int|None=None,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return run(lambda:SurveyStudyService(db).list(campaign_id,user,page,page_size,status,study_type,parish_id))
@router.post("/campaigns/{campaign_id}/survey-studies",response_model=StudyRead,status_code=201)
def create_study(campaign_id:UUID,data:StudyCreate,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return run(lambda:SurveyStudyService(db).create(campaign_id,data,user))
@router.get("/survey-studies/{study_id}",response_model=StudyDetail)
def detail(study_id:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return run(lambda:SurveyStudyService(db).read(SurveyStudyService(db).get(study_id,user),True))
@router.patch("/survey-studies/{study_id}",response_model=StudyRead)
def update(study_id:UUID,data:StudyUpdate,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return run(lambda:SurveyStudyService(db).update(study_id,data,user))
@router.delete("/survey-studies/{study_id}",status_code=204)
def delete(study_id:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):run(lambda:SurveyStudyService(db).delete(study_id,user));return Response(status_code=204)
@router.post("/survey-studies/{study_id}/territories",response_model=TerritoryRead,status_code=201)
def territory(study_id:UUID,data:TerritoryInput,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return run(lambda:SurveyStudyService(db).add_territory(study_id,data,user))
@router.post("/survey-studies/{study_id}/options",response_model=OptionRead,status_code=201)
def option(study_id:UUID,data:OptionInput,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return run(lambda:SurveyStudyService(db).add_option(study_id,data,user))
@router.get("/survey-studies/{study_id}/results",response_model=list[ResultRead])
def results(study_id:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return run(lambda:SurveyStudyService(db).read(SurveyStudyService(db).get(study_id,user),True).results)
@router.put("/survey-studies/{study_id}/results",response_model=list[ResultRead])
def put_results(study_id:UUID,data:list[ResultInput],user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return run(lambda:SurveyStudyService(db).replace_results(study_id,data,user))
@router.post("/survey-studies/{study_id}/validate",response_model=ValidationResponse)
def validate(study_id:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return run(lambda:SurveyStudyService(db).validate(study_id,user))
@router.post("/survey-studies/{study_id}/publish",response_model=StudyDetail)
def publish(study_id:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return run(lambda:SurveyStudyService(db).publish(study_id,user))
@router.post("/survey-studies/{study_id}/archive",response_model=StudyDetail)
def archive(study_id:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return run(lambda:SurveyStudyService(db).archive(study_id,user))
@router.get("/campaigns/{campaign_id}/survey-analysis",response_model=ComparisonResponse)
def analysis(campaign_id:UUID,study_ids:list[UUID]=Query(),user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    service=SurveyStudyService(db);service.campaign(campaign_id,user)
    return run(lambda:service.compare(study_ids,user))
@router.post("/campaigns/{campaign_id}/survey-imports/validate",response_model=SurveyImportSummary)
async def validate_import(campaign_id:UUID,file:UploadFile=File(),user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    if not (file.filename or "").lower().endswith(".csv"):raise HTTPException(415,"Solo se permiten archivos CSV")
    content=await file.read();return run(lambda:SurveyStudyService(db).validate_import(campaign_id,content,user))
@router.post("/campaigns/{campaign_id}/survey-imports/execute",response_model=SurveyImportSummary)
async def execute_import(campaign_id:UUID,file:UploadFile=File(),user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    if not (file.filename or "").lower().endswith(".csv"):raise HTTPException(415,"Solo se permiten archivos CSV")
    content=await file.read();return run(lambda:SurveyStudyService(db).execute_import(campaign_id,content,user))
@router.get("/campaigns/{campaign_id}/survey-imports/template")
def import_template(campaign_id:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    service=SurveyStudyService(db);service.campaign(campaign_id,user,True)
    csv=("study_code,question_code,question_text,question_type,option_code,option_label,percentage,base_n,parish_dpa\n"
         "DEMO_ESTUDIO,Q1,Principal problema del cantón,SINGLE_CHOICE,OPCION_A,Opción sintética A,42.5,800,\n")
    return Response(content=csv,media_type="text/csv; charset=utf-8",headers={"Content-Disposition":"attachment; filename=plantilla_encuesta_general.csv"})
