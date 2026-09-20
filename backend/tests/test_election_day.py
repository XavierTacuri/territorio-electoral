from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.security import hash_password
from app.models.assignments import CampaignUser
from app.models.campaign import Campaign
from app.models.election_day import ElectionDayAdminSupportSession, ElectionDayAssignment, ElectionDayDocument, ElectionDayIncident, ElectionDayOperation, ElectoralBoard, PollingPlace
from app.models.historical import DataSource, ElectoralContest, ElectoralProcess
from app.models.security import SecurityAuditEvent
from app.models.territory import Canton, Parish, Province
from app.models.user import User
from app.schemas.election_day import CheckInRequest, ElectionDayAdminSupportStartRequest, ElectionDayAssignmentCreate, ElectionDayAssignmentReplace, ElectionDayCloseRequest, ElectionDayIncidentCreate, ElectionDayIncidentResolve, ElectionDayOperationCreate
from app.schemas.alerts import AlertEvaluationRequest
from app.services.alert_service import AlertService
from app.services.election_day_admin_support_service import ElectionDayAdminSupportService
from app.services.election_day_service import ElectionDayService
from app.services.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.services.role_service import RoleService
from app.scripts.seed_reports_and_alerts import seed as seed_alert_rules


# ---------- Fixtures / helpers ----------

def _election_day_dataset(db, admin, index=1):
    province = Province(id=980 + index, code=f"{98 + index:02}", name=f"Provincia ED {index}")
    canton = Canton(id=980 + index, province_id=980 + index, code=f"{index:02}", dpa_code=f"{98 + index:02}{index:02}", name=f"Cantón ED {index}")
    parish_a = Parish(id=9900 + index * 2, canton_id=canton.id, code="01", dpa_code=f"{canton.dpa_code}01", name=f"Parroquia A ED {index}", parish_type="RURAL")
    parish_b = Parish(id=9900 + index * 2 + 1, canton_id=canton.id, code="02", dpa_code=f"{canton.dpa_code}02", name=f"Parroquia B ED {index}", parish_type="RURAL")
    db.add_all([province, canton, parish_a, parish_b])
    db.flush()
    campaign = Campaign(name=f"Campaña ED {index}", slug=f"ed-{index}-{uuid4().hex[:6]}", canton_id=canton.id, office_type="MAYOR", election_name=f"Elección ED {index}", election_date=date(2027, 2, 14), status="ACTIVE", created_by_user_id=admin.id)
    db.add(campaign)
    db.flush()
    source = DataSource(code=f"ED-{index}-{uuid4().hex[:4]}", institution="Consejo Nacional Electoral", dataset_name="Recintos ED", dataset_type="CNE_POLLING_PLACES", created_by_user_id=admin.id)
    db.add(source)
    db.flush()
    process = ElectoralProcess(code=f"ED-P-{index}-{uuid4().hex[:4]}", name=f"Proceso ED {index}", process_type="SECTIONAL", election_date=date(2027, 2, 14), year=2027, status="VALIDATED", is_final=True, source_id=source.id, is_active=True)
    db.add(process)
    db.flush()
    contest = ElectoralContest(electoral_process_id=process.id, office_type="MAYOR", name=f"Alcaldía ED {index}", vote_method="SINGLE_CHOICE", canton_id=canton.id, seats=1, is_active=True)
    db.add(contest)
    db.commit()
    return campaign, canton, parish_a, parish_b, process


def _polling_place(db, process, canton, parish, code="R01", name="Escuela Central", source_id=None):
    """Simula un recinto ya publicado por administración vía Data Hub (§1):
    se inserta directamente, nunca vía la API operativa de campaña."""
    place = PollingPlace(electoral_process_id=process.id, province_id=canton.province_id, canton_id=canton.id, parish_id=parish.id, official_code=code, name=name, is_active=True, data_source_id=source_id or process.source_id)
    db.add(place)
    db.commit()
    db.refresh(place)
    return place


def _board(db, place, code="J01", number=1, registered_voters=300):
    board = ElectoralBoard(polling_place_id=place.id, official_code=code, board_number=number, registered_voters=registered_voters, is_active=True)
    db.add(board)
    db.commit()
    db.refresh(board)
    return board


def _member(db, admin, campaign, code="TERRITORIAL_COORDINATOR"):
    role = RoleService(db).repository.get_by_code(code)
    suffix = uuid4().hex[:8]
    user = User(email=f"ed-{suffix}@example.test", username=f"ed-{suffix}", first_name="ED", last_name=code.title(), hashed_password=hash_password("MemberPass123"), is_active=True, roles=[role])
    db.add(user)
    db.flush()
    db.add(CampaignUser(campaign_id=campaign.id, user_id=user.id, assigned_by_user_id=admin.id, is_active=True))
    db.commit()
    return user


@pytest.fixture
def ed(db, admin):
    seed_alert_rules(db)
    db.commit()
    return _election_day_dataset(db, admin, 1)


def _create_operation(db, campaign, process, executive):
    return ElectionDayService(db).create_operation(campaign.id, ElectionDayOperationCreate(electoral_process_id=process.id, election_date=date(2027, 2, 14)), executive)


def _ready_operation(db, admin, campaign, canton, process, parish):
    """Jornada con datos oficiales + delegado + validador ya asignados: pasa
    el preflight y puede activarse. Devuelve (op, place, board, delegate,
    validator, executive)."""
    executive = _member(db, admin, campaign, "CANDIDATE")
    svc = ElectionDayService(db)
    op = _create_operation(db, campaign, process, executive)
    place = _polling_place(db, process, canton, parish)
    board = _board(db, place)
    delegate = _member(db, admin, campaign)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=delegate.id, assignment_role="POLLING_PLACE_DELEGATE", polling_place_id=place.id), executive)
    validator = _member(db, admin, campaign)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=validator.id, assignment_role="ACT_VALIDATOR"), executive)
    op = svc.open_operation(campaign.id, executive)
    return op, place, board, delegate, validator, executive


# ---------- Ownership: only CANDIDATE/CAMPAIGN_MANAGER, never admin by default ----------

