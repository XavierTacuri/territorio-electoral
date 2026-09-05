from datetime import date
import pytest
from sqlalchemy import select
from app.core.security import hash_password
from app.models.operational import CitizenNeed,Commitment
from app.models.security import SecurityAuditEvent
from app.models.user import User
from app.schemas.campaign import CampaignCreate,CampaignUserAssign,TerritorialAssignmentCreate
from app.schemas.operational import ActivityCancelRequest,ActivityCloseCommitmentCreate,ActivityCloseNeedCreate,ActivityCloseRequest,ActivitySuspendRequest,CitizenNeedCreate,CommitmentCreate,TerritorialActivityCreate,TerritorialActivityUpdate
from app.scripts.seed_gualaceo import seed as seed_territory
from app.services.activity_catalog_service import seed as seed_catalogs
from app.services.campaign_service import CampaignService
from app.services.exceptions import BusinessRuleError
from app.services.operational_service import OperationalService
from app.services.role_service import RoleService
from app.services.territorial_assignment_service import TerritorialAssignmentService

@pytest.fixture
def v24(db,admin):
    _,canton,parishes=seed_territory(db);seed_catalogs(db);db.commit()
    campaign=CampaignService(db).create(CampaignCreate(name="Operación V24",slug="operacion-v24",canton_id=canton.id,office_type="MAYOR",election_name="Elección sintética",election_date=date(2027,2,14),status="ACTIVE"),admin)
    roles=RoleService(db)
    def user(code,name):
        obj=User(email=f"{name}@example.test",username=name,first_name=name,last_name="E2E",hashed_password=hash_password("Testing123"),roles=[roles.repository.get_by_code(code)]);db.add(obj);db.flush();return obj
    manager=user("CAMPAIGN_MANAGER","manager_v24");delegate=user("TERRITORIAL_COORDINATOR","delegate_v24");db.commit()
    assignments=TerritorialAssignmentService(db)
    for member in (manager,delegate):assignments.assign_user(campaign.id,CampaignUserAssign(user_id=member.id),admin)
    assignments.create(campaign.id,TerritorialAssignmentCreate(user_id=delegate.id,parish_id=parishes[0].id),admin)
    return campaign,parishes,manager,delegate

def payload(parish,title="Asamblea territorial"):
    return TerritorialActivityCreate(activity_type_code="ASSEMBLY",title=title,description="Objetivo comunitario",activity_date=date(2026,8,20),parish_id=parish,status="PLANNED")

def test_approval_rejection_resubmit_and_material_edit(db,v24):
    campaign,parishes,manager,delegate=v24;service=OperationalService(db)
    manager.first_name="Manager";manager.last_name="Demo";db.flush()
    activity=service.create_activity(campaign.id,payload(parishes[0].id),delegate)
    assert activity.approval_status=="PENDING_APPROVAL" and activity.status=="PLANNED"
    with pytest.raises(PermissionError):service.approve_activity(campaign.id,activity.id,delegate)
    service.reject_activity(campaign.id,activity.id,manager,"Conflicto de horario");assert activity.approval_status=="REJECTED"
    assert service.activity(campaign.id,activity.id,manager).rejected_by=={"id":manager.id,"display_name":"Manager Demo","username":manager.username,"role_codes":["CAMPAIGN_MANAGER"]}
    service.update_activity(campaign.id,activity.id,TerritorialActivityUpdate(title="Asamblea corregida"),delegate)
    service.submit_activity(campaign.id,activity.id,delegate);service.approve_activity(campaign.id,activity.id,manager)
    assert activity.approval_status=="APPROVED" and activity.status=="PLANNED"
    service.update_activity(campaign.id,activity.id,TerritorialActivityUpdate(location_name="Casa comunal"),delegate)
    assert activity.approval_status=="PENDING_APPROVAL"
    events=list(db.scalars(select(SecurityAuditEvent).where(SecurityAuditEvent.resource_id==activity.id)))
    assert {x.event_type for x in events}>={"create","submit_for_approval","reject","resubmit","approve"}

def test_coordinator_cannot_resubmit_rejected_activity_outside_scope(db,v24):
    campaign,parishes,manager,delegate=v24;service=OperationalService(db)
    activity=service.create_activity(campaign.id,payload(parishes[1].id,title="Actividad fuera del scope"),manager)
    activity.approval_status="REJECTED";activity.rejection_reason="Requiere corrección";db.commit()
    with pytest.raises(PermissionError):service.submit_activity(campaign.id,activity.id,delegate)

def test_candidate_shares_executive_approval_capability(db,v24):
    campaign,parishes,manager,delegate=v24
    roles=RoleService(db)
    candidate=User(email="candidate-approval@example.test",username="candidate-approval",first_name="Candidate",last_name="Approval",hashed_password=hash_password("Testing123"),roles=[roles.repository.get_by_code("CANDIDATE")])
    db.add(candidate); db.flush(); TerritorialAssignmentService(db).assign_user(campaign.id,CampaignUserAssign(user_id=candidate.id),manager); db.commit()
    service=OperationalService(db)
    activity=service.create_activity(campaign.id,payload(parishes[0].id,title="Actividad para candidato"),delegate)
    service.approve_activity(campaign.id,activity.id,candidate)
    assert activity.approval_status=="APPROVED" and activity.approved_by_user_id==candidate.id
    activity2=service.create_activity(campaign.id,payload(parishes[0].id,title="Actividad para rechazo"),delegate)
    service.reject_activity(campaign.id,activity2.id,candidate,"Motivo de demostración")
    assert activity2.approval_status=="REJECTED" and activity2.rejected_by_user_id==candidate.id
    assert service.activity(campaign.id,activity2.id,candidate).rejected_by["display_name"]=="Candidate Approval"

