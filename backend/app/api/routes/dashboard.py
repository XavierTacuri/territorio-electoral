from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import ValidationError
from app.api.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.dashboard import *
from app.services.dashboard_service import DashboardService
from app.services.exceptions import BusinessRuleError, NotFoundError

router=APIRouter(prefix="/campaigns/{campaign_id}/dashboard",tags=["Dashboard"])

def common_filters(date_from:date|None=None,date_to:date|None=None,period:DashboardPeriod|None=None,parish_id:int|None=None,community_id:UUID|None=None,sector_id:UUID|None=None,compare_previous_period:bool=False,survey_ids:Annotated[list[UUID]|None,Query(max_length=20)]=None,electoral_process_ids:Annotated[list[UUID]|None,Query(max_length=10)]=None,demographic_indicator_codes:Annotated[list[str]|None,Query(max_length=50)]=None)->DashboardFilters:
 try:return DashboardFilters(date_from=date_from,date_to=date_to,period=period,parish_id=parish_id,community_id=community_id,sector_id=sector_id,compare_previous_period=compare_previous_period,survey_ids=survey_ids,electoral_process_ids=electoral_process_ids,demographic_indicator_codes=demographic_indicator_codes)
 except ValidationError as exc:raise HTTPException(422,"Filtros de dashboard inválidos") from exc

def invoke(method,*args,**kwargs):
 try:return method(*args,**kwargs)
 except PermissionError as exc:raise HTTPException(403,str(exc)) from exc
 except NotFoundError as exc:raise HTTPException(404,str(exc)) from exc
 except BusinessRuleError as exc:raise HTTPException(400,str(exc)) from exc

@router.get("/filter-options",response_model=DashboardFilterOptionsRead)
def filter_options(campaign_id:UUID,filters:DashboardFilters=Depends(common_filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):return invoke(DashboardService(db).filter_options,campaign_id,user,filters)
@router.get("/overview",response_model=CampaignDashboardOverviewRead)
def overview(campaign_id:UUID,filters:DashboardFilters=Depends(common_filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):return invoke(DashboardService(db).overview,campaign_id,user,filters)
@router.get("/territories",response_model=TerritorialDashboardRead)
def territories(campaign_id:UUID,level:str=Query("PARISH",pattern="^(PARISH|COMMUNITY|SECTOR)$"),page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),sort_by:str="name",sort_order:str=Query("asc",pattern="^(asc|desc)$"),filters:DashboardFilters=Depends(common_filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):return invoke(DashboardService(db).territories,campaign_id,user,filters,level,page,page_size,sort_by,sort_order)
@router.get("/activity-trends",response_model=ActivityTrendRead)
def activity_trends(campaign_id:UUID,group_by:str=Query("DAY",pattern="^(DAY|WEEK|MONTH)$"),fill_missing_periods:bool=False,activity_type_codes:list[str]|None=Query(None),statuses:list[str]|None=Query(None),filters:DashboardFilters=Depends(common_filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):return invoke(DashboardService(db).activity_trends,campaign_id,user,filters,group_by,fill_missing_periods,activity_type_codes,statuses)
@router.get("/needs",response_model=NeedDashboardRead)
def needs(campaign_id:UUID,filters:DashboardFilters=Depends(common_filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):return invoke(DashboardService(db).needs,campaign_id,user,filters)
@router.get("/commitments",response_model=CommitmentDashboardRead)
def commitments(campaign_id:UUID,filters:DashboardFilters=Depends(common_filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):return invoke(DashboardService(db).commitments,campaign_id,user,filters)
@router.get("/surveys",response_model=SurveyDashboardRead)
def surveys(campaign_id:UUID,filters:DashboardFilters=Depends(common_filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):return invoke(DashboardService(db).surveys,campaign_id,user,filters)
@router.get("/electoral-history",response_model=ElectoralHistoryDashboardRead)
def electoral_history(campaign_id:UUID,filters:DashboardFilters=Depends(common_filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):return invoke(DashboardService(db).electoral_history,campaign_id,user,filters)
@router.get("/demographics",response_model=DemographicDashboardRead)
def demographics(campaign_id:UUID,reference_year:int|None=None,source_id:UUID|None=None,filters:DashboardFilters=Depends(common_filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):return invoke(DashboardService(db).demographics,campaign_id,user,filters,reference_year,source_id)
@router.get("/data-quality",response_model=DataQualityDashboardRead)
def data_quality(campaign_id:UUID,filters:DashboardFilters=Depends(common_filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):return invoke(DashboardService(db).data_quality,campaign_id,user,filters)
@router.get("",response_model=CampaignDashboardRead)
def consolidated(campaign_id:UUID,filters:DashboardFilters=Depends(common_filters),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):return invoke(DashboardService(db).consolidated,campaign_id,user,filters)
