from datetime import date,datetime,timedelta,timezone
import pytest
from sqlalchemy import select
from app.core.security import hash_password
from decimal import Decimal
from app.models.alerts import AlertAcknowledgement,AlertRule
from app.models.historical import DatasetVersion
from app.models.survey_study import SurveyStudy,SurveyStudyOption,SurveyStudyResult,SurveyStudyTerritory
from app.models.user import User
from app.schemas.alerts import AlertActionRequest,AlertEvaluationRequest
from app.schemas.campaign import CampaignCreate,CampaignUserAssign,TerritorialAssignmentCreate
from app.schemas.historical import DataSourceCreate,ElectoralContestCreate,ElectoralMilestoneCreate,ElectoralMilestoneUpdate,ElectoralProcessCreate
from app.schemas.operational import ActivityCloseRequest,ActivitySuspendRequest,CitizenNeedCreate,CommitmentCreate,TerritorialActivityCreate
from app.scripts.seed_gualaceo import seed as seed_territory
from app.services.activity_catalog_service import seed as seed_catalogs
from app.services.alert_service import AlertService
from app.services.calendar_service import CalendarService
from app.services.campaign_service import CampaignService
from app.services.data_import_service import DataImportService
from app.services.data_source_service import DataSourceService
from app.services.dataset_version_service import DatasetVersionService
from app.services.electoral_milestone_service import ElectoralMilestoneService
from app.services.electoral_service import ElectoralService
from app.services.exceptions import BusinessRuleError,ConflictError,NotFoundError
from app.services.operational_service import OperationalService
from app.services.role_service import RoleService
from app.services.territorial_assignment_service import TerritorialAssignmentService
from app.scripts.seed_reports_and_alerts import seed as seed_alert_rules

@pytest.fixture
def ctx(db,admin):
 province,canton,parishes=seed_territory(db);seed_catalogs(db);db.commit()
 campaign=CampaignService(db).create(CampaignCreate(name="Calendario y Alertas",slug="calendario-alertas",canton_id=canton.id,office_type="MAYOR",election_name="Elección sintética",election_date=date(2027,2,14),status="ACTIVE"),admin)
 roles=RoleService(db)
 def user(code,name):
  obj=User(email=f"{name}@example.test",username=name,first_name=name,last_name="Test",hashed_password=hash_password("Testing123"),roles=[roles.repository.get_by_code(code)]);db.add(obj);db.flush();return obj
 manager=user("CAMPAIGN_MANAGER","ca_manager");coordinator=user("TERRITORIAL_COORDINATOR","ca_coordinator");analyst=user("ANALYST","ca_analyst");db.commit()
 assignments=TerritorialAssignmentService(db)
 for member in (manager,coordinator,analyst):assignments.assign_user(campaign.id,CampaignUserAssign(user_id=member.id),admin)
 assignments.create(campaign.id,TerritorialAssignmentCreate(user_id=coordinator.id,parish_id=parishes[0].id),admin)
 seed_alert_rules(db);db.commit()
 return campaign,province,canton,parishes,manager,coordinator,analyst

def electoral_source(db,admin,code="CA_SOURCE"):
 return DataSourceService(db).create(DataSourceCreate(code=code,institution="Consejo Nacional Electoral",dataset_name="Calendario sintético",dataset_type="CNE_ELECTORAL_ROLL_SNAPSHOT"),admin)

def rule_code_of(db,alert):return db.get(AlertRule,alert.alert_rule_id).condition_type

def _published_study(db,admin,campaign,code,fieldwork_end,percentage,question_code="VOTE_INTENTION",sampling_method="Aleatorio simple"):
 study=SurveyStudy(campaign_id=campaign.id,code=code,name=f"Estudio {code}",study_type="GENERAL_SURVEY",status="PUBLISHED",fieldwork_start_date=fieldwork_end-timedelta(days=2),fieldwork_end_date=fieldwork_end,geography_level="CANTON",sample_size_total=400,universe_description="Universo cantonal",sampling_method=sampling_method,collection_method="Telefónica",source_type="ESTUDIO",question_code=question_code,created_by_user_id=admin.id)
 db.add(study);db.flush()
 option=SurveyStudyOption(study_id=study.id,question_code=question_code,question_text="¿Por quién votaría?",question_type="VOTE_INTENTION",code="CAND_A",label="Candidato A",option_type="CANDIDATE",display_order=0)
 db.add(option);db.flush()
 territory=SurveyStudyTerritory(study_id=study.id,parish_id=None,sample_size=400)
 db.add(territory);db.flush()
 db.add(SurveyStudyResult(study_id=study.id,study_territory_id=territory.id,option_id=option.id,response_count=int(400*percentage),percentage=Decimal(str(percentage))))
 db.commit();return study

