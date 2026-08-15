from datetime import date,datetime
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_active_user
from app.db.session import get_db
from app.core.config import settings
from app.models.public_intelligence import PublicIntelligenceItem,PublicItemNeedLink,PublicSource,PublicSourceFetchRun,PublicTopic
from app.models.user import User
from app.schemas.public_intelligence import *
from app.services.exceptions import NotFoundError
from app.services.public_intelligence_service import PublicIntelligenceService

router=APIRouter(tags=["public-intelligence"])
def call(fn):
    try:return fn()
    except PermissionError as e:raise HTTPException(403,str(e))
    except NotFoundError as e:raise HTTPException(404,str(e))
    except Exception as e:raise HTTPException(400,str(e))
@router.get("/campaigns/{cid}/public-sources",response_model=list[PublicSourceRead])
def sources(cid:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:PublicIntelligenceService(db).sources(cid,user))
@router.post("/campaigns/{cid}/public-sources",response_model=PublicSourceRead,status_code=201)
def create(cid:UUID,data:PublicSourceCreate,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:PublicIntelligenceService(db).create_source(cid,user,data))
@router.patch("/public-sources/{sid}",response_model=PublicSourceRead)
def update(sid:UUID,data:PublicSourceUpdate,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:PublicIntelligenceService(db).update_source(sid,user,data))
@router.post("/public-sources/{sid}/fetch",response_model=FetchRunRead)
def fetch(sid:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:PublicIntelligenceService(db).fetch(sid,user))
@router.get("/public-sources/{sid}/fetch-runs",response_model=list[FetchRunRead])
def runs(sid:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    service=PublicIntelligenceService(db);source=call(lambda:service.source(sid));call(lambda:service.access.require_access(source.campaign_id,user));return list(db.scalars(select(PublicSourceFetchRun).where(PublicSourceFetchRun.source_id==sid).order_by(PublicSourceFetchRun.started_at.desc()).limit(100)))
@router.get("/public-topics")
def topics(user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return [{"id":x.id,"code":x.code,"name":x.name} for x in db.scalars(select(PublicTopic).where(PublicTopic.active.is_(True)).order_by(PublicTopic.name))]
@router.get("/campaigns/{cid}/public-intelligence/items",response_model=ItemPage)
def items(cid:UUID,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),search:str|None=None,source_id:UUID|None=None,topic:str|None=None,parish_id:int|None=None,date_from:date|None=None,date_to:date|None=None,official:bool|None=None,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:PublicIntelligenceService(db).items(cid,user,page,page_size,search,source_id,topic,parish_id,date_from,date_to,official))
@router.get("/campaigns/{cid}/public-intelligence/items/{iid}",response_model=ItemRead)
def detail(cid:UUID,iid:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:PublicIntelligenceService(db).detail(cid,iid,user))
@router.get("/campaigns/{cid}/public-intelligence/summary",response_model=SummaryRead)
def summary(cid:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:PublicIntelligenceService(db).summary(cid,user))
@router.get("/campaigns/{cid}/public-intelligence/map",response_model=list[MapMetricRead])
def map_metrics(cid:UUID,period:str=Query("30",pattern="^(7|30|total)$"),topic:str|None=None,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:PublicIntelligenceService(db).map_metrics(cid,user,period,topic))
@router.post("/campaigns/{cid}/public-intelligence/evaluate-stale")
def evaluate_stale(cid:UUID,at:datetime|None=None,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    if at is not None and settings.app_env!="e2e":raise HTTPException(400,"El reloj controlado solo está disponible en E2E")
    return call(lambda:PublicIntelligenceService(db).evaluate_stale_sources(cid,user,at))
@router.post("/campaigns/{cid}/public-intelligence/items/{iid}/needs",status_code=201)
def link_need(cid:UUID,iid:UUID,data:NeedLinkCreate,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return call(lambda:{"id":str(PublicIntelligenceService(db).link_need(cid,iid,user,data.need_id).id)})
@router.get("/campaigns/{cid}/needs/{need_id}/public-intelligence",response_model=list[ItemRead])
def need_items(cid:UUID,need_id:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    service=PublicIntelligenceService(db);service.access.require_access(cid,user);rows=db.scalars(select(PublicIntelligenceItem).join(PublicItemNeedLink).join(PublicSource).where(PublicItemNeedLink.need_id==need_id,PublicSource.campaign_id==cid)).all();return [service._read(x) for x in rows]
