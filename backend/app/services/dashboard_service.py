from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from math import ceil
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.campaign import Campaign
from app.models.historical import DataImportJob, DataSource, DemographicIndicator, DemographicObservation, ElectoralContest, ElectoralGeography, ElectoralProcess, ElectoralTurnout
from app.models.operational import ActivityEvidence, ActivityParticipantSummary, ActivityType, CitizenNeed, Commitment, NeedCategory, TerritorialActivity
from app.models.survey import Survey, SurveyQuestion, SurveyResponse
from app.models.territory import Community, Parish, Sector
from app.models.user import User
from app.repositories.dashboard_repository import DashboardRepository
from app.schemas.dashboard import DashboardDataStatus, DashboardFilters, DashboardMetricRead, DashboardPeriodRead
from app.services.campaign_access_service import CampaignAccessService
from app.services.dashboard_filter_service import DashboardFilterService
from app.services.demographic_service import DemographicService
from app.services.electoral_service import ElectoralService


def percentage(value: int | Decimal, denominator: int | Decimal):
    return (Decimal(value) * 100 / Decimal(denominator)).quantize(Decimal("0.01"), ROUND_HALF_UP) if denominator else None


class DashboardService:
    def __init__(self, db: Session, today_provider=date.today):
        self.db = db
        self.today_provider = today_provider
        self.access = CampaignAccessService(db)
        self.filters = DashboardFilterService(db, today_provider)
        self.repo = DashboardRepository(db)

    def context(self, campaign_id: UUID, user: User, filters: DashboardFilters):
        campaign = self.access.require_access(campaign_id, user)
        return campaign, self.filters.resolve_period(campaign, filters), self.filters.scope(campaign, user, filters)

    @staticmethod
    def metric(code, label, value, unit="COUNT", previous=None, denominator=None, note=None):
        comparable = previous is not None and previous != 0
        change = value - previous if previous is not None else None
        return DashboardMetricRead(code=code, label=label, value=value, unit=unit, denominator=denominator, previous_value=previous, absolute_change=change, percentage_change=percentage(change, previous) if comparable else None, is_comparable=comparable, data_status=DashboardDataStatus.AVAILABLE, note=note)

    def overview(self, campaign_id: UUID, user: User, filters: DashboardFilters):
        campaign, period, scope = self.context(campaign_id, user, filters)
        current = self.repo.operational_counts(campaign.id, period.date_from, period.date_to, scope.parish_ids)
        commitments = self.repo.commitment_counts(campaign.id, period.date_to, scope.parish_ids)
        previous = self.repo.operational_counts(campaign.id, period.previous_date_from, period.previous_date_to, scope.parish_ids) if period.previous_date_from else {}
        total_parishes = len(scope.parish_ids)
        coverage = percentage(current["covered"], total_parishes)
        survey_row = self.db.execute(select(
            func.count(Survey.id).filter(Survey.status == "PUBLISHED"),
            func.count(Survey.id).filter(Survey.status == "CLOSED"),
        ).where(Survey.campaign_id == campaign.id, Survey.is_active.is_(True))).one()
        valid_responses = self.db.scalar(select(func.count(SurveyResponse.id)).where(SurveyResponse.campaign_id == campaign.id, SurveyResponse.is_valid.is_(True), SurveyResponse.response_date.between(period.date_from, period.date_to), SurveyResponse.parish_id.in_(scope.parish_ids) if scope.parish_ids else False)) or 0
        sources = self.db.scalar(select(func.count(DataSource.id)).where(DataSource.is_official.is_(True), DataSource.is_active.is_(True))) or 0
        processes = self.db.scalar(select(func.count(func.distinct(ElectoralProcess.id))).join(ElectoralContest).where(ElectoralContest.canton_id == campaign.canton_id, ElectoralContest.office_type == campaign.office_type, ElectoralProcess.is_active.is_(True))) or 0
        indicators = self.db.scalar(select(func.count(func.distinct(DemographicIndicator.id))).join(DemographicObservation).where(DemographicObservation.canton_id == campaign.canton_id, DemographicObservation.is_active.is_(True), DemographicObservation.is_official.is_(True))) or 0
        top_needs = [{"code": code, "name": name, "mentions": mentions, "activities": activities} for code, name, mentions, activities in self.db.execute(select(NeedCategory.code, NeedCategory.name, func.sum(CitizenNeed.mentions_count), func.count(func.distinct(CitizenNeed.activity_id))).join(CitizenNeed).join(TerritorialActivity, TerritorialActivity.id == CitizenNeed.activity_id).where(CitizenNeed.campaign_id == campaign.id, CitizenNeed.is_active.is_(True), TerritorialActivity.activity_date.between(period.date_from, period.date_to), CitizenNeed.parish_id.in_(scope.parish_ids) if scope.parish_ids else False).group_by(NeedCategory.id).order_by(func.count(func.distinct(CitizenNeed.activity_id)).desc(), NeedCategory.name).limit(5))]
        metric_specs = [
            ("completed_activities", "Actividades completadas", current["completed"]), ("planned_activities", "Actividades planificadas", current["planned"]), ("cancelled_activities", "Actividades canceladas", current["cancelled"]), ("estimated_attendees", "Asistentes estimados", current["attendees"]),
            ("covered_parishes", "Parroquias con actividades completadas", current["covered"]), ("uncovered_parishes", "Parroquias sin actividades completadas", max(total_parishes-current["covered"], 0)), ("active_needs", "Necesidades activas", current["needs"]), ("need_mentions", "Menciones de necesidades", current["mentions"]),
            ("pending_commitments", "Seguimientos pendientes", commitments["pending"]), ("in_progress_commitments", "Seguimientos en curso", commitments["in_progress"]), ("completed_commitments", "Seguimientos realizados", commitments["completed"]), ("overdue_commitments", "Seguimientos por revisar", commitments["overdue"]),
            ("valid_survey_responses", "Respuestas válidas de encuestas", valid_responses), ("published_surveys", "Encuestas publicadas", survey_row[0]), ("closed_surveys", "Encuestas cerradas", survey_row[1]), ("official_sources", "Fuentes oficiales disponibles", sources), ("historical_processes", "Procesos históricos compatibles", processes), ("demographic_indicators", "Indicadores demográficos disponibles", indicators),
        ]
        previous_keys={"completed_activities":"completed","planned_activities":"planned","cancelled_activities":"cancelled","estimated_attendees":"attendees","active_needs":"needs","need_mentions":"mentions"}
        metrics = [self.metric(code, label, value, previous=previous.get(previous_keys[code]) if previous and code in previous_keys else None) for code,label,value in metric_specs]
        metrics.insert(6, self.metric("parish_coverage_rate", "Cobertura operativa territorial", coverage, "PERCENT", denominator=total_parishes))
        summary = f'Durante el período se registraron {current["completed"]} actividades completadas en {current["covered"]} parroquias. Se contabilizaron {current["attendees"]} asistentes estimados, {current["needs"]} necesidades registradas y {commitments["overdue"]} seguimientos por revisar.'
        return {"campaign":{"id":campaign.id,"name":campaign.name,"office_type":campaign.office_type,"election_date":campaign.election_date},"scope":scope,"period":period,"as_of_date":self.today_provider(),"metrics":metrics,"territorial_coverage":{"accessible_parishes":total_parishes,"covered_parishes":current["covered"],"uncovered_parishes":max(total_parishes-current["covered"],0),"coverage_rate":coverage},"top_needs":top_needs,"commitment_summary":commitments,"survey_summary":{"published":survey_row[0],"closed":survey_row[1],"valid_responses":valid_responses},"data_quality":{"status":"AVAILABLE" if any([current["completed"],valid_responses,processes,indicators]) else "UNAVAILABLE"},"summary_text":summary}

    def filter_options(self, campaign_id, user, filters):
        campaign, _, scope = self.context(campaign_id,user,filters)
        parishes=list(self.db.execute(select(Parish.id,Parish.name,Parish.dpa_code).where(Parish.id.in_(scope.parish_ids)).order_by(Parish.name))) if scope.parish_ids else []
        communities=list(self.db.execute(select(Community.id,Community.name,Community.parish_id).where(Community.id.in_(scope.community_ids)).order_by(Community.name))) if scope.community_ids else []
        sectors=list(self.db.execute(select(Sector.id,Sector.name,Sector.community_id).where(Sector.id.in_(scope.sector_ids)).order_by(Sector.name))) if scope.sector_ids else []
        surveys=list(self.db.execute(select(Survey.id,Survey.title,Survey.status).where(Survey.campaign_id==campaign.id,Survey.is_active.is_(True))))
        processes=list(self.db.execute(select(ElectoralProcess.id,ElectoralProcess.name,ElectoralProcess.election_date).join(ElectoralContest).where(ElectoralContest.canton_id==campaign.canton_id,ElectoralContest.office_type==campaign.office_type)))
        indicators=list(self.db.execute(select(DemographicIndicator.code,DemographicIndicator.name).join(DemographicObservation).where(DemographicObservation.canton_id==campaign.canton_id).distinct()))
        min_date=self.db.scalar(select(func.min(TerritorialActivity.activity_date)).where(TerritorialActivity.campaign_id==campaign.id));max_date=self.db.scalar(select(func.max(TerritorialActivity.activity_date)).where(TerritorialActivity.campaign_id==campaign.id))
        return {"periods":[x.value for x in __import__('app.schemas.dashboard',fromlist=['DashboardPeriod']).DashboardPeriod],"parishes":[{"id":x.id,"name":x.name,"code":x.dpa_code} for x in parishes],"communities":[{"id":x.id,"name":x.name,"parish_id":x.parish_id} for x in communities],"sectors":[{"id":x.id,"name":x.name,"community_id":x.community_id} for x in sectors],"surveys":[{"id":x.id,"title":x.title,"status":x.status} for x in surveys],"electoral_processes":[{"id":x.id,"name":x.name,"election_date":x.election_date} for x in processes],"demographic_indicators":[{"code":x.code,"name":x.name} for x in indicators],"min_date":min_date,"max_date":max_date,"scope":scope}

    def activity_trends(self,campaign_id,user,filters,group_by="DAY",fill_missing_periods=False,activity_type_codes=None,statuses=None):
        campaign,period,scope=self.context(campaign_id,user,filters);q=select(TerritorialActivity.activity_date,TerritorialActivity.status,func.count(),func.coalesce(func.sum(ActivityParticipantSummary.estimated_attendees),0),func.count(func.distinct(TerritorialActivity.activity_type_id))).outerjoin(ActivityParticipantSummary).where(TerritorialActivity.campaign_id==campaign.id,TerritorialActivity.is_active.is_(True),TerritorialActivity.activity_date.between(period.date_from,period.date_to),TerritorialActivity.parish_id.in_(scope.parish_ids) if scope.parish_ids else False)
        if statuses:q=q.where(TerritorialActivity.status.in_(statuses))
        if activity_type_codes:q=q.join(ActivityType).where(ActivityType.code.in_(activity_type_codes))
        rows=self.db.execute(q.group_by(TerritorialActivity.activity_date,TerritorialActivity.status));points={}
        for d,status,count,attendees,types in rows:
            key=d if group_by=="DAY" else d-timedelta(days=d.weekday()) if group_by=="WEEK" else d.replace(day=1);p=points.setdefault(key,{"period_start":key,"completed":0,"planned":0,"cancelled":0,"estimated_attendees":0,"distinct_activity_types":0});p[status.lower()]+=count
            if status=="COMPLETED":p["estimated_attendees"]+=attendees
            p["distinct_activity_types"]+=types
        if fill_missing_periods:
            cursor=period.date_from if group_by=="DAY" else period.date_from-timedelta(days=period.date_from.weekday()) if group_by=="WEEK" else period.date_from.replace(day=1)
            while cursor<=period.date_to:
                points.setdefault(cursor,{"period_start":cursor,"completed":0,"planned":0,"cancelled":0,"estimated_attendees":0,"distinct_activity_types":0});cursor=cursor+(timedelta(days=1) if group_by=="DAY" else timedelta(days=7) if group_by=="WEEK" else timedelta(days=monthrange(cursor.year,cursor.month)[1]))
        return {"period":period,"group_by":group_by,"points":[points[k] for k in sorted(points)]}

    def needs(self,campaign_id,user,filters):
        campaign,period,scope=self.context(campaign_id,user,filters);base=[CitizenNeed.campaign_id==campaign.id,CitizenNeed.is_active.is_(True),TerritorialActivity.activity_date.between(period.date_from,period.date_to),CitizenNeed.parish_id.in_(scope.parish_ids) if scope.parish_ids else False]
        total=self.db.execute(select(func.count(CitizenNeed.id),func.coalesce(func.sum(CitizenNeed.mentions_count),0)).join(TerritorialActivity).where(*base)).one();rows=self.db.execute(select(NeedCategory.code,NeedCategory.name,func.count(CitizenNeed.id),func.sum(CitizenNeed.mentions_count),func.count(func.distinct(CitizenNeed.activity_id)),func.count(func.distinct(CitizenNeed.parish_id))).join(CitizenNeed).join(TerritorialActivity,TerritorialActivity.id==CitizenNeed.activity_id).where(*base).group_by(NeedCategory.id).order_by(func.count(func.distinct(CitizenNeed.activity_id)).desc(),NeedCategory.name))
        return {"total_needs":total[0],"total_mentions":total[1],"categories":[{"code":r[0],"name":r[1],"needs":r[2],"mentions":r[3],"activities":r[4],"territories":r[5]} for r in rows],"by_priority":self._group_count(CitizenNeed.priority,base,join_activity=True),"by_status":self._group_count(CitizenNeed.status,base,join_activity=True),"note":"Las menciones son datos agregados y no representan preferencia electoral."}

    def _group_count(self,column,conditions,join_activity=False):
        q=select(column,func.count()).select_from(CitizenNeed)
        if join_activity:q=q.join(TerritorialActivity)
        return {str(k):v for k,v in self.db.execute(q.where(*conditions).group_by(column))}

    def commitments(self,campaign_id,user,filters):
        campaign,period,scope=self.context(campaign_id,user,filters);counts=self.repo.commitment_counts(campaign.id,period.date_to,scope.parish_ids);den=counts["pending"]+counts["in_progress"]+counts["completed"]+counts["cancelled"]
        return {**counts,"completion_rate":percentage(counts["completed"],den),"completion_denominator":den,"cutoff_date":period.date_to}

    def surveys(self,campaign_id,user,filters):
        campaign,period,scope=self.context(campaign_id,user,filters);survey_q=select(Survey).where(Survey.campaign_id==campaign.id,Survey.is_active.is_(True));survey_q=survey_q.where(Survey.id.in_(filters.survey_ids)) if filters.survey_ids else survey_q;surveys=list(self.db.scalars(survey_q));items=[]
        for survey in surveys:
            row=self.db.execute(select(func.count(),func.count().filter(SurveyResponse.is_valid.is_(True)),func.count().filter(SurveyResponse.is_valid.is_(False)),func.count().filter(SurveyResponse.is_complete.is_(True))).where(SurveyResponse.survey_id==survey.id,SurveyResponse.response_date.between(period.date_from,period.date_to),SurveyResponse.parish_id.in_(scope.parish_ids) if scope.parish_ids else False)).one();items.append({"survey_id":survey.id,"title":survey.title,"status":survey.status,"total_responses":row[0],"valid_responses":row[1],"invalid_responses":row[2],"complete_responses":row[3],"suppressed":row[1]<settings.survey_min_aggregate_responses})
        return {"surveys":items,"published":sum(x.status=="PUBLISHED" for x in surveys),"closed":sum(x.status=="CLOSED" for x in surveys),"privacy_threshold":settings.survey_min_aggregate_responses,"contains_individual_responses":False,"contains_open_text":False}

    def electoral_history(self,campaign_id,user,filters):
        campaign,_,scope=self.context(campaign_id,user,filters);ctx=ElectoralService(self.db).historical_context(campaign.id,user,filters.electoral_process_ids);payload=ctx.model_dump(mode="json")
        restricted="TERRITORIAL_COORDINATOR" in {r.code for r in user.roles} and not self.access.admin(user)
        if restricted:
            payload["turnout_comparison"]=[];payload["candidate_results"]=[];payload["message"]="Los detalles cantonales se omiten para respetar el alcance territorial."
        else:payload["message"]=None if payload["processes"] else "No existen procesos históricos compatibles importados."
        payload["data_available"]=bool(payload["processes"]);payload["scope_parish_ids"]=scope.parish_ids;return payload

    def demographics(self,campaign_id,user,filters,reference_year=None,source_id=None):
        campaign,_,scope=self.context(campaign_id,user,filters);restricted="TERRITORIAL_COORDINATOR" in {r.code for r in user.roles} and not self.access.admin(user)
        if restricted:
            q=select(DemographicObservation,DemographicIndicator).join(DemographicIndicator).where(DemographicObservation.canton_id==campaign.canton_id,DemographicObservation.parish_id.in_(scope.parish_ids),DemographicObservation.is_official.is_(True),DemographicObservation.is_active.is_(True))
            if reference_year:q=q.where(DemographicObservation.reference_year==reference_year)
            if filters.demographic_indicator_codes:q=q.where(DemographicIndicator.code.in_(filters.demographic_indicator_codes))
            items=[{"indicator_code":i.code,"name":i.name,"unit":i.unit,"value":str(o.value),"reference_year":o.reference_year,"source_id":str(o.source_id),"parish_id":o.parish_id} for o,i in self.db.execute(q)]
        else:items=DemographicService(self.db).profile(campaign.canton_id,filters.parish_id,reference_year,filters.demographic_indicator_codes)["observations"]
        if source_id:items=[x for x in items if x["source_id"]==str(source_id)]
        return {"items":items,"data_available":bool(items),"warnings":[] if len({x['reference_year'] for x in items})<=1 else ["Los indicadores corresponden a años distintos."],"interpolated":False,"correlated_with_electoral_results":False}

    def data_quality(self,campaign_id,user,filters):
        campaign,period,scope=self.context(campaign_id,user,filters);activity_base=[TerritorialActivity.campaign_id==campaign.id,TerritorialActivity.is_active.is_(True),TerritorialActivity.parish_id.in_(scope.parish_ids) if scope.parish_ids else False]
        issues=[]
        def add(code,desc,count,source,action=None,status="WARNING"):
            if count:issues.append({"code":code,"description":desc,"count":count,"scope":scope.type,"source":source,"status":status,"technical_action":action})
        add("ACTIVITIES_WITHOUT_PARTICIPANTS","Actividades sin resumen de participantes",self.db.scalar(select(func.count()).select_from(TerritorialActivity).outerjoin(ActivityParticipantSummary).where(*activity_base,ActivityParticipantSummary.id.is_(None))) or 0,"OPERATIONS","Completar el resumen agregado de participantes.")
        add("ACTIVITIES_WITHOUT_RESPONSIBLE","Actividades sin responsable",self.db.scalar(select(func.count()).select_from(TerritorialActivity).where(*activity_base,TerritorialActivity.responsible_user_id.is_(None))) or 0,"OPERATIONS")
        add("ACTIVITIES_WITHOUT_EVIDENCE","Actividades sin evidencia",self.db.scalar(select(func.count()).select_from(TerritorialActivity).outerjoin(ActivityEvidence).where(*activity_base,ActivityEvidence.id.is_(None))) or 0,"OPERATIONS")
        commitments=self.repo.commitment_counts(campaign.id,period.date_to,scope.parish_ids);add("COMMITMENTS_WITHOUT_RESPONSIBLE","Seguimientos sin responsable",commitments["without_responsible"],"COMMITMENTS","Asignar un responsable.")
        add("FAILED_IMPORTS","Importaciones fallidas",self.db.scalar(select(func.count()).select_from(DataImportJob).where(DataImportJob.status=="FAILED")) or 0,"ELECTORAL_DATA","Revisar los errores controlados de importación.")
        add("UNMAPPED_GEOGRAPHIES","Geografías sin mapear",self.db.scalar(select(func.count()).select_from(ElectoralGeography).where(ElectoralGeography.is_mapped.is_(False),ElectoralGeography.canton_id==campaign.canton_id)) or 0,"ELECTORAL_DATA","Revisar geografías sin mapear.")
        return {"status":"OK" if not issues else "WARNING","issues":issues}

    def territories(self,campaign_id,user,filters,level="PARISH",page=1,page_size=20,sort_by="name",sort_order="asc"):
        campaign,period,scope=self.context(campaign_id,user,filters);model=Parish if level=="PARISH" else Community if level=="COMMUNITY" else Sector;ids=scope.parish_ids if level=="PARISH" else scope.community_ids if level=="COMMUNITY" else scope.sector_ids;objects=list(self.db.scalars(select(model).where(model.id.in_(ids)).order_by(model.name))) if ids else [];items=[]
        group_col=TerritorialActivity.parish_id if level=="PARISH" else TerritorialActivity.community_id if level=="COMMUNITY" else TerritorialActivity.sector_id
        rows=self.db.execute(select(group_col,func.count().filter(TerritorialActivity.status=="COMPLETED"),func.count().filter(TerritorialActivity.status=="PLANNED"),func.count().filter(TerritorialActivity.status=="CANCELLED"),func.max(TerritorialActivity.activity_date).filter(TerritorialActivity.status=="COMPLETED"),func.coalesce(func.sum(ActivityParticipantSummary.estimated_attendees).filter(TerritorialActivity.status=="COMPLETED"),0),func.count(func.distinct(TerritorialActivity.activity_type_id))).outerjoin(ActivityParticipantSummary).where(TerritorialActivity.campaign_id==campaign.id,TerritorialActivity.is_active.is_(True),TerritorialActivity.activity_date.between(period.date_from,period.date_to),group_col.in_(ids)).group_by(group_col)) if ids else []
        aggregates={r[0]:r[1:] for r in rows}
        for obj in objects:
            row=aggregates.get(obj.id,(0,0,0,None,0,0));last=row[3];items.append({"id":obj.id,"name":obj.name,"territory_type":level,"code":getattr(obj,"dpa_code",getattr(obj,"code",None)),"completed_activities":row[0],"planned_activities":row[1],"cancelled_activities":row[2],"last_completed_activity_date":last,"days_since_last_activity":(period.date_to-last).days if last else None,"estimated_attendees":row[4],"distinct_activity_types":row[5],"need_mentions":0,"overdue_commitments":0,"valid_survey_responses":0,"survey_privacy_status":"SUPPRESSED","data_status":"AVAILABLE" if any(row[:3]) else "UNAVAILABLE"})
        reverse=sort_order=="desc";keymap={"name":"name","completed_activities":"completed_activities","estimated_attendees":"estimated_attendees","need_mentions":"need_mentions","overdue_commitments":"overdue_commitments","valid_survey_responses":"valid_survey_responses"};items.sort(key=lambda x:x[keymap.get(sort_by,"name")],reverse=reverse);total=len(items);items=items[(page-1)*page_size:page*page_size];return {"items":items,"page":page,"page_size":page_size,"total":total,"total_pages":ceil(total/page_size) if total else 0}

    def consolidated(self,campaign_id,user,filters):
        overview=self.overview(campaign_id,user,filters);return {"overview":overview,"top_needs":overview["top_needs"],"commitments":overview["commitment_summary"],"surveys":overview["survey_summary"],"coverage":overview["territorial_coverage"],"quality":overview["data_quality"]}
