"""Fase 3 — Centro de Control Electoral: consolidado factual derivado
EXCLUSIVAMENTE de ElectionAct.status == 'VALIDATED' vía validated_revision_id.
Nunca predicción, proyección, probabilidad ni ganador — un conteo interno
NO OFICIAL. Cubre servicio (conteo/cobertura/aislamiento) y HTTP (matriz RBAC
exacta, CLOSED de solo lectura)."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.historical import ElectoralContest
from app.schemas.election_act import ElectionActCorrectionCreate, ElectionActDraftCreate, ElectionActObserveRequest, ElectionActResultInput, ElectionActValidateRequest
from app.schemas.election_day import ElectionDayAdminSupportStartRequest, ElectionDayAssignmentCreate, ElectionDayCloseRequest
from app.services.election_act_service import ElectionActService
from app.services.election_day_admin_support_service import ElectionDayAdminSupportService
from app.services.election_day_service import ElectionDayService

from tests.test_election_acts import JPEG_BYTES, _candidates
from tests.test_election_day import _board, _create_operation, _election_day_dataset, _member, _polling_place

PASSWORD = "MemberPass123"


@pytest.fixture
def cc_ready(db, admin, client: TestClient):
    """Campaña en SCRUTINY con DOS juntas en el mismo recinto (para poder
    tener varias actas en distintos estados a la vez) y todos los roles
    necesarios para la matriz RBAC del Centro de Control."""
    campaign, canton, parish_a, parish_b, process = _election_day_dataset(db, admin, 601)
    contest = db.scalars(select(ElectoralContest).where(ElectoralContest.electoral_process_id == process.id)).first()
    executive = _member(db, admin, campaign, "CANDIDATE")
    manager = _member(db, admin, campaign, "CAMPAIGN_MANAGER")
    svc = ElectionDayService(db)
    op = _create_operation(db, campaign, process, executive)
    place = _polling_place(db, process, canton, parish_a, code="R01", name="Recinto Uno")
    board1 = _board(db, place, code="J01", number=1)
    board2 = _board(db, place, code="J02", number=2)
    delegate = _member(db, admin, campaign)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=delegate.id, assignment_role="POLLING_PLACE_DELEGATE", polling_place_id=place.id), executive)
    validator = _member(db, admin, campaign)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=validator.id, assignment_role="ACT_VALIDATOR"), executive)
    coordinator = _member(db, admin, campaign, "TERRITORIAL_COORDINATOR")
    analyst = _member(db, admin, campaign, "ANALYST")
    svc.open_operation(campaign.id, executive)
    op = svc.start_scrutiny(campaign.id, executive)
    candidates = _candidates(db, contest, process.source_id)
    return {
        "campaign": campaign, "op": op, "place": place, "board1": board1, "board2": board2,
        "executive": executive, "manager": manager, "delegate": delegate, "validator": validator,
        "coordinator": coordinator, "analyst": analyst, "contest": contest, "candidates": candidates, "admin": admin,
        "parish_id": parish_a.id,
    }


def _draft(ctx, board, votes=(10, 5), blank=1, null=1):
    results = [ElectionActResultInput(electoral_candidate_id=ctx["candidates"][i].id, votes=v) for i, v in enumerate(votes)]
    valid = sum(votes)
    return ElectionActDraftCreate(
        polling_place_id=ctx["place"].id, electoral_board_id=board.id, electoral_contest_id=ctx["contest"].id,
        blank_ballots=blank, null_ballots=null, valid_ballots=valid, ballots_counted=valid + blank + null,
        results=results,
    )


def _submit(service, ctx, board, votes=(10, 5)):
    act, revision = service.create_draft(ctx["campaign"].id, _draft(ctx, board, votes=votes), ctx["delegate"])
    service.upload_evidence(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], file_bytes=JPEG_BYTES, original_filename="a.jpg", client_generated_id=None)
    return service.submit_revision(ctx["campaign"].id, act.id, revision.id, ctx["delegate"])


def _validate(service, ctx, act, revision):
    service.claim(ctx["campaign"].id, act.id, ctx["validator"])
    return service.validate_act(ctx["campaign"].id, act.id, ElectionActValidateRequest(revision_id=revision.id), ctx["validator"])


# ---------- COUNTING: solo VALIDATED suma, siempre vía validated_revision_id ----------

def test_received_does_not_count_votes(db, cc_ready):
    ctx = cc_ready
    service = ElectionActService(db)
    _submit(service, ctx, ctx["board1"], votes=(10, 5))
    summary = service.control_center_summary(ctx["campaign"].id, ctx["executive"])
    contest = summary["contests"][0]
    assert contest["validated_acts"] == 0
    assert contest["valid_votes"] == 0
    assert all(c["votes"] == 0 for c in contest["candidates"])


def test_in_review_does_not_count_votes(db, cc_ready):
    ctx = cc_ready
    service = ElectionActService(db)
    act, revision = _submit(service, ctx, ctx["board1"], votes=(10, 5))
    service.claim(ctx["campaign"].id, act.id, ctx["validator"])
    summary = service.control_center_summary(ctx["campaign"].id, ctx["executive"])
    contest = summary["contests"][0]
    assert contest["validated_acts"] == 0
    assert contest["valid_votes"] == 0


def test_observed_does_not_count_votes(db, cc_ready):
    ctx = cc_ready
    service = ElectionActService(db)
    act, revision = _submit(service, ctx, ctx["board1"], votes=(10, 5))
    service.claim(ctx["campaign"].id, act.id, ctx["validator"])
    service.observe_act(ctx["campaign"].id, act.id, ElectionActObserveRequest(revision_id=revision.id, reason="revisar"), ctx["validator"])
    summary = service.control_center_summary(ctx["campaign"].id, ctx["executive"])
    contest = summary["contests"][0]
    assert contest["validated_acts"] == 0
    assert contest["valid_votes"] == 0


def test_validated_counts_via_validated_revision_id(db, cc_ready):
    ctx = cc_ready
    service = ElectionActService(db)
    act, revision = _submit(service, ctx, ctx["board1"], votes=(10, 5))
    act = _validate(service, ctx, act, revision)
    assert act.validated_revision_id == revision.id
    summary = service.control_center_summary(ctx["campaign"].id, ctx["executive"])
    contest = summary["contests"][0]
    assert contest["validated_acts"] == 1
    assert contest["valid_votes"] == 15
    votes_by_candidate = {c["candidate_id"]: c["votes"] for c in contest["candidates"]}
    assert votes_by_candidate[ctx["candidates"][0].id] == 10
    assert votes_by_candidate[ctx["candidates"][1].id] == 5


def test_old_revision_never_counts_after_correction(db, cc_ready):
    """§9/§30: revisión anterior no suma — la corrección validada reemplaza
    a la observada, nunca se suman ambas ni queda la vieja."""
    ctx = cc_ready
    service = ElectionActService(db)
    act, revision1 = _submit(service, ctx, ctx["board1"], votes=(10, 5))
    service.claim(ctx["campaign"].id, act.id, ctx["validator"])
    service.observe_act(ctx["campaign"].id, act.id, ElectionActObserveRequest(revision_id=revision1.id, reason="no cuadra"), ctx["validator"])

    correction = ElectionActCorrectionCreate(
        blank_ballots=1, null_ballots=1, valid_ballots=20, ballots_counted=22,
        results=[ElectionActResultInput(electoral_candidate_id=ctx["candidates"][0].id, votes=14), ElectionActResultInput(electoral_candidate_id=ctx["candidates"][1].id, votes=6)],
        correction_reason="recuento físico",
    )
    act, revision2 = service.create_correction(ctx["campaign"].id, act.id, correction, ctx["delegate"])
    service.upload_evidence(ctx["campaign"].id, act.id, revision2.id, ctx["delegate"], file_bytes=JPEG_BYTES, original_filename="b.jpg", client_generated_id=None)
    act, revision2 = service.submit_revision(ctx["campaign"].id, act.id, revision2.id, ctx["delegate"])
    act = _validate(service, ctx, act, revision2)
    assert act.validated_revision_id == revision2.id

    summary = service.control_center_summary(ctx["campaign"].id, ctx["executive"])
    contest = summary["contests"][0]
    assert contest["validated_acts"] == 1  # nunca 2 (no se cuentan ambas revisiones)
    assert contest["valid_votes"] == 20  # la corrección (20), no la original (15)
    votes_by_candidate = {c["candidate_id"]: c["votes"] for c in contest["candidates"]}
    assert votes_by_candidate[ctx["candidates"][0].id] == 14
    assert votes_by_candidate[ctx["candidates"][1].id] == 6


def test_multiple_validated_acts_sum_correctly_blank_null(db, cc_ready):
    ctx = cc_ready
    service = ElectionActService(db)
    act1, rev1 = _submit(service, ctx, ctx["board1"], votes=(10, 5))
    _validate(service, ctx, act1, rev1)
    act2, rev2 = _submit(service, ctx, ctx["board2"], votes=(7, 3))
    _validate(service, ctx, act2, rev2)

    summary = service.control_center_summary(ctx["campaign"].id, ctx["executive"])
    contest = summary["contests"][0]
    assert contest["validated_acts"] == 2
    assert contest["valid_votes"] == 25
    assert contest["blank_votes"] == 2
    assert contest["null_votes"] == 2
    assert contest["ballots_counted"] == 29
    votes_by_candidate = {c["candidate_id"]: c["votes"] for c in contest["candidates"]}
    assert votes_by_candidate[ctx["candidates"][0].id] == 17
    assert votes_by_candidate[ctx["candidates"][1].id] == 8


# ---------- COVERAGE ----------

def test_coverage_expected_received_validated_pending(db, cc_ready):
    ctx = cc_ready
    service = ElectionActService(db)
    act1, rev1 = _submit(service, ctx, ctx["board1"], votes=(10, 5))
    _validate(service, ctx, act1, rev1)
    # board2 sin acta todavía -> pending
    summary = service.control_center_summary(ctx["campaign"].id, ctx["executive"])
    cov = summary["acts_coverage"]
    assert cov["expected_boards"] == 2
    assert cov["received"] == 1
    assert cov["validated"] == 1
    assert cov["pending"] == 1
    assert cov["received_coverage_pct"] == 50.0
    assert cov["validated_coverage_pct"] == 50.0


def test_coverage_percentages_denominator_zero_never_divides_by_zero(db, admin):
    """Operación sin ninguna junta configurada: expected_boards=0, los
    porcentajes deben ser 0.0, nunca ZeroDivisionError."""
    campaign, canton, parish_a, parish_b, process = _election_day_dataset(db, admin, 602)
    executive = _member(db, admin, campaign, "CANDIDATE")
    op = _create_operation(db, campaign, process, executive)
    validator = _member(db, admin, campaign)
    from app.services.election_day_service import ElectionDayService as _S
    svc = _S(db)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=validator.id, assignment_role="ACT_VALIDATOR"), executive)
    service = ElectionActService(db)
    summary = service.control_center_summary(campaign.id, executive)
    cov = summary["acts_coverage"]
    assert cov["expected_boards"] == 0
    assert cov["received_coverage_pct"] == 0.0
    assert cov["validated_coverage_pct"] == 0.0
    assert summary["polling_places"] == []
    assert summary["parishes"] == []


def test_candidate_percentage_zero_when_no_valid_votes_yet(db, cc_ready):
    ctx = cc_ready
    service = ElectionActService(db)
    summary = service.control_center_summary(ctx["campaign"].id, ctx["executive"])
    contest = summary["contests"][0]
    assert contest["valid_votes"] == 0
    assert all(c["pct_valid_votes"] == 0.0 for c in contest["candidates"])


# ---------- Recintos / parroquias ----------

def test_polling_place_and_parish_breakdown(db, cc_ready):
    ctx = cc_ready
    service = ElectionActService(db)
    act1, rev1 = _submit(service, ctx, ctx["board1"], votes=(10, 5))
    _validate(service, ctx, act1, rev1)

    summary = service.control_center_summary(ctx["campaign"].id, ctx["executive"])
    places = {p["polling_place_id"]: p for p in summary["polling_places"]}
    place_summary = places[ctx["place"].id]
    assert place_summary["expected_boards"] == 2
    assert place_summary["validated"] == 1
    assert place_summary["pending"] == 1
    assert place_summary["coverage_validated_pct"] == 50.0

    parishes = {p["parish_id"]: p for p in summary["parishes"]}
    parish_summary = parishes[ctx["parish_id"]]
    assert parish_summary["expected_boards"] == 2
    assert parish_summary["validated"] == 1
    assert parish_summary["valid_votes"] == 15
    assert parish_summary["blank_votes"] == 1
    assert parish_summary["null_votes"] == 1


# ---------- Multi-contienda (§16): nunca mezclar votos de dignidades/ámbitos distintos ----------

def test_multiple_eligible_contests_never_mix_votes(db, admin):
    """Dos contiendas PARISH_BOARD elegibles a la vez (una por parroquia):
    cada una debe sumar únicamente los votos y la cobertura de SU propia
    parroquia, nunca mezclarse con la otra."""
    campaign, canton, parish_a, parish_b, process = _election_day_dataset(db, admin, 620)
    campaign.office_type = "PARISH_BOARD"
    db.add(campaign)
    db.commit()
    contest_a = ElectoralContest(electoral_process_id=process.id, office_type="PARISH_BOARD", name="Junta Parroquial A", vote_method="SINGLE_CHOICE", canton_id=canton.id, parish_id=parish_a.id, seats=1, is_active=True)
    contest_b = ElectoralContest(electoral_process_id=process.id, office_type="PARISH_BOARD", name="Junta Parroquial B", vote_method="SINGLE_CHOICE", canton_id=canton.id, parish_id=parish_b.id, seats=1, is_active=True)
    db.add_all([contest_a, contest_b])
    db.commit()

    executive = _member(db, admin, campaign, "CANDIDATE")
    svc = ElectionDayService(db)
    op = _create_operation(db, campaign, process, executive)
    place_a = _polling_place(db, process, canton, parish_a, code="RA", name="Recinto A")
    board_a = _board(db, place_a, code="JA1")
    place_b = _polling_place(db, process, canton, parish_b, code="RB", name="Recinto B")
    board_b = _board(db, place_b, code="JB1")
    delegate = _member(db, admin, campaign)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=delegate.id, assignment_role="POLLING_PLACE_DELEGATE", polling_place_id=place_a.id), executive)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=delegate.id, assignment_role="POLLING_PLACE_DELEGATE", polling_place_id=place_b.id), executive)
    validator = _member(db, admin, campaign)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=validator.id, assignment_role="ACT_VALIDATOR"), executive)
    svc.open_operation(campaign.id, executive)
    svc.start_scrutiny(campaign.id, executive)
    candidates_a = _candidates(db, contest_a, process.source_id)
    candidates_b = _candidates(db, contest_b, process.source_id)

    service = ElectionActService(db)
    ctx_a = {"campaign": campaign, "place": place_a, "contest": contest_a, "candidates": candidates_a, "delegate": delegate, "validator": validator}
    ctx_b = {"campaign": campaign, "place": place_b, "contest": contest_b, "candidates": candidates_b, "delegate": delegate, "validator": validator}
    act_a, rev_a = _submit(service, ctx_a, board_a, votes=(8, 2))
    _validate(service, ctx_a, act_a, rev_a)
    act_b, rev_b = _submit(service, ctx_b, board_b, votes=(3, 1))
    _validate(service, ctx_b, act_b, rev_b)

    summary = service.control_center_summary(campaign.id, executive)
    contests = {c["contest_id"]: c for c in summary["contests"]}
    assert len(contests) == 2
    assert contests[contest_a.id]["valid_votes"] == 10
    assert contests[contest_a.id]["expected_acts"] == 1  # solo la junta de parish_a
    assert contests[contest_b.id]["valid_votes"] == 4
    assert contests[contest_b.id]["expected_acts"] == 1  # solo la junta de parish_b
    votes_a = {c["candidate_id"]: c["votes"] for c in contests[contest_a.id]["candidates"]}
    votes_b = {c["candidate_id"]: c["votes"] for c in contests[contest_b.id]["candidates"]}
    assert votes_a[candidates_a[0].id] == 8
    assert votes_b[candidates_b[0].id] == 3
    # Los candidatos de una contienda nunca aparecen en la otra.
    assert set(votes_a) == {c.id for c in candidates_a}
    assert set(votes_b) == {c.id for c in candidates_b}


# ---------- ISOLATION ----------

def test_isolation_across_campaigns(db, admin):
    """Dos campañas/operaciones independientes: el consolidado de una nunca
    incluye actas de la otra (aislamiento por campaign/organization/operation/
    process/canton/contest, todos distintos aquí)."""
    campaign_a, canton_a, parish_a1, _, process_a = _election_day_dataset(db, admin, 610)
    campaign_b, canton_b, parish_b1, _, process_b = _election_day_dataset(db, admin, 611)
    contest_a = db.scalars(select(ElectoralContest).where(ElectoralContest.electoral_process_id == process_a.id)).first()
    contest_b = db.scalars(select(ElectoralContest).where(ElectoralContest.electoral_process_id == process_b.id)).first()

    def setup(campaign, canton, parish, process, contest, idx):
        executive = _member(db, admin, campaign, "CANDIDATE")
        svc = ElectionDayService(db)
        op = _create_operation(db, campaign, process, executive)
        place = _polling_place(db, process, canton, parish, code=f"R{idx}", name=f"Recinto {idx}")
        board = _board(db, place, code=f"J{idx}")
        delegate = _member(db, admin, campaign)
        svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=delegate.id, assignment_role="POLLING_PLACE_DELEGATE", polling_place_id=place.id), executive)
        validator = _member(db, admin, campaign)
        svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=validator.id, assignment_role="ACT_VALIDATOR"), executive)
        svc.open_operation(campaign.id, executive)
        svc.start_scrutiny(campaign.id, executive)
        candidates = _candidates(db, contest, process.source_id)
        return {"campaign": campaign, "place": place, "board": board, "delegate": delegate, "validator": validator, "executive": executive, "contest": contest, "candidates": candidates}

    ctx_a = setup(campaign_a, canton_a, parish_a1, process_a, contest_a, 1)
    ctx_b = setup(campaign_b, canton_b, parish_b1, process_b, contest_b, 2)

    service = ElectionActService(db)
    act_a, rev_a = _submit(service, ctx_a, ctx_a["board"], votes=(10, 5))
    _validate(service, ctx_a, act_a, rev_a)

    summary_b = service.control_center_summary(campaign_b.id, ctx_b["executive"])
    assert summary_b["acts_coverage"]["validated"] == 0
    assert summary_b["contests"][0]["validated_acts"] == 0
    assert summary_b["contests"][0]["valid_votes"] == 0

    summary_a = service.control_center_summary(campaign_a.id, ctx_a["executive"])
    assert summary_a["acts_coverage"]["validated"] == 1
    assert summary_a["contests"][0]["valid_votes"] == 15


# ---------- CLOSED ----------

def test_control_center_readable_when_closed(db, cc_ready):
    ctx = cc_ready
    service = ElectionActService(db)
    act1, rev1 = _submit(service, ctx, ctx["board1"], votes=(10, 5))
    _validate(service, ctx, act1, rev1)
    ElectionDayService(db).close_operation(ctx["campaign"].id, ElectionDayCloseRequest(), ctx["executive"])
    summary = service.control_center_summary(ctx["campaign"].id, ctx["executive"])
    assert summary["contests"][0]["valid_votes"] == 15


# ---------- ACCESS (HTTP real) ----------

def _login(client: TestClient, username: str) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", data={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_access_matrix_http(client: TestClient, db, cc_ready, admin_headers):
    ctx = cc_ready
    campaign_id = ctx["campaign"].id
    url = f"/api/v1/campaigns/{campaign_id}/election-day/control-center"

    allowed = {"executive": 200, "manager": 200}
    for key, expected in allowed.items():
        headers = _login(client, ctx[key].username)
        resp = client.get(url, headers=headers)
        assert resp.status_code == expected, f"{key}: {resp.text}"
        assert "control_center" in resp.json()

    denied = {"validator": 403, "delegate": 403, "analyst": 403, "coordinator": 403}
    for key, expected in denied.items():
        headers = _login(client, ctx[key].username)
        resp = client.get(url, headers=headers)
        assert resp.status_code == expected, f"{key}: {resp.text}"

    # ADMIN sin soporte activo -> 403.
    resp = client.get(url, headers=admin_headers)
    assert resp.status_code == 403, resp.text

    # ADMIN con soporte activo -> 200, mismos números que el ejecutivo.
    ElectionDayAdminSupportService(db).start(campaign_id, ElectionDayAdminSupportStartRequest(reason="auditoría"), ctx["admin"])
    resp = client.get(url, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    exec_headers = _login(client, ctx["executive"].username)
    exec_resp = client.get(url, headers=exec_headers)
    assert resp.json()["control_center"]["acts_coverage"] == exec_resp.json()["control_center"]["acts_coverage"]


def test_no_official_language_leaks_into_response_shape(cc_ready):
    """No es un test de UI, pero confirma que el contrato de datos nunca
    incluye campos de predicción/ranking/ganador — solo lo enumerado."""
    from app.schemas.election_act import ControlCenterContestSummary, ControlCenterCandidateResult
    contest_fields = set(ControlCenterContestSummary.model_fields.keys())
    candidate_fields = set(ControlCenterCandidateResult.model_fields.keys())
    forbidden = {"winner", "is_winner", "probability", "win_probability", "projection", "forecast", "rank", "trend"}
    assert not (contest_fields & forbidden)
    assert not (candidate_fields & forbidden)
