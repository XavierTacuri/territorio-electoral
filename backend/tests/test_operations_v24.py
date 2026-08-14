from datetime import date
import pytest
from sqlalchemy import select
from app.core.security import hash_password
from app.models.operational import Commitment
from app.models.security import SecurityAuditEvent
from app.models.user import User
from app.schemas.campaign import CampaignCreate,CampaignUserAssign,TerritorialAssignmentCreate
from app.schemas.operational import CitizenNeedCreate,CommitmentCreate,TerritorialActivityCreate,TerritorialActivityUpdate
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
    activity=service.create_activity(campaign.id,payload(parishes[0].id),delegate)
    assert activity.approval_status=="DRAFT" and activity.status=="PLANNED"
    service.submit_activity(campaign.id,activity.id,delegate);assert activity.approval_status=="PENDING_APPROVAL"
    with pytest.raises(PermissionError):service.approve_activity(campaign.id,activity.id,delegate)
    service.reject_activity(campaign.id,activity.id,manager,"Conflicto de horario");assert activity.approval_status=="REJECTED"
    service.update_activity(campaign.id,activity.id,TerritorialActivityUpdate(title="Asamblea corregida"),delegate)
    service.submit_activity(campaign.id,activity.id,delegate);service.approve_activity(campaign.id,activity.id,manager)
    assert activity.approval_status=="APPROVED" and activity.status=="PLANNED"
    service.update_activity(campaign.id,activity.id,TerritorialActivityUpdate(location_name="Casa comunal"),delegate)
    assert activity.approval_status=="PENDING_APPROVAL"
    events=list(db.scalars(select(SecurityAuditEvent).where(SecurityAuditEvent.resource_id==activity.id)))
    assert {x.event_type for x in events}>={"create","submit_for_approval","reject","resubmit","approve"}

def test_territorial_rbac_direct_need_validation_and_commitment(db,v24):
    campaign,parishes,manager,delegate=v24;service=OperationalService(db)
    with pytest.raises(PermissionError):service.create_activity(campaign.id,payload(parishes[1].id),delegate)
    need=service.create_need(campaign.id,None,CitizenNeedCreate(need_category_code="ROADS",title="Mantenimiento vial",description="Tramos deteriorados",priority="HIGH",urgency="HIGH",parish_id=parishes[0].id,source_type="ASSEMBLY",reported_date=date(2026,8,20),scope="PARISH"),delegate)
    with pytest.raises(PermissionError):service.create_need(campaign.id,None,CitizenNeedCreate(need_category_code="ROADS",title="Fuera de alcance",priority="HIGH",parish_id=parishes[1].id),delegate)
    service.review_need(campaign.id,need.id,delegate)
    with pytest.raises(PermissionError):service.validate_need(campaign.id,need.id,delegate)
    service.validate_need(campaign.id,need.id,manager,"Verificada en territorio")
    commitment=service.create_commitment(campaign.id,CommitmentCreate(need_id=need.id,title="Revisar propuesta técnica",priority="HIGH",parish_id=need.parish_id),manager)
    assert commitment.need_id==need.id and need.status=="IN_PLAN" and db.get(Commitment,commitment.id)

def test_execution_transitions_and_operations_summary(db,v24):
    campaign,parishes,manager,_=v24;service=OperationalService(db,today_provider=lambda:date(2026,8,13))
    activity=service.create_activity(campaign.id,payload(parishes[0].id).model_copy(update={"activity_date":date(2026,8,13)}),manager)
    assert activity.approval_status=="APPROVED"
    service.update_activity(campaign.id,activity.id,TerritorialActivityUpdate(status="IN_PROGRESS"),manager)
    service.update_activity(campaign.id,activity.id,TerritorialActivityUpdate(status="COMPLETED"),manager)
    with pytest.raises(BusinessRuleError):service.update_activity(campaign.id,activity.id,TerritorialActivityUpdate(status="PLANNED"),manager)
    summary=service.operations_overview(campaign.id,manager)
    assert summary["activities"]["completed"]==1 and summary["coverage"]["with_activities"]==1
