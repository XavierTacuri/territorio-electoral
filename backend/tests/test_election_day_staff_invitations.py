from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.security import hash_password
from app.models.assignments import CampaignUser
from app.models.election_day import (
    ElectionDayAssignment,
    ElectionDayStaffInvitation,
    ElectionDayStaffInvitationPollingPlace,
)
from app.models.organization import OrganizationMembership
from app.models.security import SecurityAuditEvent
from app.models.territory import Canton, Parish, Province
from app.models.user import User
from app.schemas.election_day import (
    ElectionDayAdminSupportStartRequest,
    ElectionDayCloseRequest,
    ElectionDayInvitationAcceptNewAccount,
    ElectionDayOperationCreate,
    ElectionDayStaffInvitationCreate,
)
from app.services.election_day_admin_support_service import ElectionDayAdminSupportService
from app.services.election_day_service import ElectionDayService
from app.services.election_day_staff_invitation_service import ElectionDayStaffInvitationService
from app.services.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.services.role_service import RoleService
from app.scripts.seed_reports_and_alerts import seed as seed_alert_rules

from tests.test_election_day import _election_day_dataset, _member, _polling_place, _ready_operation


@pytest.fixture
def ed(db, admin):
    seed_alert_rules(db)
    db.commit()
    return _election_day_dataset(db, admin, 77)


def _bare_user(db, suffix=None):
    """Un usuario sin CampaignUser/OrganizationMembership/UserRole — la
    forma exacta en la que queda el personal de Jornada tras aceptar (§2)."""
    suffix = suffix or uuid4().hex[:8]
    user = User(email=f"bare-{suffix}@example.com", username=f"bare-{suffix}", first_name="Bare", last_name="User", hashed_password=hash_password("BarePass123"), is_active=True, roles=[])
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_invite(db, campaign, executive, *, staff_type="POLLING_PLACE_DELEGATE", polling_place_ids=None, email=None):
    data = ElectionDayStaffInvitationCreate(
        first_name="Juan", last_name="Lopez", email=email or f"invitee-{uuid4().hex[:8]}@example.com",
        staff_type=staff_type, polling_place_ids=polling_place_ids or [],
    )
    return ElectionDayStaffInvitationService(db).create(campaign.id, data, executive)


# ---------- Permisos para crear invitaciones (§7) ----------