def test_activity_actor_uses_username_when_name_is_missing(db,v24):
    campaign,parishes,manager,delegate=v24;service=OperationalService(db)
    manager.first_name="";manager.last_name="";db.flush()
    activity=service.create_activity(campaign.id,payload(parishes[0].id,title="Actor fallback"),delegate)
    service.reject_activity(campaign.id,activity.id,manager,"Requiere corrección")
    assert service.activity(campaign.id,activity.id,manager).rejected_by["display_name"]==manager.username

def test_activity_contract_includes_parish_name_without_replacing_id(db,v24):
    campaign,parishes,manager,delegate=v24; service=OperationalService(db)
    activity=service.create_activity(campaign.id,payload(parishes[0].id,title="Actividad con parroquia"),manager)
    listed=service.list_activities(campaign.id,manager,1,20).items
    result=next(x for x in listed if x.id==activity.id)
    assert result.parish_id==parishes[0].id and result.parish_name==parishes[0].name
    detail=service.activity(campaign.id,activity.id,manager)
    assert detail.parish_name==parishes[0].name

def test_structured_close_creates_need_and_commitment_atomically(db,v24):
    campaign,parishes,manager,delegate=v24; service=OperationalService(db)
    activity=service.create_activity(campaign.id,payload(parishes[0].id,title="Cierre estructurado"),manager)
    request=ActivityCloseRequest(summary="Se realizó la actividad y se recogieron observaciones comunitarias.",outcome_notes="Resultados agregados para demostración.",new_needs=[ActivityCloseNeedCreate(need_category_code="ROADS",title="Necesidad de cierre vial",priority="HIGH")],commitments=[ActivityCloseCommitmentCreate(title="Dar seguimiento al cierre",priority="HIGH",due_date=date(2026,9,1))])
    closed=service.complete_activity(campaign.id,activity.id,request,manager)
    assert closed.status=="COMPLETED" and closed.completion_summary==request.summary and closed.completed_by_user_id==manager.id
    need=next(iter(db.scalars(select(CitizenNeed).where(CitizenNeed.activity_id==activity.id))))
    commitment=db.scalar(select(Commitment).where(Commitment.activity_id==activity.id))
    assert need.campaign_id==campaign.id and need.parish_id==parishes[0].id and commitment and commitment.parish_id==parishes[0].id

def test_structured_close_links_existing_need_and_rejects_missing_summary(db,v24):
    campaign,parishes,manager,delegate=v24; service=OperationalService(db)
    outside=service.create_need(campaign.id,None,CitizenNeedCreate(need_category_code="ROADS",title="Necesidad fuera",priority="HIGH",parish_id=parishes[1].id),manager)
    need=service.create_need(campaign.id,None,CitizenNeedCreate(need_category_code="ROADS",title="Necesidad existente",priority="HIGH",parish_id=parishes[0].id),manager)
    activity=service.create_activity(campaign.id,payload(parishes[0].id,title="Cierre vinculado"),manager)
    with pytest.raises(Exception):service.complete_activity(campaign.id,activity.id,ActivityCloseRequest(summary="corta"),manager)
    with pytest.raises(Exception):service.complete_activity(campaign.id,activity.id,ActivityCloseRequest(summary="Se intentará vincular una necesidad fuera del territorio.",existing_need_ids=[outside.id]),manager)
    assert activity.status=="PLANNED"
    closed=service.complete_activity(campaign.id,activity.id,ActivityCloseRequest(summary="Se realizó el cierre y se vinculó la necesidad existente.",existing_need_ids=[need.id]),manager)
    assert closed.status=="COMPLETED" and db.get(type(need),need.id).mentions_count==2

def test_complete_retry_is_rejected_without_side_effects(db,v24):
    campaign,parishes,manager,delegate=v24;service=OperationalService(db)
    activity=service.create_activity(campaign.id,payload(parishes[0].id,title="Cierre repetido"),manager)
    closed=service.complete_activity(campaign.id,activity.id,ActivityCloseRequest(summary="Se realizó un cierre estructurado de demostración."),manager)
    completed_at=closed.completed_at;mentions_before=list(db.scalars(select(CitizenNeed).where(CitizenNeed.activity_id==activity.id)))
    with pytest.raises(BusinessRuleError):service.complete_activity(campaign.id,activity.id,ActivityCloseRequest(summary="Segundo intento de cierre."),manager)
    db.expire_all();current=db.get(type(activity),activity.id)
    assert current.status=="COMPLETED" and current.completed_at==completed_at and len(list(db.scalars(select(CitizenNeed).where(CitizenNeed.activity_id==activity.id))))==len(mentions_before)

