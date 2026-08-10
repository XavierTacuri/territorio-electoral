from datetime import date
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query,Response
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.survey import *
from app.services.exceptions import ConflictError,NotFoundError
from app.services.survey_service import SurveyService
router=APIRouter(tags=['surveys'])
def fail(e):
    if isinstance(e,PermissionError):return HTTPException(403,str(e))
    if isinstance(e,NotFoundError):return HTTPException(404,str(e))
    if isinstance(e,ConflictError):return HTTPException(409,str(e))
    return HTTPException(400,str(e))
def call(fn):
    try:return fn()
    except Exception as e:raise fail(e)
@router.post('/campaigns/{cid}/surveys',response_model=SurveyRead,status_code=201)
def create(cid:UUID,data:SurveyCreate,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:SurveyService(db).create(cid,data,user))
@router.get('/campaigns/{cid}/surveys',response_model=SurveyListResponse)
def surveys(cid:UUID,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),search:str|None=None,status:SurveyStatus|None=None,target_scope:TargetScope|None=None,is_active:bool|None=None,date_from:date|None=None,date_to:date|None=None,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    if date_from and date_to and date_from>date_to:raise HTTPException(400,'Rango inválido')
    return call(lambda:SurveyService(db).list(cid,user,page,page_size,search=search,status=status,target_scope=target_scope,is_active=is_active,date_from=date_from,date_to=date_to))
