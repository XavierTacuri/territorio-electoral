"""Idempotent synthetic dataset for the isolated E2E database only."""
import os
from datetime import date
from decimal import Decimal
from hashlib import sha256

from sqlalchemy import func, select, update

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.alerts import AlertRule, OperationalAlert
from app.models.assignments import CampaignUser, TerritorialAssignment
from app.models.campaign import Campaign
from app.models.historical import DataImportJob, DataSource, DemographicIndicator, DemographicObservation, ElectoralContest, ElectoralGeography, ElectoralProcess, ElectoralRollSnapshot, ElectoralRollSnapshotEntry, ElectoralTurnout, ParticipationProjectionResult, ParticipationProjectionRun
from app.models.operational import CitizenNeed, Commitment, TerritorialActivity
from app.models.reports import ReportRun, ReportTemplate
from app.models.survey import Survey
from app.models.territory import Canton, Community, Parish, Province, Sector
from app.models.user import User
from app.schemas.campaign import CampaignCreate, CampaignUserAssign, TerritorialAssignmentCreate
from app.schemas.historical import DataSourceCreate, DemographicIndicatorCreate, ElectoralContestCreate, ElectoralProcessCreate
from app.schemas.operational import CommitmentCreate, CitizenNeedCreate, ParticipantSummaryUpsert, TerritorialActivityCreate
from app.schemas.reports import ReportGenerationRequest
from app.schemas.survey import SurveyAnswerInput, SurveyCreate, SurveyOptionCreate, SurveyQuestionCreate, SurveySectionCreate, SurveySubmissionCreate
from app.scripts.seed_gualaceo import seed as seed_gualaceo
from app.scripts.seed_reports_and_alerts import seed as seed_reports_alerts
from app.services.activity_catalog_service import seed as seed_catalogs
from app.services.campaign_service import CampaignService
from app.services.data_import_service import DataImportService
from app.services.data_source_service import DataSourceService
from app.services.demographic_service import DemographicService
from app.services.electoral_service import ElectoralService
from app.services.operational_service import OperationalService
from app.services.report_service import ReportService
from app.services.role_service import RoleService
from app.services.survey_service import SurveyService
from app.services.territorial_assignment_service import TerritorialAssignmentService

USERS = [("admin-e2e@example.com", "admin_e2e", "ADMIN"), ("manager-e2e@example.com", "manager_e2e", "CAMPAIGN_MANAGER"), ("coordinator-e2e@example.com", "coordinator_e2e", "TERRITORIAL_COORDINATOR"), ("analyst-e2e@example.com", "analyst_e2e", "ANALYST"), ("candidate-e2e@example.com", "candidate_e2e", "CANDIDATE")]

