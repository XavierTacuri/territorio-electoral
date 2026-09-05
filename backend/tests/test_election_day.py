from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.security import hash_password
from app.models.assignments import CampaignUser, TerritorialAssignment
from app.models.campaign import Campaign
from app.models.election_day import ElectionDayAssignment, ElectionDayDocument, ElectionDayIncident, ElectionDayOperation, ElectoralBoard, PollingPlace
from app.models.historical import DataSource, ElectoralContest, ElectoralProcess
from app.models.territory import Canton, Parish, Province
from app.models.user import User
from app.schemas.election_day import CheckInRequest, ElectionDayAssignmentCreate, ElectionDayAssignmentReplace, ElectionDayCloseRequest, ElectionDayIncidentCreate, ElectionDayIncidentResolve, ElectionDayOperationCreate, ElectoralBoardCreate, PollingPlaceCreate
from app.schemas.alerts import AlertEvaluationRequest
from app.services.alert_service import AlertService
from app.services.election_day_service import ElectionDayService
from app.services.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.services.role_service import RoleService
from app.scripts.seed_reports_and_alerts import seed as seed_alert_rules


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
    source = DataSource(code=f"ED-{index}-{uuid4().hex[:4]}", institution="Consejo Nacional Electoral", dataset_name="Recintos ED", dataset_type="CNE_ELECTORAL_ROLL_SNAPSHOT", created_by_user_id=admin.id)
    db.add(source)
    db.flush()
    process = ElectoralProcess(code=f"ED-P-{index}-{uuid4().hex[:4]}", name=f"Proceso ED {index}", process_type="SECTIONAL", election_date=date(2027, 2, 14), year=2027, status="VALIDATED", is_final=True, source_id=source.id, is_active=True)
    db.add(process)
    db.flush()
    contest = ElectoralContest(electoral_process_id=process.id, office_type="MAYOR", name=f"Alcaldía ED {index}", vote_method="SINGLE_CHOICE", canton_id=canton.id, seats=1, is_active=True)
    db.add(contest)
    db.commit()
    return campaign, canton, parish_a, parish_b, process


def _coordinator(db, admin, campaign, parish):
    role = RoleService(db).repository.get_by_code("TERRITORIAL_COORDINATOR")
    user = User(email=f"ed-coord-{uuid4().hex[:6]}@example.test", username=f"ed-coord-{uuid4().hex[:6]}", first_name="ED", last_name="Coord", hashed_password=hash_password("CoordPass123"), is_active=True, roles=[role])
    db.add(user)
    db.flush()
    db.add(CampaignUser(campaign_id=campaign.id, user_id=user.id, assigned_by_user_id=admin.id, is_active=True))
    db.add(TerritorialAssignment(campaign_id=campaign.id, user_id=user.id, parish_id=parish.id, assigned_by_user_id=admin.id, is_active=True))
    db.commit()
    return user


def _member(db, admin, campaign, code="TERRITORIAL_COORDINATOR", parish=None):
    role = RoleService(db).repository.get_by_code(code)
    user = User(email=f"ed-member-{uuid4().hex[:6]}@example.test", username=f"ed-member-{uuid4().hex[:6]}", first_name="ED", last_name="Member", hashed_password=hash_password("MemberPass123"), is_active=True, roles=[role])
    db.add(user)
    db.flush()
    db.add(CampaignUser(campaign_id=campaign.id, user_id=user.id, assigned_by_user_id=admin.id, is_active=True))
    if parish:
        db.add(TerritorialAssignment(campaign_id=campaign.id, user_id=user.id, parish_id=parish.id, assigned_by_user_id=admin.id, is_active=True))
    db.commit()
    return user


@pytest.fixture
def ed(db, admin):
    seed_alert_rules(db)
    db.commit()
    campaign, canton, parish_a, parish_b, process = _election_day_dataset(db, admin, 1)
    return campaign, canton, parish_a, parish_b, process


def _active_operation(db, admin, campaign, process):
    svc = ElectionDayService(db)
    op = svc.create_operation(campaign.id, ElectionDayOperationCreate(electoral_process_id=process.id, election_date=date(2027, 2, 14)), admin)
    return svc.open_operation(campaign.id, admin)