@router.get('/campaigns/{cid}/surveys/{sid}',response_model=SurveyDetail)
def detail(cid:UUID,sid:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:SurveyService(db).detail(cid,sid,user))
@router.patch('/campaigns/{cid}/surveys/{sid}',response_model=SurveyRead)
def update(cid:UUID,sid:UUID,data:SurveyUpdate,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:SurveyService(db).update(cid,sid,data,user))
@router.delete('/campaigns/{cid}/surveys/{sid}',status_code=204)
def delete(cid:UUID,sid:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):call(lambda:SurveyService(db).deactivate(cid,sid,user));return Response(status_code=204)
@router.post('/campaigns/{cid}/surveys/{sid}/sections',response_model=SurveySectionRead,status_code=201)
def section(cid:UUID,sid:UUID,data:SurveySectionCreate,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:SurveyService(db).add_section(cid,sid,data,user))
@router.patch('/campaigns/{cid}/surveys/{sid}/sections/{id}',response_model=SurveySectionRead)
def section_update(cid:UUID,sid:UUID,id:UUID,data:SurveySectionUpdate,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:SurveyService(db).update_section(cid,sid,id,data,user))
@router.delete('/campaigns/{cid}/surveys/{sid}/sections/{id}',status_code=204)
def section_delete(cid:UUID,sid:UUID,id:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    def work():o=SurveyService(db).section(cid,sid,id,user);o.is_active=False;db.commit()
    call(work);return Response(status_code=204)
@router.post('/campaigns/{cid}/surveys/{sid}/sections/{section_id}/questions',response_model=SurveyQuestionRead,status_code=201)
def question(cid:UUID,sid:UUID,section_id:UUID,data:SurveyQuestionCreate,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:SurveyService(db).add_question(cid,sid,section_id,data,user))
@router.patch('/campaigns/{cid}/surveys/{sid}/questions/{id}',response_model=SurveyQuestionRead)
def question_update(cid:UUID,sid:UUID,id:UUID,data:SurveyQuestionUpdate,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:SurveyService(db).update_question(cid,sid,id,data,user))
@router.delete('/campaigns/{cid}/surveys/{sid}/questions/{id}',status_code=204)
def question_delete(cid:UUID,sid:UUID,id:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    def work():o=SurveyService(db).question(cid,sid,id,user);o.is_active=False;db.commit()
    call(work);return Response(status_code=204)
@router.post('/campaigns/{cid}/surveys/{sid}/questions/{qid}/options',response_model=SurveyOptionRead,status_code=201)
def option(cid:UUID,sid:UUID,qid:UUID,data:SurveyOptionCreate,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:SurveyService(db).add_option(cid,sid,qid,data,user))
@router.patch('/campaigns/{cid}/surveys/{sid}/questions/{qid}/options/{id}',response_model=SurveyOptionRead)
def option_update(cid:UUID,sid:UUID,qid:UUID,id:UUID,data:SurveyOptionUpdate,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:SurveyService(db).update_option(cid,sid,qid,id,data,user))
@router.delete('/campaigns/{cid}/surveys/{sid}/questions/{qid}/options/{id}',status_code=204)
def option_delete(cid:UUID,sid:UUID,qid:UUID,id:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    def work():o=SurveyService(db).option(cid,sid,qid,id,user);o.is_active=False;db.commit()
    call(work);return Response(status_code=204)
@router.post('/campaigns/{cid}/surveys/{sid}/publish',response_model=SurveyPublishResponse)
def publish(cid:UUID,sid:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:SurveyService(db).publish(cid,sid,user))
@router.post('/campaigns/{cid}/surveys/{sid}/close',response_model=SurveyCloseResponse)
def close(cid:UUID,sid:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:SurveyService(db).transition(cid,sid,user,'CLOSED'))
@router.post('/campaigns/{cid}/surveys/{sid}/archive',response_model=SurveyRead)
def archive(cid:UUID,sid:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:SurveyService(db).transition(cid,sid,user,'ARCHIVED'))
@router.post('/campaigns/{cid}/surveys/{sid}/responses',response_model=SurveyResponseSummary,status_code=201)
def submit(cid:UUID,sid:UUID,data:SurveySubmissionCreate,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:SurveyService(db).submit(cid,sid,data,user))
@router.get('/campaigns/{cid}/surveys/{sid}/responses',response_model=SurveyResponseListResponse)
def responses(cid:UUID,sid:UUID,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),date_from:date|None=None,date_to:date|None=None,parish_id:int|None=None,community_id:UUID|None=None,sector_id:UUID|None=None,activity_id:UUID|None=None,source_channel:SourceChannel|None=None,age_range:AgeRange|None=None,is_valid:bool|None=None,is_complete:bool|None=None,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    if date_from and date_to and date_from>date_to:raise HTTPException(400,'Rango inválido')
    return call(lambda:SurveyService(db).responses(cid,sid,user,page,page_size,date_from=date_from,date_to=date_to,parish_id=parish_id,community_id=community_id,sector_id=sector_id,activity_id=activity_id,source_channel=source_channel,age_range=age_range,is_valid=is_valid,is_complete=is_complete))
@router.get('/campaigns/{cid}/surveys/{sid}/responses/{rid}',response_model=SurveyResponseRead)
def response(cid:UUID,sid:UUID,rid:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:SurveyService(db).response(cid,sid,rid,user))
@router.post('/campaigns/{cid}/surveys/{sid}/responses/{rid}/invalidate',response_model=SurveyResponseSummary)
def invalidate(cid:UUID,sid:UUID,rid:UUID,data:SurveyResponseInvalidation,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:SurveyService(db).invalidate(cid,sid,rid,data.reason,user))
def filters(date_from,date_to,parish_id,community_id,sector_id,activity_id,source_channel,age_range):
    if date_from and date_to and date_from>date_to:raise HTTPException(400,'Rango inválido')
    return dict(date_from=date_from,date_to=date_to,parish_id=parish_id,community_id=community_id,sector_id=sector_id,activity_id=activity_id,source_channel=source_channel,age_range=age_range)
@router.get('/campaigns/{cid}/surveys/{sid}/results',response_model=SurveyResultsRead)
def results(cid:UUID,sid:UUID,date_from:date|None=None,date_to:date|None=None,parish_id:int|None=None,community_id:UUID|None=None,sector_id:UUID|None=None,activity_id:UUID|None=None,source_channel:SourceChannel|None=None,age_range:AgeRange|None=None,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:SurveyService(db).results(cid,sid,user,**filters(date_from,date_to,parish_id,community_id,sector_id,activity_id,source_channel,age_range)))
@router.get('/campaigns/{cid}/surveys/{sid}/territorial-comparison',response_model=SurveyComparisonRead)
def comparison(cid:UUID,sid:UUID,level:str,question_code:str,date_from:date|None=None,date_to:date|None=None,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:SurveyService(db).comparison(cid,sid,user,level,question_code,date_from=date_from,date_to=date_to))
@router.get('/campaigns/{cid}/surveys/{sid}/participation-summary',response_model=SurveyParticipationSummary)
def participation(cid:UUID,sid:UUID,date_from:date|None=None,date_to:date|None=None,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:SurveyService(db).participation(cid,sid,user,date_from=date_from,date_to=date_to))
@router.get('/campaigns/{cid}/surveys/{sid}/export-data')
def export(cid:UUID,sid:UUID,date_from:date|None=None,date_to:date|None=None,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:SurveyService(db).export(cid,sid,user,date_from=date_from,date_to=date_to))
