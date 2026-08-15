from app.schemas.dashboard import DashboardFilters
from app.services.dashboard_service import DashboardService
from app.models.historical import ParticipationProjectionRun, ParticipationProjectionResult, ElectoralRollSnapshot, ElectoralProcess, DataSource, DemographicObservation
from app.models.campaign import Campaign
from app.models.territory import Canton
from sqlalchemy import select

class ReportDataService:
    def __init__(self,db):self.dashboard=DashboardService(db)
    def collect(self,campaign_id,user,report_type,request,template_code=None):
        if template_code == "PUBLIC_INTELLIGENCE_REPORT":
            from app.services.public_intelligence_service import PublicIntelligenceService
            service=PublicIntelligenceService(self.dashboard.db)
            return {"public_intelligence":{"summary":service.summary(campaign_id,user).model_dump(mode="json"),"sources":[{"name":x.name,"publisher":x.publisher,"source_type":x.source_type,"official":x.official,"base_url":x.base_url,"last_success_at":x.last_success_at} for x in service.sources(campaign_id,user)],"publications":[x.model_dump(mode="json") for x in service.items(campaign_id,user,1,500,date_from=request.date_from,date_to=request.date_to).items],"methodology":"Monitoreo descriptivo con provenance; no mide favorabilidad, persuasión ni impacto electoral."}}
        if template_code == "SURVEY_STUDY_REPORT":
            from app.services.survey_study_service import SurveyStudyService
            if len(request.survey_ids)!=1: raise ValueError("El informe requiere exactamente un estudio")
            service=SurveyStudyService(self.dashboard.db);study=service.get(request.survey_ids[0],user)
            if study.campaign_id!=campaign_id:raise ValueError("Estudio fuera de la campaña")
            return {"survey_study":service.read(study,True).model_dump(mode="python")}
        if template_code in {"CURRENT_ELECTION_EXECUTIVE", "PARISH_TERRITORIAL_PROFILE"}:
            from app.api.routes.participation import current_election_analysis
            analysis = current_election_analysis(campaign_id,user,self.dashboard.db)
            campaign = self.dashboard.db.get(Campaign, campaign_id)
            run = self.dashboard.db.scalar(select(ParticipationProjectionRun).where(ParticipationProjectionRun.campaign_id == campaign_id).order_by(ParticipationProjectionRun.created_at.desc()))
            snapshot = self.dashboard.db.get(ElectoralRollSnapshot, run.snapshot_id) if run else None
            process = self.dashboard.db.get(ElectoralProcess, run.electoral_process_id) if run else None
            source_ids = set(run.historical_process_ids if run else [])
            historical_processes = list(self.dashboard.db.scalars(select(ElectoralProcess).where(ElectoralProcess.id.in_(source_ids)))) if source_ids else []
            ids = {p.source_id for p in historical_processes}
            if snapshot: ids.add(snapshot.source_id)
            ids.update(self.dashboard.db.scalars(select(DemographicObservation.source_id).where(DemographicObservation.is_official.is_(True)).distinct()))
            sources = list(self.dashboard.db.scalars(select(DataSource).where(DataSource.id.in_(ids)))) if ids else []
            analysis["report_context"] = {
                "campaign_name": campaign.name if campaign else None,
                "canton_name": self.dashboard.db.get(Canton, campaign.canton_id).name if campaign else None,
                "election_name": campaign.election_name if campaign else (process.name if process else None),
                "sources": [{"institution": s.institution, "dataset": s.dataset_name, "reference_date": s.reference_date, "reference_year": s.reference_year, "publication_date": s.publication_date, "official_url": s.official_url} for s in sources],
            }
            if template_code == "PARISH_TERRITORIAL_PROFILE":
                if request.parish_id is None: raise ValueError("La ficha territorial requiere parroquia")
                parish = next((p for p in analysis["parishes"] if p["parish_id"] == request.parish_id), None)
                if parish is None: raise ValueError("Parroquia sin análisis disponible")
                analysis["parishes"] = [parish]
                analysis["snapshot"].update({"registered_voters":parish["registered_voters_current"],"male_voters":parish["male_voters"],"female_voters":parish["female_voters"],"juntas":parish["juntas"]})
                analysis["historical"] = {year: parish.get(f"historical_{year}") or {} for year in ("2019","2023")}
                projection=parish.get("projection") or {};analysis["projection"].update({key:projection.get(key) for key in ("expected_voters_low","expected_voters_central","expected_voters_high")})
                analysis["report_context"]["parish_name"] = parish["name"];analysis["report_context"]["dpa_code"] = parish["dpa_code"]
            return {"current_election": analysis}
        filters=DashboardFilters(date_from=request.date_from,date_to=request.date_to,period=request.period,parish_id=request.parish_id,community_id=request.community_id,sector_id=request.sector_id,compare_previous_period=request.include_comparisons,survey_ids=request.survey_ids or None,electoral_process_ids=request.electoral_process_ids or None,demographic_indicator_codes=request.demographic_indicator_codes or None)
        overview=self.dashboard.overview(campaign_id,user,filters)
        data={"overview":overview}
        calls={"OPERATIONAL_ACTIVITY":"activity_trends","TERRITORIAL_COVERAGE":"territories","NEEDS":"needs","COMMITMENTS":"commitments","SURVEY_RESULTS":"surveys","ELECTORAL_HISTORY":"electoral_history","DEMOGRAPHIC_PROFILE":"demographics","DATA_QUALITY":"data_quality","GEOGRAPHIC_AVAILABILITY":"data_quality"}
        if report_type == "PARTICIPATION_PROJECTION":
            run=self.dashboard.db.scalar(select(ParticipationProjectionRun).where(ParticipationProjectionRun.campaign_id==campaign_id).order_by(ParticipationProjectionRun.created_at.desc()))
            if run:
                snapshot=self.dashboard.db.get(ElectoralRollSnapshot,run.snapshot_id)
                results=list(self.dashboard.db.scalars(select(ParticipationProjectionResult).where(ParticipationProjectionResult.run_id==run.id)))
                data["detail"]={"model_code":run.model_code,"model_version":run.model_version,"parameters":run.parameters,"snapshot_date":snapshot.snapshot_date.isoformat() if snapshot else None,"warning":"Estimación estadística de participación. No constituye pronóstico de resultados electorales ni intención de voto.","results":[{"parish_id":r.parish_id,"registered_voters":r.registered_voters,"turnout_rate_low":str(r.turnout_rate_low),"turnout_rate_central":str(r.turnout_rate_central),"turnout_rate_high":str(r.turnout_rate_high),"expected_voters_central":r.expected_voters_central,"quality":r.data_quality_status} for r in results]}
        method=calls.get(report_type)
        if method:
            fn=getattr(self.dashboard,method)
            if method=="activity_trends":data["detail"]=fn(campaign_id,user,filters,"DAY",False,None,None)
            elif method=="territories":data["detail"]=fn(campaign_id,user,filters,"PARISH",1,100,"name","asc")
            else:data["detail"]=fn(campaign_id,user,filters)
            if report_type == "ELECTORAL_HISTORY":
                run=self.dashboard.db.scalar(select(ParticipationProjectionRun).where(ParticipationProjectionRun.campaign_id==campaign_id).order_by(ParticipationProjectionRun.created_at.desc()))
                if run:
                    snapshot=self.dashboard.db.get(ElectoralRollSnapshot,run.snapshot_id)
                    results=list(self.dashboard.db.scalars(select(ParticipationProjectionResult).where(ParticipationProjectionResult.run_id==run.id)))
                    data["detail"]["participation_projection"]={"model_code":run.model_code,"model_version":run.model_version,"parameters":run.parameters,"snapshot_date":snapshot.snapshot_date.isoformat() if snapshot else None,"warning":"Estimación estadística de participación. No constituye pronóstico de resultados electorales ni intención de voto.","results":[{"parish_id":r.parish_id,"registered_voters":r.registered_voters,"turnout_rate_central":str(r.turnout_rate_central),"expected_voters_central":r.expected_voters_central,"quality":r.data_quality_status} for r in results]}
        else:
            data.update({"needs":self.dashboard.needs(campaign_id,user,filters),"commitments":self.dashboard.commitments(campaign_id,user,filters),"surveys":self.dashboard.surveys(campaign_id,user,filters),"quality":self.dashboard.data_quality(campaign_id,user,filters)})
        return data