def matching_process(db,admin,canton,source,code="CA_PROC"):
 service=ElectoralService(db)
 process=service.create_process(ElectoralProcessCreate(code=code,name="Proceso sintético",process_type="SECTIONAL",election_date=date(2027,2,14),year=2027,status="VALIDATED",source_id=source.id))
 service.create_contest(process.id,ElectoralContestCreate(office_type="MAYOR",name="MAYOR_CA",vote_method="SINGLE_CHOICE",canton_id=canton.id))
 return process

# --- Official milestones: RBAC + idempotency + campaign/process isolation ---

def test_milestone_rbac_admin_write_others_read_only(db,admin,ctx):
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx;source=electoral_source(db,admin);process=matching_process(db,admin,canton,source)
 data=ElectoralMilestoneCreate(electoral_process_id=process.id,title="Convocatoria",milestone_type="CONVOCATORIA",starts_at=datetime(2027,1,1,tzinfo=timezone.utc),source_id=source.id)
 milestone=ElectoralMilestoneService(db).create(data,admin);assert milestone.status=="ACTIVE" and milestone.is_official
 updated=ElectoralMilestoneService(db).update(milestone.id,ElectoralMilestoneUpdate(title="Convocatoria oficial"),admin);assert updated.title=="Convocatoria oficial"
 archived=ElectoralMilestoneService(db).set_status(milestone.id,"ARCHIVED",admin);assert archived.status=="ARCHIVED"

def test_milestone_duplicate_identity_rejected(db,admin,ctx):
 campaign,province,canton,parishes,*_=ctx;source=electoral_source(db,admin);process=matching_process(db,admin,canton,source)
 data=ElectoralMilestoneCreate(electoral_process_id=process.id,title="Elección",milestone_type="ELECTION_DAY",starts_at=datetime(2027,2,14,tzinfo=timezone.utc),source_id=source.id)
 ElectoralMilestoneService(db).create(data,admin)
 with pytest.raises(ConflictError):ElectoralMilestoneService(db).create(data,admin)

def test_milestone_http_rbac(db,admin,client,admin_headers,ctx):
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx;source=electoral_source(db,admin);process=matching_process(db,admin,canton,source)
 payload={"electoral_process_id":str(process.id),"title":"Silencio electoral","milestone_type":"ELECTORAL_SILENCE","starts_at":"2027-02-12T00:00:00Z","source_id":str(source.id)}
 assert client.post("/api/v1/electoral-milestones",json=payload).status_code==401
 analyst_headers={"Authorization":"Bearer "+client.post("/api/v1/auth/login",data={"username":"ca_analyst","password":"Testing123"}).json()["access_token"]}
 assert client.post("/api/v1/electoral-milestones",headers=analyst_headers,json=payload).status_code==403
 created=client.post("/api/v1/electoral-milestones",headers=admin_headers,json=payload);assert created.status_code==201
 assert client.get("/api/v1/electoral-milestones",headers=analyst_headers).status_code==200

def test_campaign_sees_only_its_matching_process_milestones(db,admin,ctx):
 # Los hitos oficiales ya no viven en el Calendario de campaña (retiro de
 # producto): el emparejamiento campaña→proceso electoral sigue vigente en la
 # alerta operativa UPCOMING_OFFICIAL_MILESTONE, que es donde ahora se prueba.
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx;source=electoral_source(db,admin)
 process_a=matching_process(db,admin,canton,source,"CA_PROC_A")
 service=ElectoralService(db)
 process_b=service.create_process(ElectoralProcessCreate(code="CA_PROC_B",name="Otro proceso",process_type="SECTIONAL",election_date=date(2027,2,14),year=2027,status="VALIDATED",source_id=source.id))
 service.create_contest(process_b.id,ElectoralContestCreate(office_type="URBAN_COUNCILOR",name="COUNCIL_CA",vote_method="MULTI_VOTE",canton_id=canton.id))
 ElectoralMilestoneService(db).create(ElectoralMilestoneCreate(electoral_process_id=process_a.id,title="Hito A",milestone_type="DEBATE",starts_at=datetime(2027,1,15,tzinfo=timezone.utc),source_id=source.id),admin)
 ElectoralMilestoneService(db).create(ElectoralMilestoneCreate(electoral_process_id=process_b.id,title="Hito B",milestone_type="DEBATE",starts_at=datetime(2027,1,16,tzinfo=timezone.utc),source_id=source.id),admin)
 svc=AlertService(db);req=AlertEvaluationRequest(rule_codes=["UPCOMING_OFFICIAL_MILESTONE"],as_of_date=date(2027,1,10));svc.evaluate(campaign.id,admin,req)
 items,_=svc.list(campaign.id,admin,status="OPEN")
 titles={i.evidence.get("title") for i in items}
 assert titles=={"Hito A"},"la campaña (MAYOR) solo debe ver hitos del proceso con contienda MAYOR, no la de URBAN_COUNCILOR"

