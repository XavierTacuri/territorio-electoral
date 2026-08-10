from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query,status
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_active_user,require_admin
from app.db.session import get_db
from app.models.candidate import Candidate
from app.models.user import User
from app.schemas.campaign import *
from app.schemas.user import MessageResponse
from app.services.campaign_service import CampaignService
from app.services.candidate_service import CandidateService
from app.services.exceptions import BusinessRuleError,ConflictError,NotFoundError
from app.services.territorial_assignment_service import TerritorialAssignmentService
router=APIRouter(prefix="/campaigns",tags=["campaigns"])
def fail(e):
    if isinstance(e,PermissionError):return HTTPException(403,str(e))
    if isinstance(e,NotFoundError):return HTTPException(404,str(e))
    if isinstance(e,ConflictError):return HTTPException(409,str(e))
    return HTTPException(400,str(e))
@router.post("",response_model=CampaignSummary,status_code=201)
def create(data:CampaignCreate,actor:User=Depends(require_admin),db:Session=Depends(get_db)):
    try:return CampaignService(db).create(data,actor)
    except Exception as e:raise fail(e)
@router.get("",response_model=CampaignListResponse)
def listing(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),canton_id:int|None=None,status:CampaignStatus|None=None,office_type:OfficeType|None=None,is_active:bool|None=None,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    return CampaignService(db).list(actor,page,page_size,canton_id,status,office_type,is_active)
@router.get("/{campaign_id}",response_model=CampaignRead)
def get(campaign_id:UUID,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:
        campaign=CampaignService(db).get(campaign_id,actor);candidate=db.scalar(select(Candidate).where(Candidate.campaign_id==campaign_id)); data=CampaignSummary.model_validate(campaign).model_dump();data.update(start_date=campaign.start_date,end_date=campaign.end_date,description=campaign.description,candidate=candidate);return data
    except Exception as e:raise fail(e)
@router.patch("/{campaign_id}",response_model=CampaignSummary)
def update(campaign_id:UUID,data:CampaignUpdate,actor:User=Depends(require_admin),db:Session=Depends(get_db)):
    try:return CampaignService(db).update(campaign_id,data,actor)
    except Exception as e:raise fail(e)
@router.post("/{campaign_id}/candidate",response_model=CandidateRead,status_code=201)
def create_candidate(campaign_id:UUID,data:CandidateCreate,actor:User=Depends(require_admin),db:Session=Depends(get_db)):
    try:return CandidateService(db).create(campaign_id,data,actor)
    except Exception as e:raise fail(e)
@router.get("/{campaign_id}/candidate",response_model=CandidateRead)
def get_candidate(campaign_id:UUID,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return CandidateService(db).get(campaign_id,actor)
    except Exception as e:raise fail(e)
@router.patch("/{campaign_id}/candidate",response_model=CandidateRead)
def update_candidate(campaign_id:UUID,data:CandidateUpdate,actor:User=Depends(require_admin),db:Session=Depends(get_db)):
    try:return CandidateService(db).update(campaign_id,data,actor)
    except Exception as e:raise fail(e)
@router.post("/{campaign_id}/users",response_model=CampaignUserRead,status_code=201)
def assign_user(campaign_id:UUID,data:CampaignUserAssign,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return TerritorialAssignmentService(db).assign_user(campaign_id,data,actor)
    except Exception as e:raise fail(e)
@router.get("/{campaign_id}/users",response_model=list[CampaignUserRead])
def campaign_users(campaign_id:UUID,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return TerritorialAssignmentService(db).users(campaign_id,actor)
    except Exception as e:raise fail(e)
@router.delete("/{campaign_id}/users/{user_id}",response_model=MessageResponse)
def remove_user(campaign_id:UUID,user_id:UUID,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:TerritorialAssignmentService(db).remove_user(campaign_id,user_id,actor);return MessageResponse(message="Usuario removido de la campaña")
    except Exception as e:raise fail(e)
@router.post("/{campaign_id}/territorial-assignments",response_model=TerritorialAssignmentRead,status_code=201)
def create_assignment(campaign_id:UUID,data:TerritorialAssignmentCreate,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return TerritorialAssignmentService(db).create(campaign_id,data,actor)
    except Exception as e:raise fail(e)
@router.get("/{campaign_id}/territorial-assignments",response_model=list[TerritorialAssignmentRead])
def assignments(campaign_id:UUID,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return TerritorialAssignmentService(db).list(campaign_id,actor)
    except Exception as e:raise fail(e)
@router.delete("/{campaign_id}/territorial-assignments/{id}",response_model=MessageResponse)
def remove_assignment(campaign_id:UUID,id:UUID,actor:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:TerritorialAssignmentService(db).remove(campaign_id,id,actor);return MessageResponse(message="Asignación territorial removida")
    except Exception as e:raise fail(e)
