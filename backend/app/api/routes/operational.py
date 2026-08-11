from datetime import date
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query,Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_active_user,require_admin
from app.db.session import get_db
from app.models.operational import ActivityType,NeedCategory,CitizenNeed,Commitment,ActivityEvidence
from app.models.user import User
from app.schemas.operational import *
from app.services.exceptions import ConflictError,NotFoundError
from app.services.operational_service import OperationalService
router=APIRouter(tags=["operations"])
def fail(e):
    if isinstance(e,PermissionError):return HTTPException(403,str(e))
    if isinstance(e,NotFoundError):return HTTPException(404,str(e))
    if isinstance(e,(ConflictError,IntegrityError)):return HTTPException(409,"Conflicto de datos")
    return HTTPException(400,str(e))
def admin(user):return user.is_superuser or "ADMIN" in {r.code for r in user.roles}
@router.get("/activity-types",response_model=list[ActivityTypeRead])
def activity_types(include_inactive:bool=False,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    if include_inactive and not admin(user):raise HTTPException(403,"Permisos insuficientes")
    q=select(ActivityType).order_by(ActivityType.display_order,ActivityType.code)
    if not include_inactive:q=q.where(ActivityType.is_active.is_(True))
    return list(db.scalars(q))
@router.post("/activity-types",response_model=ActivityTypeRead,status_code=201)
def create_type(data:ActivityTypeCreate,_:User=Depends(require_admin),db:Session=Depends(get_db)):
    o=ActivityType(**data.model_dump());db.add(o)
    try:db.commit();db.refresh(o);return o
    except IntegrityError as e:db.rollback();raise fail(e)
@router.patch("/activity-types/{id}",response_model=ActivityTypeRead)
def update_type(id:int,data:ActivityTypeUpdate,_:User=Depends(require_admin),db:Session=Depends(get_db)):
    o=db.get(ActivityType,id)
    if not o:raise HTTPException(404,"Tipo no encontrado")
    for k,v in data.model_dump(exclude_unset=True).items():setattr(o,k,v)
    db.commit();db.refresh(o);return o
@router.get("/need-categories",response_model=list[NeedCategoryRead])
def categories(include_inactive:bool=False,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    if include_inactive and not admin(user):raise HTTPException(403,"Permisos insuficientes")
    q=select(NeedCategory).order_by(NeedCategory.display_order,NeedCategory.code)
    if not include_inactive:q=q.where(NeedCategory.is_active.is_(True))
    return list(db.scalars(q))
@router.post("/need-categories",response_model=NeedCategoryRead,status_code=201)
def create_category(data:NeedCategoryCreate,_:User=Depends(require_admin),db:Session=Depends(get_db)):
    o=NeedCategory(**data.model_dump());db.add(o)
    try:db.commit();db.refresh(o);return o
    except IntegrityError as e:db.rollback();raise fail(e)
@router.patch("/need-categories/{id}",response_model=NeedCategoryRead)
def update_category(id:int,data:NeedCategoryUpdate,_:User=Depends(require_admin),db:Session=Depends(get_db)):
    o=db.get(NeedCategory,id)
    if not o:raise HTTPException(404,"Categoría no encontrada")
    for k,v in data.model_dump(exclude_unset=True).items():setattr(o,k,v)
    db.commit();db.refresh(o);return o
@router.post("/campaigns/{cid}/activities",response_model=TerritorialActivityRead,status_code=201)
def create_activity(cid:UUID,data:TerritorialActivityCreate,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return OperationalService(db).create_activity(cid,data,user)
    except Exception as e:raise fail(e)
@router.get("/campaigns/{cid}/activities",response_model=TerritorialActivityListResponse)
def activities(cid:UUID,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),search:str|None=None,activity_type_code:str|None=None,status:ActivityStatus|None=None,parish_id:int|None=None,community_id:UUID|None=None,sector_id:UUID|None=None,responsible_user_id:UUID|None=None,date_from:date|None=None,date_to:date|None=None,include_inactive:bool=False,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    if date_from and date_to and date_from>date_to:raise HTTPException(400,"Rango inválido")
    if include_inactive and not admin(user):raise HTTPException(403,"Permisos insuficientes")
    try:return OperationalService(db).list_activities(cid,user,page,page_size,search=search,activity_type_code=activity_type_code,status=status,parish_id=parish_id,community_id=community_id,sector_id=sector_id,responsible_user_id=responsible_user_id,date_from=date_from,date_to=date_to,include_inactive=include_inactive)
    except Exception as e:raise fail(e)
@router.get("/campaigns/{cid}/activities/{id}",response_model=TerritorialActivityRead)
def activity(cid:UUID,id:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return OperationalService(db).activity(cid,id,user)
    except Exception as e:raise fail(e)
@router.patch("/campaigns/{cid}/activities/{id}",response_model=TerritorialActivityRead)
def update_activity(cid:UUID,id:UUID,data:TerritorialActivityUpdate,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return OperationalService(db).update_activity(cid,id,data,user)
    except Exception as e:raise fail(e)
@router.delete("/campaigns/{cid}/activities/{id}",status_code=204)
def deactivate_activity(cid:UUID,id:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:OperationalService(db).deactivate_activity(cid,id,user);return Response(status_code=204)
    except Exception as e:raise fail(e)
@router.put("/campaigns/{cid}/activities/{aid}/participant-summary",response_model=ParticipantSummaryRead)
def put_participants(cid:UUID,aid:UUID,data:ParticipantSummaryUpsert,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return OperationalService(db).participant(cid,aid,user,data)
    except Exception as e:raise fail(e)
@router.get("/campaigns/{cid}/activities/{aid}/participant-summary",response_model=ParticipantSummaryRead)
def get_participants(cid:UUID,aid:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return OperationalService(db).participant(cid,aid,user)
    except Exception as e:raise fail(e)
@router.post("/campaigns/{cid}/activities/{aid}/needs",response_model=CitizenNeedRead,status_code=201)
def create_need(cid:UUID,aid:UUID,data:CitizenNeedCreate,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return OperationalService(db).create_need(cid,aid,data,user)
    except Exception as e:raise fail(e)
@router.get("/campaigns/{cid}/activities/{aid}/needs",response_model=CitizenNeedListResponse)
def activity_needs(cid:UUID,aid:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return OperationalService(db).needs(cid,user,activity_id=aid)
    except Exception as e:raise fail(e)
@router.get("/campaigns/{cid}/needs",response_model=CitizenNeedListResponse)
def needs(cid:UUID,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),need_category_code:str|None=None,priority:Priority|None=None,status:NeedStatus|None=None,parish_id:int|None=None,community_id:UUID|None=None,sector_id:UUID|None=None,activity_id:UUID|None=None,date_from:date|None=None,date_to:date|None=None,search:str|None=None,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    if date_from and date_to and date_from>date_to:raise HTTPException(400,"Rango inv?lido")
    try:return OperationalService(db).needs(cid,user,page,page_size,activity_id=activity_id,need_category_code=need_category_code,priority=priority,status=status,parish_id=parish_id,community_id=community_id,sector_id=sector_id,date_from=date_from,date_to=date_to,search=search)
    except Exception as e:raise fail(e)
@router.get("/campaigns/{cid}/needs/{id}",response_model=CitizenNeedRead)
def need(cid:UUID,id:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return OperationalService(db).need(cid,id,user)
    except Exception as e:raise fail(e)
@router.patch("/campaigns/{cid}/needs/{id}",response_model=CitizenNeedRead)
def update_need(cid:UUID,id:UUID,data:CitizenNeedUpdate,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return OperationalService(db).update_need(cid,id,data,user)
    except Exception as e:raise fail(e)
@router.delete("/campaigns/{cid}/needs/{id}",status_code=204)
def delete_need(cid:UUID,id:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:o=OperationalService(db).need(cid,id,user,True);o.is_active=False;db.commit();return Response(status_code=204)
    except Exception as e:raise fail(e)
@router.post("/campaigns/{cid}/commitments",response_model=CommitmentRead,status_code=201)
def create_commitment(cid:UUID,data:CommitmentCreate,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return OperationalService(db).create_commitment(cid,data,user)
    except Exception as e:raise fail(e)
@router.get("/campaigns/{cid}/commitments",response_model=CommitmentListResponse)
def commitments(cid:UUID,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),status:CommitmentStatus|None=None,priority:Priority|None=None,responsible_user_id:UUID|None=None,parish_id:int|None=None,community_id:UUID|None=None,sector_id:UUID|None=None,activity_id:UUID|None=None,due_date_from:date|None=None,due_date_to:date|None=None,overdue:bool=False,search:str|None=None,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    if due_date_from and due_date_to and due_date_from>due_date_to:raise HTTPException(400,"Rango inv?lido")
    try:return OperationalService(db).commitments(cid,user,page,page_size,overdue,status=status,priority=priority,responsible_user_id=responsible_user_id,parish_id=parish_id,community_id=community_id,sector_id=sector_id,activity_id=activity_id,due_date_from=due_date_from,due_date_to=due_date_to,search=search)
    except Exception as e:raise fail(e)
@router.get("/campaigns/{cid}/commitments/{id}",response_model=CommitmentRead)
def commitment(cid:UUID,id:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return OperationalService(db).commitment(cid,id,user)
    except Exception as e:raise fail(e)
@router.patch("/campaigns/{cid}/commitments/{id}",response_model=CommitmentRead)
def update_commitment(cid:UUID,id:UUID,data:CommitmentUpdate,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return OperationalService(db).update_commitment(cid,id,data,user)
    except Exception as e:raise fail(e)
@router.delete("/campaigns/{cid}/commitments/{id}",status_code=204)
def delete_commitment(cid:UUID,id:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:o=OperationalService(db).commitment(cid,id,user,True);o.is_active=False;db.commit();return Response(status_code=204)
    except Exception as e:raise fail(e)
@router.post("/campaigns/{cid}/activities/{aid}/evidence",response_model=ActivityEvidenceRead,status_code=201)
def create_evidence(cid:UUID,aid:UUID,data:ActivityEvidenceCreate,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return OperationalService(db).evidence(cid,aid,user,data)
    except Exception as e:raise fail(e)
@router.get("/campaigns/{cid}/activities/{aid}/evidence",response_model=list[ActivityEvidenceRead])
def evidence(cid:UUID,aid:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return OperationalService(db).evidence(cid,aid,user)
    except Exception as e:raise fail(e)
@router.patch("/campaigns/{cid}/activities/{aid}/evidence/{id}",response_model=ActivityEvidenceRead)
def update_evidence(cid:UUID,aid:UUID,id:UUID,data:ActivityEvidenceUpdate,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return OperationalService(db).evidence(cid,aid,user,data,id)
    except Exception as e:raise fail(e)
@router.delete("/campaigns/{cid}/activities/{aid}/evidence/{id}",status_code=204)
def delete_evidence(cid:UUID,aid:UUID,id:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:
        svc=OperationalService(db);o=svc.evidence(cid,aid,user,id=id)
        if not svc.access.admin(user) and "CAMPAIGN_MANAGER" not in {r.code for r in user.roles}:raise PermissionError("Sin permisos")
        o.is_active=False;db.commit();return Response(status_code=204)
    except Exception as e:raise fail(e)
@router.get("/campaigns/{cid}/operational-summary",response_model=OperationalSummaryRead)
def summary(cid:UUID,date_from:date|None=None,date_to:date|None=None,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    if date_from and date_to and date_from>date_to:raise HTTPException(400,"Rango inválido")
    try:return OperationalService(db).summary(cid,user,date_from,date_to)
    except Exception as e:raise fail(e)
@router.get("/campaigns/{cid}/territories/summary")
def territory_summaries(cid:UUID,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return OperationalService(db).territory_summaries(cid,user)
    except Exception as e:raise fail(e)