# --- Calendar composition ---

def test_calendar_only_shows_campaign_activities_not_commitment_survey_or_milestone(db,admin,ctx):
 # Calendario de campaña: retiro de producto de hitos oficiales, seguimientos y
 # encuestas. Esos datos siguen viviendo en sus propios módulos, pero el
 # read-model del calendario ahora solo compone TerritorialActivity vigente.
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx;ops=OperationalService(db)
 activity=ops.create_activity(campaign.id,TerritorialActivityCreate(activity_type_code="ASSEMBLY",title="Asamblea territorial",description="Objetivo",activity_date=date(2027,1,10),parish_id=parishes[0].id,status="PLANNED"),manager)
 ops.create_commitment(campaign.id,CommitmentCreate(title="Seguimiento territorial",due_date=date(2027,1,12),parish_id=parishes[0].id,responsible_user_id=manager.id),manager)
 study=SurveyStudy(campaign_id=campaign.id,code="CA_STUDY",name="Estudio sintético",study_type="GENERAL_SURVEY",status="PUBLISHED",fieldwork_start_date=date(2027,1,14),fieldwork_end_date=date(2027,1,16),publication_date=date(2027,1,20),geography_level="CANTON",sample_size_total=500,universe_description="Universo cantonal",sampling_method="Muestreo aleatorio",collection_method="Telefónico",source_type="ESTUDIO",created_by_user_id=admin.id);db.add(study);db.commit()
 source=electoral_source(db,admin);process=matching_process(db,admin,canton,source)
 ElectoralMilestoneService(db).create(ElectoralMilestoneCreate(electoral_process_id=process.id,title="Debate territorial",milestone_type="DEBATE",starts_at=datetime(2027,1,18,tzinfo=timezone.utc),source_id=source.id),admin)
 events=CalendarService(db).events(campaign.id,manager,date(2027,1,1),date(2027,1,31))
 assert {e.event_type for e in events}=={"CAMPAIGN_ACTIVITY"}
 activity_event=events[0];assert activity_event.deep_link==f"/app/campaigns/{campaign.id}/activities/{activity.id}" and not activity_event.is_official

def test_calendar_coordinator_scope_excludes_other_parish_activity(db,admin,ctx):
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx;ops=OperationalService(db)
 ops.create_activity(campaign.id,TerritorialActivityCreate(activity_type_code="ASSEMBLY",title="Asamblea propia",description="Objetivo",activity_date=date(2027,1,10),parish_id=parishes[0].id,status="PLANNED"),manager)
 ops.create_activity(campaign.id,TerritorialActivityCreate(activity_type_code="ASSEMBLY",title="Asamblea ajena",description="Objetivo",activity_date=date(2027,1,11),parish_id=parishes[1].id,status="PLANNED"),manager)
 events=CalendarService(db).events(campaign.id,coordinator,date(2027,1,1),date(2027,1,31))
 titles={e.title for e in events if e.event_type=="CAMPAIGN_ACTIVITY"}
 assert titles=={"Asamblea propia"}

# --- Alert engine extensions ---

def test_activity_pending_approval_is_derived_deterministically_and_auto_resolves(db,admin,ctx):
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx;ops=OperationalService(db)
 activity=ops.create_activity(campaign.id,TerritorialActivityCreate(activity_type_code="ASSEMBLY",title="Pendiente de aprobación",description="Objetivo",activity_date=date(2027,1,10),parish_id=parishes[0].id,status="PLANNED"),coordinator)
 assert activity.approval_status=="PENDING_APPROVAL"
 svc=AlertService(db);req=AlertEvaluationRequest(rule_codes=["ACTIVITY_PENDING_APPROVAL"],as_of_date=date(2027,1,1))
 first=svc.evaluate(campaign.id,manager,req);assert first["created"]==1
 items,_=svc.list(campaign.id,manager,status="OPEN");assert len(items)==1 and items[0].resource_id==activity.id
 second=svc.evaluate(campaign.id,manager,req);assert second["created"]==0 and second["unchanged"]==1,"reevaluar la misma condición no debe crear una alerta nueva"
 ops.approve_activity(campaign.id,activity.id,manager)
 third=svc.evaluate(campaign.id,manager,req);assert third["resolved"]==1
 items,_=svc.list(campaign.id,manager,status="OPEN")
 assert "ACTIVITY_PENDING_APPROVAL" not in {rule_code_of(db,i) for i in items},"al aprobarse la actividad, la alerta de pendiente debe autorresolverse"