def test_candidate_creates_operation(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    candidate = _member(db, admin, campaign, "CANDIDATE")
    op = _create_operation(db, campaign, process, candidate)
    assert op.status == "PREPARATION"


def test_manager_creates_operation(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    manager = _member(db, admin, campaign, "CAMPAIGN_MANAGER")
    op = _create_operation(db, campaign, process, manager)
    assert op.status == "PREPARATION"


def test_coordinator_cannot_create_operation(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    coordinator = _member(db, admin, campaign, "TERRITORIAL_COORDINATOR")
    with pytest.raises(PermissionError):
        _create_operation(db, campaign, process, coordinator)


def test_analyst_cannot_create_operation(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    analyst = _member(db, admin, campaign, "ANALYST")
    with pytest.raises(PermissionError):
        _create_operation(db, campaign, process, analyst)


def test_admin_cannot_create_or_activate_operation_by_implicit_privilege(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    with pytest.raises(PermissionError):
        _create_operation(db, campaign, process, admin)
    # Ni siquiera sobre una jornada ya creada por el equipo ejecutivo.
    executive = _member(db, admin, campaign, "CANDIDATE")
    _create_operation(db, campaign, process, executive)
    with pytest.raises(PermissionError):
        ElectionDayService(db).open_operation(campaign.id, admin)


def test_create_operation_requires_matching_electoral_contest(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    other_process = ElectoralProcess(code=f"UNRELATED-{uuid4().hex[:4]}", name="Proceso no relacionado", process_type="SECTIONAL", election_date=date(2027, 2, 14), year=2027, status="VALIDATED", is_final=True, source_id=process.source_id, is_active=True)
    db.add(other_process)
    db.commit()
    with pytest.raises(BusinessRuleError):
        _create_operation(db, campaign, other_process, executive)


def test_cannot_create_two_operations_for_same_campaign_and_process(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    _create_operation(db, campaign, process, executive)
    with pytest.raises(ConflictError):
        _create_operation(db, campaign, process, executive)


# ---------- Lifecycle: PREPARATION -> ACTIVE -> SCRUTINY -> CLOSED ----------

def test_lifecycle_preparation_active_scrutiny_closed(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    assert op.status == "ACTIVE" and op.opened_at is not None
    svc = ElectionDayService(db)
    op = svc.start_scrutiny(campaign.id, executive)
    assert op.status == "SCRUTINY" and op.scrutiny_started_at is not None and op.scrutiny_started_by_user_id == executive.id
    op = svc.close_operation(campaign.id, ElectionDayCloseRequest(), executive)
    assert op.status == "CLOSED" and op.closed_at is not None


def test_invalid_lifecycle_jumps_rejected(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db)
    # ACTIVE -> CLOSED (saltando SCRUTINY) debe rechazarse.
    with pytest.raises(BusinessRuleError):
        svc.close_operation(campaign.id, ElectionDayCloseRequest(), executive)
    svc.start_scrutiny(campaign.id, executive)
    # SCRUTINY -> ACTIVE (retroceso) no existe como operación válida.
    with pytest.raises(BusinessRuleError):
        svc.open_operation(campaign.id, executive)
    svc.close_operation(campaign.id, ElectionDayCloseRequest(), executive)
    with pytest.raises(BusinessRuleError):
        svc.start_scrutiny(campaign.id, executive)
    with pytest.raises(BusinessRuleError):
        svc.open_operation(campaign.id, executive)


def test_start_scrutiny_requires_executive(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    with pytest.raises(PermissionError):
        ElectionDayService(db).start_scrutiny(campaign.id, delegate)
    with pytest.raises(PermissionError):
        ElectionDayService(db).start_scrutiny(campaign.id, admin)


# ---------- Preflight ----------

def test_preflight_blocks_without_official_polling_places(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    _create_operation(db, campaign, process, executive)
    result = ElectionDayService(db).preflight(campaign.id, executive)
    assert result["ready"] is False
    assert any("recintos" in b.lower() for b in result["blockers"])


def test_preflight_blocks_without_delegate(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    svc = ElectionDayService(db)
    _create_operation(db, campaign, process, executive)
    place = _polling_place(db, process, canton, parish_a)
    _board(db, place)
    validator = _member(db, admin, campaign)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=validator.id, assignment_role="ACT_VALIDATOR"), executive)
    result = svc.preflight(campaign.id, executive)
    assert result["ready"] is False
    assert any("delegado" in b.lower() for b in result["blockers"])


def test_preflight_blocks_without_validator(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    svc = ElectionDayService(db)
    _create_operation(db, campaign, process, executive)
    place = _polling_place(db, process, canton, parish_a)
    _board(db, place)
    delegate = _member(db, admin, campaign)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=delegate.id, assignment_role="POLLING_PLACE_DELEGATE", polling_place_id=place.id), executive)
    result = svc.preflight(campaign.id, executive)
    assert result["ready"] is False
    assert any("validador" in b.lower() for b in result["blockers"])


def test_preflight_warns_uncovered_polling_places_without_blocking(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db)
    extra_place = _polling_place(db, process, canton, parish_b, code="R02", name="Escuela Norte")
    _board(db, extra_place)
    result = svc.preflight(campaign.id, executive)
    assert result["ready"] is True
    assert result["warnings"] and "1 recintos sin delegado" in result["warnings"][0]
    assert result["summary"]["uncovered_polling_places"] == 1


def test_preflight_requires_control_center_access(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    coordinator = _member(db, admin, campaign, "TERRITORIAL_COORDINATOR")
    with pytest.raises(PermissionError):
        ElectionDayService(db).preflight(campaign.id, coordinator)


# ---------- Assignments: delegate/validator shape rules ----------

def test_multiple_delegates_same_polling_place_allowed(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    svc = ElectionDayService(db)
    _create_operation(db, campaign, process, executive)
    place = _polling_place(db, process, canton, parish_a)
    d1 = _member(db, admin, campaign)
    d2 = _member(db, admin, campaign)
    a1 = svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=d1.id, assignment_role="POLLING_PLACE_DELEGATE", polling_place_id=place.id), executive)
    a2 = svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=d2.id, assignment_role="POLLING_PLACE_DELEGATE", polling_place_id=place.id), executive)
    assert a1.id != a2.id and a1.polling_place_id == a2.polling_place_id


def test_delegate_can_cover_multiple_polling_places(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    svc = ElectionDayService(db)
    _create_operation(db, campaign, process, executive)
    place1 = _polling_place(db, process, canton, parish_a, code="R01")
    place2 = _polling_place(db, process, canton, parish_b, code="R02")
    delegate = _member(db, admin, campaign)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=delegate.id, assignment_role="POLLING_PLACE_DELEGATE", polling_place_id=place1.id), executive)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=delegate.id, assignment_role="POLLING_PLACE_DELEGATE", polling_place_id=place2.id), executive)
    mine = svc.my_assignments(campaign.id, delegate)
    assert {a.polling_place_id for a in mine} == {place1.id, place2.id}


def test_validator_cannot_have_polling_place_id(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    svc = ElectionDayService(db)
    _create_operation(db, campaign, process, executive)
    place = _polling_place(db, process, canton, parish_a)
    validator = _member(db, admin, campaign)
    with pytest.raises(BusinessRuleError):
        svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=validator.id, assignment_role="ACT_VALIDATOR", polling_place_id=place.id), executive)


def test_delegate_requires_polling_place_id(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    svc = ElectionDayService(db)
    _create_operation(db, campaign, process, executive)
    delegate = _member(db, admin, campaign)
    with pytest.raises(BusinessRuleError):
        svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=delegate.id, assignment_role="POLLING_PLACE_DELEGATE"), executive)


def test_no_board_id_field_accepted_on_assignment_schema():
    from app.schemas.election_day import ElectionDayAssignmentCreate
    assert "board_id" not in ElectionDayAssignmentCreate.model_fields


def test_duplicate_delegate_same_polling_place_conflicts(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    svc = ElectionDayService(db)
    _create_operation(db, campaign, process, executive)
    place = _polling_place(db, process, canton, parish_a)
    delegate = _member(db, admin, campaign)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=delegate.id, assignment_role="POLLING_PLACE_DELEGATE", polling_place_id=place.id), executive)
    with pytest.raises(ConflictError):
        svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=delegate.id, assignment_role="POLLING_PLACE_DELEGATE", polling_place_id=place.id), executive)


def test_duplicate_validator_conflicts(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    svc = ElectionDayService(db)
    _create_operation(db, campaign, process, executive)
    validator = _member(db, admin, campaign)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=validator.id, assignment_role="ACT_VALIDATOR"), executive)
    with pytest.raises(ConflictError):
        svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=validator.id, assignment_role="ACT_VALIDATOR"), executive)


def test_assignment_role_invalid_rejected(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    svc = ElectionDayService(db)
    _create_operation(db, campaign, process, executive)
    someone = _member(db, admin, campaign)
    with pytest.raises(BusinessRuleError):
        svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=someone.id, assignment_role="BOARD_DELEGATE"), executive)


def test_coordinator_cannot_manage_assignments(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    svc = ElectionDayService(db)
    _create_operation(db, campaign, process, executive)
    place = _polling_place(db, process, canton, parish_a)
    coordinator = _member(db, admin, campaign, "TERRITORIAL_COORDINATOR")
    with pytest.raises(PermissionError):
        svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=coordinator.id, assignment_role="POLLING_PLACE_DELEGATE", polling_place_id=place.id), coordinator)


def test_admin_cannot_assign_delegates_by_implicit_privilege(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    svc = ElectionDayService(db)
    _create_operation(db, campaign, process, executive)
    place = _polling_place(db, process, canton, parish_a)
    someone = _member(db, admin, campaign)
    with pytest.raises(PermissionError):
        svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=someone.id, assignment_role="POLLING_PLACE_DELEGATE", polling_place_id=place.id), admin)