# ---------- Operation lifecycle ----------

def test_create_operation_requires_matching_electoral_contest(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    svc = ElectionDayService(db)
    other_process = ElectoralProcess(code=f"UNRELATED-{uuid4().hex[:4]}", name="Proceso no relacionado", process_type="SECTIONAL", election_date=date(2027, 2, 14), year=2027, status="VALIDATED", is_final=True, source_id=db.get(DataSource, process.source_id).id, is_active=True)
    db.add(other_process)
    db.commit()
    with pytest.raises(BusinessRuleError):
        svc.create_operation(campaign.id, ElectionDayOperationCreate(electoral_process_id=other_process.id, election_date=date(2027, 2, 14)), admin)


def test_operation_lifecycle_preparation_active_closed(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    svc = ElectionDayService(db)
    op = svc.create_operation(campaign.id, ElectionDayOperationCreate(electoral_process_id=process.id, election_date=date(2027, 2, 14)), admin)
    assert op.status == "PREPARATION"
    op = svc.open_operation(campaign.id, admin)
    assert op.status == "ACTIVE" and op.opened_at is not None
    op = svc.close_operation(campaign.id, ElectionDayCloseRequest(), admin)
    assert op.status == "CLOSED" and op.closed_at is not None


def test_cannot_create_two_operations_for_same_campaign_and_process(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    svc = ElectionDayService(db)
    svc.create_operation(campaign.id, ElectionDayOperationCreate(electoral_process_id=process.id, election_date=date(2027, 2, 14)), admin)
    with pytest.raises(ConflictError):
        svc.create_operation(campaign.id, ElectionDayOperationCreate(electoral_process_id=process.id, election_date=date(2027, 2, 14)), admin)


def test_only_executive_or_admin_can_activate_operation(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    coordinator = _coordinator(db, admin, campaign, parish_a)
    svc = ElectionDayService(db)
    with pytest.raises(PermissionError):
        svc.create_operation(campaign.id, ElectionDayOperationCreate(electoral_process_id=process.id, election_date=date(2027, 2, 14)), coordinator)


def test_close_operation_does_not_block_on_open_incidents(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    svc = ElectionDayService(db)
    _active_operation(db, admin, campaign, process)
    place = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R01", name="Recinto 1", parish_id=parish_a.id), admin)
    svc.create_incident(campaign.id, ElectionDayIncidentCreate(polling_place_id=place.id, category="LOGISTICS", description="Falta de mobiliario"), admin)
    op = svc.close_operation(campaign.id, ElectionDayCloseRequest(), admin)
    assert op.status == "CLOSED"


# ---------- Polling places / boards ----------

def test_create_polling_place_and_board(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    svc = ElectionDayService(db)
    _active_operation(db, admin, campaign, process)
    place = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R01", name="Escuela Central", parish_id=parish_a.id), admin)
    assert place.canton_id == canton.id and place.province_id == canton.province_id
    board = svc.create_board(campaign.id, place.id, ElectoralBoardCreate(official_code="J01", board_number=1, registered_voters=350), admin)
    assert board.polling_place_id == place.id


def test_duplicate_polling_place_code_conflicts(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    svc = ElectionDayService(db)
    _active_operation(db, admin, campaign, process)
    svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R01", name="Escuela Central", parish_id=parish_a.id), admin)
    with pytest.raises(ConflictError):
        svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R01", name="Otra escuela", parish_id=parish_a.id), admin)


def test_polling_place_without_coordinates_is_not_a_backend_error(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    svc = ElectionDayService(db)
    _active_operation(db, admin, campaign, process)
    place = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R02", name="Sin coordenadas", parish_id=parish_a.id), admin)
    assert place.latitude is None and place.longitude is None


# ---------- Coverage matrix ----------

def test_coverage_reflects_assignments_and_checkins(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    svc = ElectionDayService(db)
    _active_operation(db, admin, campaign, process)
    place = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R01", name="Escuela Central", parish_id=parish_a.id), admin)
    board = svc.create_board(campaign.id, place.id, ElectoralBoardCreate(official_code="J01", board_number=1), admin)
    coverage = svc.coverage(campaign.id, admin)
    assert coverage["total_polling_places"] == 1 and coverage["covered_polling_places"] == 0
    delegate = _member(db, admin, campaign, "TERRITORIAL_COORDINATOR", parish_a)
    assignment = svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=delegate.id, polling_place_id=place.id, board_id=board.id, assignment_role="BOARD_DELEGATE"), admin)
    coverage = svc.coverage(campaign.id, admin)
    assert coverage["covered_polling_places"] == 1 and coverage["covered_boards"] == 1 and coverage["personnel_checked_in"] == 0
    svc.check_in(campaign.id, assignment.id, CheckInRequest(), delegate)
    coverage = svc.coverage(campaign.id, admin)
    assert coverage["personnel_checked_in"] == 1


# ---------- Assignments / replacement / check-in ----------

def test_coordinator_cannot_manage_assignments(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    svc = ElectionDayService(db)
    _active_operation(db, admin, campaign, process)
    place = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R01", name="Escuela Central", parish_id=parish_a.id), admin)
    coordinator = _coordinator(db, admin, campaign, parish_a)
    with pytest.raises(PermissionError):
        svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=coordinator.id, polling_place_id=place.id, assignment_role="POLLING_PLACE_COORDINATOR"), coordinator)


def test_replace_assignment_preserves_history_and_checkin(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    svc = ElectionDayService(db)
    _active_operation(db, admin, campaign, process)
    place = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R01", name="Escuela Central", parish_id=parish_a.id), admin)
    original = _member(db, admin, campaign, "TERRITORIAL_COORDINATOR", parish_a)
    replacement = _member(db, admin, campaign, "TERRITORIAL_COORDINATOR", parish_a)
    assignment = svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=original.id, polling_place_id=place.id, assignment_role="MOBILE_SUPPORT"), admin)
    svc.check_in(campaign.id, assignment.id, CheckInRequest(latitude=-2.9, longitude=-78.7), original)
    new_assignment = svc.replace_assignment(campaign.id, assignment.id, ElectionDayAssignmentReplace(user_id=replacement.id, reason="No disponible"), admin)
    db.refresh(assignment)
    assert assignment.status == "REPLACED" and assignment.checked_in_at is not None
    assert new_assignment.status == "ASSIGNED" and new_assignment.replaced_by_assignment_id is None
    assert assignment.replaced_by_assignment_id == new_assignment.id


def test_replace_assignment_rejects_same_user_as_duplicate(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    svc = ElectionDayService(db)
    _active_operation(db, admin, campaign, process)
    place = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R01", name="Escuela Central", parish_id=parish_a.id), admin)
    delegate = _member(db, admin, campaign, "TERRITORIAL_COORDINATOR", parish_a)
    assignment = svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=delegate.id, polling_place_id=place.id, assignment_role="MOBILE_SUPPORT"), admin)
    with pytest.raises(BusinessRuleError):
        svc.replace_assignment(campaign.id, assignment.id, ElectionDayAssignmentReplace(user_id=delegate.id), admin)


def test_eligible_users_lists_only_active_campaign_members_and_requires_manage_permission(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    svc = ElectionDayService(db)
    member = _member(db, admin, campaign, "TERRITORIAL_COORDINATOR", parish_a)
    outsider = _coordinator(db, admin, campaign, parish_a)
    db.execute(CampaignUser.__table__.update().where(CampaignUser.campaign_id == campaign.id, CampaignUser.user_id == outsider.id).values(is_active=False))
    db.commit()
    users = svc.eligible_users(campaign.id, admin)
    ids = {u.id for u in users}
    assert member.id in ids
    assert outsider.id not in ids
    with pytest.raises(PermissionError):
        svc.eligible_users(campaign.id, member)


def test_checkin_is_idempotent_by_client_generated_id(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    svc = ElectionDayService(db)
    _active_operation(db, admin, campaign, process)
    place = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R01", name="Escuela Central", parish_id=parish_a.id), admin)
    delegate = _member(db, admin, campaign, "TERRITORIAL_COORDINATOR", parish_a)
    assignment = svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=delegate.id, polling_place_id=place.id, assignment_role="MOBILE_SUPPORT"), admin)
    cid = uuid4()
    first = svc.check_in(campaign.id, assignment.id, CheckInRequest(client_generated_id=cid), delegate)
    second = svc.check_in(campaign.id, assignment.id, CheckInRequest(client_generated_id=cid), delegate)
    assert first.checked_in_at == second.checked_in_at


def test_replaced_assignment_denies_further_checkin(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    svc = ElectionDayService(db)
    _active_operation(db, admin, campaign, process)
    place = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R01", name="Escuela Central", parish_id=parish_a.id), admin)
    original = _member(db, admin, campaign, "TERRITORIAL_COORDINATOR", parish_a)
    replacement = _member(db, admin, campaign, "TERRITORIAL_COORDINATOR", parish_a)
    assignment = svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=original.id, polling_place_id=place.id, assignment_role="MOBILE_SUPPORT"), admin)
    svc.replace_assignment(campaign.id, assignment.id, ElectionDayAssignmentReplace(user_id=replacement.id), admin)
    with pytest.raises(PermissionError):
        svc.check_in(campaign.id, assignment.id, CheckInRequest(), original)


def test_only_assigned_person_can_check_in_for_themselves(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    svc = ElectionDayService(db)
    _active_operation(db, admin, campaign, process)
    place = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R01", name="Escuela Central", parish_id=parish_a.id), admin)
    delegate = _member(db, admin, campaign, "TERRITORIAL_COORDINATOR", parish_a)
    other = _member(db, admin, campaign, "TERRITORIAL_COORDINATOR", parish_a)
    assignment = svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=delegate.id, polling_place_id=place.id, assignment_role="MOBILE_SUPPORT"), admin)
    with pytest.raises(PermissionError):
        svc.check_in(campaign.id, assignment.id, CheckInRequest(), other)


def test_closed_operation_rejects_new_checkins(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    svc = ElectionDayService(db)
    op = _active_operation(db, admin, campaign, process)
    place = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R01", name="Escuela Central", parish_id=parish_a.id), admin)
    delegate = _member(db, admin, campaign, "TERRITORIAL_COORDINATOR", parish_a)
    assignment = svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=delegate.id, polling_place_id=place.id, assignment_role="MOBILE_SUPPORT"), admin)
    svc.close_operation(campaign.id, ElectionDayCloseRequest(), admin)
    with pytest.raises(BusinessRuleError):
        svc.check_in(campaign.id, assignment.id, CheckInRequest(), delegate)


# ---------- Incidents ----------

def test_incident_reported_and_resolved(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    svc = ElectionDayService(db)
    _active_operation(db, admin, campaign, process)
    place = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R01", name="Escuela Central", parish_id=parish_a.id), admin)
    incident = svc.create_incident(campaign.id, ElectionDayIncidentCreate(polling_place_id=place.id, category="CONNECTIVITY", description="Sin señal para reportar"), admin)
    assert incident.status == "OPEN"
    resolved = svc.resolve_incident(campaign.id, incident.id, ElectionDayIncidentResolve(status="RESOLVED", resolution_notes="Se restableció la señal"), admin)
    assert resolved.status == "RESOLVED" and resolved.resolved_at is not None


def test_incident_offline_idempotent_by_client_generated_id(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    svc = ElectionDayService(db)
    _active_operation(db, admin, campaign, process)
    place = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R01", name="Escuela Central", parish_id=parish_a.id), admin)
    cid = uuid4()
    first = svc.create_incident(campaign.id, ElectionDayIncidentCreate(polling_place_id=place.id, category="ACCESS", description="Puerta cerrada", client_generated_id=cid), admin)
    second = svc.create_incident(campaign.id, ElectionDayIncidentCreate(polling_place_id=place.id, category="ACCESS", description="Puerta cerrada", client_generated_id=cid), admin)
    assert first.id == second.id


def test_coordinator_cannot_report_incident_outside_assigned_parish(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    svc = ElectionDayService(db)
    _active_operation(db, admin, campaign, process)
    place_b = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R02", name="Escuela Norte", parish_id=parish_b.id), admin)
    coordinator = _coordinator(db, admin, campaign, parish_a)
    with pytest.raises(PermissionError):
        svc.create_incident(campaign.id, ElectionDayIncidentCreate(polling_place_id=place_b.id, category="OTHER", description="Observación"), coordinator)


def test_coordinator_without_territorial_assignment_still_operates_own_election_day_assignment(db, admin, ed):
    """Un Coordinator asignado a un recinto solo para la jornada (sin
    TerritorialAssignment permanente) debe poder ver la junta y reportar una
    incidencia en su propio recinto — la asignación de jornada por sí misma
    otorga alcance, sin depender del sistema territorial preexistente."""
    campaign, canton, parish_a, parish_b, process = ed
    svc = ElectionDayService(db)
    _active_operation(db, admin, campaign, process)
    place = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R01", name="Escuela Central", parish_id=parish_a.id), admin)
    other_place = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R02", name="Escuela Norte", parish_id=parish_b.id), admin)
    delegate = _member(db, admin, campaign, "TERRITORIAL_COORDINATOR", parish=None)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=delegate.id, polling_place_id=place.id, assignment_role="BOARD_DELEGATE"), admin)
    # Su propio recinto: permitido pese a no tener TerritorialAssignment.
    svc.list_boards(campaign.id, delegate, place.id)
    svc.create_incident(campaign.id, ElectionDayIncidentCreate(polling_place_id=place.id, category="LOGISTICS", description="Observación"), delegate)
    # Un recinto donde no tiene ninguna asignación de jornada sigue fuera de alcance.
    with pytest.raises(PermissionError):
        svc.list_boards(campaign.id, delegate, other_place.id)


def test_incident_categories_never_include_fraud_or_political_language(db, admin, ed):
    from app.services.election_day_service import INCIDENT_CATEGORIES
    assert INCIDENT_CATEGORIES == {"PERSONNEL", "ACCESS", "LOGISTICS", "DOCUMENTATION", "CONNECTIVITY", "OTHER"}


# ---------- Documents / storage RBAC ----------

def test_document_upload_and_download_scoped_to_parish(db, admin, ed, tmp_path):
    from app.services.evidence_storage_service import LocalEvidenceStorage
    campaign, canton, parish_a, parish_b, process = ed
    svc = ElectionDayService(db, LocalEvidenceStorage(str(tmp_path), 10))
    _active_operation(db, admin, campaign, process)
    place = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R01", name="Escuela Central", parish_id=parish_a.id), admin)
    pdf_bytes = b"%PDF-1.4 fixture"
    doc = svc.upload_document(campaign.id, admin, polling_place_id=place.id, board_id=None, document_type="ACTA_COPY", file_bytes=pdf_bytes, original_filename="acta.pdf", client_generated_id=None)
    assert doc.status == "RECEIVED" and doc.sha256
    path, obj = svc.document_file(campaign.id, doc.id, admin)
    assert path.exists() and path.read_bytes() == pdf_bytes
    coordinator = _coordinator(db, admin, campaign, parish_b)
    with pytest.raises(PermissionError):
        svc.document_file(campaign.id, doc.id, coordinator)


def test_document_rejects_non_pdf_non_image_content(db, admin, ed, tmp_path):
    from app.services.evidence_storage_service import LocalEvidenceStorage
    campaign, canton, parish_a, parish_b, process = ed
    svc = ElectionDayService(db, LocalEvidenceStorage(str(tmp_path), 10))
    _active_operation(db, admin, campaign, process)
    place = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R01", name="Escuela Central", parish_id=parish_a.id), admin)
    with pytest.raises(BusinessRuleError):
        svc.upload_document(campaign.id, admin, polling_place_id=place.id, board_id=None, document_type="ACTA_COPY", file_bytes=b"not a real file", original_filename="acta.txt", client_generated_id=None)


def test_document_upload_idempotent_by_client_generated_id(db, admin, ed, tmp_path):
    from app.services.evidence_storage_service import LocalEvidenceStorage
    campaign, canton, parish_a, parish_b, process = ed
    svc = ElectionDayService(db, LocalEvidenceStorage(str(tmp_path), 10))
    _active_operation(db, admin, campaign, process)
    place = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R01", name="Escuela Central", parish_id=parish_a.id), admin)
    cid = uuid4()
    first = svc.upload_document(campaign.id, admin, polling_place_id=place.id, board_id=None, document_type="ACTA_COPY", file_bytes=b"%PDF-1.4 fixture", original_filename="acta.pdf", client_generated_id=cid)
    second = svc.upload_document(campaign.id, admin, polling_place_id=place.id, board_id=None, document_type="ACTA_COPY", file_bytes=b"%PDF-1.4 fixture", original_filename="acta.pdf", client_generated_id=cid)
    assert first.id == second.id


# ---------- Multi-campaign / multi-canton isolation ----------

def test_multi_campaign_isolation_of_operations_and_polling_places(db, admin):
    campaign_a, canton_a, parish_a1, parish_a2, process_a = _election_day_dataset(db, admin, 10)
    campaign_b, canton_b, parish_b1, parish_b2, process_b = _election_day_dataset(db, admin, 11)
    svc = ElectionDayService(db)
    op_a = _active_operation(db, admin, campaign_a, process_a)
    op_b = _active_operation(db, admin, campaign_b, process_b)
    place_a = svc.create_polling_place(campaign_a.id, PollingPlaceCreate(official_code="R01", name="Recinto A", parish_id=parish_a1.id), admin)
    place_b = svc.create_polling_place(campaign_b.id, PollingPlaceCreate(official_code="R01", name="Recinto B", parish_id=parish_b1.id), admin)
    places_in_a = svc.list_polling_places(campaign_a.id, admin)
    places_in_b = svc.list_polling_places(campaign_b.id, admin)
    assert {p.id for p in places_in_a} == {place_a.id}
    assert {p.id for p in places_in_b} == {place_b.id}
    with pytest.raises(NotFoundError):
        svc.polling_place_detail(campaign_a.id, place_b.id, admin)


# ---------- Smart Alerts ----------

def test_election_place_and_board_uncovered_alerts(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    seed_alert_rules(db)
    svc = ElectionDayService(db)
    _active_operation(db, admin, campaign, process)
    place = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R01", name="Escuela Central", parish_id=parish_a.id), admin)
    svc.create_board(campaign.id, place.id, ElectoralBoardCreate(official_code="J01", board_number=1), admin)
    result = AlertService(db).evaluate(campaign.id, admin, AlertEvaluationRequest(rule_codes=["ELECTION_PLACE_UNCOVERED", "BOARD_UNCOVERED"], as_of_date=date(2027, 2, 14)))
    assert result["created"] == 2
    items, _ = AlertService(db).list(campaign.id, admin, status="OPEN")
    assert {i.evidence.get("polling_place_name") for i in items if "polling_place_name" in i.evidence} == {"Escuela Central"}


def test_election_place_uncovered_resolves_once_assigned(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    seed_alert_rules(db)
    svc = ElectionDayService(db)
    _active_operation(db, admin, campaign, process)
    place = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R01", name="Escuela Central", parish_id=parish_a.id), admin)
    req = AlertEvaluationRequest(rule_codes=["ELECTION_PLACE_UNCOVERED"], as_of_date=date(2027, 2, 14))
    AlertService(db).evaluate(campaign.id, admin, req)
    delegate = _member(db, admin, campaign, "TERRITORIAL_COORDINATOR", parish_a)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=delegate.id, polling_place_id=place.id, assignment_role="POLLING_PLACE_COORDINATOR"), admin)
    AlertService(db).evaluate(campaign.id, admin, req)
    items, _ = AlertService(db).list(campaign.id, admin, status="OPEN")
    assert items == []


def test_open_election_incident_alert(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    seed_alert_rules(db)
    svc = ElectionDayService(db)
    _active_operation(db, admin, campaign, process)
    place = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R01", name="Escuela Central", parish_id=parish_a.id), admin)
    svc.create_incident(campaign.id, ElectionDayIncidentCreate(polling_place_id=place.id, category="CONNECTIVITY", description="Sin señal"), admin)
    result = AlertService(db).evaluate(campaign.id, admin, AlertEvaluationRequest(rule_codes=["OPEN_ELECTION_INCIDENT"], as_of_date=date(2027, 2, 14)))
    assert result["created"] == 1


def test_board_document_missing_alert(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    seed_alert_rules(db)
    svc = ElectionDayService(db)
    _active_operation(db, admin, campaign, process)
    place = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R01", name="Escuela Central", parish_id=parish_a.id), admin)
    svc.create_board(campaign.id, place.id, ElectoralBoardCreate(official_code="J01", board_number=1), admin)
    result = AlertService(db).evaluate(campaign.id, admin, AlertEvaluationRequest(rule_codes=["BOARD_DOCUMENT_MISSING"], as_of_date=date(2027, 2, 14)))
    assert result["created"] == 1


def test_assigned_person_not_checked_in_respects_grace_period(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    seed_alert_rules(db)
    svc = ElectionDayService(db)
    op = _active_operation(db, admin, campaign, process)
    place = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R01", name="Escuela Central", parish_id=parish_a.id), admin)
    delegate = _member(db, admin, campaign, "TERRITORIAL_COORDINATOR", parish_a)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=delegate.id, polling_place_id=place.id, assignment_role="MOBILE_SUPPORT"), admin)
    req = AlertEvaluationRequest(rule_codes=["ASSIGNED_PERSON_NOT_CHECKED_IN"], as_of_date=date(2027, 2, 14))
    result = AlertService(db).evaluate(campaign.id, admin, req)
    assert result["created"] == 0, "aun dentro del umbral de gracia, no debe alertar"
    op.opened_at = datetime.now(timezone.utc) - timedelta(minutes=90)
    db.commit()
    result = AlertService(db).evaluate(campaign.id, admin, req)
    assert result["created"] == 1


def test_alert_severities_are_operational_never_political(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    seed_alert_rules(db)
    from app.models.alerts import AlertRule
    codes = {"ELECTION_PLACE_UNCOVERED", "BOARD_UNCOVERED", "ASSIGNED_PERSON_NOT_CHECKED_IN", "OPEN_ELECTION_INCIDENT", "BOARD_DOCUMENT_MISSING", "OFFLINE_SYNC_FAILURE"}
    rules = list(db.query(AlertRule).filter(AlertRule.code.in_(codes)))
    assert len(rules) == 6
    assert all(r.default_severity in {"INFO", "WARNING"} for r in rules)


# ---------- Informe de Jornada Electoral ----------

def test_election_day_report_requires_existing_operation(db, admin, ed):
    from app.schemas.reports import ReportGenerationRequest
    from app.services.report_service import ReportService
    campaign, canton, parish_a, parish_b, process = ed
    request = ReportGenerationRequest(template_code="ELECTION_DAY_REPORT", format="PDF", title="Informe de jornada", report_date=date(2027, 2, 14))
    with pytest.raises(ValueError):
        ReportService(db).preview(campaign.id, request, admin)


def test_election_day_report_shows_coverage_incidents_documents_and_no_results(db, admin, ed, tmp_path):
    from app.schemas.reports import ReportGenerationRequest
    from app.services.report_service import ReportService
    campaign, canton, parish_a, parish_b, process = ed
    svc = ElectionDayService(db)
    _active_operation(db, admin, campaign, process)
    place = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R01", name="Escuela Central", parish_id=parish_a.id), admin)
    svc.create_incident(campaign.id, ElectionDayIncidentCreate(polling_place_id=place.id, category="LOGISTICS", description="Falta de mobiliario"), admin)
    request = ReportGenerationRequest(template_code="ELECTION_DAY_REPORT", format="PDF", title="Informe de jornada", report_date=date(2027, 2, 14))
    preview = ReportService(db).preview(campaign.id, request, admin)
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
    svc = ElectionDayService(db)
    _active_operation(db, admin, campaign, process)
    svc.close_operation(campaign.id, ElectionDayCloseRequest(), admin)
    request = ReportGenerationRequest(template_code="ELECTION_DAY_REPORT", format="PDF", title="Informe de jornada", report_date=date(2027, 2, 14))
    preview = ReportService(db).preview(campaign.id, request, admin)
    full_text = " ".join((s.text or "") for s in preview.sections)
    assert "PROVISIONAL" not in full_text
    assert any(s.title == "Estado de la jornada" and any(row == ["Estado", "Jornada cerrada"] for row in s.rows) for s in preview.sections)


def test_election_day_report_generates_pdf_and_persists(db, admin, ed, tmp_path):
    from app.schemas.reports import ReportGenerationRequest
    from app.services.report_service import ReportService
    from app.services.report_storage_service import LocalReportStorage
    campaign, canton, parish_a, parish_b, process = ed
    _active_operation(db, admin, campaign, process)
    service = ReportService(db, LocalReportStorage(str(tmp_path), 10))
    run = service.generate(campaign.id, ReportGenerationRequest(template_code="ELECTION_DAY_REPORT", format="PDF", title="Informe de jornada", report_date=date(2027, 2, 14)), admin)
    assert run.status == "COMPLETED"
    artifact = service.artifact(run)
    assert artifact is not None and artifact.original_download_name.startswith("informe-jornada-electoral-")


# ---------- Territorio IA ----------

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
    svc = ElectionDayService(db)
    _active_operation(db, admin, campaign, process)
    place = svc.create_polling_place(campaign.id, PollingPlaceCreate(official_code="R01", name="Escuela Central", parish_id=parish_a.id), admin)
    svc.create_incident(campaign.id, ElectionDayIncidentCreate(polling_place_id=place.id, category="CONNECTIVITY", description="Sin señal"), admin)
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

def test_http_full_flow_and_cross_campaign_isolation(client, admin_headers, db, admin):
    campaign, canton, parish_a, parish_b, process = _election_day_dataset(db, admin, 30)
    other_campaign, _other_canton, other_parish_a, _other_parish_b, other_process = _election_day_dataset(db, admin, 31)
    create = client.post(f"/api/v1/campaigns/{campaign.id}/election-day/operation", headers=admin_headers, json={"electoral_process_id": str(process.id), "election_date": "2027-02-14"})
    assert create.status_code == 201
    opened = client.post(f"/api/v1/campaigns/{campaign.id}/election-day/operation/open", headers=admin_headers)
    assert opened.status_code == 200 and opened.json()["status"] == "ACTIVE"
    other_create = client.post(f"/api/v1/campaigns/{other_campaign.id}/election-day/operation", headers=admin_headers, json={"electoral_process_id": str(other_process.id), "election_date": "2027-02-14"})
    assert other_create.status_code == 201
    place_resp = client.post(f"/api/v1/campaigns/{campaign.id}/election-day/polling-places", headers=admin_headers, json={"official_code": "R01", "name": "Escuela Central", "parish_id": parish_a.id})
    assert place_resp.status_code == 201
    place_id = place_resp.json()["id"]
    coverage = client.get(f"/api/v1/campaigns/{campaign.id}/election-day/coverage", headers=admin_headers)
    assert coverage.status_code == 200 and coverage.json()["total_polling_places"] == 1
    # El recinto de `campaign` (proceso propio) no debe ser visible desde
    # `other_campaign`, aunque esta también tenga una jornada activa.
    cross = client.get(f"/api/v1/campaigns/{other_campaign.id}/election-day/polling-places/{place_id}", headers=admin_headers)
    assert cross.status_code == 404
    other_coverage = client.get(f"/api/v1/campaigns/{other_campaign.id}/election-day/coverage", headers=admin_headers)
    assert other_coverage.status_code == 200 and other_coverage.json()["total_polling_places"] == 0


def test_multi_canton_polling_places_isolated_by_canton_not_name(db, admin):
    campaign_a, canton_a, parish_a1, parish_a2, process_a = _election_day_dataset(db, admin, 20)
    campaign_b, canton_b, parish_b1, parish_b2, process_b = _election_day_dataset(db, admin, 21)
    svc = ElectionDayService(db)
    _active_operation(db, admin, campaign_a, process_a)
    _active_operation(db, admin, campaign_b, process_b)
    svc.create_polling_place(campaign_a.id, PollingPlaceCreate(official_code="SAME", name="Escuela Central", parish_id=parish_a1.id), admin)
    svc.create_polling_place(campaign_b.id, PollingPlaceCreate(official_code="SAME", name="Escuela Central", parish_id=parish_b1.id), admin)
    places_a = svc.list_polling_places(campaign_a.id, admin)
    places_b = svc.list_polling_places(campaign_b.id, admin)
    assert len(places_a) == 1 and len(places_b) == 1 and places_a[0].id != places_b[0].id