def test_http_alert_list_exposes_total_for_pagination(client,db,admin,admin_headers,ctx):
 """Regresión: AlertListResponse antes omitía `total`, dejando la UI sin forma
 de saber que existían más alertas allá de la primera página (page_size fijo
 sin control de paginación visible — riesgo real de alertas invisibles en una
 campaña de larga duración)."""
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx;ops=OperationalService(db)
 for i in range(3):
  ops.create_activity(campaign.id,TerritorialActivityCreate(activity_type_code="ASSEMBLY",title=f"Pendiente {i}",description="Objetivo",activity_date=date(2027,1,10),parish_id=parishes[0].id,status="PLANNED"),coordinator)
 AlertService(db).evaluate(campaign.id,manager,AlertEvaluationRequest(rule_codes=["ACTIVITY_PENDING_APPROVAL"],as_of_date=date(2027,1,1)))
 response=client.get(f"/api/v1/campaigns/{campaign.id}/alerts?page=1&page_size=2",headers=admin_headers)
 assert response.status_code==200
 body=response.json()
 assert len(body["items"])==2
 assert body["total"]>=3,"total debe reflejar el conteo real, no solo el tamaño de la página devuelta"

def test_coordinator_does_not_see_approval_pending_alert(db,admin,ctx):
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx;ops=OperationalService(db)
 ops.create_activity(campaign.id,TerritorialActivityCreate(activity_type_code="ASSEMBLY",title="Pendiente",description="Objetivo",activity_date=date(2027,1,10),parish_id=parishes[0].id,status="PLANNED"),coordinator)
 svc=AlertService(db);req=AlertEvaluationRequest(rule_codes=["ACTIVITY_PENDING_APPROVAL"],as_of_date=date(2027,1,1));svc.evaluate(campaign.id,manager,req)
 manager_items,_=svc.list(campaign.id,manager,status="OPEN");assert len(manager_items)==1
 coordinator_items,_=svc.list(campaign.id,coordinator,status="OPEN");assert not coordinator_items,"un coordinador no puede aprobar, así que no debe ver la alerta"

def test_activity_suspended_alert(db,admin,ctx):
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx;ops=OperationalService(db)
 activity=ops.create_activity(campaign.id,TerritorialActivityCreate(activity_type_code="ASSEMBLY",title="Actividad a suspender",description="Objetivo",activity_date=date(2027,1,10),parish_id=parishes[0].id,status="PLANNED"),manager)
 ops.suspend_activity(campaign.id,activity.id,ActivitySuspendRequest(reason="Condiciones climáticas"),manager)
 svc=AlertService(db);req=AlertEvaluationRequest(rule_codes=["ACTIVITY_SUSPENDED"],as_of_date=date(2027,1,1));result=svc.evaluate(campaign.id,manager,req);assert result["created"]==1
 items,_=svc.list(campaign.id,manager,status="OPEN");assert items[0].evidence["reason"]=="Condiciones climáticas"

def test_activity_completed_without_evidence_alert(db,admin,ctx):
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx;ops=OperationalService(db)
 activity=ops.create_activity(campaign.id,TerritorialActivityCreate(activity_type_code="ASSEMBLY",title="Actividad sin evidencia",description="Objetivo",activity_date=date(2027,1,5),parish_id=parishes[0].id,status="PLANNED"),manager)
 ops.complete_activity(campaign.id,activity.id,ActivityCloseRequest(summary="Actividad realizada sin evidencia adjunta."),manager)
 svc=AlertService(db);req=AlertEvaluationRequest(rule_codes=["ACTIVITY_COMPLETED_WITHOUT_EVIDENCE"],as_of_date=date(2027,1,10));result=svc.evaluate(campaign.id,manager,req)
 assert result["created"]==1
 items,_=svc.list(campaign.id,manager,status="OPEN");assert items[0].resource_id==activity.id

def test_needs_topic_recurrence_alert_is_descriptive_not_political(db,admin,ctx):
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx;ops=OperationalService(db)
 activity=ops.create_activity(campaign.id,TerritorialActivityCreate(activity_type_code="ASSEMBLY",title="Recorrido vial",description="Objetivo",activity_date=date(2027,1,5),parish_id=parishes[0].id,status="PLANNED"),manager)
 for i in range(3):
  ops.create_need(campaign.id,activity.id,CitizenNeedCreate(need_category_code="ROADS",title=f"Bache vial {i}",description="Vía en mal estado",priority="HIGH",urgency="HIGH",source_type="CAMPAIGN_ACTIVITY",reported_date=date(2027,1,5)+timedelta(days=i),scope="PARISH"),manager)
 svc=AlertService(db);req=AlertEvaluationRequest(rule_codes=["NEEDS_TOPIC_RECURRENCE"],as_of_date=date(2027,1,8));result=svc.evaluate(campaign.id,manager,req)
 assert result["created"]==1
 items,_=svc.list(campaign.id,manager,status="OPEN");alert=items[0]
 assert alert.evidence["theme"]=="VIALIDAD" and alert.evidence["count"]==3
 assert "prioridad" not in alert.message.lower() and "oportunidad" not in alert.message.lower()

