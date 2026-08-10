from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_active_user,require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.historical import DemographicIndicatorCreate,DemographicIndicatorRead,DemographicObservationRead,DemographicProfileRead
from app.services.demographic_service import DemographicService
router=APIRouter(tags=['demographics'])
@router.post('/demographic-indicators',response_model=DemographicIndicatorRead,status_code=201)
def create(data:DemographicIndicatorCreate,_:User=Depends(require_admin),db:Session=Depends(get_db)):
 try:return DemographicService(db).create(data)
 except Exception as e:raise HTTPException(409,str(e))
@router.get('/demographic-indicators',response_model=list[DemographicIndicatorRead])
def indicators(_:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return DemographicService(db).list()
@router.patch('/demographic-indicators/{id}',response_model=DemographicIndicatorRead)
def update(id:UUID,data:DemographicIndicatorCreate,_:User=Depends(require_admin),db:Session=Depends(get_db)):return DemographicService(db).update(id,data)
@router.get('/demographic-observations',response_model=list[DemographicObservationRead])
def observations(indicator_id:UUID|None=None,reference_year:int|None=None,geography_level:str|None=None,province_id:int|None=None,canton_id:int|None=None,parish_id:int|None=None,source_id:UUID|None=None,_:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return DemographicService(db).observations(indicator_id=indicator_id,reference_year=reference_year,geography_level=geography_level,province_id=province_id,canton_id=canton_id,parish_id=parish_id,source_id=source_id)
@router.get('/territories/demographic-profile',response_model=DemographicProfileRead)
def profile(canton_id:int,parish_id:int|None=None,reference_year:int|None=None,indicator_codes:list[str]|None=Query(None),_:User=Depends(get_current_active_user),db:Session=Depends(get_db)):return DemographicService(db).profile(canton_id,parish_id,reference_year,indicator_codes)
