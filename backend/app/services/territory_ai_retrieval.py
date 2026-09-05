from datetime import date,timedelta
from decimal import Decimal
from uuid import UUID
from sqlalchemy import func,or_,select
from sqlalchemy.orm import Session
from app.models.alerts import AlertRule
from app.models.campaign import Campaign
from app.models.election_day import ElectionDayAssignment,ElectionDayDocument,ElectionDayIncident,ElectionDayOperation,ElectoralBoard,PollingPlace
from app.models.historical import DataSource,DemographicIndicator,DemographicObservation,ElectoralContest,ElectoralGeography,ElectoralMilestone,ElectoralProcess,ElectoralRollSnapshot,ElectoralRollSnapshotEntry,ElectoralTurnout,ParticipationProjectionResult,ParticipationProjectionRun
from app.models.operational import ActivityEvidence,CitizenNeed,Commitment,TerritorialActivity
from app.models.public_intelligence import PublicIntelligenceItem,PublicSource
from app.models.survey_study import SurveyStudy,SurveyStudyTerritory
from app.models.territory import Parish
from app.models.user import User
from app.schemas.territory_ai import TerritoryAIEvidence,TerritoryAIQueryPlan,TerritoryAISourceKind
from app.services.alert_service import AlertService
from app.services.calendar_service import CalendarService
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
        metadata=kw.get("metadata") or {}
        if metadata.get("demo"):evidence_class="DEMO"
        elif kind in {TerritoryAISourceKind.CNE,TerritoryAISourceKind.INEC}:evidence_class="OFFICIAL"
        elif kind==TerritoryAISourceKind.PUBLIC_INTELLIGENCE:evidence_class="PUBLIC"
        elif kind==TerritoryAISourceKind.SURVEY_STUDY and metadata.get("official"):evidence_class="OFFICIAL"
        else:evidence_class="CAMPAIGN"
        return TerritoryAIEvidence(evidence_id="0",source_kind=kind,evidence_class=evidence_class,title=title,structured_data={k:serial(v) for k,v in data.items()},source_name=source,territory=territory,campaign_id=campaign_id,**kw)
    def retrieve(self,campaign_id:UUID,user:User,plan:TerritoryAIQueryPlan,question:str):
        parish_ids=self._scope(campaign_id,user,plan.territory);out=[]
        for kind in plan.source_kinds:
            method=getattr(self,f"_{kind.value.lower()}",None)
            if method:out.extend(method(campaign_id,user,plan,parish_ids,question))
        for index,item in enumerate(out,1):item.evidence_id=str(index)
        return out
    @staticmethod
    def _subject(question):
        normalized=question.casefold()
        for words,subject in ((('vialidad','vial','carretera','calle'),'vial'),(('agua','saneamiento'),'agua'),(('alumbrado','iluminación'),'alumbrado'),(('transporte','movilidad'),'transporte')):
            if any(word in normalized for word in words):return subject
        return None
    def _cne(self,cid,user,plan,pids,question):
        campaign=self.db.get(Campaign,cid)
        run=self.db.scalar(select(ParticipationProjectionRun).where(ParticipationProjectionRun.campaign_id==cid).order_by(ParticipationProjectionRun.created_at.desc()))
        q=select(ElectoralRollSnapshotEntry,ElectoralRollSnapshot,DataSource,Parish).join(ElectoralRollSnapshot,ElectoralRollSnapshot.id==ElectoralRollSnapshotEntry.snapshot_id).join(DataSource,DataSource.id==ElectoralRollSnapshot.source_id).outerjoin(Parish,Parish.id==ElectoralRollSnapshotEntry.parish_id).where(ElectoralRollSnapshot.status.in_(["PUBLISHED","VALIDATED","IMPORTED"]),ElectoralRollSnapshotEntry.geography_level=="PARISH",ElectoralRollSnapshotEntry.canton_id==campaign.canton_id)
        if run:q=q.where(ElectoralRollSnapshotEntry.snapshot_id==run.snapshot_id)
        if pids is not None:q=q.where(ElectoralRollSnapshotEntry.parish_id.in_(pids))
        rows=self.db.execute(q.order_by(ElectoralRollSnapshot.snapshot_date.desc())).all();latest={}
        for entry,snapshot,source,parish in rows:latest.setdefault(entry.parish_id,(entry,snapshot,source,parish))
        out=[]
        for entry,snapshot,source,parish in latest.values():
            territory=plan.territory if plan.territory and plan.territory.id==entry.parish_id else None
            out.append(self._e(cid,TerritoryAISourceKind.CNE,"Padrón electoral actual",{"registered_voters":entry.registered_voters,"male_voters":entry.male_voters,"female_voters":entry.female_voters,"electoral_zones":entry.electoral_zones,"juntas":entry.juntas,"snapshot":snapshot.name},source.institution,territory,source_url=source.official_url,record_date=snapshot.snapshot_date,data_cutoff=snapshot.snapshot_date,freshness="CURRENT",internal_path=f"/app/campaigns/{cid}/current-election",metadata={"series_break_caution":True},data_source_id=source.id))
        hq=select(ElectoralTurnout,ElectoralGeography,ElectoralContest,ElectoralProcess,DataSource,Parish).join(ElectoralGeography,ElectoralGeography.id==ElectoralTurnout.electoral_geography_id).join(ElectoralContest,ElectoralContest.id==ElectoralTurnout.electoral_contest_id).join(ElectoralProcess,ElectoralProcess.id==ElectoralContest.electoral_process_id).join(DataSource,DataSource.id==ElectoralTurnout.source_id).outerjoin(Parish,Parish.id==ElectoralGeography.parish_id).where(ElectoralGeography.level=="PARISH",ElectoralGeography.canton_id==campaign.canton_id,ElectoralTurnout.is_active.is_(True))
        if pids is not None:hq=hq.where(ElectoralGeography.parish_id.in_(pids))
        for turnout,geo,contest,process,source,parish in self.db.execute(hq.order_by(ElectoralProcess.year.desc())).all():
            rate=float(turnout.ballots_cast/turnout.registered_voters) if turnout.registered_voters else None
            territory=plan.territory if plan.territory and plan.territory.id==geo.parish_id else None
            out.append(self._e(cid,TerritoryAISourceKind.CNE,f"Participación histórica {process.year}",{"year":process.year,"registered_voters":turnout.registered_voters,"ballots_cast":turnout.ballots_cast,"turnout_rate":rate,"process":process.name},source.institution,territory,source_url=source.official_url,record_date=process.election_date,data_cutoff=process.election_date,freshness="HISTORICAL",internal_path=f"/app/campaigns/{cid}/current-election",data_source_id=source.id,import_job_id=turnout.import_job_id))
        if plan.territory and plan.territory.level=="CANTON":
            aggregated=[];current=[e for e in out if e.structured_data.get("snapshot") is not None]
            if current:
                first=current[0];keys=("registered_voters","male_voters","female_voters","electoral_zones","juntas");data={key:sum(e.structured_data.get(key) or 0 for e in current) for key in keys};data["snapshot"]=first.structured_data.get("snapshot")
                aggregated.append(self._e(cid,TerritoryAISourceKind.CNE,first.title,data,first.source_name,plan.territory,source_url=first.source_url,record_date=first.record_date,data_cutoff=first.data_cutoff,freshness="CURRENT",internal_path=first.internal_path,metadata={"series_break_caution":True,"aggregation":"SUM_PARISHES"},data_source_id=first.data_source_id))
            years={e.structured_data.get("year") for e in out if e.structured_data.get("year") is not None}
            for year in sorted(years,reverse=True):
                grouped=[e for e in out if e.structured_data.get("year")==year];registered=sum(e.structured_data.get("registered_voters") or 0 for e in grouped);ballots=sum(e.structured_data.get("ballots_cast") or 0 for e in grouped);first=grouped[0]
                aggregated.append(self._e(cid,TerritoryAISourceKind.CNE,first.title,{"year":year,"registered_voters":registered,"ballots_cast":ballots,"turnout_rate":ballots/registered if registered else None,"process":first.structured_data.get("process")},first.source_name,plan.territory,source_url=first.source_url,record_date=first.record_date,data_cutoff=first.data_cutoff,freshness="HISTORICAL",internal_path=first.internal_path,metadata={"aggregation":"SUM_PARISHES"},data_source_id=first.data_source_id))
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
        campaign=self.db.get(Campaign,cid);q=select(DemographicObservation,DemographicIndicator,DataSource).join(DemographicIndicator,DemographicIndicator.id==DemographicObservation.demographic_indicator_id).join(DataSource,DataSource.id==DemographicObservation.source_id).where(DemographicObservation.is_active.is_(True),DemographicObservation.is_official.is_(True),DemographicIndicator.is_active.is_(True))
        if pids is not None:q=q.where(DemographicObservation.parish_id.in_(pids))
        else:q=q.where(DemographicObservation.canton_id==campaign.canton_id)
        rows=self.db.execute(q.order_by(DemographicObservation.reference_year.desc())).all()
        # Panorama Electoral derives population from official parish POP_TOTAL
        # rows. Keep those rows ahead of secondary indicators so the IA facts
        # use the same persisted inputs instead of an unrelated canton record.
        rows.sort(key=lambda row:(row[1].code!="POP_TOTAL",-(row[0].reference_year or 0),row[0].parish_id is None))
        rows=rows[:40]
        return [self._e(cid,TerritoryAISourceKind.INEC,indicator.name,{"indicator_code":indicator.code,"value":obs.value,"unit":indicator.unit,"reference_year":obs.reference_year,"category":indicator.category,"geography_level":obs.geography_level,"canton_id":obs.canton_id,"parish_id":obs.parish_id},source.institution,plan.territory if plan.territory and plan.territory.id==obs.parish_id else None,source_url=source.official_url,record_date=date(obs.reference_year,1,1),data_cutoff=source.reference_date,freshness="REFERENCE_YEAR",internal_path=f"/app/campaigns/{cid}/demographics",metadata={"population_not_electors":True},data_source_id=source.id,import_job_id=obs.import_job_id) for obs,indicator,source in rows]
    def _survey_study(self,cid,user,plan,pids,question):
        q=select(SurveyStudy).where(SurveyStudy.campaign_id==cid,SurveyStudy.status=="PUBLISHED")
        if plan.context_ids.get("study_id"):q=q.where(SurveyStudy.id==UUID(plan.context_ids["study_id"]))
        if pids is not None:q=q.join(SurveyStudyTerritory).where((SurveyStudyTerritory.parish_id.in_(pids))|(SurveyStudyTerritory.parish_id.is_(None)))
        studies=list(self.db.scalars(q.distinct().order_by(SurveyStudy.fieldwork_end_date.desc()).limit(8)));svc=SurveyStudyService(self.db);out=[]
        for study in studies:
            detail=svc.read(study,True);option_map={o.id:o for o in detail.options};territory_map={t.id:t for t in detail.territories};data={"study_id":str(study.id),"name":study.name,"study_type":study.study_type,"status":study.status,"sample_size":study.sample_size_total,"fieldwork_start":study.fieldwork_start_date,"fieldwork_end":study.fieldwork_end_date,"methodology":study.sampling_method,"collection_method":study.collection_method,"margin_of_error":float(study.margin_of_error) if study.margin_of_error is not None else None,"confidence_level":float(study.confidence_level) if study.confidence_level is not None else None,"coverage":study.geography_level,"pollster":study.pollster_name,"limitations":study.notes,"source":{"name":study.source_name,"url":study.source_url,"document":study.source_document,"publication_date":study.publication_date},"results":[{"question_code":option_map[r.option_id].question_code,"question":option_map[r.option_id].question_text,"question_type":option_map[r.option_id].question_type,"territory":territory_map[r.study_territory_id].parish_name or "Cantonal","option":r.option_label,"observed_percentage":float(r.percentage),"base_n":r.response_count} for r in detail.results]}
            warning="Este estudio no sustituye los resultados oficiales del proceso electoral." if study.study_type in {"CNE_EXIT_POLL","EXIT_POLL"} else None
            is_demo=study.code.startswith("DEMO_") or study.name.startswith("[DEMO]")
            data["demo"]=is_demo;out.append(self._e(cid,TerritoryAISourceKind.SURVEY_STUDY,study.name,data,study.pollster_name or "Encuesta",plan.territory,source_url=study.source_url,record_date=study.publication_date or study.fieldwork_end_date,data_cutoff=study.fieldwork_end_date,freshness="FIELDWORK_DATE",internal_path=f"/app/campaigns/{cid}/survey-studies/{study.id}",metadata={"source_kind_label":"Encuesta","fieldwork_start":str(study.fieldwork_start_date),"fieldwork_end":str(study.fieldwork_end_date),"sample_size":study.sample_size_total,"methodology":study.sampling_method,"coverage":study.geography_level,"exit_poll_warning":warning,"percentage_label":"porcentaje observado en el estudio","methodology_completeness":detail.methodology_completeness,"demo":is_demo,"official":False,"demo_disclaimer":"DATOS SIMULADOS PARA DEMOSTRACIÓN." if is_demo else None}))
        return out
    def _operational(self,model,kind,cid,plan,pids,question,title_field="title"):
        q=select(model).where(model.campaign_id==cid,model.is_active.is_(True))
        context_key={TerritoryAISourceKind.TERRITORIAL_ACTIVITY:"activity_id",TerritoryAISourceKind.CITIZEN_NEED:"need_id",TerritoryAISourceKind.COMMITMENT:"commitment_id"}[kind]
        if plan.context_ids.get(context_key):q=q.where(model.id==UUID(plan.context_ids[context_key]))
        if pids is not None:q=q.where(model.parish_id.in_(pids))
        subject=self._subject(question)
        if subject and hasattr(model,"description"):q=q.where(or_(model.title.ilike(f"%{subject}%"),model.description.ilike(f"%{subject}%")))
        rows=list(self.db.scalars(q.order_by(model.updated_at.desc()).limit(12)));out=[]
        for x in rows:
            keys=["id","title","status","approval_status","activity_date","due_date","mentions_count"]
            data={k:serial(getattr(x,k)) for k in keys if hasattr(x,k)}
            parish=self.db.get(Parish,x.parish_id)
            data["parish_id"]=x.parish_id;data["parish_name"]=parish.name if parish else None
            is_demo=getattr(x,title_field).startswith("[DEMO]")
            if kind==TerritoryAISourceKind.CITIZEN_NEED:
                data["semantic_definition"]="Tema registrado en territorio; no es una promesa ni una propuesta de gobierno."
                data["description"]=x.description;data["evidence_notes"]=x.evidence_notes
                activity=self.db.get(TerritorialActivity,x.activity_id) if x.activity_id else None
                data["origin_activity_id"]=serial(x.activity_id) if x.activity_id else None;data["origin_activity_title"]=activity.title if activity else None
            elif kind==TerritoryAISourceKind.COMMITMENT:
                data["semantic_definition"]="Seguimiento operativo interno del equipo de campaÃ±a; no es un compromiso gubernamental."
                data["follow_up_date"]=data.pop("due_date",None)
            out.append(self._e(cid,kind,getattr(x,title_field),data,"Territorio Electoral",plan.territory if plan.territory and plan.territory.id==x.parish_id else None,record_date=getattr(x,"activity_date",None) or getattr(x,"reported_date",None),freshness="INTERNAL",internal_path=f"/app/campaigns/{cid}/"+({TerritoryAISourceKind.TERRITORIAL_ACTIVITY:"activities",TerritoryAISourceKind.CITIZEN_NEED:"needs",TerritoryAISourceKind.COMMITMENT:"commitments"}[kind])+f"/{x.id}",metadata={"demo":is_demo,"official":False if is_demo else None,"demo_disclaimer":"DATOS SIMULADOS PARA DEMOSTRACIÓN." if is_demo else None}))
        return out
    def _territorial_activity(self,cid,user,plan,pids,question):return self._operational(TerritorialActivity,TerritoryAISourceKind.TERRITORIAL_ACTIVITY,cid,plan,pids,question)
    def _citizen_need(self,cid,user,plan,pids,question):return self._operational(CitizenNeed,TerritoryAISourceKind.CITIZEN_NEED,cid,plan,pids,question)
    def _commitment(self,cid,user,plan,pids,question):return self._operational(Commitment,TerritoryAISourceKind.COMMITMENT,cid,plan,pids,question)
    def _activity_evidence(self,cid,user,plan,pids,question):
        q=select(ActivityEvidence,TerritorialActivity).join(TerritorialActivity,TerritorialActivity.id==ActivityEvidence.activity_id).where(TerritorialActivity.campaign_id==cid,TerritorialActivity.is_active.is_(True),ActivityEvidence.is_active.is_(True))
        if plan.context_ids.get("activity_id"):q=q.where(ActivityEvidence.activity_id==UUID(plan.context_ids["activity_id"]))
        if pids is not None:q=q.where(TerritorialActivity.parish_id.in_(pids))
        subject=self._subject(question)
        if subject:q=q.where(or_(ActivityEvidence.title.ilike(f"%{subject}%"),ActivityEvidence.description.ilike(f"%{subject}%"),TerritorialActivity.title.ilike(f"%{subject}%"),TerritorialActivity.description.ilike(f"%{subject}%")))
        rows=list(self.db.execute(q.order_by(ActivityEvidence.created_at.desc()).limit(12)).all());out=[]
        for evidence,activity in rows:
            parish=self.db.get(Parish,activity.parish_id);is_demo=activity.title.startswith("[DEMO]")
            data={"evidence_type":evidence.evidence_type,"evidence_date":serial(evidence.evidence_date),"activity_id":serial(activity.id),"activity_title":activity.title,"parish_id":activity.parish_id,"parish_name":parish.name if parish else None,"has_file":evidence.storage_key is not None}
            out.append(self._e(cid,TerritoryAISourceKind.ACTIVITY_EVIDENCE,evidence.title,data,"Territorio Electoral",plan.territory if plan.territory and plan.territory.id==activity.parish_id else None,excerpt=evidence.description,source_url=evidence.url,record_date=evidence.evidence_date,freshness="INTERNAL",internal_path=f"/app/campaigns/{cid}/activities/{activity.id}",metadata={"demo":is_demo,"official":False if is_demo else None,"demo_disclaimer":"DATOS SIMULADOS PARA DEMOSTRACIÓN." if is_demo else None}))
        return out
    def _public_intelligence(self,cid,user,plan,pids,question):
        service=PublicIntelligenceService(self.db)
        if plan.context_ids.get("public_item_id"):items=[service.detail(cid,UUID(plan.context_ids["public_item_id"]),user)]
        else:items=service.items(cid,user,1,8,search=self._subject(question),parish_id=plan.territory.id if plan.territory and plan.territory.level=="PARISH" else None).items
        return [self._e(cid,TerritoryAISourceKind.PUBLIC_INTELLIGENCE,item.title,{"publisher":item.publisher,"official":item.official,"item_type":item.item_type,"topics":[t.get("name") if isinstance(t, dict) else t.name for t in item.topics]},item.publisher,plan.territory,excerpt=(item.summary or item.content_excerpt or "")[:1200],source_url=item.url,record_date=item.published_at,data_cutoff=item.fetched_at,freshness="FETCHED",internal_path=f"/app/campaigns/{cid}/public-intelligence/{item.id}",metadata={"official":item.official,"demo":item.title.startswith("[DEMO]"),"demo_disclaimer":"DATOS SIMULADOS PARA DEMOSTRACIÓN." if item.title.startswith("[DEMO]") else None},trust_level="UNTRUSTED_EVIDENCE") for item in items]
    def _campaign_schedule(self,cid,user,plan,pids,question):
        # El Calendario de campaña (CalendarService) solo compone actividades de
        # campaña (retiro de producto). Los hitos oficiales ya no aparecen ahí,
        # pero siguen disponibles para Territorio IA como evidencia factual
        # (Data Hub) — se agregan aquí, no en el calendario.
        today=date.today();events=CalendarService(self.db).events(cid,user,today,today+timedelta(days=30))
        out=[]
        for e in events:
            territory=plan.territory if plan.territory and plan.territory.id==e.parish_id else None
            out.append(self._e(cid,TerritoryAISourceKind.CAMPAIGN_SCHEDULE,e.title,{"event_type":e.event_type,"status":e.status,"is_official":e.is_official,"parish_id":e.parish_id,"parish_name":e.parish_name},e.source_name or "Territorio Electoral",territory,source_url=e.source_url,record_date=e.starts_at,data_cutoff=e.starts_at,freshness="CURRENT",internal_path=e.deep_link,metadata={"official":e.is_official}))
        out.extend(self._official_milestones(cid,plan,today,today+timedelta(days=30)))
        return out
    def _official_milestones(self,cid,plan,date_from,date_to):
        campaign=self.db.get(Campaign,cid)
        processes=select(ElectoralContest.electoral_process_id).where(ElectoralContest.canton_id==campaign.canton_id,ElectoralContest.office_type==campaign.office_type)
        q=select(ElectoralMilestone).where(ElectoralMilestone.electoral_process_id.in_(processes),ElectoralMilestone.status=="ACTIVE",func.date(ElectoralMilestone.starts_at).between(date_from,date_to))
        out=[]
        for m in self.db.scalars(q):
            source=self.db.get(DataSource,m.source_id)
            out.append(self._e(cid,TerritoryAISourceKind.CAMPAIGN_SCHEDULE,m.title,{"event_type":"OFFICIAL_ELECTORAL_MILESTONE","is_official":True},source.institution if source else "Territorio Electoral",plan.territory,source_url=m.source_url or (source.official_url if source else None),record_date=m.starts_at,data_cutoff=m.starts_at,freshness="CURRENT",metadata={"official":True}))
        return out
    def _operational_alert(self,cid,user,plan,pids,question):
        items,_=AlertService(self.db).list(cid,user,1,10,status="OPEN");out=[]
        for a in items:
            rule=self.db.get(AlertRule,a.alert_rule_id);territory=plan.territory if plan.territory and plan.territory.id==a.parish_id else None
            # a.evidence ya es JSON-safe (persistido tal cual en la columna JSON de
            # la alerta): exponerlo aquí permite que Territorio IA describa hechos
            # concretos (p. ej. valores de una comparación de encuestas) en lugar
            # de solo el título/mensaje genérico de la regla.
            out.append(self._e(cid,TerritoryAISourceKind.OPERATIONAL_ALERT,a.title,{"severity":a.severity,"status":a.status,"module":rule.module if rule else None,"message":a.message,"evidence":a.evidence},"Territorio Electoral",territory,record_date=a.detected_date,freshness="CURRENT",internal_path=f"/app/campaigns/{cid}/alerts",metadata={"severity":a.severity}))
        return out
    def _election_day(self,cid,user,plan,pids,question):
        # Facts operativos únicamente (§57-59): cobertura, presencia,
        # incidencias y documentación — nunca resultados/ganador/apoyo.
        campaign=self.db.get(Campaign,cid)
        op=self.db.scalar(select(ElectionDayOperation).where(ElectionDayOperation.campaign_id==cid).order_by(ElectionDayOperation.created_at.desc()))
        if not op:return []
        places=list(self.db.scalars(select(PollingPlace).where(PollingPlace.electoral_process_id==op.electoral_process_id,PollingPlace.canton_id==campaign.canton_id,PollingPlace.is_active.is_(True))))
        place_ids=[p.id for p in places];place_by_id={p.id:p for p in places}
        boards=list(self.db.scalars(select(ElectoralBoard).where(ElectoralBoard.polling_place_id.in_(place_ids),ElectoralBoard.is_active.is_(True)))) if place_ids else []
        board_ids={b.id for b in boards}
        assignments=list(self.db.scalars(select(ElectionDayAssignment).where(ElectionDayAssignment.operation_id==op.id,ElectionDayAssignment.status!="REPLACED")))
        covered_places={a.polling_place_id for a in assignments}&set(place_ids)
        covered_boards={a.board_id for a in assignments if a.board_id}&board_ids
        confirmed=sum(1 for a in assignments if a.status in {"CONFIRMED","CHECKED_IN"})
        checked_in=sum(1 for a in assignments if a.status=="CHECKED_IN")
        documented_boards={d.board_id for d in self.db.scalars(select(ElectionDayDocument).where(ElectionDayDocument.operation_id==op.id,ElectionDayDocument.is_active.is_(True),ElectionDayDocument.document_type=="ACTA_COPY")) if d.board_id}&board_ids
        out=[self._e(cid,TerritoryAISourceKind.ELECTION_DAY,"Estado operativo de la jornada",{"status":op.status,"total_polling_places":len(places),"covered_polling_places":len(covered_places),"total_boards":len(boards),"covered_boards":len(covered_boards),"personnel_confirmed":confirmed,"personnel_checked_in":checked_in,"boards_with_document":len(documented_boards),"boards_missing_document":len(board_ids-documented_boards)},"Territorio Electoral",freshness="CURRENT",internal_path=f"/app/campaigns/{cid}/election-day")]
        for i in self.db.scalars(select(ElectionDayIncident).where(ElectionDayIncident.operation_id==op.id,ElectionDayIncident.status!="RESOLVED",ElectionDayIncident.is_active.is_(True)).order_by(ElectionDayIncident.reported_at.desc()).limit(15)):
            place=place_by_id.get(i.polling_place_id)
            out.append(self._e(cid,TerritoryAISourceKind.ELECTION_DAY,f"Incidencia — {place.name if place else 'recinto'}",{"category":i.category,"status":i.status,"polling_place_name":place.name if place else None},"Territorio Electoral",freshness="CURRENT",internal_path=f"/app/campaigns/{cid}/election-day",excerpt=(i.description or "")[:300]))
        for b in boards:
            if b.id not in documented_boards:
                place=place_by_id.get(b.polling_place_id)
                out.append(self._e(cid,TerritoryAISourceKind.ELECTION_DAY,f"Documentación pendiente — Junta {b.official_code}",{"board_code":b.official_code,"polling_place_name":place.name if place else None,"document_status":"MISSING"},"Territorio Electoral",freshness="CURRENT",internal_path=f"/app/campaigns/{cid}/election-day"))
        return out
    def _system_metadata(self,cid,user,plan,pids,question):
        return [self._e(cid,TerritoryAISourceKind.SYSTEM_METADATA,"Metodología de participación V1",{"model_code":"TURNOUT_HISTORICAL_WEIGHTED_V1","model_version":"1.0","central_formula":"0.35 × rate_2019 + 0.65 × rate_2023","cantonal_aggregation":"suma de expected voters parroquiales","series_break":"REGISTRATION_SERIES_BREAK requiere cautela: una disminución no implica automáticamente despoblación"},"Territorio Electoral",plan.territory,freshness="VERSIONED",metadata={"read_only":True})]