def test_cancel_requires_reason_and_never_creates_closure_data(db,v24):
    campaign,parishes,manager,delegate=v24; service=OperationalService(db)
    activity=service.create_activity(campaign.id,payload(parishes[0].id,title="Cancelación estructurada"),manager)
    with pytest.raises(Exception):service.suspend_activity(campaign.id,activity.id,ActivitySuspendRequest(reason="  "),manager)
    suspended=service.suspend_activity(campaign.id,activity.id,ActivitySuspendRequest(reason="No se pudo realizar por agenda territorial."),manager)
    assert suspended.status=="SUSPENDED" and suspended.suspension_reason and suspended.completed_at is None
    resumed=service.resume_activity(campaign.id,activity.id,manager)
    assert resumed.status=="PLANNED" and resumed.suspension_reason
    with pytest.raises(BusinessRuleError):service.resume_activity(campaign.id,activity.id,manager)

def test_close_requires_approved_and_rolls_back_need_when_commitment_fails(db,v24,monkeypatch):
    campaign,parishes,manager,delegate=v24;service=OperationalService(db)
    draft=service.create_activity(campaign.id,payload(parishes[0].id,title="Cierre sin aprobación"),delegate)
    with pytest.raises(BusinessRuleError):service.complete_activity(campaign.id,draft.id,ActivityCloseRequest(summary="No debe cerrar mientras siga pendiente."),delegate)
    with pytest.raises(BusinessRuleError):service.suspend_activity(campaign.id,draft.id,ActivitySuspendRequest(reason="No debe suspender mientras siga pendiente."),delegate)
    assert draft.status=="PLANNED"
    activity=service.create_activity(campaign.id,payload(parishes[0].id,title="Rollback de cierre"),manager)
    original=service.responsible;calls=[0]
    def fail_after_need(campaign_id,user_id):
        calls[0]+=1
        if calls[0]>1: raise RuntimeError("fallo sintético de compromiso")
        return original(campaign_id,user_id)
    monkeypatch.setattr(service,"responsible",fail_after_need)
    request=ActivityCloseRequest(summary="Cierre que debe revertirse completamente.",new_needs=[ActivityCloseNeedCreate(need_category_code="ROADS",title="Necesidad rollback")],commitments=[ActivityCloseCommitmentCreate(title="Compromiso rollback")])
    with pytest.raises(RuntimeError):service.complete_activity(campaign.id,activity.id,request,manager)
    db.expire_all()
    assert db.get(type(activity),activity.id).status=="PLANNED"
    assert not list(db.scalars(select(CitizenNeed).where(CitizenNeed.activity_id==activity.id)))
    assert not list(db.scalars(select(Commitment).where(Commitment.activity_id==activity.id)))

def test_territorial_rbac_direct_need_validation_and_commitment(db,v24):
    campaign,parishes,manager,delegate=v24;service=OperationalService(db)
    with pytest.raises(PermissionError):service.create_activity(campaign.id,payload(parishes[1].id),delegate)
    need=service.create_need(campaign.id,None,CitizenNeedCreate(need_category_code="ROADS",title="Mantenimiento vial",description="Tramos deteriorados",priority="HIGH",urgency="HIGH",parish_id=parishes[0].id,source_type="ASSEMBLY",reported_date=date(2026,8,20),scope="PARISH"),delegate)
    with pytest.raises(PermissionError):service.create_need(campaign.id,None,CitizenNeedCreate(need_category_code="ROADS",title="Fuera de alcance",priority="HIGH",parish_id=parishes[1].id),delegate)
    service.review_need(campaign.id,need.id,delegate)
    with pytest.raises(PermissionError):service.validate_need(campaign.id,need.id,delegate)
    service.validate_need(campaign.id,need.id,manager,"Verificada en territorio")
    commitment=service.create_commitment(campaign.id,CommitmentCreate(need_id=need.id,title="Revisar propuesta técnica",priority="HIGH",parish_id=need.parish_id),manager)
    assert commitment.need_id==need.id and need.status=="VALIDATED" and db.get(Commitment,commitment.id)

def test_execution_transitions_and_operations_summary(db,v24):
    campaign,parishes,manager,_=v24;service=OperationalService(db,today_provider=lambda:date(2026,8,13))
    activity=service.create_activity(campaign.id,payload(parishes[0].id).model_copy(update={"activity_date":date(2026,8,13)}),manager)
    assert activity.approval_status=="APPROVED"
    with pytest.raises(BusinessRuleError):service.update_activity(campaign.id,activity.id,TerritorialActivityUpdate(status="IN_PROGRESS"),manager)
    with pytest.raises(BusinessRuleError):service.update_activity(campaign.id,activity.id,TerritorialActivityUpdate(status="COMPLETED"),manager)
    service.complete_activity(campaign.id,activity.id,ActivityCloseRequest(summary="Actividad completada mediante el cierre estructurado."),manager)
    summary=service.operations_overview(campaign.id,manager)
    assert summary["activities"]["completed"]==1 and summary["coverage"]["with_activities"]==1
