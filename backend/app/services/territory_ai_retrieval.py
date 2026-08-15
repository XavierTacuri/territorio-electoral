from datetime import date
from decimal import Decimal
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.campaign import Campaign
from app.models.historical import DataSource,DemographicIndicator,DemographicObservation,ElectoralContest,ElectoralGeography,ElectoralProcess,ElectoralRollSnapshot,ElectoralRollSnapshotEntry,ElectoralTurnout,ParticipationProjectionResult,ParticipationProjectionRun
from app.models.operational import CitizenNeed,Commitment,TerritorialActivity
from app.models.public_intelligence import PublicIntelligenceItem,PublicSource
from app.models.survey_study import SurveyStudy,SurveyStudyTerritory
from app.models.territory import Parish
from app.models.user import User
from app.schemas.territory_ai import TerritoryAIEvidence,TerritoryAIQueryPlan,TerritoryAISourceKind
from app.services.campaign_access_service import CampaignAccessService
from app.services.survey_study_service import SurveyStudyService
from app.services.public_intelligence_service import PublicIntelligenceService

def serial(value):
    if isinstance(value,Decimal):return float(value)
    if isinstance(value,(date,)):return value.isoformat()
    if isinstance(value,UUID):return str(value)
    return value
class TerritoryAIEvidenceRetriever:
    def __init__(self,db:Session):self.db=db;self.access=CampaignAccessService(db)
    def _scope(self,campaign_id,user,territory):
        assignments=self.access.territorial_ids(campaign_id,user)
        allowed=None if assignments is None else {x.parish_id for x in assignments}
        if territory and territory.level=="PARISH":
            if allowed is not None and territory.id not in allowed:raise PermissionError("Territorio fuera del alcance autorizado")
            return {territory.id}
        return allowed
    def _e(self,campaign_id,kind,title,data,source,territory=None,**kw):
        return TerritoryAIEvidence(evidence_id="0",source_kind=kind,title=title,structured_data={k:serial(v) for k,v in data.items()},source_name=source,territory=territory,campaign_id=campaign_id,**kw)
    def retrieve(self,campaign_id:UUID,user:User,plan:TerritoryAIQueryPlan,question:str):
        parish_ids=self._scope(campaign_id,user,plan.territory);out=[]
        for kind in plan.source_kinds:
            method=getattr(self,f"_{kind.value.lower()}",None)
            if method:out.extend(method(campaign_id,user,plan,parish_ids,question))
        for index,item in enumerate(out,1):item.evidence_id=str(index)
        return out
    def _cne(self,cid,user,plan,pids,question):
        campaign=self.db.get(Campaign,cid)
        q=select(ElectoralRollSnapshotEntry,ElectoralRollSnapshot,DataSource,Parish).join(ElectoralRollSnapshot,ElectoralRollSnapshot.id==ElectoralRollSnapshotEntry.snapshot_id).join(DataSource,DataSource.id==ElectoralRollSnapshot.source_id).outerjoin(Parish,Parish.id==ElectoralRollSnapshotEntry.parish_id).where(ElectoralRollSnapshot.status.in_(["PUBLISHED","VALIDATED","IMPORTED"]),ElectoralRollSnapshotEntry.geography_level=="PARISH",ElectoralRollSnapshotEntry.canton_id==campaign.canton_id)
        if pids is not None:q=q.where(ElectoralRollSnapshotEntry.parish_id.in_(pids))
        rows=self.db.execute(q.order_by(ElectoralRollSnapshot.snapshot_date.desc())).all();latest={}
        for entry,snapshot,source,parish in rows:latest.setdefault(entry.parish_id,(entry,snapshot,source,parish))
        out=[]
        for entry,snapshot,source,parish in latest.values():
            territory=plan.territory if plan.territory and plan.territory.id==entry.parish_id else None
            out.append(self._e(cid,TerritoryAISourceKind.CNE,"Padrón electoral actual",{"registered_voters":entry.registered_voters,"male_voters":entry.male_voters,"female_voters":entry.female_voters,"electoral_zones":entry.electoral_zones,"juntas":entry.juntas,"snapshot":snapshot.name},source.institution,territory,source_url=source.official_url,record_date=snapshot.snapshot_date,data_cutoff=snapshot.snapshot_date,freshness="CURRENT",internal_path=f"/app/campaigns/{cid}/current-election",metadata={"series_break_caution":True}))
        hq=select(ElectoralTurnout,ElectoralGeography,ElectoralContest,ElectoralProcess,DataSource,Parish).join(ElectoralGeography,ElectoralGeography.id==ElectoralTurnout.electoral_geography_id).join(ElectoralContest,ElectoralContest.id==ElectoralTurnout.electoral_contest_id).join(ElectoralProcess,ElectoralProcess.id==ElectoralContest.electoral_process_id).join(DataSource,DataSource.id==ElectoralTurnout.source_id).outerjoin(Parish,Parish.id==ElectoralGeography.parish_id).where(ElectoralGeography.level=="PARISH",ElectoralGeography.canton_id==campaign.canton_id,ElectoralTurnout.is_active.is_(True))
        if pids is not None:hq=hq.where(ElectoralGeography.parish_id.in_(pids))
        for turnout,geo,contest,process,source,parish in self.db.execute(hq.order_by(ElectoralProcess.year.desc())).all()[:12]:
            rate=float(turnout.ballots_cast/turnout.registered_voters) if turnout.registered_voters else None
            territory=plan.territory if plan.territory and plan.territory.id==geo.parish_id else None
            out.append(self._e(cid,TerritoryAISourceKind.CNE,f"Participación histórica {process.year}",{"year":process.year,"registered_voters":turnout.registered_voters,"ballots_cast":turnout.ballots_cast,"turnout_rate":rate,"process":process.name},source.institution,territory,source_url=source.official_url,record_date=process.election_date,data_cutoff=process.election_date,freshness="HISTORICAL",internal_path=f"/app/campaigns/{cid}/current-election"))
        if plan.territory and plan.territory.level=="CANTON":
            aggregated=[];current=[e for e in out if e.structured_data.get("snapshot") is not None]
            if current:
                first=current[0];keys=("registered_voters","male_voters","female_voters","electoral_zones","juntas");data={key:sum(e.structured_data.get(key) or 0 for e in current) for key in keys};data["snapshot"]=first.structured_data.get("snapshot")
                aggregated.append(self._e(cid,TerritoryAISourceKind.CNE,first.title,data,first.source_name,plan.territory,source_url=first.source_url,record_date=first.record_date,data_cutoff=first.data_cutoff,freshness="CURRENT",internal_path=first.internal_path,metadata={"series_break_caution":True,"aggregation":"SUM_PARISHES"}))
            years={e.structured_data.get("year") for e in out if e.structured_data.get("year") is not None}
            for year in sorted(years,reverse=True):
                grouped=[e for e in out if e.structured_data.get("year")==year];registered=sum(e.structured_data.get("registered_voters") or 0 for e in grouped);ballots=sum(e.structured_data.get("ballots_cast") or 0 for e in grouped);first=grouped[0]
                aggregated.append(self._e(cid,TerritoryAISourceKind.CNE,first.title,{"year":year,"registered_voters":registered,"ballots_cast":ballots,"turnout_rate":ballots/registered if registered else None,"process":first.structured_data.get("process")},first.source_name,plan.territory,source_url=first.source_url,record_date=first.record_date,data_cutoff=first.data_cutoff,freshness="HISTORICAL",internal_path=first.internal_path,metadata={"aggregation":"SUM_PARISHES"}))
            return aggregated
        return out
    def _turnout_model(self,cid,user,plan,pids,question):
        q=select(ParticipationProjectionResult,ParticipationProjectionRun,Parish).join(ParticipationProjectionRun,ParticipationProjectionRun.id==ParticipationProjectionResult.run_id).join(Parish,Parish.id==ParticipationProjectionResult.parish_id).where(ParticipationProjectionRun.campaign_id==cid,ParticipationProjectionRun.model_code=="TURNOUT_HISTORICAL_WEIGHTED_V1")
        if pids is not None:q=q.where(ParticipationProjectionResult.parish_id.in_(pids))
        rows=self.db.execute(q.order_by(ParticipationProjectionRun.run_date.desc())).all();latest={}
        for result,run,parish in rows:latest.setdefault(result.parish_id,(result,run,parish))
        evidence=[self._e(cid,TerritoryAISourceKind.TURNOUT_MODEL,"Proyección de participación V1",{"registered_voters":r.registered_voters,"turnout_rate_low":r.turnout_rate_low,"turnout_rate_central":r.turnout_rate_central,"turnout_rate_high":r.turnout_rate_high,"expected_voters_low":r.expected_voters_low,"expected_voters_central":r.expected_voters_central,"expected_voters_high":r.expected_voters_high,"model_code":run.model_code,"model_version":run.model_version,"data_quality_status":r.data_quality_status,"explanation":r.explanation},"Territorio Electoral — modelo de participación",plan.territory if plan.territory and (plan.territory.level=="CANTON" or plan.territory.id==r.parish_id) else None,record_date=run.run_date,data_cutoff=run.run_date,freshness="MODEL_RUN",internal_path=f"/app/campaigns/{cid}/current-election",metadata={"methodology":"CENTRAL = 0.35 × rate_2019 + 0.65 × rate_2023 por parroquia; cantonal = suma de expected voters parroquiales","not_support_prediction":True}) for r,run,p in latest.values()]
        if plan.territory and plan.territory.level=="CANTON" and evidence:
            first=evidence[0];registered=sum(e.structured_data["registered_voters"] for e in evidence);low=sum(e.structured_data["expected_voters_low"] for e in evidence);central=sum(e.structured_data["expected_voters_central"] for e in evidence);high=sum(e.structured_data["expected_voters_high"] for e in evidence)
            data={"registered_voters":registered,"expected_voters_low":low,"expected_voters_central":central,"expected_voters_high":high,"model_code":first.structured_data["model_code"],"model_version":first.structured_data["model_version"],"turnout_rate_low":low/registered if registered else None,"turnout_rate_central":central/registered if registered else None,"turnout_rate_high":high/registered if registered else None,"data_quality_status":"AGGREGATED"}
            return [self._e(cid,TerritoryAISourceKind.TURNOUT_MODEL,first.title,data,first.source_name,plan.territory,record_date=first.record_date,data_cutoff=first.data_cutoff,freshness="MODEL_RUN",internal_path=first.internal_path,metadata={"methodology":"Cantonal = suma de expected voters parroquiales","not_support_prediction":True,"aggregation":"SUM_PARISHES"})]
        return evidence
    def _inec(self,cid,user,plan,pids,question):
        campaign=self.db.get(Campaign,cid);q=select(DemographicObservation,DemographicIndicator,DataSource).join(DemographicIndicator,DemographicIndicator.id==DemographicObservation.demographic_indicator_id).join(DataSource,DataSource.id==DemographicObservation.source_id).where(DemographicObservation.is_active.is_(True),DemographicIndicator.is_active.is_(True))
        if pids is not None:q=q.where(DemographicObservation.parish_id.in_(pids))
        else:q=q.where(DemographicObservation.canton_id==campaign.canton_id)
        rows=self.db.execute(q.order_by(DemographicObservation.reference_year.desc())).all()[:20]
        return [self._e(cid,TerritoryAISourceKind.INEC,indicator.name,{"indicator_code":indicator.code,"value":obs.value,"unit":indicator.unit,"reference_year":obs.reference_year,"category":indicator.category},source.institution,plan.territory if plan.territory and plan.territory.id==obs.parish_id else None,source_url=source.official_url,record_date=date(obs.reference_year,1,1),data_cutoff=source.reference_date,freshness="REFERENCE_YEAR",internal_path=f"/app/campaigns/{cid}/demographics",metadata={"population_not_electors":True}) for obs,indicator,source in rows]
    def _survey_study(self,cid,user,plan,pids,question):
        q=select(SurveyStudy).where(SurveyStudy.campaign_id==cid,SurveyStudy.status.in_(["PUBLISHED","VALIDATED"]))
        if plan.context_ids.get("study_id"):q=q.where(SurveyStudy.id==UUID(plan.context_ids["study_id"]))
        if pids is not None:q=q.join(SurveyStudyTerritory).where((SurveyStudyTerritory.parish_id.in_(pids))|(SurveyStudyTerritory.parish_id.is_(None)))
        studies=list(self.db.scalars(q.distinct().order_by(SurveyStudy.fieldwork_end_date.desc()).limit(8)));svc=SurveyStudyService(self.db);out=[]
        for study in studies:
            detail=svc.read(study,True);data={"study_type":study.study_type,"status":study.status,"sample_size":study.sample_size_total,"fieldwork_start":study.fieldwork_start_date,"fieldwork_end":study.fieldwork_end_date,"methodology":study.sampling_method,"collection_method":study.collection_method,"pollster":study.pollster_name,"results":[{"territory_id":str(r.study_territory_id),"option":r.option_label,"observed_percentage":float(r.percentage)} for r in detail.results]}
            warning="EXIT POLL — NO OFICIAL CNE" if study.study_type=="EXIT_POLL" else None
            out.append(self._e(cid,TerritoryAISourceKind.SURVEY_STUDY,study.name,data,study.pollster_name or "Estudio agregado",plan.territory,source_url=study.source_url,record_date=study.publication_date or study.fieldwork_end_date,data_cutoff=study.fieldwork_end_date,freshness="FIELDWORK_DATE",internal_path=f"/app/campaigns/{cid}/survey-studies/{study.id}",metadata={"exit_poll_warning":warning,"percentage_label":"porcentaje observado","methodology_completeness":detail.methodology_completeness}))
        return out
    def _operational(self,model,kind,cid,plan,pids,title_field="title"):
        q=select(model).where(model.campaign_id==cid,model.is_active.is_(True))
        context_key={TerritoryAISourceKind.TERRITORIAL_ACTIVITY:"activity_id",TerritoryAISourceKind.CITIZEN_NEED:"need_id",TerritoryAISourceKind.COMMITMENT:"commitment_id"}[kind]
        if plan.context_ids.get(context_key):q=q.where(model.id==UUID(plan.context_ids[context_key]))
        if pids is not None:q=q.where(model.parish_id.in_(pids))
        rows=list(self.db.scalars(q.order_by(model.updated_at.desc()).limit(12)));out=[]
        for x in rows:
            keys=["id","title","status","approval_status","priority","urgency","activity_date","due_date","mentions_count"]
            data={k:serial(getattr(x,k)) for k in keys if hasattr(x,k)}
            out.append(self._e(cid,kind,getattr(x,title_field),data,"Territorio Electoral",plan.territory if plan.territory and plan.territory.id==x.parish_id else None,record_date=getattr(x,"activity_date",None) or getattr(x,"reported_date",None),freshness="INTERNAL",internal_path=f"/app/campaigns/{cid}/"+({TerritoryAISourceKind.TERRITORIAL_ACTIVITY:"activities",TerritoryAISourceKind.CITIZEN_NEED:"needs",TerritoryAISourceKind.COMMITMENT:"commitments"}[kind])+f"/{x.id}"))
        return out
    def _territorial_activity(self,cid,user,plan,pids,question):return self._operational(TerritorialActivity,TerritoryAISourceKind.TERRITORIAL_ACTIVITY,cid,plan,pids)
    def _citizen_need(self,cid,user,plan,pids,question):return self._operational(CitizenNeed,TerritoryAISourceKind.CITIZEN_NEED,cid,plan,pids)
    def _commitment(self,cid,user,plan,pids,question):return self._operational(Commitment,TerritoryAISourceKind.COMMITMENT,cid,plan,pids)
    def _public_intelligence(self,cid,user,plan,pids,question):
        service=PublicIntelligenceService(self.db)
        if plan.context_ids.get("public_item_id"):items=[service.detail(cid,UUID(plan.context_ids["public_item_id"]),user)]
        else:items=service.items(cid,user,1,8,parish_id=plan.territory.id if plan.territory else None).items
        return [self._e(cid,TerritoryAISourceKind.PUBLIC_INTELLIGENCE,item.title,{"publisher":item.publisher,"official":item.official,"item_type":item.item_type,"topics":[t.name for t in item.topics]},item.publisher,plan.territory,excerpt=(item.summary or item.content_excerpt or "")[:1200],source_url=item.url,record_date=item.published_at,data_cutoff=item.fetched_at,freshness="FETCHED",internal_path=f"/app/campaigns/{cid}/public-intelligence/{item.id}",metadata={"official":item.official},trust_level="UNTRUSTED_EVIDENCE") for item in items]
    def _system_metadata(self,cid,user,plan,pids,question):
        return [self._e(cid,TerritoryAISourceKind.SYSTEM_METADATA,"Metodología de participación V1",{"model_code":"TURNOUT_HISTORICAL_WEIGHTED_V1","model_version":"1.0","central_formula":"0.35 × rate_2019 + 0.65 × rate_2023","cantonal_aggregation":"suma de expected voters parroquiales","series_break":"REGISTRATION_SERIES_BREAK requiere cautela: una disminución no implica automáticamente despoblación"},"Territorio Electoral",plan.territory,freshness="VERSIONED",metadata={"read_only":True})]