def test_report_data_updated_since_generation_alert_offers_new_version_signal(db,admin,ctx,tmp_path):
 from app.schemas.reports import ReportGenerationRequest
 from app.services.report_service import ReportService
 from app.services.report_storage_service import LocalReportStorage
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx
 request=ReportGenerationRequest(template_code="CAMPAIGN_EXECUTIVE_REPORT",format="PDF",title="Informe base",report_date=date.today())
 run=ReportService(db,LocalReportStorage(str(tmp_path),10)).generate(campaign.id,request,manager)
 assert run.status=="COMPLETED"
 study=SurveyStudy(campaign_id=campaign.id,code="CA_FRESH_SURVEY",name="Encuesta reciente",study_type="GENERAL_SURVEY",status="PUBLISHED",fieldwork_start_date=date.today(),fieldwork_end_date=date.today(),publication_date=date.today()+timedelta(days=1),geography_level="CANTON",sample_size_total=300,universe_description="Universo",sampling_method="Aleatorio",collection_method="Presencial",source_type="ESTUDIO",created_by_user_id=admin.id)
 db.add(study);db.commit()
 svc=AlertService(db);req=AlertEvaluationRequest(rule_codes=["REPORT_DATA_UPDATED_SINCE_GENERATION"],as_of_date=date.today());result=svc.evaluate(campaign.id,manager,req)
 assert result["created"]==1
 items,_=svc.list(campaign.id,manager,status="OPEN");assert items[0].resource_id==run.id
 assert any("encuesta" in reason for reason in items[0].evidence["reasons"])

def test_survey_comparison_change_alert_between_comparable_studies_is_descriptive(db,admin,ctx):
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx
 _published_study(db,admin,campaign,"CA_SC_V1",date(2027,1,1),0.284)
 newer=_published_study(db,admin,campaign,"CA_SC_V2",date(2027,1,15),0.311)
 svc=AlertService(db);req=AlertEvaluationRequest(rule_codes=["SURVEY_COMPARISON_CHANGE"],as_of_date=date(2027,1,20));result=svc.evaluate(campaign.id,manager,req)
 assert result["created"]==1
 items,_=svc.list(campaign.id,manager,status="OPEN");alert=next(a for a in items if a.evidence["new_study_id"]==str(newer.id))
 assert alert.evidence["previous_percentage"]==0.284 and alert.evidence["new_percentage"]==0.311 and alert.evidence["difference_points"]==2.7
 banned=("ganando","oportunidad","favorabilidad","caída preocupante","tendencia favorable","apoyo subió","mejoró la campaña")
 assert not any(word in alert.message.lower() for word in banned)
 assert not any(word in alert.title.lower() for word in banned)

def test_survey_comparison_change_skips_incompatible_studies(db,admin,ctx):
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx
 _published_study(db,admin,campaign,"CA_SC_INC1",date(2027,1,1),0.30)
 _published_study(db,admin,campaign,"CA_SC_INC2",date(2027,1,15),0.35,sampling_method="Presencial por cuotas")
 svc=AlertService(db);req=AlertEvaluationRequest(rule_codes=["SURVEY_COMPARISON_CHANGE"],as_of_date=date(2027,1,20));result=svc.evaluate(campaign.id,manager,req)
 assert result["created"]==0

def test_survey_comparison_uses_immediately_previous_compatible_study_not_v1(db,admin,ctx):
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx
 v1=_published_study(db,admin,campaign,"CA_SC_S1",date(2027,1,1),0.20)
 v2=_published_study(db,admin,campaign,"CA_SC_S2",date(2027,1,10),0.25)
 v3=_published_study(db,admin,campaign,"CA_SC_S3",date(2027,1,20),0.30)
 svc=AlertService(db);req=AlertEvaluationRequest(rule_codes=["SURVEY_COMPARISON_CHANGE"],as_of_date=date(2027,1,25));result=svc.evaluate(campaign.id,manager,req)
 assert result["created"]==2
 items,_=svc.list(campaign.id,manager,status="OPEN")
 alert_v3=next(a for a in items if a.evidence["new_study_id"]==str(v3.id));alert_v2=next(a for a in items if a.evidence["new_study_id"]==str(v2.id))
 assert alert_v3.evidence["previous_study_id"]==str(v2.id)
 assert alert_v2.evidence["previous_study_id"]==str(v1.id)