def test_replace_assignment_preserves_history_and_checkin(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db)
    assignment = svc.my_assignments(campaign.id, delegate)[0]
    svc.check_in(campaign.id, assignment.id, CheckInRequest(latitude=-2.9, longitude=-78.7), delegate)
    replacement = _member(db, admin, campaign)
    new_assignment = svc.replace_assignment(campaign.id, assignment.id, ElectionDayAssignmentReplace(user_id=replacement.id, reason="No disponible"), executive)
    db.refresh(assignment)
    assert assignment.status == "REPLACED" and assignment.checked_in_at is not None
    assert new_assignment.status == "ASSIGNED" and new_assignment.replaced_by_assignment_id is None
    assert assignment.replaced_by_assignment_id == new_assignment.id
    assert new_assignment.polling_place_id == place.id


def test_replace_assignment_rejects_same_user_as_duplicate(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db)
    assignment = svc.my_assignments(campaign.id, delegate)[0]
    with pytest.raises(BusinessRuleError):
        svc.replace_assignment(campaign.id, assignment.id, ElectionDayAssignmentReplace(user_id=delegate.id), executive)


def test_eligible_users_requires_executive(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    users = ElectionDayService(db).eligible_users(campaign.id, executive)
    assert delegate.id in {u.id for u in users}
    with pytest.raises(PermissionError):
        ElectionDayService(db).eligible_users(campaign.id, delegate)


# ---------- Access boundaries: Coordinator/Analyst/delegate/validator scope ----------

def test_delegate_sees_only_own_polling_places(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    other_place = _polling_place(db, process, canton, parish_b, code="R02", name="Escuela Norte")
    svc = ElectionDayService(db)
    visible = svc.list_polling_places(campaign.id, delegate)
    assert {p.id for p in visible} == {place.id}
    with pytest.raises(PermissionError):
        svc.polling_place_detail(campaign.id, other_place.id, delegate)
    with pytest.raises(PermissionError):
        svc.list_boards(campaign.id, delegate, other_place.id)
    # Su propio recinto sí es accesible.
    assert svc.polling_place_detail(campaign.id, place.id, delegate).id == place.id


def test_delegate_cannot_access_control_center(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db)
    with pytest.raises(PermissionError):
        svc.coverage(campaign.id, delegate)
    with pytest.raises(PermissionError):
        svc.control_center(campaign.id, delegate)
    with pytest.raises(PermissionError):
        svc.list_assignments(campaign.id, delegate)


def test_validator_cannot_access_control_center(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db)
    with pytest.raises(PermissionError):
        svc.control_center(campaign.id, validator)
    with pytest.raises(PermissionError):
        svc.coverage(campaign.id, validator)


def test_validator_access_is_limited_to_validation_screen(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    status = ElectionDayService(db).validation_status(campaign.id, validator)
    assert status == {"operation_status": "ACTIVE", "pending_reviews": 0}
    with pytest.raises(PermissionError):
        ElectionDayService(db).validation_status(campaign.id, delegate)


def test_coordinator_role_alone_has_no_election_day_access(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    coordinator = _member(db, admin, campaign, "TERRITORIAL_COORDINATOR")
    svc = ElectionDayService(db)
    with pytest.raises(PermissionError):
        svc.get_operation(campaign.id, coordinator)
    with pytest.raises(PermissionError):
        svc.list_polling_places(campaign.id, coordinator)
    with pytest.raises(PermissionError):
        svc.control_center(campaign.id, coordinator)


def test_analyst_has_no_election_day_access(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    analyst = _member(db, admin, campaign, "ANALYST")
    svc = ElectionDayService(db)
    with pytest.raises(PermissionError):
        svc.get_operation(campaign.id, analyst)
    with pytest.raises(PermissionError):
        svc.control_center(campaign.id, analyst)


# ---------- Cross-campaign / cross-canton / cross-process isolation ----------

def test_multi_campaign_isolation_of_operations_and_polling_places(db, admin):
    campaign_a, canton_a, parish_a1, parish_a2, process_a = _election_day_dataset(db, admin, 10)
    campaign_b, canton_b, parish_b1, parish_b2, process_b = _election_day_dataset(db, admin, 11)
    op_a, place_a, *_rest_a = _ready_operation(db, admin, campaign_a, canton_a, process_a, parish_a1)
    op_b, place_b, *_rest_b = _ready_operation(db, admin, campaign_b, canton_b, process_b, parish_b1)
    svc = ElectionDayService(db)
    executive_a = _rest_a[-1]
    places_in_a = svc.list_polling_places(campaign_a.id, executive_a)
    assert {p.id for p in places_in_a} == {place_a.id}
    with pytest.raises(NotFoundError):
        svc.polling_place_detail(campaign_a.id, place_b.id, executive_a)


def test_multi_canton_polling_places_isolated_by_canton_not_name(db, admin):
    campaign_a, canton_a, parish_a1, parish_a2, process_a = _election_day_dataset(db, admin, 20)
    campaign_b, canton_b, parish_b1, parish_b2, process_b = _election_day_dataset(db, admin, 21)
    executive_a = _member(db, admin, campaign_a, "CANDIDATE")
    executive_b = _member(db, admin, campaign_b, "CANDIDATE")
    svc = ElectionDayService(db)
    _create_operation(db, campaign_a, process_a, executive_a)
    _create_operation(db, campaign_b, process_b, executive_b)
    place_a = _polling_place(db, process_a, canton_a, parish_a1, code="SAME", name="Escuela Central")
    place_b = _polling_place(db, process_b, canton_b, parish_b1, code="SAME", name="Escuela Central")
    places_a = svc.list_polling_places(campaign_a.id, executive_a)
    places_b = svc.list_polling_places(campaign_b.id, executive_b)
    assert len(places_a) == 1 and len(places_b) == 1 and places_a[0].id != places_b[0].id


def test_cross_process_polling_places_never_mix(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    other_process = ElectoralProcess(code=f"OTHER-{uuid4().hex[:4]}", name="Otro proceso", process_type="SECTIONAL", election_date=date(2023, 2, 5), year=2023, status="VALIDATED", is_final=True, source_id=process.source_id, is_active=True)
    db.add(other_process)
    db.commit()
    svc = ElectionDayService(db)
    _create_operation(db, campaign, process, executive)
    _polling_place(db, process, canton, parish_a, code="R01", name="Recinto proceso actual")
    _polling_place(db, other_process, canton, parish_a, code="R01", name="Recinto proceso viejo")
    places = svc.list_polling_places(campaign.id, executive)
    assert [p.name for p in places] == ["Recinto proceso actual"]


# ---------- Admin support mode ----------

def test_admin_starts_and_ends_support_session(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    support = ElectionDayAdminSupportService(db)
    session = support.start(campaign.id, ElectionDayAdminSupportStartRequest(reason="Apoyo operativo"), admin)
    assert session.campaign_id == campaign.id and session.ended_at is None
    ended = support.end(campaign.id, admin)
    assert ended.ended_at is not None


def _second_admin(db):
    role = RoleService(db).repository.get_by_code("ADMIN")
    suffix = uuid4().hex[:8]
    user = User(email=f"admin2-{suffix}@example.test", username=f"admin2-{suffix}", first_name="Admin", last_name="Dos", hashed_password=hash_password("AdminPass123"), is_active=True, is_superuser=True, roles=[role])
    db.add(user)
    db.commit()
    return user


def test_admin_support_session_persists_beyond_the_request_that_created_it(db, admin, ed):
    """Simula "se cierra el navegador y vuelve a entrar": una instancia nueva
    del servicio, sin ningún estado en memoria, debe seguir viendo la sesión
    activa — la garantía vive en la fila de base de datos, nunca en el
    proceso (§18)."""
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    ElectionDayAdminSupportService(db).start(campaign.id, ElectionDayAdminSupportStartRequest(reason="Reingreso"), admin)
    # Nueva instancia del servicio (equivalente a una petición HTTP nueva tras
    # cerrar y reabrir el navegador): ningún estado en memoria del proceso.
    reentry = ElectionDayAdminSupportService(db).current(campaign.id, admin)
    assert reentry is not None and reentry.ended_at is None and reentry.reason == "Reingreso"
    assert ElectionDayService(db).control_center(campaign.id, admin)[0].id == op.id


def test_two_different_admins_can_each_hold_an_active_support_session(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    other_campaign, other_canton, other_parish_a, other_parish_b, other_process = _election_day_dataset(db, admin, 14)
    _ready_operation(db, admin, other_campaign, other_canton, other_process, other_parish_a)
    admin_two = _second_admin(db)
    support = ElectionDayAdminSupportService(db)
    session_one = support.start(campaign.id, ElectionDayAdminSupportStartRequest(), admin)
    session_two = support.start(other_campaign.id, ElectionDayAdminSupportStartRequest(), admin_two)
    assert session_one.ended_at is None and session_two.ended_at is None
    assert ElectionDayService(db).control_center(campaign.id, admin)[0].id == op.id
    # admin (uno) no puede ver el Centro de Control de la campaña de admin_two.
    with pytest.raises(PermissionError):
        ElectionDayService(db).control_center(other_campaign.id, admin)


def test_admin_without_support_gets_403_on_control_center(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    with pytest.raises(PermissionError):
        ElectionDayService(db).control_center(campaign.id, admin)


def test_admin_with_support_accesses_control_center(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    ElectionDayAdminSupportService(db).start(campaign.id, ElectionDayAdminSupportStartRequest(), admin)
    result_op, coverage = ElectionDayService(db).control_center(campaign.id, admin)
    assert result_op.id == op.id and coverage["total_polling_places"] == 1


def test_ending_support_revokes_control_center_access(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    support = ElectionDayAdminSupportService(db)
    support.start(campaign.id, ElectionDayAdminSupportStartRequest(), admin)
    support.end(campaign.id, admin)
    with pytest.raises(PermissionError):
        ElectionDayService(db).control_center(campaign.id, admin)


def test_admin_cannot_have_two_active_support_sessions(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    other_campaign, other_canton, other_parish_a, other_parish_b, other_process = _election_day_dataset(db, admin, 12)
    _ready_operation(db, admin, other_campaign, other_canton, other_process, other_parish_a)
    support = ElectionDayAdminSupportService(db)
    support.start(campaign.id, ElectionDayAdminSupportStartRequest(), admin)
    with pytest.raises(BusinessRuleError):
        support.start(other_campaign.id, ElectionDayAdminSupportStartRequest(), admin)
    # Reabrir sobre la MISMA campaña es idempotente.
    same = support.start(campaign.id, ElectionDayAdminSupportStartRequest(), admin)
    assert same.campaign_id == campaign.id


def test_admin_must_end_before_switching_campaign(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    other_campaign, other_canton, other_parish_a, other_parish_b, other_process = _election_day_dataset(db, admin, 13)
    _ready_operation(db, admin, other_campaign, other_canton, other_process, other_parish_a)
    support = ElectionDayAdminSupportService(db)
    support.start(campaign.id, ElectionDayAdminSupportStartRequest(), admin)
    support.end(campaign.id, admin)
    switched = support.start(other_campaign.id, ElectionDayAdminSupportStartRequest(), admin)
    assert switched.campaign_id == other_campaign.id


def test_admin_support_requires_existing_operation(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    with pytest.raises(NotFoundError):
        ElectionDayAdminSupportService(db).start(campaign.id, ElectionDayAdminSupportStartRequest(), admin)


def test_admin_support_events_are_audited(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    support = ElectionDayAdminSupportService(db)
    support.start(campaign.id, ElectionDayAdminSupportStartRequest(reason="Verificación"), admin)
    support.end(campaign.id, admin)
    events = {e.event_type for e in db.query(SecurityAuditEvent).filter(SecurityAuditEvent.campaign_id == campaign.id).all()}
    assert {"ELECTION_DAY_ADMIN_SUPPORT_STARTED", "ELECTION_DAY_ADMIN_SUPPORT_ENDED"} <= events


# ---------- Fase 3.1 §7: listado ADMIN de campañas con Jornada configurada ----------

def test_admin_support_campaigns_lists_only_ones_with_operation_ordered_by_status(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    ElectionDayService(db).open_operation(campaign.id, executive)  # ACTIVE

    other_campaign, other_canton, other_parish_a, other_parish_b, other_process = _election_day_dataset(db, admin, 16)
    other_executive = _member(db, admin, other_campaign, "CANDIDATE")
    _create_operation(db, other_campaign, other_process, other_executive)  # se queda en PREPARATION (nunca se activa)

    campaign_without_jornada = Campaign(
        name="Campaña sin jornada", slug=f"sin-jornada-{uuid4().hex[:6]}", canton_id=canton.id, office_type="MAYOR",
        election_name="Elección sin jornada", election_date=date(2027, 2, 14), status="ACTIVE", created_by_user_id=admin.id,
    )
    db.add(campaign_without_jornada)
    db.commit()

    rows = ElectionDayAdminSupportService(db).list_campaigns_with_operation(admin)
    by_campaign = {r["campaign_id"]: r for r in rows}
    assert campaign.id in by_campaign and other_campaign.id in by_campaign
    assert campaign_without_jornada.id not in by_campaign
    assert by_campaign[campaign.id]["operation_status"] == "ACTIVE"
    assert by_campaign[other_campaign.id]["operation_status"] == "PREPARATION"
    statuses = [r["operation_status"] for r in rows]
    assert statuses.index("ACTIVE") < statuses.index("PREPARATION")
    assert by_campaign[campaign.id]["campaign_name"] == campaign.name
    assert by_campaign[campaign.id]["organization_name"]


def test_admin_support_campaigns_denied_for_non_admin(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    with pytest.raises(PermissionError):
        ElectionDayAdminSupportService(db).list_campaigns_with_operation(executive)


def test_admin_support_campaigns_http_only_admin_and_scoped_to_operations(client, admin_headers, db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    _ready_operation(db, admin, campaign, canton, process, parish_a)

    resp = client.get("/api/v1/election-day/admin-support/campaigns", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert any(r["campaign_id"] == str(campaign.id) for r in payload)
    for row in payload:
        assert set(row.keys()) == {
            "campaign_id", "campaign_name", "organization_name", "operation_id", "operation_status", "election_date",
        }

    non_admin = _member(db, admin, campaign, "CAMPAIGN_MANAGER")
    login = client.post("/api/v1/auth/login", data={"username": non_admin.username, "password": "MemberPass123"})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    denied = client.get("/api/v1/election-day/admin-support/campaigns", headers=headers)
    assert denied.status_code == 403, denied.text


def test_executive_accesses_control_center_without_support(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    result_op, _coverage = ElectionDayService(db).control_center(campaign.id, executive)
    assert result_op.id == op.id


def test_admin_with_support_still_cannot_manage_lifecycle_or_assignments(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    ElectionDayAdminSupportService(db).start(campaign.id, ElectionDayAdminSupportStartRequest(), admin)
    svc = ElectionDayService(db)
    with pytest.raises(PermissionError):
        svc.start_scrutiny(campaign.id, admin)
    with pytest.raises(PermissionError):
        svc.close_operation(campaign.id, ElectionDayCloseRequest(), admin)
    someone = _member(db, admin, campaign)
    with pytest.raises(PermissionError):
        svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=someone.id, assignment_role="ACT_VALIDATOR"), admin)
    assignment = svc.my_assignments(campaign.id, delegate)[0]
    with pytest.raises(PermissionError):
        svc.replace_assignment(campaign.id, assignment.id, ElectionDayAssignmentReplace(user_id=someone.id), admin)


def test_admin_with_support_can_help_resolve_incident(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db)
    incident = svc.create_incident(campaign.id, ElectionDayIncidentCreate(polling_place_id=place.id, category="LOGISTICS", description="Falta mobiliario"), delegate)
    ElectionDayAdminSupportService(db).start(campaign.id, ElectionDayAdminSupportStartRequest(), admin)
    resolved = svc.resolve_incident(campaign.id, incident.id, ElectionDayIncidentResolve(status="RESOLVED"), admin)
    assert resolved.status == "RESOLVED"


# ---------- Check-in ----------

def test_delegate_checks_in_own_assignment(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db)
    assignment = svc.my_assignments(campaign.id, delegate)[0]
    result = svc.check_in(campaign.id, assignment.id, CheckInRequest(latitude=-2.9, longitude=-78.7), delegate)
    assert result.status == "CHECKED_IN"


def test_only_assigned_delegate_can_check_in_for_self(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db)
    assignment = svc.my_assignments(campaign.id, delegate)[0]
    other = _member(db, admin, campaign)
    with pytest.raises(PermissionError):
        svc.check_in(campaign.id, assignment.id, CheckInRequest(), other)
    # Ni el equipo ejecutivo hace check-in en nombre del delegado.
    with pytest.raises(PermissionError):
        svc.check_in(campaign.id, assignment.id, CheckInRequest(), executive)


def test_checkin_is_idempotent_by_client_generated_id(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db)
    assignment = svc.my_assignments(campaign.id, delegate)[0]
    cid = uuid4()
    first = svc.check_in(campaign.id, assignment.id, CheckInRequest(client_generated_id=cid), delegate)
    second = svc.check_in(campaign.id, assignment.id, CheckInRequest(client_generated_id=cid), delegate)
    assert first.checked_in_at == second.checked_in_at


def test_checkin_rejected_outside_active_status(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db)
    assignment = svc.my_assignments(campaign.id, delegate)[0]
    svc.start_scrutiny(campaign.id, executive)
    with pytest.raises(BusinessRuleError):
        svc.check_in(campaign.id, assignment.id, CheckInRequest(), delegate)


def test_replaced_assignment_denies_further_checkin(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db)
    assignment = svc.my_assignments(campaign.id, delegate)[0]
    replacement = _member(db, admin, campaign)
    svc.replace_assignment(campaign.id, assignment.id, ElectionDayAssignmentReplace(user_id=replacement.id), executive)
    with pytest.raises(PermissionError):
        svc.check_in(campaign.id, assignment.id, CheckInRequest(), delegate)


def test_validator_cannot_check_in(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db)
    assignment = svc.my_assignments(campaign.id, validator)[0]
    with pytest.raises(BusinessRuleError):
        svc.check_in(campaign.id, assignment.id, CheckInRequest(), validator)


# ---------- Incidents ----------

def test_delegate_creates_incident_for_own_recinto(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    incident = ElectionDayService(db).create_incident(campaign.id, ElectionDayIncidentCreate(polling_place_id=place.id, category="CONNECTIVITY", description="Sin señal"), delegate)
    assert incident.status == "OPEN"


def test_delegate_cannot_create_incident_outside_own_recinto(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    other_place = _polling_place(db, process, canton, parish_b, code="R02", name="Escuela Norte")
    with pytest.raises(PermissionError):
        ElectionDayService(db).create_incident(campaign.id, ElectionDayIncidentCreate(polling_place_id=other_place.id, category="OTHER", description="Fuera de alcance"), delegate)


def test_incident_offline_idempotent_by_client_generated_id(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db)
    cid = uuid4()
    first = svc.create_incident(campaign.id, ElectionDayIncidentCreate(polling_place_id=place.id, category="ACCESS", description="Puerta cerrada", client_generated_id=cid), delegate)
    second = svc.create_incident(campaign.id, ElectionDayIncidentCreate(polling_place_id=place.id, category="ACCESS", description="Puerta cerrada", client_generated_id=cid), delegate)
    assert first.id == second.id


def test_incident_creation_blocked_outside_active(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db)
    svc.start_scrutiny(campaign.id, executive)
    with pytest.raises(BusinessRuleError):
        svc.create_incident(campaign.id, ElectionDayIncidentCreate(polling_place_id=place.id, category="OTHER", description="Nueva en escrutinio"), delegate)


def test_executive_and_admin_support_read_all_incidents_delegate_reads_own(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db)
    other_place = _polling_place(db, process, canton, parish_b, code="R02", name="Escuela Norte")
    other_delegate = _member(db, admin, campaign)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=other_delegate.id, assignment_role="POLLING_PLACE_DELEGATE", polling_place_id=other_place.id), executive)
    svc.create_incident(campaign.id, ElectionDayIncidentCreate(polling_place_id=place.id, category="OTHER", description="Incidencia A"), delegate)
    svc.create_incident(campaign.id, ElectionDayIncidentCreate(polling_place_id=other_place.id, category="OTHER", description="Incidencia B"), other_delegate)
    assert len(svc.list_incidents(campaign.id, executive)) == 2
    own = svc.list_incidents(campaign.id, delegate)
    assert len(own) == 1 and own[0].polling_place_id == place.id


def test_only_executive_or_admin_support_resolves_incident(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db)
    incident = svc.create_incident(campaign.id, ElectionDayIncidentCreate(polling_place_id=place.id, category="OTHER", description="Pendiente"), delegate)
    with pytest.raises(PermissionError):
        svc.resolve_incident(campaign.id, incident.id, ElectionDayIncidentResolve(status="RESOLVED"), delegate)
    resolved = svc.resolve_incident(campaign.id, incident.id, ElectionDayIncidentResolve(status="RESOLVED", resolution_notes="Atendido"), executive)
    assert resolved.status == "RESOLVED" and resolved.resolved_at is not None


def test_resolve_incident_blocked_when_closed(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db)
    incident = svc.create_incident(campaign.id, ElectionDayIncidentCreate(polling_place_id=place.id, category="OTHER", description="Pendiente"), delegate)
    svc.start_scrutiny(campaign.id, executive)
    svc.close_operation(campaign.id, ElectionDayCloseRequest(), executive)
    with pytest.raises(BusinessRuleError):
        svc.resolve_incident(campaign.id, incident.id, ElectionDayIncidentResolve(status="RESOLVED"), executive)


def test_incident_categories_never_include_fraud_or_political_language():
    from app.services.election_day_service import INCIDENT_CATEGORIES
    assert INCIDENT_CATEGORIES == {"PERSONNEL", "ACCESS", "LOGISTICS", "DOCUMENTATION", "CONNECTIVITY", "OTHER"}


# ---------- Documents ----------

def test_delegate_uploads_document_for_own_recinto_and_downloads(db, admin, ed, tmp_path):
    from app.services.evidence_storage_service import LocalEvidenceStorage
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db, LocalEvidenceStorage(str(tmp_path), 10))
    pdf_bytes = b"%PDF-1.4 fixture"
    doc = svc.upload_document(campaign.id, delegate, polling_place_id=place.id, board_id=None, document_type="ACTA_COPY", file_bytes=pdf_bytes, original_filename="acta.pdf", client_generated_id=None)
    assert doc.status == "RECEIVED" and doc.sha256
    path, obj = svc.document_file(campaign.id, doc.id, delegate)
    assert path.exists() and path.read_bytes() == pdf_bytes
    path, obj = svc.document_file(campaign.id, doc.id, executive)
    assert path.exists()


def test_document_upload_rejected_outside_own_recinto(db, admin, ed, tmp_path):
    from app.services.evidence_storage_service import LocalEvidenceStorage
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    other_place = _polling_place(db, process, canton, parish_b, code="R02", name="Escuela Norte")
    svc = ElectionDayService(db, LocalEvidenceStorage(str(tmp_path), 10))
    with pytest.raises(PermissionError):
        svc.upload_document(campaign.id, delegate, polling_place_id=other_place.id, board_id=None, document_type="ACTA_COPY", file_bytes=b"%PDF-1.4 fixture", original_filename="acta.pdf", client_generated_id=None)


def test_document_rejects_non_pdf_non_image_content(db, admin, ed, tmp_path):
    from app.services.evidence_storage_service import LocalEvidenceStorage
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db, LocalEvidenceStorage(str(tmp_path), 10))
    with pytest.raises(BusinessRuleError):
        svc.upload_document(campaign.id, delegate, polling_place_id=place.id, board_id=None, document_type="ACTA_COPY", file_bytes=b"not a real file", original_filename="acta.txt", client_generated_id=None)


def test_document_upload_idempotent_by_client_generated_id(db, admin, ed, tmp_path):
    from app.services.evidence_storage_service import LocalEvidenceStorage
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db, LocalEvidenceStorage(str(tmp_path), 10))
    cid = uuid4()
    first = svc.upload_document(campaign.id, delegate, polling_place_id=place.id, board_id=None, document_type="ACTA_COPY", file_bytes=b"%PDF-1.4 fixture", original_filename="acta.pdf", client_generated_id=cid)
    second = svc.upload_document(campaign.id, delegate, polling_place_id=place.id, board_id=None, document_type="ACTA_COPY", file_bytes=b"%PDF-1.4 fixture", original_filename="acta.pdf", client_generated_id=cid)
    assert first.id == second.id


def test_document_upload_blocked_outside_active(db, admin, ed, tmp_path):
    from app.services.evidence_storage_service import LocalEvidenceStorage
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db, LocalEvidenceStorage(str(tmp_path), 10))
    svc.start_scrutiny(campaign.id, executive)
    with pytest.raises(BusinessRuleError):
        svc.upload_document(campaign.id, delegate, polling_place_id=place.id, board_id=None, document_type="ACTA_COPY", file_bytes=b"%PDF-1.4 fixture", original_filename="acta.pdf", client_generated_id=None)


def test_update_document_status_requires_executive(db, admin, ed, tmp_path):
    from app.services.evidence_storage_service import LocalEvidenceStorage
    from app.schemas.election_day import ElectionDayDocumentStatusUpdate
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db, LocalEvidenceStorage(str(tmp_path), 10))
    doc = svc.upload_document(campaign.id, delegate, polling_place_id=place.id, board_id=None, document_type="ACTA_COPY", file_bytes=b"%PDF-1.4 fixture", original_filename="acta.pdf", client_generated_id=None)
    with pytest.raises(PermissionError):
        svc.update_document_status(campaign.id, doc.id, ElectionDayDocumentStatusUpdate(status="VALIDATED"), delegate)
    updated = svc.update_document_status(campaign.id, doc.id, ElectionDayDocumentStatusUpdate(status="VALIDATED"), executive)
    assert updated.status == "VALIDATED"


# ---------- My assignments (plural) ----------

def test_my_assignments_returns_all_active_assignments(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db)
    other_place = _polling_place(db, process, canton, parish_b, code="R02", name="Escuela Norte")
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=delegate.id, assignment_role="POLLING_PLACE_DELEGATE", polling_place_id=other_place.id), executive)
    mine = svc.my_assignments(campaign.id, delegate)
    assert {a.polling_place_id for a in mine} == {place.id, other_place.id}
    legacy = svc.my_assignment(campaign.id, delegate)
    assert legacy is not None and legacy.id in {a.id for a in mine}


# ---------- Smart Alerts (regression) ----------

def test_election_place_and_board_uncovered_alerts(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    svc = ElectionDayService(db)
    _create_operation(db, campaign, process, executive)
    place = _polling_place(db, process, canton, parish_a)
    _board(db, place)
    # Se activa la fila directamente, sin pasar por el preflight estricto,
    # deliberadamente sin delegado/validador — es justo el escenario que la
    # alerta de cobertura debe detectar.
    db.execute(ElectionDayOperation.__table__.update().where(ElectionDayOperation.campaign_id == campaign.id).values(status="ACTIVE", opened_at=datetime.now(timezone.utc), opened_by_user_id=executive.id))
    db.commit()
    result = AlertService(db).evaluate(campaign.id, admin, AlertEvaluationRequest(rule_codes=["ELECTION_PLACE_UNCOVERED", "BOARD_UNCOVERED"], as_of_date=date(2027, 2, 14)))
    assert result["created"] == 2
    items, _ = AlertService(db).list(campaign.id, admin, status="OPEN")
    assert {i.evidence.get("polling_place_name") for i in items if "polling_place_name" in i.evidence} == {"Escuela Central"}


def test_election_place_uncovered_resolves_once_assigned(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    req = AlertEvaluationRequest(rule_codes=["ELECTION_PLACE_UNCOVERED"], as_of_date=date(2027, 2, 14))
    AlertService(db).evaluate(campaign.id, admin, req)
    items, _ = AlertService(db).list(campaign.id, admin, status="OPEN")
    assert items == []


def test_open_election_incident_alert(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    ElectionDayService(db).create_incident(campaign.id, ElectionDayIncidentCreate(polling_place_id=place.id, category="CONNECTIVITY", description="Sin señal"), delegate)
    result = AlertService(db).evaluate(campaign.id, admin, AlertEvaluationRequest(rule_codes=["OPEN_ELECTION_INCIDENT"], as_of_date=date(2027, 2, 14)))
    assert result["created"] == 1


def test_board_document_missing_alert(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    result = AlertService(db).evaluate(campaign.id, admin, AlertEvaluationRequest(rule_codes=["BOARD_DOCUMENT_MISSING"], as_of_date=date(2027, 2, 14)))
    assert result["created"] == 1


def test_assigned_person_not_checked_in_respects_grace_period(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    req = AlertEvaluationRequest(rule_codes=["ASSIGNED_PERSON_NOT_CHECKED_IN"], as_of_date=date(2027, 2, 14))
    result = AlertService(db).evaluate(campaign.id, admin, req)
    assert result["created"] == 0, "aun dentro del umbral de gracia, no debe alertar"
    op.opened_at = datetime.now(timezone.utc) - timedelta(minutes=90)
    db.commit()
    result = AlertService(db).evaluate(campaign.id, admin, req)
    assert result["created"] >= 1


def test_alert_severities_are_operational_never_political(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    from app.models.alerts import AlertRule
    codes = {"ELECTION_PLACE_UNCOVERED", "BOARD_UNCOVERED", "ASSIGNED_PERSON_NOT_CHECKED_IN", "OPEN_ELECTION_INCIDENT", "BOARD_DOCUMENT_MISSING", "OFFLINE_SYNC_FAILURE"}
    rules = list(db.query(AlertRule).filter(AlertRule.code.in_(codes)))
    assert len(rules) == 6
    assert all(r.default_severity in {"INFO", "WARNING"} for r in rules)


# ---------- Informe de Jornada Electoral (regression) ----------

def test_election_day_report_requires_existing_operation(db, admin, ed):
    from app.schemas.reports import ReportGenerationRequest
    from app.services.report_service import ReportService
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    request = ReportGenerationRequest(template_code="ELECTION_DAY_REPORT", format="PDF", title="Informe de jornada", report_date=date(2027, 2, 14))
    with pytest.raises(ValueError):
        ReportService(db).preview(campaign.id, request, executive)


def test_election_day_report_shows_coverage_incidents_documents_and_no_results(db, admin, ed, tmp_path):
    from app.schemas.reports import ReportGenerationRequest
    from app.services.report_service import ReportService
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    ElectionDayService(db).create_incident(campaign.id, ElectionDayIncidentCreate(polling_place_id=place.id, category="LOGISTICS", description="Falta de mobiliario"), delegate)
    request = ReportGenerationRequest(template_code="ELECTION_DAY_REPORT", format="PDF", title="Informe de jornada", report_date=date(2027, 2, 14))
    preview = ReportService(db).preview(campaign.id, request, executive)
    titles = {s.title for s in preview.sections}
    assert {"Estado de la jornada", "Incidencias", "Documentación recibida", "Aviso"} <= titles
    full_text = " ".join((s.text or "") + " ".join(str(v) for row in s.rows for v in row) for s in preview.sections)
    for banned in ("ganador", "porcentaje electoral", "candidato", "votos"):
        assert banned not in full_text.casefold()
    assert "PROVISIONAL" in full_text


def test_election_day_report_no_longer_provisional_after_closing(db, admin, ed, tmp_path):
    from app.schemas.reports import ReportGenerationRequest
    from app.services.report_service import ReportService
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db)
    svc.start_scrutiny(campaign.id, executive)
    svc.close_operation(campaign.id, ElectionDayCloseRequest(), executive)
    request = ReportGenerationRequest(template_code="ELECTION_DAY_REPORT", format="PDF", title="Informe de jornada", report_date=date(2027, 2, 14))
    preview = ReportService(db).preview(campaign.id, request, executive)
    full_text = " ".join((s.text or "") for s in preview.sections)
    assert "PROVISIONAL" not in full_text
    assert any(s.title == "Estado de la jornada" and any(row == ["Estado", "Jornada cerrada"] for row in s.rows) for s in preview.sections)


def test_election_day_report_generates_pdf_and_persists(db, admin, ed, tmp_path):
    from app.schemas.reports import ReportGenerationRequest
    from app.services.report_service import ReportService
    from app.services.report_storage_service import LocalReportStorage
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    service = ReportService(db, LocalReportStorage(str(tmp_path), 10))
    run = service.generate(campaign.id, ReportGenerationRequest(template_code="ELECTION_DAY_REPORT", format="PDF", title="Informe de jornada", report_date=date(2027, 2, 14)), executive)
    assert run.status == "COMPLETED"
    artifact = service.artifact(run)
    assert artifact is not None and artifact.original_download_name.startswith("informe-jornada-electoral-")


# ---------- Territorio IA (regression) ----------

def test_territory_ai_intent_routes_election_day_questions(db, admin):
    from app.schemas.territory_ai import TerritoryAIIntent
    from app.services.territory_ai_intent import TerritoryAIIntentRouter
    router = TerritoryAIIntentRouter()
    for question in ("¿Cuál es el estado operativo de la jornada?", "¿Qué recintos tienen incidencias abiertas?", "¿Qué documentación falta recibir?"):
        assert router.route(question) == TerritoryAIIntent.ELECTION_DAY_OPERATIONS


def test_territory_ai_retrieval_returns_real_election_day_facts_not_invented(db, admin, ed):
    from app.schemas.territory_ai import TerritoryAIIntent, TerritoryAIQueryPlan
    from app.services.territory_ai_planner import TerritoryAIQueryPlanner
    from app.services.territory_ai_retrieval import TerritoryAIEvidenceRetriever
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    ElectionDayService(db).create_incident(campaign.id, ElectionDayIncidentCreate(polling_place_id=place.id, category="CONNECTIVITY", description="Sin señal"), delegate)
    plan = TerritoryAIQueryPlanner().plan(TerritoryAIIntent.ELECTION_DAY_OPERATIONS)
    evidence = TerritoryAIEvidenceRetriever(db)._election_day(campaign.id, admin, TerritoryAIQueryPlan(intent=plan.intent, source_kinds=plan.source_kinds, territory=None), None, "jornada")
    assert evidence[0].structured_data["total_polling_places"] == 1
    assert any("Escuela Central" in e.title for e in evidence[1:])
    assert all("porcentaje" not in str(e.structured_data).lower() and "ganador" not in str(e.structured_data).lower() for e in evidence)


def test_territory_ai_blocks_who_is_winning_questions_for_election_day(db, admin):
    from app.services.territory_ai_policy import TerritoryAIPolicy
    policy = TerritoryAIPolicy()
    for question in ("¿Dónde vamos ganando?", "¿Qué actas muestran ventaja?"):
        assert not policy.evaluate(question).allowed


# ---------- HTTP integration ----------

def _login(client, username, password="MemberPass123"):
    response = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_manual_polling_place_and_board_creation_no_longer_exposed(db, admin, admin_headers, client, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    headers = _login(client, executive.username)
    client.post(f"/api/v1/campaigns/{campaign.id}/election-day/operation", headers=headers, json={"electoral_process_id": str(process.id), "election_date": "2027-02-14"})
    place_resp = client.post(f"/api/v1/campaigns/{campaign.id}/election-day/polling-places", headers=headers, json={"official_code": "R01", "name": "Escuela Central", "parish_id": parish_a.id})
    assert place_resp.status_code == 405
    place = _polling_place(db, process, canton, parish_a)
    board_resp = client.post(f"/api/v1/campaigns/{campaign.id}/election-day/polling-places/{place.id}/boards", headers=headers, json={"official_code": "J01", "board_number": 1})
    assert board_resp.status_code == 405


def test_http_full_flow_admin_never_creates_or_activates(db, admin, admin_headers, client, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    headers = _login(client, executive.username)
    create = client.post(f"/api/v1/campaigns/{campaign.id}/election-day/operation", headers=headers, json={"electoral_process_id": str(process.id), "election_date": "2027-02-14"})
    assert create.status_code == 201
    admin_create = client.post(f"/api/v1/campaigns/{campaign.id}/election-day/operation", headers=admin_headers, json={"electoral_process_id": str(process.id), "election_date": "2027-02-14"})
    assert admin_create.status_code == 403
    admin_open = client.post(f"/api/v1/campaigns/{campaign.id}/election-day/operation/open", headers=admin_headers)
    assert admin_open.status_code == 403


def test_http_admin_support_flow(db, admin, admin_headers, client, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    denied = client.get(f"/api/v1/campaigns/{campaign.id}/election-day/control-center", headers=admin_headers)
    assert denied.status_code == 403
    start = client.post(f"/api/v1/campaigns/{campaign.id}/election-day/admin-support/start", headers=admin_headers, json={"reason": "Verificación"})
    assert start.status_code == 201
    granted = client.get(f"/api/v1/campaigns/{campaign.id}/election-day/control-center", headers=admin_headers)
    assert granted.status_code == 200
    end = client.post(f"/api/v1/campaigns/{campaign.id}/election-day/admin-support/end", headers=admin_headers)
    assert end.status_code == 200
    denied_again = client.get(f"/api/v1/campaigns/{campaign.id}/election-day/control-center", headers=admin_headers)
    assert denied_again.status_code == 403


def test_http_cross_campaign_isolation(db, admin, admin_headers, client):
    campaign, canton, parish_a, parish_b, process = _election_day_dataset(db, admin, 30)
    other_campaign, _other_canton, other_parish_a, _other_parish_b, other_process = _election_day_dataset(db, admin, 31)
    executive = _member(db, admin, campaign, "CANDIDATE")
    headers = _login(client, executive.username)
    create = client.post(f"/api/v1/campaigns/{campaign.id}/election-day/operation", headers=headers, json={"electoral_process_id": str(process.id), "election_date": "2027-02-14"})
    assert create.status_code == 201
    place = _polling_place(db, process, canton, parish_a)
    _board(db, place)
    delegate = _member(db, admin, campaign)
    assign = client.post(f"/api/v1/campaigns/{campaign.id}/election-day/assignments", headers=headers, json={"user_id": str(delegate.id), "assignment_role": "POLLING_PLACE_DELEGATE", "polling_place_id": str(place.id)})
    assert assign.status_code == 201
    validator = _member(db, admin, campaign)
    client.post(f"/api/v1/campaigns/{campaign.id}/election-day/assignments", headers=headers, json={"user_id": str(validator.id), "assignment_role": "ACT_VALIDATOR"})
    opened = client.post(f"/api/v1/campaigns/{campaign.id}/election-day/operation/open", headers=headers)
    assert opened.status_code == 200 and opened.json()["status"] == "ACTIVE"
    # Un ejecutivo con acceso legítimo a OTRA campaña sigue sin poder ver el
    # recinto de esta: el aislamiento es por campaña, no por privilegio general.
    other_executive = _member(db, admin, other_campaign, "CANDIDATE")
    other_headers = _login(client, other_executive.username)
    client.post(f"/api/v1/campaigns/{other_campaign.id}/election-day/operation", headers=other_headers, json={"electoral_process_id": str(other_process.id), "election_date": "2027-02-14"})
    cross = client.get(f"/api/v1/campaigns/{other_campaign.id}/election-day/polling-places/{place.id}", headers=other_headers)
    assert cross.status_code == 404
    other_operation = client.get(f"/api/v1/campaigns/{other_campaign.id}/election-day/operation", headers=admin_headers)
    assert other_operation.status_code == 403


def test_http_rbac_matrix_direct_url_access(db, admin, admin_headers, client, ed):
    """Validación de cierre §3: la matriz completa de RBAC contra la URL real
    del API (TestClient sobre las rutas HTTP), no solo contra la capa de
    servicio — cada rol golpea el endpoint real con su propio token."""
    campaign, canton, parish_a, parish_b, process = ed
    base = f"/api/v1/campaigns/{campaign.id}/election-day"

    candidate = _member(db, admin, campaign, "CANDIDATE")
    candidate_headers = _login(client, candidate.username)
    coordinator = _member(db, admin, campaign, "TERRITORIAL_COORDINATOR")
    coordinator_headers = _login(client, coordinator.username)
    analyst = _member(db, admin, campaign, "ANALYST")
    analyst_headers = _login(client, analyst.username)

    # ---- CANDIDATE: ciclo de vida completo por HTTP ----
    create = client.post(f"{base}/operation", headers=candidate_headers, json={"electoral_process_id": str(process.id), "election_date": "2027-02-14"})
    assert create.status_code == 201, create.text

    # ---- ADMIN sin soporte: 403 en todo, incluida la creación/activación ----
    assert client.post(f"{base}/operation", headers=admin_headers, json={"electoral_process_id": str(process.id), "election_date": "2027-02-14"}).status_code == 403
    assert client.post(f"{base}/operation/open", headers=admin_headers).status_code == 403
    assert client.get(f"{base}/control-center", headers=admin_headers).status_code == 403

    # ---- TERRITORIAL_COORDINATOR / ANALYST: 403 en Jornada Electoral ----
    assert client.get(f"{base}/operation", headers=coordinator_headers).status_code == 403
    assert client.get(f"{base}/control-center", headers=coordinator_headers).status_code == 403
    assert client.get(f"{base}/operation", headers=analyst_headers).status_code == 403
    assert client.get(f"{base}/control-center", headers=analyst_headers).status_code == 403

    # Datos oficiales (simulan Data Hub) + personal operativo, vía CANDIDATE.
    place = _polling_place(db, process, canton, parish_a)
    other_place = _polling_place(db, process, canton, parish_b, code="R02", name="Escuela Norte")
    _board(db, place)
    delegate = _member(db, admin, campaign)
    delegate_headers = _login(client, delegate.username)
    validator = _member(db, admin, campaign)
    validator_headers = _login(client, validator.username)

    assign_delegate = client.post(f"{base}/assignments", headers=candidate_headers, json={"user_id": str(delegate.id), "assignment_role": "POLLING_PLACE_DELEGATE", "polling_place_id": str(place.id)})
    assert assign_delegate.status_code == 201
    assign_validator = client.post(f"{base}/assignments", headers=candidate_headers, json={"user_id": str(validator.id), "assignment_role": "ACT_VALIDATOR"})
    assert assign_validator.status_code == 201

    # ---- ADMIN sin soporte tampoco puede asignar ----
    someone = _member(db, admin, campaign)
    assert client.post(f"{base}/assignments", headers=admin_headers, json={"user_id": str(someone.id), "assignment_role": "ACT_VALIDATOR"}).status_code == 403

    opened = client.post(f"{base}/operation/open", headers=candidate_headers)
    assert opened.status_code == 200 and opened.json()["status"] == "ACTIVE"

    # ---- POLLING_PLACE_DELEGATE: solo su(s) recinto(s), nunca Centro de Control ----
    assert client.get(f"{base}/polling-places/{place.id}", headers=delegate_headers).status_code == 200
    assert client.get(f"{base}/polling-places/{other_place.id}", headers=delegate_headers).status_code == 403
    assert client.get(f"{base}/control-center", headers=delegate_headers).status_code == 403
    mine = client.get(f"{base}/my-assignments", headers=delegate_headers)
    assert mine.status_code == 200 and len(mine.json()) == 1 and mine.json()[0]["assignment_role"] == "POLLING_PLACE_DELEGATE"

    # ---- ACT_VALIDATOR: solo /validation, nunca Centro de Control ----
    assert client.get(f"{base}/validation", headers=validator_headers).status_code == 200
    assert client.get(f"{base}/control-center", headers=validator_headers).status_code == 403
    assert client.get(f"{base}/validation", headers=delegate_headers).status_code == 403
    assert client.get(f"{base}/validation", headers=candidate_headers).status_code == 403

    # ---- ADMIN con soporte activo: entra al Centro de Control, sigue sin ser propietario ----
    start_support = client.post(f"{base}/admin-support/start", headers=admin_headers, json={"reason": "Auditoría de cierre"})
    assert start_support.status_code == 201
    assert client.get(f"{base}/control-center", headers=admin_headers).status_code == 200
    assert client.post(f"{base}/operation/start-scrutiny", headers=admin_headers).status_code == 403
    assert client.post(f"{base}/assignments", headers=admin_headers, json={"user_id": str(someone.id), "assignment_role": "ACT_VALIDATOR"}).status_code == 403
    end_support = client.post(f"{base}/admin-support/end", headers=admin_headers)
    assert end_support.status_code == 200
    assert client.get(f"{base}/control-center", headers=admin_headers).status_code == 403

    # ---- CANDIDATE: escrutinio y cierre por HTTP ----
    assert client.post(f"{base}/operation/start-scrutiny", headers=candidate_headers).status_code == 200
    assert client.post(f"{base}/operation/close", headers=candidate_headers, json={}).status_code == 200


def test_http_campaign_manager_full_lifecycle_direct_url(db, admin, client):
    """Mismo recorrido que CANDIDATE, pero como CAMPAIGN_MANAGER, en una
    campaña propia — confirma que ambos roles ejecutivos comparten exactamente
    el mismo comportamiento por HTTP directo."""
    campaign, canton, parish_a, parish_b, process = _election_day_dataset(db, admin, 40)
    base = f"/api/v1/campaigns/{campaign.id}/election-day"
    manager = _member(db, admin, campaign, "CAMPAIGN_MANAGER")
    headers = _login(client, manager.username)

    assert client.post(f"{base}/operation", headers=headers, json={"electoral_process_id": str(process.id), "election_date": "2027-02-14"}).status_code == 201
    place = _polling_place(db, process, canton, parish_a)
    _board(db, place)
    delegate = _member(db, admin, campaign)
    validator = _member(db, admin, campaign)
    assert client.post(f"{base}/assignments", headers=headers, json={"user_id": str(delegate.id), "assignment_role": "POLLING_PLACE_DELEGATE", "polling_place_id": str(place.id)}).status_code == 201
    assert client.post(f"{base}/assignments", headers=headers, json={"user_id": str(validator.id), "assignment_role": "ACT_VALIDATOR"}).status_code == 201
    assert client.post(f"{base}/operation/open", headers=headers).status_code == 200
    assert client.get(f"{base}/control-center", headers=headers).status_code == 200
    assert client.post(f"{base}/operation/start-scrutiny", headers=headers).status_code == 200
    assert client.post(f"{base}/operation/close", headers=headers, json={}).status_code == 200
