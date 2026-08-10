from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query,status
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_active_user,require_admin
from app.db.session import get_db
from app.models.user import User
from app.models.assignments import TerritorialAssignment
from app.models.campaign import Campaign
from app.models.territory import Community, Parish, Sector
from app.services.campaign_access_service import CampaignAccessService
from app.schemas.territory import *
from app.services.exceptions import ConflictError,NotFoundError
from app.services.territory_service import TerritoryService
router=APIRouter(tags=["territory"])

def allowed_parish(parish: Parish, user: User, db: Session) -> bool:
    access = CampaignAccessService(db)
    if access.admin(user): return True
    campaigns = list(db.scalars(select(Campaign).where(Campaign.id.in_(access.accessible_ids(user)))))
    if {"CANDIDATE", "CAMPAIGN_MANAGER"}.intersection(r.code for r in user.roles):
        return parish.canton_id in {campaign.canton_id for campaign in campaigns}
    return bool(db.scalar(select(TerritorialAssignment.id).where(TerritorialAssignment.user_id == user.id, TerritorialAssignment.parish_id == parish.id, TerritorialAssignment.is_active.is_(True))))

def allowed_community(item: Community, user: User, db: Session) -> bool:
    parish = db.get(Parish, item.parish_id)
    if not allowed_parish(parish, user, db): return False
    if CampaignAccessService(db).admin(user) or {"CANDIDATE", "CAMPAIGN_MANAGER"}.intersection(r.code for r in user.roles): return True
    return bool(db.scalar(select(TerritorialAssignment.id).where(TerritorialAssignment.user_id == user.id, TerritorialAssignment.parish_id == item.parish_id, TerritorialAssignment.is_active.is_(True), (TerritorialAssignment.community_id.is_(None)) | (TerritorialAssignment.community_id == item.id))))

def allowed_sector(item: Sector, user: User, db: Session) -> bool:
    community = db.get(Community, item.community_id)
    if not allowed_community(community, user, db): return False
    if CampaignAccessService(db).admin(user) or {"CANDIDATE", "CAMPAIGN_MANAGER"}.intersection(r.code for r in user.roles): return True
    return bool(db.scalar(select(TerritorialAssignment.id).where(TerritorialAssignment.user_id == user.id, TerritorialAssignment.community_id == item.community_id, TerritorialAssignment.is_active.is_(True), (TerritorialAssignment.sector_id.is_(None)) | (TerritorialAssignment.sector_id == item.id))))
def fail(e):
    if isinstance(e,NotFoundError):return HTTPException(404,str(e))
    if isinstance(e,ConflictError):return HTTPException(409,str(e))
    return HTTPException(400,str(e))
@router.get("/provinces",response_model=list[ProvinceRead])
def provinces(_:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return TerritoryService(db).provinces()
@router.get("/cantons",response_model=list[CantonRead])
def cantons(province_id:int|None=None,_:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return TerritoryService(db).cantons(province_id)
@router.get("/cantons/{id}",response_model=CantonRead)
def canton(id:int,_:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return TerritoryService(db).canton(id)
    except Exception as e:raise fail(e)
@router.post("/cantons",response_model=CantonRead,status_code=201)
def create_canton(data:CantonCreate,_:User=Depends(require_admin),db:Session=Depends(get_db)):
    try:return TerritoryService(db).create_canton(data)
    except Exception as e:raise fail(e)
@router.patch("/cantons/{id}",response_model=CantonRead)
def update_canton(id:int,data:CantonUpdate,_:User=Depends(require_admin),db:Session=Depends(get_db)):
    try:return TerritoryService(db).update_canton(id,data)
    except Exception as e:raise fail(e)
@router.get("/parishes",response_model=list[ParishRead])
def parishes(canton_id:int|None=None,parish_type:ParishType|None=None,is_active:bool|None=None,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    return [item for item in TerritoryService(db).parishes(canton_id,parish_type,is_active) if allowed_parish(item,user,db)]
@router.get("/parishes/{id}",response_model=ParishRead)
def parish(id:int,user:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:
        item=TerritoryService(db).parish(id)
        if not allowed_parish(item,user,db):raise PermissionError("Sin acceso territorial")
        return item
    except PermissionError as e:raise HTTPException(403,str(e))
    except Exception as e:raise fail(e)
@router.post("/parishes",response_model=ParishRead,status_code=201)
def create_parish(data:ParishCreate,_:User=Depends(require_admin),db:Session=Depends(get_db)):
    try:return TerritoryService(db).create_parish(data)
    except Exception as e:raise fail(e)
@router.patch("/parishes/{id}",response_model=ParishRead)
def update_parish(id:int,data:ParishUpdate,_:User=Depends(require_admin),db:Session=Depends(get_db)):
    try:return TerritoryService(db).update_parish(id,data)
    except Exception as e:raise fail(e)
@router.get("/communities",response_model=CommunityListResponse)
def communities(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),parish_id:int|None=None,search:str|None=None,_:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    items,total,pages=TerritoryService(db).communities(page,page_size,parish_id,search);items=[x for x in items if allowed_community(x,_,db)];return CommunityListResponse(items=items,page=page,page_size=page_size,total=len(items),total_pages=1 if items else 0)
@router.get("/communities/{id}",response_model=CommunityRead)
def community(id:UUID,_:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return TerritoryService(db).community(id)
    except Exception as e:raise fail(e)
@router.post("/communities",response_model=CommunityRead,status_code=201)
def create_community(data:CommunityCreate,_:User=Depends(require_admin),db:Session=Depends(get_db)):
    try:return TerritoryService(db).create_community(data)
    except Exception as e:raise fail(e)
@router.patch("/communities/{id}",response_model=CommunityRead)
def update_community(id:UUID,data:CommunityUpdate,_:User=Depends(require_admin),db:Session=Depends(get_db)):
    try:return TerritoryService(db).update_community(id,data)
    except Exception as e:raise fail(e)
@router.get("/sectors",response_model=SectorListResponse)
def sectors(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),community_id:UUID|None=None,search:str|None=None,_:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    items,total,pages=TerritoryService(db).sectors(page,page_size,community_id,search);items=[x for x in items if allowed_sector(x,_,db)];return SectorListResponse(items=items,page=page,page_size=page_size,total=len(items),total_pages=1 if items else 0)
@router.get("/sectors/{id}",response_model=SectorRead)
def sector(id:UUID,_:User=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:return TerritoryService(db).sector(id)
    except Exception as e:raise fail(e)
@router.post("/sectors",response_model=SectorRead,status_code=201)
def create_sector(data:SectorCreate,_:User=Depends(require_admin),db:Session=Depends(get_db)):
    try:return TerritoryService(db).create_sector(data)
    except Exception as e:raise fail(e)
@router.patch("/sectors/{id}",response_model=SectorRead)
def update_sector(id:UUID,data:SectorUpdate,_:User=Depends(require_admin),db:Session=Depends(get_db)):
    try:return TerritoryService(db).update_sector(id,data)
    except Exception as e:raise fail(e)