def test_survey_comparison_change_does_not_duplicate_on_reevaluate(db,admin,ctx):
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx
 _published_study(db,admin,campaign,"CA_SC_D1",date(2027,1,1),0.30)
 _published_study(db,admin,campaign,"CA_SC_D2",date(2027,1,15),0.33)
 svc=AlertService(db);req=AlertEvaluationRequest(rule_codes=["SURVEY_COMPARISON_CHANGE"],as_of_date=date(2027,1,20))
 first=svc.evaluate(campaign.id,manager,req);assert first["created"]==1
 second=svc.evaluate(campaign.id,manager,req);assert second["created"]==0

def test_operational_alert_retrieval_surfaces_survey_comparison_facts_for_territory_ai(db,admin,ctx):
 from app.schemas.territory_ai import TerritoryAIIntent,TerritoryAIQueryPlan
 from app.services.territory_ai_planner import TerritoryAIQueryPlanner
 from app.services.territory_ai_retrieval import TerritoryAIEvidenceRetriever
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx
 _published_study(db,admin,campaign,"CA_SC_TIA1",date(2027,1,1),0.284)
 _published_study(db,admin,campaign,"CA_SC_TIA2",date(2027,1,15),0.311)
 AlertService(db).evaluate(campaign.id,manager,AlertEvaluationRequest(rule_codes=["SURVEY_COMPARISON_CHANGE"],as_of_date=date(2027,1,20)))
 plan=TerritoryAIQueryPlanner().plan(TerritoryAIIntent.OPERATIONAL_ALERTS)
 evidence=TerritoryAIEvidenceRetriever(db)._operational_alert(campaign.id,manager,TerritoryAIQueryPlan(intent=plan.intent,source_kinds=plan.source_kinds,territory=None),None,"¿qué cambió en las últimas encuestas?")
 comparison=next(e for e in evidence if e.structured_data.get("evidence",{}).get("question_code"))
 assert comparison.structured_data["evidence"]["previous_percentage"]==0.284
 assert comparison.structured_data["evidence"]["new_percentage"]==0.311

def test_upcoming_official_milestone_alert(db,admin,ctx):
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx;source=electoral_source(db,admin);process=matching_process(db,admin,canton,source)
 ElectoralMilestoneService(db).create(ElectoralMilestoneCreate(electoral_process_id=process.id,title="Debate próximo",milestone_type="DEBATE",starts_at=datetime(2027,1,6,tzinfo=timezone.utc),source_id=source.id),admin)
 svc=AlertService(db);req=AlertEvaluationRequest(rule_codes=["UPCOMING_OFFICIAL_MILESTONE"],as_of_date=date(2027,1,1));result=svc.evaluate(campaign.id,manager,req)
 assert result["created"]==1;items,_=svc.list(campaign.id,manager,status="OPEN");assert items[0].evidence["days_until"]==5

def test_dataset_update_and_campaign_without_active_roll_alerts(db,admin,ctx):
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx
 svc=AlertService(db);req=AlertEvaluationRequest(rule_codes=["CAMPAIGN_WITHOUT_ACTIVE_ROLL"],as_of_date=date.today())
 result=svc.evaluate(campaign.id,manager,req);assert result["created"]==1,"sin versión activa del padrón, debe alertar"
 source=electoral_source(db,admin,"CA_ROLL_SOURCE");content=b'snapshot_date,process_code,geography_level,province_dpa,canton_dpa,parish_dpa,registered_voters,male_voters,female_voters,electoral_zones,juntas\n2027-01-01,,PARISH,01,0103,'+parishes[0].dpa_code.encode()+b',100,50,50,,\n'
 job=DataImportService(db).run(source.id,'CNE_ELECTORAL_ROLL_SNAPSHOT','r.csv',content,admin,False,'CANONICAL_ELECTORAL_ROLL_SNAPSHOT');version=DatasetVersionService(db).create_from_job(job,source);DatasetVersionService(db).activate(version.id,admin)
 req2=AlertEvaluationRequest(rule_codes=["CAMPAIGN_WITHOUT_ACTIVE_ROLL","DATASET_UPDATE"],as_of_date=date.today());result2=svc.evaluate(campaign.id,manager,req2)
 open_items,_=svc.list(campaign.id,manager,status="OPEN");codes={rule_code_of(db,i) for i in open_items}
 assert "CAMPAIGN_WITHOUT_ACTIVE_ROLL" not in codes,"al activarse una versión, la alerta de padrón faltante debe autorresolverse"
 assert "DATASET_UPDATE" in codes