def test_candidate_can_create_invitation(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    candidate = _member(db, admin, campaign, "CANDIDATE")
    op = ElectionDayService(db).create_operation(campaign.id, ElectionDayOperationCreate(electoral_process_id=process.id, election_date=date(2027, 2, 14)), candidate)
    place = _polling_place(db, process, canton, parish_a)
    invitation, token = _create_invite(db, campaign, candidate, polling_place_ids=[place.id])
    assert invitation.status == "PENDING"
    assert len(token) > 20
    assert invitation.operation_id == op.id


def test_manager_can_create_invitation(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    manager = _member(db, admin, campaign, "CAMPAIGN_MANAGER")
    ElectionDayService(db).create_operation(campaign.id, ElectionDayOperationCreate(electoral_process_id=process.id, election_date=date(2027, 2, 14)), manager)
    place = _polling_place(db, process, canton, parish_a)
    invitation, _token = _create_invite(db, campaign, manager, polling_place_ids=[place.id])
    assert invitation.status == "PENDING"


@pytest.mark.parametrize("role", ["TERRITORIAL_COORDINATOR", "ANALYST"])
def test_non_executive_roles_cannot_create_invitation(db, admin, ed, role):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    ElectionDayService(db).create_operation(campaign.id, ElectionDayOperationCreate(electoral_process_id=process.id, election_date=date(2027, 2, 14)), executive)
    other = _member(db, admin, campaign, role)
    with pytest.raises(PermissionError):
        _create_invite(db, campaign, other, staff_type="ACT_VALIDATOR")


def test_admin_cannot_create_invitation_by_implicit_privilege(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    ElectionDayService(db).create_operation(campaign.id, ElectionDayOperationCreate(electoral_process_id=process.id, election_date=date(2027, 2, 14)), executive)
    with pytest.raises(PermissionError):
        _create_invite(db, campaign, admin, staff_type="ACT_VALIDATOR")


def test_admin_in_support_mode_still_cannot_create_invitation(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    ElectionDayService(db).create_operation(campaign.id, ElectionDayOperationCreate(electoral_process_id=process.id, election_date=date(2027, 2, 14)), executive)
    ElectionDayAdminSupportService(db).start(campaign.id, ElectionDayAdminSupportStartRequest(), admin)
    with pytest.raises(PermissionError):
        _create_invite(db, campaign, admin, staff_type="ACT_VALIDATOR")


def test_delegate_and_validator_cannot_create_invitation(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    with pytest.raises(PermissionError):
        _create_invite(db, campaign, delegate, staff_type="ACT_VALIDATOR")
    with pytest.raises(PermissionError):
        _create_invite(db, campaign, validator, staff_type="ACT_VALIDATOR")


# ---------- Forma de la invitación: delegado vs validador (§5) ----------

def test_delegate_invitation_requires_at_least_one_polling_place():
    with pytest.raises(ValidationError):
        ElectionDayStaffInvitationCreate(first_name="A", last_name="B", email="a@example.com", staff_type="POLLING_PLACE_DELEGATE", polling_place_ids=[])


def test_validator_invitation_rejects_polling_places():
    with pytest.raises(ValidationError):
        ElectionDayStaffInvitationCreate(first_name="A", last_name="B", email="a@example.com", staff_type="ACT_VALIDATOR", polling_place_ids=[uuid4()])


def test_delegate_invitation_accepts_multiple_polling_places(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    ElectionDayService(db).create_operation(campaign.id, ElectionDayOperationCreate(electoral_process_id=process.id, election_date=date(2027, 2, 14)), executive)
    place_a = _polling_place(db, process, canton, parish_a, code="R01")
    place_b = _polling_place(db, process, canton, parish_b, code="R02")
    invitation, _token = _create_invite(db, campaign, executive, polling_place_ids=[place_a.id, place_b.id])
    ids = ElectionDayStaffInvitationService(db)._polling_place_ids(invitation.id)
    assert set(ids) == {place_a.id, place_b.id}


def test_invitation_rejects_polling_place_from_other_electoral_process(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    ElectionDayService(db).create_operation(campaign.id, ElectionDayOperationCreate(electoral_process_id=process.id, election_date=date(2027, 2, 14)), executive)
    from app.models.historical import DataSource, ElectoralProcess
    other_source = DataSource(code=f"OTHER-{uuid4().hex[:4]}", institution="CNE", dataset_name="Recintos", dataset_type="CNE_POLLING_PLACES", created_by_user_id=admin.id)
    db.add(other_source)
    db.flush()
    other_process = ElectoralProcess(code=f"OTHER-P-{uuid4().hex[:4]}", name="Otro proceso", process_type="SECTIONAL", election_date=date(2027, 2, 14), year=2027, status="VALIDATED", is_final=True, source_id=other_source.id, is_active=True)
    db.add(other_process)
    db.commit()
    foreign_place = _polling_place(db, other_process, canton, parish_a, code="FOREIGN", source_id=other_source.id)
    with pytest.raises(NotFoundError):
        _create_invite(db, campaign, executive, polling_place_ids=[foreign_place.id])


def test_invitation_rejects_polling_place_from_other_canton(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    ElectionDayService(db).create_operation(campaign.id, ElectionDayOperationCreate(electoral_process_id=process.id, election_date=date(2027, 2, 14)), executive)
    other_canton = Canton(id=canton.id + 500, province_id=canton.province_id, code="99", dpa_code=f"{canton.province_id}99", name="Otro cantón")
    other_parish = Parish(id=canton.id + 5000, canton_id=other_canton.id, code="01", dpa_code=f"{other_canton.dpa_code}01", name="Otra parroquia", parish_type="RURAL")
    db.add_all([other_canton, other_parish])
    db.commit()
    foreign_place = _polling_place(db, process, other_canton, other_parish, code="FOREIGN-CANTON")
    with pytest.raises(NotFoundError):
        _create_invite(db, campaign, executive, polling_place_ids=[foreign_place.id])


# ---------- Seguridad del token (§4) ----------

def _setup_with_operation(db, admin, ed, staff_type="POLLING_PLACE_DELEGATE"):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    ElectionDayService(db).create_operation(campaign.id, ElectionDayOperationCreate(electoral_process_id=process.id, election_date=date(2027, 2, 14)), executive)
    place = _polling_place(db, process, canton, parish_a)
    invitation, token = _create_invite(db, campaign, executive, staff_type=staff_type, polling_place_ids=[place.id] if staff_type == "POLLING_PLACE_DELEGATE" else [])
    return campaign, executive, invitation, token, place


def test_only_token_hash_is_persisted(db, admin, ed):
    campaign, executive, invitation, token, place = _setup_with_operation(db, admin, ed)
    row = db.get(ElectionDayStaffInvitation, invitation.id)
    assert row.token_hash != token
    from app.services.election_day_staff_invitation_service import ElectionDayStaffInvitationService as Svc
    assert row.token_hash == Svc._hash_token(token)
    assert len(row.token_hash) == 64  # sha256 hex digest


def test_list_and_get_never_expose_token(db, admin, ed):
    campaign, executive, invitation, token, place = _setup_with_operation(db, admin, ed)
    service = ElectionDayStaffInvitationService(db)
    items = service.list_invitations(campaign.id, executive)
    for item in items:
        read = service.to_read_dict(item)
        assert "token" not in read and "token_hash" not in read
    preview = service.preview(token)
    assert "token" not in preview


def test_preview_valid_token(db, admin, ed):
    campaign, executive, invitation, token, place = _setup_with_operation(db, admin, ed)
    preview = ElectionDayStaffInvitationService(db).preview(token)
    assert preview["status"] == "PENDING"
    assert preview["staff_type"] == "POLLING_PLACE_DELEGATE"
    assert preview["requires_login"] is False
    assert [p["id"] for p in preview["polling_places"]] == [place.id]


def test_preview_invalid_token_not_found(db, admin, ed):
    with pytest.raises(NotFoundError):
        ElectionDayStaffInvitationService(db).preview("not-a-real-token")


def test_expired_invitation_reports_expired_and_blocks_accept(db, admin, ed):
    campaign, executive, invitation, token, place = _setup_with_operation(db, admin, ed)
    invitation.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    preview = ElectionDayStaffInvitationService(db).preview(token)
    assert preview["status"] == "EXPIRED"
    with pytest.raises(BusinessRuleError):
        ElectionDayStaffInvitationService(db).accept_new_account(token, ElectionDayInvitationAcceptNewAccount(token=token, first_name="A", last_name="B", password="Passw0rd1", password_confirmation="Passw0rd1"))
    db.refresh(invitation)
    assert invitation.status == "EXPIRED"


def test_revoked_invitation_blocks_accept(db, admin, ed):
    campaign, executive, invitation, token, place = _setup_with_operation(db, admin, ed)
    ElectionDayStaffInvitationService(db).revoke(campaign.id, invitation.id, executive)
    with pytest.raises(BusinessRuleError):
        ElectionDayStaffInvitationService(db).accept_new_account(token, ElectionDayInvitationAcceptNewAccount(token=token, first_name="A", last_name="B", password="Passw0rd1", password_confirmation="Passw0rd1"))


def test_reissue_invalidates_previous_token(db, admin, ed):
    campaign, executive, invitation, old_token, place = _setup_with_operation(db, admin, ed)
    _invitation2, new_token = ElectionDayStaffInvitationService(db).reissue(campaign.id, invitation.id, executive)
    assert new_token != old_token
    with pytest.raises(NotFoundError):
        ElectionDayStaffInvitationService(db).preview(old_token)
    preview = ElectionDayStaffInvitationService(db).preview(new_token)
    assert preview["status"] == "PENDING"


def test_closed_operation_blocks_create_accept_and_reissue(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    op, place, board, delegate, validator, executive = _ready_operation(db, admin, campaign, canton, process, parish_a)
    svc = ElectionDayService(db)
    # Emitir una invitación mientras aún está ACTIVE.
    invitation, token = _create_invite(db, campaign, executive, polling_place_ids=[place.id])
    svc.start_scrutiny(campaign.id, executive)
    svc.close_operation(campaign.id, ElectionDayCloseRequest(), executive)
    with pytest.raises(BusinessRuleError):
        _create_invite(db, campaign, executive, polling_place_ids=[place.id])
    with pytest.raises(BusinessRuleError):
        ElectionDayStaffInvitationService(db).accept_new_account(token, ElectionDayInvitationAcceptNewAccount(token=token, first_name="A", last_name="B", password="Passw0rd1", password_confirmation="Passw0rd1"))
    with pytest.raises(BusinessRuleError):
        ElectionDayStaffInvitationService(db).reissue(campaign.id, invitation.id, executive)


# ---------- Nueva cuenta al aceptar (§10/§2) ----------

def test_accept_new_account_creates_bare_user_and_delegate_assignments(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    ElectionDayService(db).create_operation(campaign.id, ElectionDayOperationCreate(electoral_process_id=process.id, election_date=date(2027, 2, 14)), executive)
    place_a = _polling_place(db, process, canton, parish_a, code="R01")
    place_b = _polling_place(db, process, canton, parish_b, code="R02")
    invitation, token = _create_invite(db, campaign, executive, polling_place_ids=[place_a.id, place_b.id])

    service = ElectionDayStaffInvitationService(db)
    accepted = service.accept_new_account(token, ElectionDayInvitationAcceptNewAccount(token=token, first_name="Juana", last_name="Perez", password="Passw0rd1", password_confirmation="Passw0rd1"))

    assert accepted.status == "ACCEPTED"
    user = db.get(User, accepted.accepted_user_id)
    assert user.email == invitation.email
    assert user.is_active is True
    assert user.is_superuser is False
    assert user.roles == []
    assert db.query(CampaignUser).filter(CampaignUser.user_id == user.id).count() == 0
    assert db.query(OrganizationMembership).filter(OrganizationMembership.user_id == user.id).count() == 0
    assignments = db.query(ElectionDayAssignment).filter(ElectionDayAssignment.user_id == user.id).all()
    assert {a.polling_place_id for a in assignments} == {place_a.id, place_b.id}
    assert all(a.assignment_role == "POLLING_PLACE_DELEGATE" and a.status == "ASSIGNED" for a in assignments)


def test_accept_new_account_creates_single_validator_assignment(db, admin, ed):
    campaign, executive, invitation, token, place = _setup_with_operation(db, admin, ed, staff_type="ACT_VALIDATOR")
    accepted = ElectionDayStaffInvitationService(db).accept_new_account(token, ElectionDayInvitationAcceptNewAccount(token=token, first_name="Carlos", last_name="Vega", password="Passw0rd1", password_confirmation="Passw0rd1"))
    user = db.get(User, accepted.accepted_user_id)
    assignments = db.query(ElectionDayAssignment).filter(ElectionDayAssignment.user_id == user.id).all()
    assert len(assignments) == 1
    assert assignments[0].assignment_role == "ACT_VALIDATOR"
    assert assignments[0].polling_place_id is None


def test_accept_new_account_rejects_weak_password():
    with pytest.raises(ValidationError):
        ElectionDayInvitationAcceptNewAccount(token="x" * 32, first_name="A", last_name="B", password="weak", password_confirmation="weak")


def test_accept_new_account_rejects_mismatched_confirmation():
    with pytest.raises(ValidationError):
        ElectionDayInvitationAcceptNewAccount(token="x" * 32, first_name="A", last_name="B", password="Passw0rd1", password_confirmation="Different1")


def test_accept_new_account_rejects_when_email_already_has_account(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    ElectionDayService(db).create_operation(campaign.id, ElectionDayOperationCreate(electoral_process_id=process.id, election_date=date(2027, 2, 14)), executive)
    place = _polling_place(db, process, canton, parish_a)
    existing = _bare_user(db)
    invitation, token = _create_invite(db, campaign, executive, polling_place_ids=[place.id], email=existing.email)
    with pytest.raises(BusinessRuleError):
        ElectionDayStaffInvitationService(db).accept_new_account(token, ElectionDayInvitationAcceptNewAccount(token=token, first_name="A", last_name="B", password="Passw0rd1", password_confirmation="Passw0rd1"))


# ---------- Cuenta existente (§9/§12) ----------

def test_accept_existing_requires_matching_email(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    ElectionDayService(db).create_operation(campaign.id, ElectionDayOperationCreate(electoral_process_id=process.id, election_date=date(2027, 2, 14)), executive)
    place = _polling_place(db, process, canton, parish_a)
    existing = _bare_user(db)
    invitation, token = _create_invite(db, campaign, executive, polling_place_ids=[place.id], email=existing.email)
    other_user = _bare_user(db)
    with pytest.raises(PermissionError):
        ElectionDayStaffInvitationService(db).accept_existing(token, other_user)
    db.refresh(invitation)
    assert invitation.status == "PENDING"


def test_accept_existing_does_not_create_a_new_user(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    ElectionDayService(db).create_operation(campaign.id, ElectionDayOperationCreate(electoral_process_id=process.id, election_date=date(2027, 2, 14)), executive)
    place = _polling_place(db, process, canton, parish_a)
    existing = _bare_user(db)
    invitation, token = _create_invite(db, campaign, executive, polling_place_ids=[place.id], email=existing.email)
    before = db.query(User).count()
    accepted = ElectionDayStaffInvitationService(db).accept_existing(token, existing)
    after = db.query(User).count()
    assert before == after
    assert accepted.accepted_user_id == existing.id
    assignments = db.query(ElectionDayAssignment).filter(ElectionDayAssignment.user_id == existing.id).all()
    assert len(assignments) == 1 and assignments[0].polling_place_id == place.id


# ---------- Idempotencia (§13) ----------

def test_accept_new_account_is_idempotent_on_replay(db, admin, ed):
    campaign, executive, invitation, token, place = _setup_with_operation(db, admin, ed)
    service = ElectionDayStaffInvitationService(db)
    payload = ElectionDayInvitationAcceptNewAccount(token=token, first_name="Juana", last_name="Perez", password="Passw0rd1", password_confirmation="Passw0rd1")
    first = service.accept_new_account(token, payload)
    second = service.accept_new_account(token, payload)
    assert first.accepted_user_id == second.accepted_user_id
    assert db.query(User).filter(User.email == invitation.email).count() == 1
    assignments = db.query(ElectionDayAssignment).filter(ElectionDayAssignment.user_id == first.accepted_user_id).all()
    assert len(assignments) == 1


def test_accept_existing_is_idempotent_on_replay(db, admin, ed):
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    ElectionDayService(db).create_operation(campaign.id, ElectionDayOperationCreate(electoral_process_id=process.id, election_date=date(2027, 2, 14)), executive)
    place = _polling_place(db, process, canton, parish_a)
    existing = _bare_user(db)
    invitation, token = _create_invite(db, campaign, executive, polling_place_ids=[place.id], email=existing.email)
    service = ElectionDayStaffInvitationService(db)
    service.accept_existing(token, existing)
    service.accept_existing(token, existing)
    assignments = db.query(ElectionDayAssignment).filter(ElectionDayAssignment.user_id == existing.id).all()
    assert len(assignments) == 1


# ---------- Revocar / reemitir (§15/§16) ----------

def test_revoke_only_pending_and_only_executive(db, admin, ed):
    campaign, executive, invitation, token, place = _setup_with_operation(db, admin, ed)
    coordinator = _member(db, admin, campaign, "TERRITORIAL_COORDINATOR")
    with pytest.raises(PermissionError):
        ElectionDayStaffInvitationService(db).revoke(campaign.id, invitation.id, coordinator)
    revoked = ElectionDayStaffInvitationService(db).revoke(campaign.id, invitation.id, executive)
    assert revoked.status == "REVOKED"
    assert revoked.revoked_by_user_id == executive.id
    with pytest.raises(BusinessRuleError):
        ElectionDayStaffInvitationService(db).revoke(campaign.id, invitation.id, executive)


def test_reissue_only_pending(db, admin, ed):
    campaign, executive, invitation, token, place = _setup_with_operation(db, admin, ed)
    ElectionDayStaffInvitationService(db).revoke(campaign.id, invitation.id, executive)
    with pytest.raises(BusinessRuleError):
        ElectionDayStaffInvitationService(db).reissue(campaign.id, invitation.id, executive)


# ---------- Acceso sin CampaignUser (§18/§19/§20) ----------

def test_staff_without_campaign_user_can_read_my_context_and_my_assignments(db, admin, ed):
    campaign, executive, invitation, token, place = _setup_with_operation(db, admin, ed)
    accepted = ElectionDayStaffInvitationService(db).accept_new_account(token, ElectionDayInvitationAcceptNewAccount(token=token, first_name="Juana", last_name="Perez", password="Passw0rd1", password_confirmation="Passw0rd1"))
    user = db.get(User, accepted.accepted_user_id)
    assert db.query(CampaignUser).filter(CampaignUser.user_id == user.id).count() == 0

    context = ElectionDayStaffInvitationService(db).my_context(campaign.id, user)
    assert context["campaign_id"] == campaign.id
    assert "POLLING_PLACE_DELEGATE" in context["staff_types"]
    assert [p["id"] for p in context["polling_places"]] == [place.id]

    assignments = ElectionDayService(db).my_assignments(campaign.id, user)
    assert len(assignments) == 1 and assignments[0].polling_place_id == place.id

    contexts = ElectionDayStaffInvitationService(db).my_contexts(user)
    assert len(contexts) == 1 and contexts[0]["campaign_id"] == campaign.id


def test_staff_without_campaign_user_cannot_access_general_campaign_api(db, admin, ed):
    from app.services.campaign_access_service import CampaignAccessService
    campaign, executive, invitation, token, place = _setup_with_operation(db, admin, ed)
    accepted = ElectionDayStaffInvitationService(db).accept_new_account(token, ElectionDayInvitationAcceptNewAccount(token=token, first_name="Juana", last_name="Perez", password="Passw0rd1", password_confirmation="Passw0rd1"))
    user = db.get(User, accepted.accepted_user_id)
    with pytest.raises(PermissionError):
        CampaignAccessService(db).require_access(campaign.id, user)


def test_delegate_and_validator_without_campaign_user_cannot_reach_control_center(db, admin, ed):
    from app.services.election_day_access_service import ElectionDayAccessService
    campaign, executive, invitation, token, place = _setup_with_operation(db, admin, ed)
    accepted = ElectionDayStaffInvitationService(db).accept_new_account(token, ElectionDayInvitationAcceptNewAccount(token=token, first_name="Juana", last_name="Perez", password="Passw0rd1", password_confirmation="Passw0rd1"))
    delegate = db.get(User, accepted.accepted_user_id)
    with pytest.raises(PermissionError):
        ElectionDayAccessService(db).require_control_center_access(campaign.id, delegate)

    ed2 = _election_day_dataset(db, admin, 78)
    campaign2, executive2, invitation2, token2, _place2 = _setup_with_operation(db, admin, ed2, staff_type="ACT_VALIDATOR")
    accepted2 = ElectionDayStaffInvitationService(db).accept_new_account(token2, ElectionDayInvitationAcceptNewAccount(token=token2, first_name="Carlos", last_name="Vega", password="Passw0rd1", password_confirmation="Passw0rd1"))
    validator = db.get(User, accepted2.accepted_user_id)
    with pytest.raises(PermissionError):
        ElectionDayAccessService(db).require_control_center_access(campaign2.id, validator)


def test_unrelated_executive_role_holder_cannot_reach_another_campaigns_control_center(db, admin, ed):
    """Blindaje contra escalamiento: is_executive() es un chequeo de rol
    GLOBAL. Sin la membresía real en _campaign(), un CANDIDATE de OTRA
    campaña no debe poder entrar al Centro de Control de esta."""
    from app.services.election_day_access_service import ElectionDayAccessService
    campaign, canton, parish_a, parish_b, process = ed
    executive = _member(db, admin, campaign, "CANDIDATE")
    ElectionDayService(db).create_operation(campaign.id, ElectionDayOperationCreate(electoral_process_id=process.id, election_date=date(2027, 2, 14)), executive)
    outsider = User(email=f"outsider-{uuid4().hex[:6]}@example.com", username=f"outsider-{uuid4().hex[:6]}", first_name="Out", last_name="Sider", hashed_password=hash_password("OutsiderPass123"), is_active=True, roles=[RoleService(db).repository.get_by_code("CANDIDATE")])
    db.add(outsider)
    db.commit()
    with pytest.raises(PermissionError):
        ElectionDayAccessService(db).require_control_center_access(campaign.id, outsider)


# ---------- Auditoría (§17) ----------

def test_audit_events_recorded_without_sensitive_fields(db, admin, ed):
    campaign, executive, invitation, token, place = _setup_with_operation(db, admin, ed)
    ElectionDayStaffInvitationService(db).accept_new_account(token, ElectionDayInvitationAcceptNewAccount(token=token, first_name="Juana", last_name="Perez", password="Passw0rd1", password_confirmation="Passw0rd1"))
    events = db.query(SecurityAuditEvent).filter(SecurityAuditEvent.event_type.in_([
        "ELECTION_DAY_STAFF_INVITED", "ELECTION_DAY_STAFF_INVITATION_ACCEPTED", "ELECTION_DAY_STAFF_ACCOUNT_CREATED",
    ])).all()
    event_types = {e.event_type for e in events}
    assert {"ELECTION_DAY_STAFF_INVITED", "ELECTION_DAY_STAFF_INVITATION_ACCEPTED", "ELECTION_DAY_STAFF_ACCOUNT_CREATED"} <= event_types
    for event in events:
        metadata_text = str(event.event_metadata).lower()
        assert "token" not in metadata_text
        assert "password" not in metadata_text
        assert "hash" not in metadata_text


# ---------- El token nunca viaja en la URL (path ni query) ----------

def test_openapi_has_no_token_path_routes(client):
    schema = client.get("/openapi.json").json()
    token_paths = [p for p in schema["paths"] if "invitation" in p and "{token}" in p]
    assert token_paths == []
    assert "/api/v1/election-day/invitations/preview" in schema["paths"]
    assert "/api/v1/election-day/invitations/accept" in schema["paths"]
    assert "/api/v1/election-day/invitations/accept-new-account" in schema["paths"]
    assert schema["paths"]["/api/v1/election-day/invitations/preview"]["post"]["requestBody"]


def test_http_preview_accepts_token_only_in_json_body_never_path_or_query(client, db, admin, ed):
    campaign, executive, invitation, token, place = _setup_with_operation(db, admin, ed)
    ok = client.post("/api/v1/election-day/invitations/preview", json={"token": token})
    assert ok.status_code == 200
    assert ok.headers.get("cache-control") == "no-store"
    assert ok.json()["status"] == "PENDING"

    # No debe existir ninguna ruta que acepte el token como segmento de path.
    path_based = client.get(f"/api/v1/election-day/invitations/{token}")
    assert path_based.status_code == 404

    # Un query param nunca es aceptado (el schema exige el token en el JSON body).
    query_based = client.post(f"/api/v1/election-day/invitations/preview?token={token}", json={})
    assert query_based.status_code == 422


def test_http_accept_new_account_end_to_end_via_json_body(client, db, admin, ed):
    campaign, executive, invitation, token, place = _setup_with_operation(db, admin, ed)
    response = client.post(
        "/api/v1/election-day/invitations/accept-new-account",
        json={"token": token, "first_name": "Http", "last_name": "Flow", "password": "Passw0rd1", "password_confirmation": "Passw0rd1"},
    )
    assert response.status_code == 200
    assert response.headers.get("cache-control") == "no-store"
    body = response.json()
    assert body["message"] == "Tu acceso a la Jornada Electoral está listo."
    assert "token" not in body
