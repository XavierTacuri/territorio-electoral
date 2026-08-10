"""Idempotent synthetic dataset for the isolated E2E database only."""
import os
from datetime import date
from hashlib import sha256

from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.alerts import AlertRule, OperationalAlert
from app.models.assignments import CampaignUser, TerritorialAssignment
from app.models.campaign import Campaign
from app.models.historical import DataSource, DemographicIndicator, ElectoralProcess
from app.models.operational import CitizenNeed, Commitment, TerritorialActivity
from app.models.reports import ReportRun, ReportTemplate
from app.models.survey import Survey
from app.models.territory import Community, Sector
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
        _,canton,parishes=seed_gualaceo(db); seed_catalogs(db); seed_reports_alerts(db); db.flush()
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