def test_survey_without_methodology_and_data_source_without_reference_date(db,admin,ctx):
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx
 study=SurveyStudy(campaign_id=campaign.id,code="CA_NOMETHOD",name="Estudio sin metodología",study_type="GENERAL_SURVEY",status="PUBLISHED",fieldwork_start_date=date(2027,1,1),fieldwork_end_date=date(2027,1,3),geography_level="CANTON",sample_size_total=300,universe_description="Universo",sampling_method="",collection_method="Presencial",source_type="ESTUDIO",created_by_user_id=admin.id);db.add(study)
 DataSourceService(db).create(DataSourceCreate(code="CA_NOREF",institution="INEC",dataset_name="Sin fecha",dataset_type="INEC_DEMOGRAPHIC_INDICATORS"),admin);db.commit()
 svc=AlertService(db);req=AlertEvaluationRequest(rule_codes=["SURVEY_WITHOUT_METHODOLOGY","DATA_SOURCE_WITHOUT_REFERENCE_DATE"],as_of_date=date.today())
 result=svc.evaluate(campaign.id,manager,req);assert result["created"]==2

def test_overdue_commitment_rule_is_retired_and_never_alerts(db,admin,ctx):
 # Seguimientos/Commitment ya no es una fuente productiva de alertas (retiro de
 # producto): la regla legacy sigue existiendo para compatibilidad pero su
 # evaluación no debe volver a generar alertas nuevas.
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx;ops=OperationalService(db)
 ops.create_commitment(campaign.id,CommitmentCreate(title="Seguimiento vencido",due_date=date(2027,1,1),parish_id=parishes[0].id,responsible_user_id=manager.id),manager)
 svc=AlertService(db);req=AlertEvaluationRequest(rule_codes=["OVERDUE_COMMITMENT"],as_of_date=date(2027,1,10));svc.evaluate(campaign.id,manager,req)
 items,_=svc.list(campaign.id,manager,status="OPEN");assert items==[]

def test_acknowledge_and_resolve_do_not_delete_original_condition(db,admin,ctx):
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx;ops=OperationalService(db)
 activity=ops.create_activity(campaign.id,TerritorialActivityCreate(activity_type_code="ASSEMBLY",title="Actividad a revisar",description="Objetivo",activity_date=date(2027,1,10),parish_id=parishes[0].id,status="PLANNED"),coordinator)
 svc=AlertService(db);req=AlertEvaluationRequest(rule_codes=["ACTIVITY_PENDING_APPROVAL"],as_of_date=date(2027,1,1));svc.evaluate(campaign.id,manager,req)
 items,_=svc.list(campaign.id,manager,status="OPEN");alert=items[0]
 acknowledged=svc.action(campaign.id,alert.id,"ACKNOWLEDGE",AlertActionRequest(action_date=date(2027,1,1)),manager);assert acknowledged.status=="ACKNOWLEDGED"
 trail=list(db.scalars(select(AlertAcknowledgement).where(AlertAcknowledgement.alert_id==alert.id)));assert len(trail)==1 and trail[0].action=="ACKNOWLEDGE"
 refreshed=svc.evaluate(campaign.id,manager,req);assert refreshed["unchanged"]==1,"la condición sigue existiendo; reconocerla no debe reabrir como creación nueva"

# --- Territorio IA: CAMPAIGN_SCHEDULE / OPERATIONAL_ALERTS intents (§38-40, §58-59) ---

from app.main import app
from app.schemas.entitlement import EntitlementType,EntitlementUpsert,FeatureCode
from app.schemas.territory_ai import TerritoryAIIntent,TerritoryAIQueryPlan,TerritoryAISourceKind
from app.services.feature_entitlement_service import FeatureEntitlementService
from app.services.territory_ai_intent import TerritoryAIIntentRouter
from app.services.territory_ai_planner import TerritoryAIQueryPlanner
from app.services.territory_ai_retrieval import TerritoryAIEvidenceRetriever
from app.services.territory_ai_service import ProviderResult,get_ai_provider

class _FakeProvider:
 name="fake";available=True
 def __init__(self,result=None):self.calls=[];self.result=result or ProviderResult("Respuesta basada en evidencia real.","fake-v1",2,3,["1"])
 def generate(self,question,context):self.calls.append((question,context));return self.result

