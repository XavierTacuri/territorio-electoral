import json
from datetime import date
from decimal import Decimal
from math import ceil
from uuid import UUID
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.campaign import Campaign
from app.models.historical import DataSource,DemographicIndicator,DemographicObservation,ElectoralContest,ElectoralGeography,ElectoralProcess,ElectoralTurnout,ElectoralCandidateResult,ElectoralRollSnapshot,ElectoralRollSnapshotEntry,ParticipationProjectionRun,ParticipationProjectionResult
from app.models.operational import ActivityEvidence,ActivityParticipantSummary,CitizenNeed,Commitment,NeedCategory,TerritorialActivity
from app.models.survey import Survey,SurveyResponse
from app.models.territory import Canton,Community,Parish,Sector
from app.models.user import User
from app.repositories.map_repository import MapRepository
from app.schemas.maps import MapFilters
from app.services.campaign_access_service import CampaignAccessService
from app.services.dashboard_service import DashboardService,percentage
from app.services.geojson_service import GeoJSONService
from app.services.map_filter_service import MapFilterService
from app.services.exceptions import BusinessRuleError,NotFoundError

class MapService:
 def __init__(self,db:Session,today_provider=date.today):self.db=db;self.today_provider=today_provider;self.access=CampaignAccessService(db);self.filter=MapFilterService(db,today_provider);self.repo=MapRepository(db);self.geojson=GeoJSONService()
 def context(self,campaign_id,user,filters):
  campaign=self.access.require_access(campaign_id,user);tolerance,limit=self.filter.validate_map(filters);df=self.filter.dashboard_filters(filters);period=self.filter.resolve_period(campaign,df);scope=self.filter.scope(campaign,user,df);return campaign,period,scope,tolerance,limit
 def geom_status(self,column,model,id):
  if not self.repo.postgres:return "UNAVAILABLE"
  value=self.db.execute(select(column.is_not(None),func.ST_IsValid(column),func.ST_IsEmpty(column),func.ST_SRID(column)).where(model.id==id)).one_or_none()
  if not value or not value[0]:return "MISSING"
  return "AVAILABLE" if value[1] and not value[2] and value[3]==4326 else "INVALID"
 def layers(self,campaign_id,user,filters):
  campaign,period,scope,_,_=self.context(campaign_id,user,filters);canton=self.db.get(Canton,campaign.canton_id)
  counts={"CANTON_BOUNDARY":int(canton.geometry is not None),"PARISH_BOUNDARIES":self.db.scalar(select(func.count()).select_from(Parish).where(Parish.id.in_(scope.parish_ids),Parish.geometry.is_not(None))) or 0,"COMMUNITIES":self.db.scalar(select(func.count()).select_from(Community).where(Community.id.in_(scope.community_ids),Community.location.is_not(None))) or 0,"SECTORS":self.db.scalar(select(func.count()).select_from(Sector).where(Sector.id.in_(scope.sector_ids),Sector.location.is_not(None))) or 0,"ACTIVITIES":self.db.scalar(select(func.count()).select_from(TerritorialActivity).where(TerritorialActivity.campaign_id==campaign.id,TerritorialActivity.parish_id.in_(scope.parish_ids),TerritorialActivity.location.is_not(None))) or 0}
  specs=[("CANTON_BOUNDARY","LÃ­mite cantonal","MULTIPOLYGON"),("PARISH_BOUNDARIES","LÃ­mites parroquiales","MULTIPOLYGON"),("COMMUNITIES","Comunidades","POINT"),("SECTORS","Sectores","POINT"),("ACTIVITIES","Actividades territoriales","POINT"),("OPERATIONAL_COVERAGE","Cobertura operativa territorial","MULTIPOLYGON"),("NEEDS","Necesidades agregadas","MULTIPOLYGON"),("COMMITMENTS","Compromisos agregados","MULTIPOLYGON"),("SURVEY_PARTICIPATION","ParticipaciÃ³n agregada en encuestas","MULTIPOLYGON"),("ELECTORAL_HISTORY","Historial electoral agregado","MULTIPOLYGON"),("DEMOGRAPHICS","Indicadores demogrÃ¡ficos agregados","MULTIPOLYGON"),("PARTICIPATION_PROJECTION","ProyecciÃ³n territorial de participaciÃ³n","MULTIPOLYGON")]
  specs=[(code,"Seguimientos agregados" if code=="COMMITMENTS" else name,kind) for code,name,kind in specs]
  polygon_available=counts["PARISH_BOUNDARIES"]>0
  layers=[]
  for code,name,kind in specs:
   count=counts.get(code,counts["PARISH_BOUNDARIES"] if code not in {"CANTON_BOUNDARY"} else 0);available=count>0 if code in counts else polygon_available
   layers.append({"code":code,"name":name,"description":name,"geometry_type":kind,"territory_levels":["CANTON"] if code=="CANTON_BOUNDARY" else ["PARISH"],"metrics":self.metrics(code),"filters":["period","territory","bbox"],"min_zoom":0,"max_zoom":22,"available":available,"data_status":"AVAILABLE" if available else "MISSING","unavailable_reason":None if available else "No existen geometrÃ­as o datos disponibles."})
  return {"layers":layers}
 def metrics(self,layer):
  return {"OPERATIONAL_COVERAGE":["COMPLETED_ACTIVITIES","PLANNED_ACTIVITIES","ESTIMATED_ATTENDEES","LAST_COMPLETED_ACTIVITY_DATE","DAYS_SINCE_LAST_ACTIVITY","ACTIVITY_TYPE_DIVERSITY"],"NEEDS":["NEED_COUNT","MENTIONS_COUNT","TOP_NEED_CATEGORY","HIGH_PRIORITY_NEEDS","CRITICAL_NEEDS"],"COMMITMENTS":["PENDING_COMMITMENTS","IN_PROGRESS_COMMITMENTS","COMPLETED_COMMITMENTS","OVERDUE_COMMITMENTS","COMPLETION_RATE"],"SURVEY_PARTICIPATION":["VALID_RESPONSES","PARTICIPATION","QUESTION_DISTRIBUTION"],"ELECTORAL_HISTORY":["REGISTERED_VOTERS","PARTICIPATION_RATE","ABSENTEE_RATE","VALID_VOTE_RATE","BLANK_VOTE_RATE","NULL_VOTE_RATE","WINNER_VOTES","WINNER_VOTE_SHARE","WINNER_MARGIN_VOTES","WINNER_MARGIN_POINTS"],"PARTICIPATION_PROJECTION":["REGISTERED_VOTERS","TURNOUT_RATE_2019","TURNOUT_RATE_2023","TURNOUT_RATE_LOW","TURNOUT_RATE_CENTRAL","TURNOUT_RATE_HIGH","EXPECTED_VOTERS_CENTRAL","REGISTRATION_CHANGE_2019","REGISTRATION_CHANGE_2023","INEC_POPULATION_2022","INEC_POPULATION_GROWTH","POPULATION_DENSITY"]}.get(layer,[])
 def bounds(self,campaign_id,user,filters):
  campaign,_,scope,_,_=self.context(campaign_id,user,filters);canton=self.db.get(Canton,campaign.canton_id);canton_bbox=self.repo.extent(Canton.geometry,[Canton.id==canton.id]);accessible=self.repo.extent(Parish.geometry,[Parish.id.in_(scope.parish_ids)])
  bbox=accessible or canton_bbox;center=[(bbox[0]+bbox[2])/2,(bbox[1]+bbox[3])/2] if bbox else None;missing=self.db.scalar(select(func.count()).select_from(Parish).where(Parish.id.in_(scope.parish_ids),Parish.geometry.is_(None))) or 0
  return {"canton_bbox":canton_bbox,"accessible_bbox":accessible,"center":center,"recommended_zoom":11 if bbox else 9,"geometry_available":bbox is not None,"territories_without_geometry":missing}
 def boundaries(self,campaign_id,user,filters,level="PARISH",include_metrics=False,metric=None):
  campaign,period,scope,tolerance,limit=self.context(campaign_id,user,filters);bbox=filters.bbox.as_list() if filters.bbox else None
  if level=="CANTON":model,column,ids=Canton,Canton.geometry,[campaign.canton_id]
  elif level=="PARISH":model,column,ids=Parish,Parish.geometry,scope.parish_ids
  else:raise BusinessRuleError("Nivel territorial invÃ¡lido")
  rows=self.repo.geometry_rows(model,column,ids,filters.simplify,tolerance,bbox)[:limit];features=[]
  metric_rows={x["id"]:x for x in DashboardService(self.db,self.today_provider).territories(campaign.id,user,self.filter.dashboard_filters(filters),"PARISH",1,100)["items"]} if include_metrics and level=="PARISH" else {}
  for obj,geometry in rows:
   props={"resource_id":str(obj.id),"resource_type":level,"name":obj.name,"code":obj.dpa_code,"territory_level":level,"campaign_id":str(campaign.id),"geometry_source":"OFFICIAL_IMPORT","geometry_quality":"VALID"}
   if level=="PARISH":props["parish_type"]=obj.parish_type
   if metric and obj.id in metric_rows:props.update(metric_code=metric,metric_label=metric.replace('_',' ').title(),metric_value=metric_rows[obj.id].get(metric.lower(),metric_rows[obj.id].get("completed_activities")),metric_unit="COUNT")
   features.append(self.geojson.feature(obj.id,geometry if filters.include_geometry else None,props))
  return self.geojson.collection(features,bbox,status="AVAILABLE" if features else "MISSING",unmapped=len(ids)-len(rows),metadata={"period":period.model_dump(mode="json"),"simplified":filters.simplify,"tolerance":tolerance})
 def points(self,campaign_id,user,filters,kind):
  campaign,_,scope,_,limit=self.context(campaign_id,user,filters);model,column,ids,parent=(Community,Community.location,scope.community_ids,"parish_id") if kind=="COMMUNITY" else (Sector,Sector.location,scope.sector_ids,"community_id");rows=self.repo.geometry_rows(model,column,ids,False,0,filters.bbox.as_list() if filters.bbox else None)[:limit];features=[]
  for obj,geometry in rows:features.append(self.geojson.feature(obj.id,geometry if filters.include_geometry else None,{"resource_id":str(obj.id),"resource_type":kind,"name":obj.name,"code":obj.code,"territory_level":kind,"campaign_id":str(campaign.id),parent:str(getattr(obj,parent)),"is_active":obj.is_active,"geometry_source":f"{kind}_LOCATION","geometry_quality":"VALID"}))
  return self.geojson.collection(features,filters.bbox.as_list() if filters.bbox else None,"AVAILABLE" if features else "MISSING",len(ids)-len(rows))
 def activities(self,campaign_id,user,filters,cluster=True):
  campaign,period,scope,_,limit=self.context(campaign_id,user,filters);bbox=filters.bbox.as_list() if filters.bbox else None;total=self.db.scalar(select(func.count()).select_from(TerritorialActivity).where(TerritorialActivity.campaign_id==campaign.id,TerritorialActivity.is_active.is_(True),TerritorialActivity.activity_date.between(period.date_from,period.date_to),TerritorialActivity.parish_id.in_(scope.parish_ids))) or 0;located=self.db.scalar(select(func.count()).select_from(TerritorialActivity).where(TerritorialActivity.campaign_id==campaign.id,TerritorialActivity.is_active.is_(True),TerritorialActivity.activity_date.between(period.date_from,period.date_to),TerritorialActivity.parish_id.in_(scope.parish_ids),TerritorialActivity.location.is_not(None))) or 0
  if not cluster and located>settings.map_max_point_features_without_clustering:raise OverflowError("La consulta geogrÃ¡fica supera el lÃ­mite permitido. Reduzca el Ã¡rea, utilice clustering o aumente el nivel de zoom.")
  features=[]
  if cluster:
   for code,count,completed,planned,cancelled,attendees,geometry,extent in self.repo.activity_clusters(campaign.id,period.date_from,period.date_to,scope.parish_ids,filters.zoom,bbox)[:limit]:features.append(self.geojson.feature(f"cluster-{code}",geometry,{"resource_id":f"cluster-{code}","resource_type":"ACTIVITY_CLUSTER","cluster_id":code,"point_count":count,"completed":completed,"planned":planned,"cancelled":cancelled,"estimated_attendees":attendees,"cluster_bbox":str(extent) if extent else None,"is_cluster":True,"campaign_id":str(campaign.id),"geometry_source":"POSTGIS_CLUSTER","geometry_quality":"VALID"}))
  else:
   for activity,code,attendees,needs,commitments,geometry in self.repo.activity_points(campaign.id,period.date_from,period.date_to,scope.parish_ids,bbox)[:limit]:
    features.append(self.geojson.feature(activity.id,geometry,{"resource_id":str(activity.id),"resource_type":"ACTIVITY","name":activity.title,"activity_date":activity.activity_date.isoformat(),"status":activity.status,"activity_type":code,"parish_id":activity.parish_id,"estimated_attendees":attendees,"needs_count":needs,"commitments_count":commitments,"campaign_id":str(campaign.id),"geometry_source":"ACTIVITY_LOCATION","geometry_quality":"VALID"}))
  return self.geojson.collection(features,bbox,"AVAILABLE" if features else "MISSING",total-located,metadata={"activities_without_location":total-located,"clustered":cluster,"returned_features":len(features),"period":period.model_dump(mode="json")})
 def thematic(self,campaign_id,user,filters,layer,metric,need_category_code=None):
  if metric not in self.metrics(layer):raise BusinessRuleError('Métrica geográfica desconocida')
  campaign,period,scope,tolerance,limit=self.context(campaign_id,user,filters);rows=self.repo.geometry_rows(Parish,Parish.geometry,scope.parish_ids,filters.simplify,tolerance,filters.bbox.as_list() if filters.bbox else None)[:limit];dash=DashboardService(self.db,self.today_provider);territories={x["id"]:x for x in dash.territories(campaign.id,user,self.filter.dashboard_filters(filters),"PARISH",1,100)["items"]};need_map={};commitment_map={};features=[]
  if layer=="NEEDS":
   q=select(CitizenNeed.parish_id,func.count(CitizenNeed.id),func.coalesce(func.sum(CitizenNeed.mentions_count),0),func.count().filter(CitizenNeed.priority=='HIGH'),func.count().filter(CitizenNeed.priority=='CRITICAL')).where(CitizenNeed.campaign_id==campaign.id,CitizenNeed.parish_id.in_(scope.parish_ids),CitizenNeed.is_active.is_(True),CitizenNeed.reported_date.between(period.date_from,period.date_to))
   if need_category_code:q=q.where(CitizenNeed.need_category_id==select(NeedCategory.id).where(NeedCategory.code==need_category_code).scalar_subquery())
   need_map={r[0]:r[1:] for r in self.db.execute(q.group_by(CitizenNeed.parish_id))}
  if layer=="COMMITMENTS":commitment_map={r[0]:r[1:] for r in self.db.execute(select(Commitment.parish_id,func.count().filter(Commitment.status=='PENDING'),func.count().filter(Commitment.status=='IN_PROGRESS'),func.count().filter(Commitment.status=='COMPLETED'),func.count().filter(Commitment.due_date<period.date_to,Commitment.status.in_(['PENDING','IN_PROGRESS']))).where(Commitment.campaign_id==campaign.id,Commitment.parish_id.in_(scope.parish_ids),Commitment.is_active.is_(True)).group_by(Commitment.parish_id))}
  for parish,geometry in rows:
   values=territories.get(parish.id,{});value=None;extra={}
   if layer=="OPERATIONAL_COVERAGE":value=values.get({"COMPLETED_ACTIVITIES":"completed_activities","PLANNED_ACTIVITIES":"planned_activities","ESTIMATED_ATTENDEES":"estimated_attendees","LAST_COMPLETED_ACTIVITY_DATE":"last_completed_activity_date","DAYS_SINCE_LAST_ACTIVITY":"days_since_last_activity","ACTIVITY_TYPE_DIVERSITY":"distinct_activity_types"}.get(metric,"completed_activities"))
   elif layer=="NEEDS":
    r=need_map.get(parish.id,(0,0,0,0));value={"NEED_COUNT":r[0],"MENTIONS_COUNT":r[1],"HIGH_PRIORITY_NEEDS":r[2],"CRITICAL_NEEDS":r[3]}.get(metric,r[0]);extra={"need_count":r[0],"mentions_count":r[1],"high_priority":r[2],"critical":r[3]}
   else:
    r=commitment_map.get(parish.id,(0,0,0,0));value={"PENDING_COMMITMENTS":r[0],"IN_PROGRESS_COMMITMENTS":r[1],"COMPLETED_COMMITMENTS":r[2],"OVERDUE_COMMITMENTS":r[3]}.get(metric,r[0]);extra={"pending":r[0],"in_progress":r[1],"completed":r[2],"overdue":r[3]}
   features.append(self.geojson.feature(parish.id,geometry,{"resource_id":str(parish.id),"resource_type":"PARISH","name":parish.name,"code":parish.dpa_code,"territory_level":"PARISH","campaign_id":str(campaign.id),"metric_code":metric,"metric_label":metric.replace('_',' ').title(),"metric_value":value,"metric_unit":"COUNT","data_status":"AVAILABLE","suppressed":False,"geometry_source":"OFFICIAL_IMPORT","geometry_quality":"VALID",**extra}))
  return self.geojson.collection(features,filters.bbox.as_list() if filters.bbox else None,"AVAILABLE" if features else "MISSING",len(scope.parish_ids)-len(rows),metadata={"period":period.model_dump(mode="json")})
 def surveys(self,campaign_id,user,filters,survey_id=None,metric="VALID_RESPONSES"):
  if metric not in self.metrics('SURVEY_PARTICIPATION'):raise BusinessRuleError('Métrica geográfica desconocida')
  campaign,period,scope,tolerance,limit=self.context(campaign_id,user,filters);rows=self.repo.geometry_rows(Parish,Parish.geometry,scope.parish_ids,filters.simplify,tolerance,filters.bbox.as_list() if filters.bbox else None)[:limit];q=select(SurveyResponse.parish_id,func.count()).where(SurveyResponse.campaign_id==campaign.id,SurveyResponse.parish_id.in_(scope.parish_ids),SurveyResponse.response_date.between(period.date_from,period.date_to),SurveyResponse.is_valid.is_(True));q=q.where(SurveyResponse.survey_id==survey_id) if survey_id else q;counts={r[0]:r[1] for r in self.db.execute(q.group_by(SurveyResponse.parish_id))};features=[]
  for parish,geometry in rows:
   count=counts.get(parish.id,0);suppressed=count<settings.survey_min_aggregate_responses;features.append(self.geojson.feature(parish.id,geometry,{"resource_id":str(parish.id),"resource_type":"PARISH","name":parish.name,"code":parish.dpa_code,"territory_level":"PARISH","campaign_id":str(campaign.id),"metric_code":metric,"metric_label":"Respuestas válidas","metric_value":None if suppressed else count,"metric_unit":"COUNT","response_count":count,"distribution":None,"data_status":"SUPPRESSED" if suppressed else "AVAILABLE","suppressed":suppressed,"geometry_source":"OFFICIAL_IMPORT","geometry_quality":"VALID"}))
  return self.geojson.collection(features,status="AVAILABLE" if features else "MISSING",unmapped=len(scope.parish_ids)-len(rows),metadata={"privacy_threshold":settings.survey_min_aggregate_responses,"individual_locations":False})
 def demographics(self,campaign_id,user,filters,indicator_code,reference_year=None,source_id=None):
  campaign,_,scope,tolerance,limit=self.context(campaign_id,user,filters);indicator=self.db.scalar(select(DemographicIndicator).where(DemographicIndicator.code==indicator_code,DemographicIndicator.is_active.is_(True)))
  if not indicator:raise NotFoundError("Indicador inexistente")
  rows=self.repo.geometry_rows(Parish,Parish.geometry,scope.parish_ids,filters.simplify,tolerance,filters.bbox.as_list() if filters.bbox else None)[:limit];q=select(DemographicObservation,DataSource).join(DataSource,DataSource.id==DemographicObservation.source_id).where(DemographicObservation.demographic_indicator_id==indicator.id,DemographicObservation.parish_id.in_(scope.parish_ids),DemographicObservation.is_active.is_(True),DemographicObservation.is_official.is_(True));q=q.where(DemographicObservation.reference_year==reference_year) if reference_year else q;q=q.where(DemographicObservation.source_id==source_id) if source_id else q;observations={o.parish_id:(o,s) for o,s in self.db.execute(q.order_by(DemographicObservation.reference_year))};features=[]
  for parish,geometry in rows:
   pair=observations.get(parish.id);value,year,source=(pair[0].value,pair[0].reference_year,pair[1].institution) if pair else (None,None,None);features.append(self.geojson.feature(parish.id,geometry,{"resource_id":str(parish.id),"resource_type":"PARISH","name":parish.name,"code":parish.dpa_code,"territory_level":"PARISH","campaign_id":str(campaign.id),"metric_code":indicator.code,"metric_label":indicator.name,"metric_value":value,"metric_unit":indicator.unit,"reference_year":year,"source":source,"category":indicator.category,"data_status":"AVAILABLE" if pair else "UNAVAILABLE","suppressed":False,"geometry_source":"OFFICIAL_IMPORT","geometry_quality":"VALID","correlated_with_electoral_results":False}))
  return self.geojson.collection(features,status="AVAILABLE" if features else "MISSING",unmapped=len(scope.parish_ids)-len(rows))
 def electoral(self,campaign_id,user,filters,process_id,contest_id,metric,is_final=True):
  if metric not in self.metrics('ELECTORAL_HISTORY'):raise BusinessRuleError('Métrica geográfica desconocida')
  campaign,_,scope,tolerance,limit=self.context(campaign_id,user,filters);contest=self.db.get(ElectoralContest,contest_id);process=self.db.get(ElectoralProcess,process_id)
  if not contest or not process or contest.electoral_process_id!=process.id or contest.canton_id!=campaign.canton_id or contest.office_type!=campaign.office_type:raise BusinessRuleError("Proceso electoral incompatible")
  rows=self.repo.geometry_rows(Parish,Parish.geometry,scope.parish_ids,filters.simplify,tolerance,filters.bbox.as_list() if filters.bbox else None)[:limit];turnouts={g.parish_id:t for t,g in self.db.execute(select(ElectoralTurnout,ElectoralGeography).join(ElectoralGeography).where(ElectoralTurnout.electoral_contest_id==contest.id,ElectoralGeography.parish_id.in_(scope.parish_ids),ElectoralGeography.level=='PARISH',ElectoralTurnout.is_final==is_final))};features=[]
  for parish,geometry in rows:
   t=turnouts.get(parish.id);value={"REGISTERED_VOTERS":t.registered_voters,"PARTICIPATION_RATE":percentage(t.ballots_cast,t.registered_voters),"ABSENTEE_RATE":percentage(t.registered_voters-t.ballots_cast,t.registered_voters),"VALID_VOTE_RATE":percentage(t.valid_votes,t.ballots_cast),"BLANK_VOTE_RATE":percentage(t.blank_votes,t.ballots_cast),"NULL_VOTE_RATE":percentage(t.null_votes,t.ballots_cast)}.get(metric) if t else None;features.append(self.geojson.feature(parish.id,geometry,{"resource_id":str(parish.id),"resource_type":"PARISH","name":parish.name,"code":parish.dpa_code,"territory_level":"PARISH","campaign_id":str(campaign.id),"process_id":str(process.id),"contest_id":str(contest.id),"is_final":is_final,"metric_code":metric,"metric_label":metric.replace('_',' ').title(),"metric_value":value,"metric_unit":"PERCENT" if metric.endswith('RATE') else "COUNT","source":str(t.source_id) if t else None,"data_status":"AVAILABLE" if value is not None else "UNAVAILABLE","suppressed":False,"geometry_source":"OFFICIAL_IMPORT","geometry_quality":"VALID","prediction":False}))
  return self.geojson.collection(features,status="AVAILABLE" if features else "MISSING",unmapped=len(scope.parish_ids)-len(rows))
 def participation_projection(self,campaign_id,user,filters,metric):
  if metric not in self.metrics('PARTICIPATION_PROJECTION'): raise BusinessRuleError('MÃ©trica geogrÃ¡fica desconocida')
  campaign,_,scope,tolerance,limit=self.context(campaign_id,user,filters);run=self.db.scalar(select(ParticipationProjectionRun).where(ParticipationProjectionRun.campaign_id==campaign.id).order_by(ParticipationProjectionRun.created_at.desc()))
  if not run: return self.geojson.collection([],status='MISSING',unmapped=len(scope.parish_ids))
  result_map={r.parish_id:r for r in self.db.scalars(select(ParticipationProjectionResult).where(ParticipationProjectionResult.run_id==run.id))}
  snapshot=self.db.get(ElectoralRollSnapshot,run.snapshot_id)
  entries={e.parish_id:e for e in self.db.scalars(select(ElectoralRollSnapshotEntry).where(ElectoralRollSnapshotEntry.snapshot_id==run.snapshot_id,ElectoralRollSnapshotEntry.parish_id.in_(scope.parish_ids)))}
  history={2019:{},2023:{}}
  for process in self.db.scalars(select(ElectoralProcess).where(ElectoralProcess.id.in_([str(x) for x in run.historical_process_ids]))):
   contest=self.db.scalar(select(ElectoralContest).where(ElectoralContest.electoral_process_id==process.id,ElectoralContest.office_type==campaign.office_type,ElectoralContest.canton_id==campaign.canton_id,ElectoralContest.is_active.is_(True)))
   if contest:
    for turnout,geo in self.db.execute(select(ElectoralTurnout,ElectoralGeography).join(ElectoralGeography,ElectoralGeography.id==ElectoralTurnout.electoral_geography_id).where(ElectoralTurnout.electoral_contest_id==contest.id,ElectoralGeography.parish_id.in_(scope.parish_ids),ElectoralTurnout.is_final.is_(True))): history.setdefault(process.year,{})[geo.parish_id]=turnout
  indicators={i.code:i for i in self.db.scalars(select(DemographicIndicator).where(DemographicIndicator.code.in_(['POP_TOTAL','POPULATION_GROWTH','POP_GROWTH','POPULATION_DENSITY','DENSITY']),DemographicIndicator.is_active.is_(True)))}
  demographics={pid:{} for pid in scope.parish_ids}
  if indicators:
   for obs,indicator in self.db.execute(select(DemographicObservation,DemographicIndicator).join(DemographicIndicator).where(DemographicObservation.parish_id.in_(scope.parish_ids),DemographicObservation.demographic_indicator_id.in_([x.id for x in indicators.values()]),DemographicObservation.is_active.is_(True),DemographicObservation.is_official.is_(True)).order_by(DemographicObservation.reference_year)):
    demographics[obs.parish_id][indicator.code]=float(obs.value)
  rows=self.repo.geometry_rows(Parish,Parish.geometry,scope.parish_ids,filters.simplify,tolerance,filters.bbox.as_list() if filters.bbox else None)[:limit];features=[]
  for parish,geometry in rows:
   result=result_map.get(parish.id);h19=history.get(2019,{}).get(parish.id);h23=history.get(2023,{}).get(parish.id);demo=demographics.get(parish.id,{})
   rate19=(h19.ballots_cast/h19.registered_voters) if h19 and h19.registered_voters else None;rate23=(h23.ballots_cast/h23.registered_voters) if h23 and h23.registered_voters else None
   values={'REGISTERED_VOTERS':result.registered_voters if result else None,'TURNOUT_RATE_2019':rate19,'TURNOUT_RATE_2023':rate23,'TURNOUT_RATE_LOW':result.turnout_rate_low if result else None,'TURNOUT_RATE_CENTRAL':result.turnout_rate_central if result else None,'TURNOUT_RATE_HIGH':result.turnout_rate_high if result else None,'EXPECTED_VOTERS_CENTRAL':result.expected_voters_central if result else None,'REGISTRATION_CHANGE_2019':(entries[parish.id].registered_voters-h19.registered_voters) if parish.id in entries and h19 else None,'REGISTRATION_CHANGE_2023':(entries[parish.id].registered_voters-h23.registered_voters) if parish.id in entries and h23 else None,'INEC_POPULATION_2022':demo.get('POP_TOTAL'),'INEC_POPULATION_GROWTH':demo.get('POPULATION_GROWTH',demo.get('POP_GROWTH')),'POPULATION_DENSITY':demo.get('POPULATION_DENSITY',demo.get('DENSITY'))}
   value=values[metric]
   properties={"resource_id":str(parish.id),"resource_type":"PARISH","name":parish.name,"code":parish.dpa_code,"territory_level":"PARISH","campaign_id":str(campaign.id),"metric_code":metric,"metric_label":metric.replace('_',' ').title(),"metric_value":value,"metric_unit":"PERCENT" if ('RATE' in metric or metric=='INEC_POPULATION_GROWTH') else "COUNT","data_status":"AVAILABLE" if value is not None else "UNAVAILABLE","snapshot_date":snapshot.snapshot_date.isoformat() if snapshot else None,"registered_voters_current":entries.get(parish.id).registered_voters if entries.get(parish.id) else None,"turnout_rate_2019":rate19,"turnout_rate_2023":rate23,"turnout_rate_low":float(result.turnout_rate_low) if result else None,"turnout_rate_central":float(result.turnout_rate_central) if result else None,"turnout_rate_high":float(result.turnout_rate_high) if result else None,"expected_voters_central":result.expected_voters_central if result else None,"data_quality_status":result.data_quality_status if result else 'INSUFFICIENT_DATA',"inec_population_2022":demo.get('POP_TOTAL'),"inec_population_growth":demo.get('POPULATION_GROWTH',demo.get('POP_GROWTH')),"population_density":demo.get('POPULATION_DENSITY',demo.get('DENSITY')),"observed_source":"CNE","projection_source":"TERRITORIO ELECTORAL","demographic_source":"INEC","prediction":False,"political_preference":False}
   features.append(self.geojson.feature(parish.id,geometry,properties))
  return self.geojson.collection(features,filters.bbox.as_list() if filters.bbox else None,'AVAILABLE' if features else 'MISSING',len(scope.parish_ids)-len(rows))
 def detail(self,campaign_id,user,filters,resource_type,resource_id):
  campaign,period,scope,tolerance,_=self.context(campaign_id,user,filters);models={"PARISH":(Parish,Parish.geometry,scope.parish_ids),"COMMUNITY":(Community,Community.location,scope.community_ids),"SECTOR":(Sector,Sector.location,scope.sector_ids),"ACTIVITY":(TerritorialActivity,TerritorialActivity.location,None)}
  if resource_type not in models:raise BusinessRuleError("Tipo de recurso invÃ¡lido")
  model,column,ids=models[resource_type];obj=self.db.get(model,resource_id)
  if not obj or (ids is not None and obj.id not in ids) or (resource_type=='ACTIVITY' and (obj.campaign_id!=campaign.id or obj.parish_id not in scope.parish_ids)):raise NotFoundError("Recurso no encontrado")
  geometry=None
  if obj and getattr(obj,column.key) is not None and self.repo.postgres:geometry=self.db.scalar(select(func.ST_AsGeoJSON(column)).where(model.id==obj.id))
  props={"resource_id":str(obj.id),"resource_type":resource_type,"name":getattr(obj,"name",getattr(obj,"title",None)),"campaign_id":str(campaign.id),"geometry_quality":self.geom_status(column,model,obj.id)};summary={}
  if resource_type=='ACTIVITY':summary={"activity_date":obj.activity_date,"status":obj.status,"parish_id":obj.parish_id,"estimated_attendees":self.db.scalar(select(func.coalesce(ActivityParticipantSummary.estimated_attendees,0)).where(ActivityParticipantSummary.activity_id==obj.id)) or 0,"needs_count":self.db.scalar(select(func.count()).select_from(CitizenNeed).where(CitizenNeed.activity_id==obj.id,CitizenNeed.is_active.is_(True))) or 0,"commitments_count":self.db.scalar(select(func.count()).select_from(Commitment).where(Commitment.activity_id==obj.id,Commitment.is_active.is_(True))) or 0}
  return {"resource_type":resource_type,"resource_id":str(obj.id),"geometry":self.geojson.geometry(geometry),"properties":props,"summary":summary}
 def quality(self,campaign_id,user,filters):
  campaign,_,scope,_,_=self.context(campaign_id,user,filters);issues=[]
  def add(code,description,count,resource,status,action):
   if count:issues.append({"code":code,"description":description,"count":count,"resource_type":resource,"status":status,"technical_action":action})
  canton=self.db.get(Canton,campaign.canton_id);add("CANTON_GEOMETRY_MISSING","CantÃ³n sin geometrÃ­a",int(canton.geometry is None),"CANTON","MISSING","Importar el lÃ­mite cantonal oficial.");add("PARISH_GEOMETRY_MISSING","Parroquias sin geometrÃ­a",self.db.scalar(select(func.count()).select_from(Parish).where(Parish.id.in_(scope.parish_ids),Parish.geometry.is_(None))) or 0,"PARISH","MISSING","Importar lÃ­mites oficiales de parroquias.");add("COMMUNITY_LOCATION_MISSING","Comunidades sin punto",self.db.scalar(select(func.count()).select_from(Community).where(Community.id.in_(scope.community_ids),Community.location.is_(None))) or 0,"COMMUNITY","MISSING","Asignar ubicaciones verificadas.");add("SECTOR_LOCATION_MISSING","Sectores sin punto",self.db.scalar(select(func.count()).select_from(Sector).where(Sector.id.in_(scope.sector_ids),Sector.location.is_(None))) or 0,"SECTOR","MISSING","Asignar ubicaciones verificadas.");add("ACTIVITY_LOCATION_MISSING","Actividades sin ubicaciÃ³n",self.db.scalar(select(func.count()).select_from(TerritorialActivity).where(TerritorialActivity.campaign_id==campaign.id,TerritorialActivity.parish_id.in_(scope.parish_ids),TerritorialActivity.location.is_(None),TerritorialActivity.is_active.is_(True))) or 0,"ACTIVITY","MISSING","Asignar ubicaciÃ³n a actividades sin coordenadas.");add("ELECTORAL_GEOGRAPHY_UNMAPPED","GeografÃ­as electorales sin mapear",self.db.scalar(select(func.count()).select_from(ElectoralGeography).where(ElectoralGeography.canton_id==campaign.canton_id,ElectoralGeography.is_mapped.is_(False))) or 0,"ELECTORAL_GEOGRAPHY","WARNING","Revisar geografÃ­as sin mapear.")
  if self.repo.postgres:
   add("PARISH_GEOMETRY_INVALID","Parroquias con geometrÃ­a invÃ¡lida",self.db.scalar(select(func.count()).select_from(Parish).where(Parish.id.in_(scope.parish_ids),Parish.geometry.is_not(None),func.ST_IsValid(Parish.geometry).is_(False))) or 0,"PARISH","INVALID","Revisar geometrÃ­as invÃ¡lidas.");add("PARISH_WRONG_SRID","Parroquias con SRID incorrecto",self.db.scalar(select(func.count()).select_from(Parish).where(Parish.id.in_(scope.parish_ids),Parish.geometry.is_not(None),func.ST_SRID(Parish.geometry)!=4326)) or 0,"PARISH","INVALID","Convertir previamente a EPSG:4326.")
  return {"status":"OK" if not issues else "WARNING","issues":issues}