def ensure_current_election_fixture(db, admin):
    """Create a small deterministic territory used only by portable current-election E2E tests."""
    province=db.scalar(select(Province).where(Province.code=="99"))
    if not province:
        province=Province(code="99",name="Provincia Sintética E2E");db.add(province);db.flush()
    canton=db.scalar(select(Canton).where(Canton.dpa_code=="9999"))
    if not canton:
        canton=Canton(province_id=province.id,code="99",dpa_code="9999",name="Cantón Sintético E2E");db.add(canton);db.flush()
    parish_specs=[("999901","Parroquia Alfa",0,0),("999902","Parroquia Beta",1,0),("999903","Parroquia Gamma",0,1)]
    parishes=[]
    for index,(dpa,name,x,y) in enumerate(parish_specs,1):
        parish=db.scalar(select(Parish).where(Parish.dpa_code==dpa))
        if not parish:
            parish=Parish(canton_id=canton.id,code=f"{index:02d}",dpa_code=dpa,name=name,parish_type="URBAN" if index==1 else "RURAL");db.add(parish);db.flush()
        polygon=f"MULTIPOLYGON((({x} {y},{x+0.8} {y},{x+0.8} {y+0.8},{x} {y+0.8},{x} {y})))"
        db.execute(update(Parish).where(Parish.id==parish.id).values(geometry=func.ST_GeomFromText(polygon,4326)))
        parishes.append(parish)
    campaign=db.scalar(select(Campaign).where(Campaign.slug=="territorio-sintetico-e2e"))
    if not campaign:
        campaign=CampaignService(db).create(CampaignCreate(name="Territorio Sintético E2E",slug="territorio-sintetico-e2e",canton_id=canton.id,office_type="MAYOR",election_name="Proceso Sintético E2E 2027",election_date=date(2027,3,7),start_date=date(2026,1,1),status="ACTIVE"),admin)
    source=db.scalar(select(DataSource).where(DataSource.code=="E2E_CURRENT_ELECTION"))
    if not source:
        source=DataSourceService(db).create(DataSourceCreate(code="E2E_CURRENT_ELECTION",institution="Institución Sintética E2E",dataset_name="Participación agregada sintética",dataset_type="CNE_ELECTORAL_ROLL_SNAPSHOT",official_url="https://example.test/current-election.csv",publication_date=date(2026,7,1),reference_year=2026),admin)
    job=db.scalar(select(DataImportJob).where(DataImportJob.source_id==source.id,DataImportJob.original_filename=="current-election-e2e.csv"))
    if not job:
        job=DataImportJob(source_id=source.id,dataset_type="CNE_ELECTORAL_ROLL_SNAPSHOT",original_filename="current-election-e2e.csv",file_sha256=sha256(b"current-election-e2e").hexdigest(),file_size_bytes=20,status="COMPLETED",validation_only=False,rows_read=30,rows_valid=30,rows_inserted=30,rows_updated=0,rows_skipped=0,rows_failed=0,executed_by_user_id=admin.id);db.add(job);db.flush()
    process_by_year={}
    for year in (2019,2023,2027):
        code=f"E2E_CURRENT_{year}"
        process=db.scalar(select(ElectoralProcess).where(ElectoralProcess.code==code))
        if not process:
            process=ElectoralProcess(code=code,name=f"Proceso Sintético E2E {year}",process_type="SECTIONAL",election_date=date(year,3,7),year=year,status="VALIDATED",is_final=True,source_id=source.id,is_active=True);db.add(process);db.flush()
        process_by_year[year]=process
    for year in (2019,2023):
        process=process_by_year[year]
        contest=db.scalar(select(ElectoralContest).where(ElectoralContest.electoral_process_id==process.id,ElectoralContest.office_type=="MAYOR",ElectoralContest.canton_id==canton.id))
        if not contest:
            contest=ElectoralContest(electoral_process_id=process.id,office_type="MAYOR",name=f"Alcaldía Sintética {year}",vote_method="SINGLE_CHOICE",seats=1,canton_id=canton.id,is_active=True);db.add(contest);db.flush()
        for index,parish in enumerate(parishes):
            geography=db.scalar(select(ElectoralGeography).where(ElectoralGeography.electoral_process_id==process.id,ElectoralGeography.level=="PARISH",ElectoralGeography.parish_id==parish.id))
            if not geography:
                geography=ElectoralGeography(electoral_process_id=process.id,level="PARISH",external_code=parish.dpa_code,name=parish.name,province_id=province.id,canton_id=canton.id,parish_id=parish.id,is_mapped=True,is_active=True);db.add(geography);db.flush()
            if not db.scalar(select(ElectoralTurnout).where(ElectoralTurnout.electoral_contest_id==contest.id,ElectoralTurnout.electoral_geography_id==geography.id)):
                registered=100+index*20;ballots=(68+index*3) if year==2019 else (72+index*3)
                db.add(ElectoralTurnout(electoral_contest_id=contest.id,electoral_geography_id=geography.id,registered_voters=registered,ballots_cast=ballots,valid_votes=ballots-4,blank_votes=2,null_votes=2,other_votes=0,is_final=True,source_id=source.id,import_job_id=job.id,is_active=True))
    snapshot=db.scalar(select(ElectoralRollSnapshot).where(ElectoralRollSnapshot.source_id==source.id,ElectoralRollSnapshot.snapshot_date==date(2026,7,1)))
    if not snapshot:
        snapshot=ElectoralRollSnapshot(source_id=source.id,electoral_process_id=process_by_year[2027].id,snapshot_date=date(2026,7,1),name="Registro Sintético E2E",status="VALIDATED",is_final=True,created_by_user_id=admin.id);db.add(snapshot);db.flush()
    registrations=[120,150,180]
    for parish,registered in zip(parishes,registrations,strict=True):
        if not db.scalar(select(ElectoralRollSnapshotEntry).where(ElectoralRollSnapshotEntry.snapshot_id==snapshot.id,ElectoralRollSnapshotEntry.parish_id==parish.id)):
            db.add(ElectoralRollSnapshotEntry(snapshot_id=snapshot.id,geography_level="PARISH",province_id=province.id,canton_id=canton.id,parish_id=parish.id,province_dpa="99",canton_dpa="9999",parish_dpa=parish.dpa_code,registered_voters=registered,male_voters=registered//2,female_voters=registered-registered//2,electoral_zones=1,juntas=2))
    run=db.scalar(select(ParticipationProjectionRun).where(ParticipationProjectionRun.campaign_id==campaign.id))
    if not run:
        run=ParticipationProjectionRun(campaign_id=campaign.id,electoral_process_id=process_by_year[2027].id,snapshot_id=snapshot.id,model_code="TURNOUT_HISTORICAL_WEIGHTED_V1",model_version="1.0",historical_process_ids=[str(process_by_year[2019].id),str(process_by_year[2023].id)],parameters={"historical_weight_old":"0.35","historical_weight_recent":"0.65"},run_date=date(2026,7,2),created_by_user_id=admin.id);db.add(run);db.flush()
    for index,(parish,registered) in enumerate(zip(parishes,registrations,strict=True)):
        if not db.scalar(select(ParticipationProjectionResult).where(ParticipationProjectionResult.run_id==run.id,ParticipationProjectionResult.parish_id==parish.id)):
            central=Decimal("0.71")+Decimal(index)*Decimal("0.02");low=central-Decimal("0.03");high=central+Decimal("0.02")
            db.add(ParticipationProjectionResult(run_id=run.id,parish_id=parish.id,registered_voters=registered,turnout_rate_low=low,turnout_rate_central=central,turnout_rate_high=high,expected_voters_low=round(registered*float(low)),expected_voters_central=round(registered*float(central)),expected_voters_high=round(registered*float(high)),data_quality_status="MEDIUM",explanation="Fixture agregado sintético y determinista."))
    indicator_values={"POP_TOTAL":[200,250,300],"POP_MALE":[95,120,145],"POP_FEMALE":[105,130,155],"POP_AGE_0_4":[20,25,30],"POP_AGE_15_19":[18,22,26],"POP_AGE_30_34":[16,20,24],"POP_AGE_45_49":[14,18,22],"POP_AGE_65_69":[10,12,14]}
    for code,values in indicator_values.items():
        indicator=db.scalar(select(DemographicIndicator).where(DemographicIndicator.code==code))
        if not indicator:
            indicator=DemographicIndicator(code=code,name=f"Indicador sintético {code}",category="POPULATION" if code.startswith("POP_TOTAL") or code in {"POP_MALE","POP_FEMALE"} else "AGE",unit="COUNT",value_type="INTEGER",source_id=source.id,is_active=True);db.add(indicator);db.flush()
        for parish,value in zip(parishes,values,strict=True):
            if not db.scalar(select(DemographicObservation).where(DemographicObservation.demographic_indicator_id==indicator.id,DemographicObservation.parish_id==parish.id,DemographicObservation.reference_year==2022)):
                db.add(DemographicObservation(demographic_indicator_id=indicator.id,geography_level="PARISH",province_id=province.id,canton_id=canton.id,parish_id=parish.id,reference_year=2022,value=Decimal(value),source_id=source.id,import_job_id=job.id,is_official=True,is_active=True))
    db.flush()

def ensure_users(db, password):
    roles=RoleService(db); roles.initialize_roles(); result={}
    for email,username,code in USERS:
        user=db.scalar(select(User).where(User.username==username)); role=roles.repository.get_by_code(code)
        if not user:
            user=User(email=email,username=username,first_name="Usuario",last_name="E2E",hashed_password=hash_password(password),is_active=True,is_superuser=code=="ADMIN",roles=[role]); db.add(user); db.flush()
        else:
            user.email=email; user.hashed_password=hash_password(password); user.is_active=True; user.roles=[role]
        result[code]=user
    return result

def main():
    if settings.app_env.lower() != "e2e": raise SystemExit("El seed E2E requiere APP_ENV=e2e")
    password=os.environ.get("E2E_USER_PASSWORD")
    if not password: raise SystemExit("E2E_USER_PASSWORD es obligatorio")
    with SessionLocal() as db:
        users=ensure_users(db,password); admin=users["ADMIN"]
        _,canton,parishes=seed_gualaceo(db); seed_catalogs(db); seed_reports_alerts(db); db.flush();ensure_current_election_fixture(db,admin)
        campaign=db.scalar(select(Campaign).where(Campaign.slug=="gualaceo-e2e-2027"))
        if not campaign: campaign=CampaignService(db).create(CampaignCreate(name="Gualaceo E2E 2027",slug="gualaceo-e2e-2027",canton_id=canton.id,office_type="MAYOR",election_name="Elecciones sintéticas 2027",election_date=date(2027,2,14),start_date=date(2026,1,1),status="ACTIVE"),admin)
        assignments=TerritorialAssignmentService(db)
        for user in users.values():
            member=db.scalar(select(CampaignUser).where(CampaignUser.campaign_id==campaign.id,CampaignUser.user_id==user.id))
            if not member: assignments.assign_user(campaign.id,CampaignUserAssign(user_id=user.id),admin)
            elif not member.is_active: member.is_active=True
        community=db.scalar(select(Community).where(Community.parish_id==parishes[0].id,Community.code=="E2E_COMMUNITY"))
        if not community:
            community=Community(parish_id=parishes[0].id,name="Comunidad sintetica E2E",code="E2E_COMMUNITY",is_official=False,is_active=True); db.add(community); db.flush()
        sector=db.scalar(select(Sector).where(Sector.community_id==community.id,Sector.code=="E2E_SECTOR"))
        if not sector:
            sector=Sector(community_id=community.id,name="Sector sintetico E2E",code="E2E_SECTOR",is_active=True); db.add(sector); db.flush()
        coordinator=users["TERRITORIAL_COORDINATOR"]
        territory=db.scalar(select(TerritorialAssignment).where(TerritorialAssignment.campaign_id==campaign.id,TerritorialAssignment.user_id==coordinator.id,TerritorialAssignment.parish_id==parishes[0].id))
        if not territory: assignments.create(campaign.id,TerritorialAssignmentCreate(user_id=coordinator.id,parish_id=parishes[0].id),admin)
        elif not territory.is_active: territory.is_active=True
        op=OperationalService(db,today_provider=lambda:date(2026,8,3)); activity=db.scalar(select(TerritorialActivity).where(TerritorialActivity.campaign_id==campaign.id,TerritorialActivity.title=="Asamblea sintética E2E"))
        if not activity:
            activity=op.create_activity(campaign.id,TerritorialActivityCreate(activity_type_code="COMMUNITY_MEETING",title="Asamblea sintética E2E",description="Actividad agregada sin participantes identificados.",activity_date=date(2026,8,3),status="COMPLETED",parish_id=parishes[0].id),admin)
            op.participant(campaign.id,activity.id,admin,ParticipantSummaryUpsert(estimated_attendees=25,organizations_count=2))
        need=db.scalar(select(CitizenNeed).where(CitizenNeed.campaign_id==campaign.id,CitizenNeed.title=="Mantenimiento vial sintético"))
        if not need: need=op.create_need(campaign.id,activity.id,CitizenNeedCreate(need_category_code="ROADS",title="Mantenimiento vial sintético",mentions_count=8,priority="HIGH"),admin)
        commitment=db.scalar(select(Commitment).where(Commitment.campaign_id==campaign.id,Commitment.title=="Revisar mantenimiento sintético"))
        if not commitment: op.create_commitment(campaign.id,CommitmentCreate(title="Revisar mantenimiento sintético",priority="HIGH",status="PENDING",due_date=date(2026,8,10),parish_id=parishes[0].id,activity_id=activity.id),admin)
        survey_service=SurveyService(db,today_provider=lambda:date(2026,8,3))
        if not db.scalar(select(Survey).where(Survey.campaign_id==campaign.id,Survey.slug=="borrador-e2e")): survey_service.create(campaign.id,SurveyCreate(title="Encuesta borrador E2E",slug="borrador-e2e",target_scope="CANTON"),admin)
        published=db.scalar(select(Survey).where(Survey.campaign_id==campaign.id,Survey.slug=="publicada-e2e"))
        if not published:
            published=survey_service.create(campaign.id,SurveyCreate(title="Encuesta publicada E2E",slug="publicada-e2e",target_scope="CANTON",start_date=date(2026,8,1),end_date=date(2026,8,31)),admin)
            section=survey_service.add_section(campaign.id,published.id,SurveySectionCreate(title="Servicios",display_order=1),admin)
            question=survey_service.add_question(campaign.id,published.id,section.id,SurveyQuestionCreate(code="PRIORIDAD",question_text="¿Cuál es la prioridad principal?",question_type="SINGLE_CHOICE",is_required=True),admin)
            survey_service.add_option(campaign.id,published.id,question.id,SurveyOptionCreate(code="VIAS",label="Vías",display_order=1),admin); survey_service.add_option(campaign.id,published.id,question.id,SurveyOptionCreate(code="AGUA",label="Agua",display_order=2),admin); survey_service.publish(campaign.id,published.id,admin)
            for index in range(5): survey_service.submit(campaign.id,published.id,SurveySubmissionCreate(response_date=date(2026,8,3),parish_id=parishes[0].id,source_channel="FIELD",age_range="NOT_PROVIDED",submission_key=f"synthetic-{index}-key",answers=[SurveyAnswerInput(question_code="PRIORIDAD",selected_option_codes=["VIAS"])]),admin)
        source=db.scalar(select(DataSource).where(DataSource.code=="E2E_OFFICIAL"))
        if not source: source=DataSourceService(db).create(DataSourceCreate(code="E2E_OFFICIAL",institution="Institución sintética",dataset_name="Datos agregados E2E",dataset_type="CNE_TURNOUT",official_url="https://example.test/datos.csv",publication_date=date(2026,1,1),reference_year=2023),admin)
        process=db.scalar(select(ElectoralProcess).where(ElectoralProcess.code=="E2E_SEC_2023"))
        if not process:
            electoral=ElectoralService(db); process=electoral.create_process(ElectoralProcessCreate(code="E2E_SEC_2023",name="Proceso sintético 2023",process_type="SECTIONAL",election_date=date(2023,2,5),year=2023,status="VALIDATED",source_id=source.id)); electoral.create_contest(process.id,ElectoralContestCreate(office_type="MAYOR",name="ALCALDÍA E2E",vote_method="SINGLE_CHOICE",canton_id=canton.id))
        indicator=db.scalar(select(DemographicIndicator).where(DemographicIndicator.code=="E2E_POP_TOTAL"))
        if not indicator:
            DemographicService(db).create(DemographicIndicatorCreate(code="E2E_POP_TOTAL",name="Población sintética",category="POPULATION",unit="COUNT",value_type="INTEGER",source_id=source.id)); DataImportService(db).run(source.id,"INEC_DEMOGRAPHIC_INDICATORS","e2e-demografia.csv",b"indicator_code,reference_year,geography_level,province_dpa,canton_dpa,parish_dpa,value,numerator,denominator\nE2E_POP_TOTAL,2022,CANTON,01,0103,,42000,,\n",admin,False,"CANONICAL_DEMOGRAPHIC_OBSERVATION")
        template=db.scalar(select(ReportTemplate).where(ReportTemplate.code=="CAMPAIGN_EXECUTIVE_SUMMARY"))
        if not db.scalar(select(ReportRun).where(ReportRun.campaign_id==campaign.id,ReportRun.title=="Informe E2E inicial")):
            ReportService(db).generate(campaign.id,ReportGenerationRequest(template_code=template.code,format="PDF",title="Informe E2E inicial",report_date=date(2026,8,3),period="LAST_30_DAYS"),admin)
        rule=db.scalar(select(AlertRule).where(AlertRule.code=="ACTIVITY_WITHOUT_LOCATION"))
        fingerprint=sha256(f"e2e:{campaign.id}".encode()).hexdigest()
        if not db.scalar(select(OperationalAlert).where(OperationalAlert.campaign_id==campaign.id,OperationalAlert.fingerprint==fingerprint)): db.add(OperationalAlert(alert_rule_id=rule.id,campaign_id=campaign.id,severity="INFO",status="OPEN",title="Alerta sintética E2E",message="Actividad agregada sin ubicación opcional.",detected_date=date(2026,8,3),last_seen_date=date(2026,8,3),parish_id=parishes[0].id,fingerprint=fingerprint,evidence={"count":1},is_active=True))
        db.commit()
    print("Seed E2E sintético e idempotente completado")

if __name__ == "__main__": main()