def test_campaign_schedule_intent_routes_and_retrieves_real_events_not_invented(db,admin,ctx):
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx;ops=OperationalService(db)
 near=date.today()+timedelta(days=5)
 ops.create_activity(campaign.id,TerritorialActivityCreate(activity_type_code="ASSEMBLY",title="Asamblea IA",description="Objetivo",activity_date=near,parish_id=parishes[0].id,status="PLANNED"),manager)
 router=TerritoryAIIntentRouter();intent=router.route("¿Cuáles son los próximos hitos electorales?")
 assert intent==TerritoryAIIntent.CAMPAIGN_SCHEDULE
 plan=TerritoryAIQueryPlanner().plan(intent);assert TerritoryAISourceKind.CAMPAIGN_SCHEDULE in plan.source_kinds
 evidence=TerritoryAIEvidenceRetriever(db)._campaign_schedule(campaign.id,manager,TerritoryAIQueryPlan(intent=intent,source_kinds=plan.source_kinds,territory=None),None,"calendario")
 titles={e.title for e in evidence};assert "Asamblea IA" in titles
 assert all(e.evidence_class!="OFFICIAL" for e in evidence),"un evento de campaña (no un hito oficial) nunca debe citarse como OFFICIAL"

def test_campaign_schedule_still_surfaces_official_milestones_for_territory_ai(db,admin,ctx):
 # Los hitos oficiales ya no aparecen en el Calendario de campaña (retiro de
 # producto), pero Territorio IA debe seguir pudiendo citarlos como evidencia
 # factual (Data Hub) al responder sobre próximos hitos electorales.
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx
 source=electoral_source(db,admin);process=matching_process(db,admin,canton,source)
 near=datetime.now(timezone.utc)+timedelta(days=5)
 ElectoralMilestoneService(db).create(ElectoralMilestoneCreate(electoral_process_id=process.id,title="Debate IA sintético",milestone_type="DEBATE",starts_at=near,source_id=source.id),admin)
 plan=TerritoryAIQueryPlanner().plan(TerritoryAIIntent.CAMPAIGN_SCHEDULE)
 evidence=TerritoryAIEvidenceRetriever(db)._campaign_schedule(campaign.id,manager,TerritoryAIQueryPlan(intent=TerritoryAIIntent.CAMPAIGN_SCHEDULE,source_kinds=plan.source_kinds,territory=None),None,"calendario")
 titles={e.title for e in evidence};assert "Debate IA sintético" in titles
 milestone_events=CalendarService(db).events(campaign.id,manager,date.today(),date.today()+timedelta(days=30))
 assert "Debate IA sintético" not in {e.title for e in milestone_events},"el hito oficial no debe aparecer en el Calendario de campaña"

def test_operational_alerts_intent_retrieves_real_alert_not_invented(db,admin,ctx):
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx;ops=OperationalService(db)
 ops.create_activity(campaign.id,TerritorialActivityCreate(activity_type_code="ASSEMBLY",title="Pendiente IA",description="Objetivo",activity_date=date.today()+timedelta(days=5),parish_id=parishes[0].id,status="PLANNED"),coordinator)
 AlertService(db).evaluate(campaign.id,manager,AlertEvaluationRequest(rule_codes=["ACTIVITY_PENDING_APPROVAL"],as_of_date=date.today()))
 router=TerritoryAIIntentRouter();intent=router.route("¿Qué requiere atención hoy?")
 assert intent==TerritoryAIIntent.OPERATIONAL_ALERTS
 plan=TerritoryAIQueryPlanner().plan(intent)
 evidence=TerritoryAIEvidenceRetriever(db)._operational_alert(campaign.id,manager,TerritoryAIQueryPlan(intent=intent,source_kinds=plan.source_kinds,territory=None),None,"alertas")
 assert any("aprobación" in e.title.lower() for e in evidence)
 assert all(e.evidence_class!="OFFICIAL" for e in evidence)

def test_territory_ai_http_query_answers_schedule_question(client,db,admin,admin_headers,ctx):
 campaign,province,canton,parishes,manager,coordinator,analyst=ctx;ops=OperationalService(db)
 ops.create_activity(campaign.id,TerritorialActivityCreate(activity_type_code="ASSEMBLY",title="Asamblea confirmada",description="Objetivo",activity_date=date.today()+timedelta(days=5),parish_id=parishes[0].id,status="PLANNED"),manager)
 FeatureEntitlementService(db).upsert(campaign.id,EntitlementUpsert(feature_code=FeatureCode.TERRITORY_AI,enabled=True,entitlement_type=EntitlementType.LICENSE,monthly_request_limit=None),admin)
 provider=_FakeProvider();app.dependency_overrides[get_ai_provider]=lambda:provider
 try:
  r=client.post(f"/api/v1/campaigns/{campaign.id}/territory-ai/query",headers=admin_headers,json={"question":"¿Cuáles son los próximos hitos electorales?"})
  assert r.status_code==200;body=r.json();assert body["intent"]=="CAMPAIGN_SCHEDULE" and body["status"]=="ANSWERED"
  assert body["citations"] and body["citations"][0]["evidence_class"]!="OFFICIAL"
 finally:app.dependency_overrides.pop(get_ai_provider,None)
