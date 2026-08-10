from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_active_user,require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.historical import *
from app.services.electoral_service import ElectoralService
from app.services.exceptions import ConflictError,NotFoundError
router=APIRouter(tags=['electoral-history'])
def fail(e):
 if isinstance(e,PermissionError):return HTTPException(403,str(e))
 if isinstance(e,NotFoundError):return HTTPException(404,str(e))
 if isinstance(e,ConflictError):return HTTPException(409,str(e))
 return HTTPException(400,str(e))
def call(fn):
 try:return fn()
 except Exception as e:raise fail(e)
@router.post('/electoral-processes',response_model=ElectoralProcessRead,status_code=201)
def create(data:ElectoralProcessCreate,_:User=Depends(require_admin),db:Session=Depends(get_db)):return call(lambda:ElectoralService(db).create_process(data))
@router.get('/electoral-processes',response_model=list[ElectoralProcessRead])
def processes(year:int|None=None,process_type:str|None=None,status:str|None=None,is_final:bool|None=None,_:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return ElectoralService(db).list_processes(year=year,process_type=process_type,status=status,is_final=is_final)
@router.get('/electoral-processes/{pid}',response_model=ElectoralProcessRead)
def process(pid:UUID,_:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:ElectoralService(db).process(pid))
@router.patch('/electoral-processes/{pid}',response_model=ElectoralProcessRead)
def update(pid:UUID,data:ElectoralProcessUpdate,_:User=Depends(require_admin),db:Session=Depends(get_db)):return call(lambda:ElectoralService(db).update_process(pid,data))
@router.post('/electoral-processes/{pid}/contests',response_model=ElectoralContestRead,status_code=201)
def contest_create(pid:UUID,data:ElectoralContestCreate,_:User=Depends(require_admin),db:Session=Depends(get_db)):return call(lambda:ElectoralService(db).create_contest(pid,data))
@router.get('/electoral-processes/{pid}/contests',response_model=list[ElectoralContestRead])
def contests(pid:UUID,_:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:ElectoralService(db).contests(pid))
@router.get('/political-organizations',response_model=list[PoliticalOrganizationRead])
def organizations(source_id:UUID,_:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:ElectoralService(db).organizations(source_id))
@router.get('/electoral-processes/{pid}/geographies',response_model=list[ElectoralGeographyRead])
def geographies(pid:UUID,aggregation_level:str|None=None,canton_id:int|None=None,is_mapped:bool|None=None,_:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:ElectoralService(db).geographies(pid,aggregation_level,canton_id,is_mapped))
@router.get('/electoral-processes/{pid}/contests/{cid}',response_model=ElectoralContestRead)
def contest(pid:UUID,cid:UUID,_:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:ElectoralService(db).contest(pid,cid))
@router.get('/electoral-processes/{pid}/contests/{cid}/candidates',response_model=list[ElectoralCandidateRead])
def candidates(pid:UUID,cid:UUID,_:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:ElectoralService(db).candidates(pid,cid))
@router.get('/electoral-processes/{pid}/contests/{cid}/turnout',response_model=list[ElectoralTurnoutRead])
def turnout(pid:UUID,cid:UUID,aggregation_level:str|None=None,province_id:int|None=None,canton_id:int|None=None,parish_id:int|None=None,geography_id:UUID|None=None,is_final:bool|None=None,_:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:ElectoralService(db).turnout(pid,cid,aggregation_level,province_id=province_id,canton_id=canton_id,parish_id=parish_id,geography_id=geography_id,is_final=is_final))
@router.get('/electoral-processes/{pid}/contests/{cid}/candidate-results',response_model=list[CandidateResultRead])
def results(pid:UUID,cid:UUID,aggregation_level:str|None=None,_:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:ElectoralService(db).results(pid,cid,aggregation_level))
@router.get('/electoral-processes/{pid}/contests/{cid}/territorial-summary',response_model=TerritorialElectoralSummary)
def summary(pid:UUID,cid:UUID,_:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:ElectoralService(db).territorial_summary(pid,cid))
@router.get('/electoral-comparison',response_model=ElectoralComparisonRead)
def comparison(process_ids:list[UUID]=Query(),office_type:str='MAYOR',canton_id:int=Query(),aggregation_level:str='PARISH',_:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:ElectoralService(db).comparison(process_ids,office_type,canton_id,aggregation_level))
@router.get('/campaigns/{campaign_id}/historical-electoral-context',response_model=HistoricalElectoralContextRead)
def context(campaign_id:UUID,process_ids:list[UUID]|None=Query(None),user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:ElectoralService(db).historical_context(campaign_id,user,process_ids))
