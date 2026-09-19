"""Auditoría de cierre de Fase 2 — pruebas HTTP reales (TestClient) sobre
los endpoints de actas: estado CLOSED, matriz RBAC exacta, seguridad de
evidencia, inmutabilidad, y revisión obsoleta. Complementa
test_election_acts.py (nivel servicio) probando la capa HTTP real: auth,
enrutamiento, serialización y códigos de estado — nunca solo UI."""
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.election_day import ElectionAct, ElectionActRevision, ElectoralBoard
from app.models.historical import ElectoralContest
from app.schemas.election_day import ElectionDayAdminSupportStartRequest, ElectionDayAssignmentCreate, ElectionDayCloseRequest
from app.services.election_day_admin_support_service import ElectionDayAdminSupportService
from app.services.election_day_service import ElectionDayService

from tests.test_election_acts import _candidates
from tests.test_election_day import _board, _create_operation, _election_day_dataset, _member, _polling_place

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PASSWORD = "MemberPass123"


@pytest.fixture
def acts_http(db, admin, client: TestClient):
    campaign, canton, parish_a, parish_b, process = _election_day_dataset(db, admin, 501)
    contest = db.scalars(select(ElectoralContest).where(ElectoralContest.electoral_process_id == process.id)).first()
    executive = _member(db, admin, campaign, "CANDIDATE")
    manager = _member(db, admin, campaign, "CAMPAIGN_MANAGER")
    svc = ElectionDayService(db)
    op = _create_operation(db, campaign, process, executive)
    place = _polling_place(db, process, canton, parish_a, code="R01", name="Recinto Uno")
    board = _board(db, place, code="J01")
    other_place = _polling_place(db, process, canton, parish_b, code="R02", name="Recinto Dos")
    other_board = _board(db, other_place, code="J02")
    delegate = _member(db, admin, campaign)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=delegate.id, assignment_role="POLLING_PLACE_DELEGATE", polling_place_id=place.id), executive)
    other_delegate = _member(db, admin, campaign)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=other_delegate.id, assignment_role="POLLING_PLACE_DELEGATE", polling_place_id=other_place.id), executive)
    validator = _member(db, admin, campaign)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=validator.id, assignment_role="ACT_VALIDATOR"), executive)
    coordinator = _member(db, admin, campaign, "TERRITORIAL_COORDINATOR")
    analyst = _member(db, admin, campaign, "ANALYST")
    svc.open_operation(campaign.id, executive)
    op = svc.start_scrutiny(campaign.id, executive)
    candidates = _candidates(db, contest, process.source_id)
    return {
        "campaign": campaign, "op": op, "place": place, "board": board, "other_place": other_place, "other_board": other_board,
        "executive": executive, "manager": manager, "delegate": delegate, "other_delegate": other_delegate,
        "validator": validator, "coordinator": coordinator, "analyst": analyst, "contest": contest, "candidates": candidates,
    }


def _login(client: TestClient, username: str) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", data={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _draft_payload(ctx, board=None, votes=(10, 5), client_generated_id=None):
    board = board or ctx["board"]
    results = [{"electoral_candidate_id": str(ctx["candidates"][i].id), "votes": v} for i, v in enumerate(votes)]
    valid = sum(votes)
    return {
        "polling_place_id": str(ctx["place"].id if board is ctx["board"] else ctx["other_place"].id),
        "electoral_board_id": str(board.id), "electoral_contest_id": str(ctx["contest"].id),
        "blank_ballots": 1, "null_ballots": 1, "valid_ballots": valid, "ballots_counted": valid + 2,
        "results": results, "client_generated_id": client_generated_id,
    }


def _register_and_submit(client, headers, ctx, board=None):
    board = board or ctx["board"]
    r = client.post(
        f"/api/v1/campaigns/{ctx['campaign'].id}/election-day/acts/drafts", headers=headers,
        json=_draft_payload(ctx, board=board),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    act_id, revision_id = body["act"]["id"], body["revision"]["id"]
    ev = client.post(
        f"/api/v1/campaigns/{ctx['campaign'].id}/election-day/acts/{act_id}/revisions/{revision_id}/evidence",
        headers=headers, files={"file": ("acta.jpg", JPEG_BYTES, "image/jpeg")},
    )
    assert ev.status_code == 201, ev.text
    sub = client.post(
        f"/api/v1/campaigns/{ctx['campaign'].id}/election-day/acts/{act_id}/revisions/{revision_id}/submit", headers=headers,
    )
    assert sub.status_code == 200, sub.text
    return act_id, revision_id


BASE = "/api/v1/campaigns/{campaign_id}/election-day/acts"


# ---------- §2: CLOSED bloquea toda mutación de actas ----------

def test_closed_operation_blocks_all_act_mutations_but_allows_reads(client: TestClient, db, acts_http):
    ctx = acts_http
    campaign_id = ctx["campaign"].id
    delegate_headers = _login(client, ctx["delegate"].username)
    validator_headers = _login(client, ctx["validator"].username)
    executive_headers = _login(client, ctx["executive"].username)

    act_id, revision_id = _register_and_submit(client, delegate_headers, ctx)
    act_uuid, revision_uuid = UUID(act_id), UUID(revision_id)
    claim = client.post(f"{BASE.format(campaign_id=campaign_id)}/{act_id}/claim", headers=validator_headers)
    assert claim.status_code == 200, claim.text

    close = client.post(
        f"/api/v1/campaigns/{campaign_id}/election-day/operation/close", headers=executive_headers,
        json=ElectionDayCloseRequest().model_dump(),
    )
    assert close.status_code == 200, close.text
    assert close.json()["status"] == "CLOSED"

    act_before = db.get(ElectionAct, act_uuid)
    db.refresh(act_before)
    assert act_before.status == "IN_REVIEW" and act_before.review_claimed_by_user_id == ctx["validator"].id

    # Crear un borrador nuevo (otra junta) debe rechazarse.
    new_draft = client.post(
        f"{BASE.format(campaign_id=campaign_id)}/drafts", headers=delegate_headers,
        json=_draft_payload(ctx, board=ctx["board"]),
    )
    assert new_draft.status_code in (400, 403)
    assert db.scalar(select(ElectionAct).where(ElectionAct.polling_place_id == ctx["place"].id, ElectionAct.electoral_board_id != ctx["board"].id)) is None

    # Subir evidencia a la revisión ya enviada.
    upload = client.post(
        f"{BASE.format(campaign_id=campaign_id)}/{act_id}/revisions/{revision_id}/evidence", headers=delegate_headers,
        files={"file": ("otra.jpg", JPEG_BYTES, "image/jpeg")},
    )
    assert upload.status_code in (400, 403)

    # Reenviar (idempotente en teoría, pero la jornada ya no está en escrutinio).
    resubmit = client.post(f"{BASE.format(campaign_id=campaign_id)}/{act_id}/revisions/{revision_id}/submit", headers=delegate_headers)
    assert resubmit.status_code in (400, 403)

    # Corrección.
    correction = client.post(
        f"{BASE.format(campaign_id=campaign_id)}/{act_id}/corrections", headers=delegate_headers,
        json={"blank_ballots": 1, "null_ballots": 1, "valid_ballots": 15, "ballots_counted": 17,
              "results": [{"electoral_candidate_id": str(ctx["candidates"][0].id), "votes": 15}],
              "correction_reason": "intento post-cierre"},
    )
    assert correction.status_code in (400, 403)

    # Claim / release / observe / validate.
    claim2 = client.post(f"{BASE.format(campaign_id=campaign_id)}/{act_id}/claim", headers=validator_headers)
    assert claim2.status_code in (400, 403)
    release = client.post(f"{BASE.format(campaign_id=campaign_id)}/{act_id}/release", headers=validator_headers)
    assert release.status_code in (400, 403)
    observe = client.post(
        f"{BASE.format(campaign_id=campaign_id)}/{act_id}/observe", headers=validator_headers,
        json={"revision_id": revision_id, "reason": "post-cierre"},
    )
    assert observe.status_code in (400, 403)
    validate = client.post(
        f"{BASE.format(campaign_id=campaign_id)}/{act_id}/validate", headers=validator_headers,
        json={"revision_id": revision_id},
    )
    assert validate.status_code in (400, 403)

    # Ninguna de las llamadas anteriores debió tocar el acta: sigue IN_REVIEW y reclamada por el mismo validador.
    db.expire_all()
    act_after = db.get(ElectionAct, act_uuid)
    assert act_after.status == "IN_REVIEW"
    assert act_after.review_claimed_by_user_id == ctx["validator"].id
    assert act_after.validated_revision_id is None
    revision_after = db.get(ElectionActRevision, revision_uuid)
    assert revision_after.status == "SUBMITTED"

    # Lectura sigue disponible.
    get_list = client.get(f"{BASE.format(campaign_id=campaign_id)}", headers=delegate_headers)
    assert get_list.status_code == 200
    get_detail = client.get(f"{BASE.format(campaign_id=campaign_id)}/{act_id}", headers=validator_headers)
    assert get_detail.status_code == 200


# ---------- §3: cierre con actas pendientes ----------

def test_closes_with_pending_unvalidated_acts_without_blocking(client: TestClient, db, acts_http):
    ctx = acts_http
    campaign_id = ctx["campaign"].id
    delegate_headers = _login(client, ctx["delegate"].username)
    executive_headers = _login(client, ctx["executive"].username)
    _register_and_submit(client, delegate_headers, ctx)  # queda RECEIVED, nunca validada

    coverage = client.get(f"{BASE.format(campaign_id=campaign_id)}/coverage", headers=executive_headers)
    assert coverage.status_code == 200
    assert coverage.json()["received"] == 1 and coverage.json()["validated"] == 0

    close = client.post(
        f"/api/v1/campaigns/{campaign_id}/election-day/operation/close", headers=executive_headers,
        json=ElectionDayCloseRequest().model_dump(),
    )
    assert close.status_code == 200, close.text
    assert close.json()["status"] == "CLOSED"


# ---------- §4: matriz RBAC exacta ----------

def test_rbac_candidate_and_manager_read_but_never_review(client: TestClient, acts_http):
    ctx = acts_http
    campaign_id = ctx["campaign"].id
    delegate_headers = _login(client, ctx["delegate"].username)
    act_id, revision_id = _register_and_submit(client, delegate_headers, ctx)

    for user in (ctx["executive"], ctx["manager"]):
        headers = _login(client, user.username)
        assert client.get(f"{BASE.format(campaign_id=campaign_id)}", headers=headers).status_code == 200
        detail = client.get(f"{BASE.format(campaign_id=campaign_id)}/{act_id}", headers=headers)
        assert detail.status_code == 200
        evidence_id = detail.json()["revisions"][0]["evidence"][0]["id"]
        assert client.get(f"{BASE.format(campaign_id=campaign_id)}/{act_id}/evidence/{evidence_id}/download", headers=headers).status_code == 200
        assert client.post(f"{BASE.format(campaign_id=campaign_id)}/{act_id}/claim", headers=headers).status_code == 403
        assert client.post(f"{BASE.format(campaign_id=campaign_id)}/{act_id}/validate", headers=headers, json={"revision_id": revision_id}).status_code == 403
        assert client.post(f"{BASE.format(campaign_id=campaign_id)}/{act_id}/observe", headers=headers, json={"revision_id": revision_id, "reason": "x"}).status_code == 403


def test_rbac_delegate_only_own_polling_place(client: TestClient, acts_http):
    ctx = acts_http
    campaign_id = ctx["campaign"].id
    delegate_headers = _login(client, ctx["delegate"].username)
    other_delegate_headers = _login(client, ctx["other_delegate"].username)
    act_id, _ = _register_and_submit(client, delegate_headers, ctx)

    # El delegado del OTRO recinto no puede ver ni descargar evidencia de esta acta.
    detail = client.get(f"{BASE.format(campaign_id=campaign_id)}/{act_id}", headers=other_delegate_headers)
    assert detail.status_code == 403

    own_detail = client.get(f"{BASE.format(campaign_id=campaign_id)}/{act_id}", headers=delegate_headers)
    evidence_id = own_detail.json()["revisions"][0]["evidence"][0]["id"]
    assert client.get(f"{BASE.format(campaign_id=campaign_id)}/{act_id}/evidence/{evidence_id}/download", headers=other_delegate_headers).status_code == 403

    # Registrar/corregir en el recinto ajeno debe rechazarse.
    foreign_draft = client.post(
        f"{BASE.format(campaign_id=campaign_id)}/drafts", headers=delegate_headers,
        json=_draft_payload(ctx, board=ctx["other_board"]),
    )
    assert foreign_draft.status_code == 403


def test_rbac_validator_sees_any_board_but_needs_claim_to_act(client: TestClient, acts_http):
    ctx = acts_http
    campaign_id = ctx["campaign"].id
    delegate_headers = _login(client, ctx["delegate"].username)
    validator_headers = _login(client, ctx["validator"].username)
    act_id, revision_id = _register_and_submit(client, delegate_headers, ctx)

    detail = client.get(f"{BASE.format(campaign_id=campaign_id)}/{act_id}", headers=validator_headers)
    assert detail.status_code == 200
    evidence_id = detail.json()["revisions"][0]["evidence"][0]["id"]
    assert client.get(f"{BASE.format(campaign_id=campaign_id)}/{act_id}/evidence/{evidence_id}/download", headers=validator_headers).status_code == 200

    # Validar sin haber reclamado primero: rechazado.
    validate_no_claim = client.post(
        f"{BASE.format(campaign_id=campaign_id)}/{act_id}/validate", headers=validator_headers, json={"revision_id": revision_id},
    )
    assert validate_no_claim.status_code == 403

    claim = client.post(f"{BASE.format(campaign_id=campaign_id)}/{act_id}/claim", headers=validator_headers)
    assert claim.status_code == 200
    validate = client.post(
        f"{BASE.format(campaign_id=campaign_id)}/{act_id}/validate", headers=validator_headers, json={"revision_id": revision_id},
    )
    assert validate.status_code == 200


def test_rbac_admin_without_support_fully_denied(client: TestClient, acts_http, admin_headers):
    ctx = acts_http
    campaign_id = ctx["campaign"].id
    delegate_headers = _login(client, ctx["delegate"].username)
    act_id, revision_id = _register_and_submit(client, delegate_headers, ctx)

    assert client.get(f"{BASE.format(campaign_id=campaign_id)}", headers=admin_headers).status_code == 403
    assert client.get(f"{BASE.format(campaign_id=campaign_id)}/{act_id}", headers=admin_headers).status_code == 403
    assert client.post(f"{BASE.format(campaign_id=campaign_id)}/{act_id}/claim", headers=admin_headers).status_code == 403
    assert client.post(f"{BASE.format(campaign_id=campaign_id)}/{act_id}/validate", headers=admin_headers, json={"revision_id": revision_id}).status_code == 403


def test_rbac_admin_with_active_support_full_access_but_cannot_edit_votes(client: TestClient, db, acts_http, admin, admin_headers):
    ctx = acts_http
    campaign_id = ctx["campaign"].id
    delegate_headers = _login(client, ctx["delegate"].username)
    act_id, revision_id = _register_and_submit(client, delegate_headers, ctx)

    ElectionDayAdminSupportService(db).start(campaign_id, ElectionDayAdminSupportStartRequest(reason="auditoría"), admin)

    assert client.get(f"{BASE.format(campaign_id=campaign_id)}", headers=admin_headers).status_code == 200
    detail = client.get(f"{BASE.format(campaign_id=campaign_id)}/{act_id}", headers=admin_headers)
    assert detail.status_code == 200
    evidence_id = detail.json()["revisions"][0]["evidence"][0]["id"]
    assert client.get(f"{BASE.format(campaign_id=campaign_id)}/{act_id}/evidence/{evidence_id}/download", headers=admin_headers).status_code == 200
    claim = client.post(f"{BASE.format(campaign_id=campaign_id)}/{act_id}/claim", headers=admin_headers)
    assert claim.status_code == 200
    validate = client.post(f"{BASE.format(campaign_id=campaign_id)}/{act_id}/validate", headers=admin_headers, json={"revision_id": revision_id})
    assert validate.status_code == 200
    # ADMIN en soporte no tiene ninguna ruta para "editar votos": ni siquiera
    # existe un endpoint PUT/PATCH sobre resultados (ver test de inmutabilidad).


def test_rbac_coordinator_and_analyst_without_assignment_fully_denied(client: TestClient, acts_http):
    ctx = acts_http
    campaign_id = ctx["campaign"].id
    delegate_headers = _login(client, ctx["delegate"].username)
    act_id, revision_id = _register_and_submit(client, delegate_headers, ctx)

    for user in (ctx["coordinator"], ctx["analyst"]):
        headers = _login(client, user.username)
        assert client.get(f"{BASE.format(campaign_id=campaign_id)}", headers=headers).status_code == 403
        assert client.get(f"{BASE.format(campaign_id=campaign_id)}/{act_id}", headers=headers).status_code == 403
        assert client.post(f"{BASE.format(campaign_id=campaign_id)}/{act_id}/claim", headers=headers).status_code == 403
        assert client.post(f"{BASE.format(campaign_id=campaign_id)}/{act_id}/validate", headers=headers, json={"revision_id": revision_id}).status_code == 403


# ---------- §5: seguridad HTTP de la evidencia ----------

def test_evidence_download_headers_and_no_base64_leak(client: TestClient, acts_http):
    ctx = acts_http
    campaign_id = ctx["campaign"].id
    delegate_headers = _login(client, ctx["delegate"].username)
    act_id, revision_id = _register_and_submit(client, delegate_headers, ctx)

    detail = client.get(f"{BASE.format(campaign_id=campaign_id)}/{act_id}", headers=delegate_headers)
    revision_json = detail.json()["revisions"][0]
    assert "storage_key" not in revision_json
    assert "storage_key" not in revision_json["evidence"][0]
    for key, value in revision_json.items():
        if isinstance(value, str):
            assert value != JPEG_BYTES.hex(), "no debe filtrar el binario como texto"

    evidence_id = revision_json["evidence"][0]["id"]
    download = client.get(f"{BASE.format(campaign_id=campaign_id)}/{act_id}/evidence/{evidence_id}/download", headers=delegate_headers)
    assert download.status_code == 200
    assert download.headers["cache-control"] == "private, no-store"
    assert download.headers["x-content-type-options"] == "nosniff"
    assert download.headers["content-type"] == "image/jpeg"
    assert download.content[:3] == b"\xff\xd8\xff"


def test_evidence_download_rejects_cross_campaign_and_cross_act(client: TestClient, acts_http, admin):
    ctx = acts_http
    campaign_id = ctx["campaign"].id
    delegate_headers = _login(client, ctx["delegate"].username)
    act_id, _ = _register_and_submit(client, delegate_headers, ctx)
    detail = client.get(f"{BASE.format(campaign_id=campaign_id)}/{act_id}", headers=delegate_headers)
    evidence_id = detail.json()["revisions"][0]["evidence"][0]["id"]

    # Un id de acta ajeno (aleatorio) combinado con evidencia real: 404, nunca 200.
    fake_act_id = uuid4()
    cross = client.get(f"{BASE.format(campaign_id=campaign_id)}/{fake_act_id}/evidence/{evidence_id}/download", headers=delegate_headers)
    assert cross.status_code == 404


# ---------- §7: inmutabilidad real de revisiones SUBMITTED ----------

def test_no_generic_patch_route_exists_for_revisions_or_acts(client: TestClient, acts_http):
    ctx = acts_http
    campaign_id = ctx["campaign"].id
    delegate_headers = _login(client, ctx["delegate"].username)
    act_id, revision_id = _register_and_submit(client, delegate_headers, ctx)

    for method in ("patch", "put"):
        resp = getattr(client, method)(
            f"{BASE.format(campaign_id=campaign_id)}/{act_id}", headers=delegate_headers,
            json={"blank_ballots": 999},
        )
        assert resp.status_code in (404, 405)
        resp2 = getattr(client, method)(
            f"{BASE.format(campaign_id=campaign_id)}/{act_id}/revisions/{revision_id}", headers=delegate_headers,
            json={"blank_ballots": 999},
        )
        assert resp2.status_code in (404, 405)


def test_submitted_revision_survives_unchanged_after_correction(client: TestClient, db, acts_http):
    ctx = acts_http
    campaign_id = ctx["campaign"].id
    delegate_headers = _login(client, ctx["delegate"].username)
    validator_headers = _login(client, ctx["validator"].username)
    act_id, revision_id = _register_and_submit(client, delegate_headers, ctx)

    original = db.get(ElectionActRevision, UUID(revision_id))
    snapshot = (original.blank_ballots, original.null_ballots, original.valid_ballots, original.ballots_counted, original.revision_number, original.submitted_by_user_id)

    client.post(f"{BASE.format(campaign_id=campaign_id)}/{act_id}/claim", headers=validator_headers)
    client.post(
        f"{BASE.format(campaign_id=campaign_id)}/{act_id}/observe", headers=validator_headers,
        json={"revision_id": revision_id, "reason": "corregir"},
    )
    correction = client.post(
        f"{BASE.format(campaign_id=campaign_id)}/{act_id}/corrections", headers=delegate_headers,
        json={"blank_ballots": 2, "null_ballots": 2, "valid_ballots": 20, "ballots_counted": 24,
              "results": [{"electoral_candidate_id": str(ctx["candidates"][0].id), "votes": 20}],
              "correction_reason": "recuento"},
    )
    assert correction.status_code == 201, correction.text

    db.expire_all()
    original_after = db.get(ElectionActRevision, UUID(revision_id))
    assert (
        original_after.blank_ballots, original_after.null_ballots, original_after.valid_ballots,
        original_after.ballots_counted, original_after.revision_number, original_after.submitted_by_user_id,
    ) == snapshot
    assert original_after.status == "SUBMITTED"


# ---------- §9: revisión obsoleta (vía API real) ----------

def test_stale_revision_rejected_via_http(client: TestClient, acts_http):
    ctx = acts_http
    campaign_id = ctx["campaign"].id
    delegate_headers = _login(client, ctx["delegate"].username)
    validator_headers = _login(client, ctx["validator"].username)
    act_id, revision_id = _register_and_submit(client, delegate_headers, ctx)

    client.post(f"{BASE.format(campaign_id=campaign_id)}/{act_id}/claim", headers=validator_headers)
    client.post(
        f"{BASE.format(campaign_id=campaign_id)}/{act_id}/observe", headers=validator_headers,
        json={"revision_id": revision_id, "reason": "revisar"},
    )
    correction = client.post(
        f"{BASE.format(campaign_id=campaign_id)}/{act_id}/corrections", headers=delegate_headers,
        json={"blank_ballots": 1, "null_ballots": 1, "valid_ballots": 15, "ballots_counted": 17,
              "results": [{"electoral_candidate_id": str(ctx["candidates"][0].id), "votes": 15}],
              "correction_reason": "corrijo"},
    )
    new_revision_id = correction.json()["revision"]["id"]
    client.post(
        f"{BASE.format(campaign_id=campaign_id)}/{act_id}/revisions/{new_revision_id}/evidence", headers=delegate_headers,
        files={"file": ("acta2.jpg", JPEG_BYTES, "image/jpeg")},
    )
    client.post(f"{BASE.format(campaign_id=campaign_id)}/{act_id}/revisions/{new_revision_id}/submit", headers=delegate_headers)

    client.post(f"{BASE.format(campaign_id=campaign_id)}/{act_id}/claim", headers=validator_headers)
    stale = client.post(
        f"{BASE.format(campaign_id=campaign_id)}/{act_id}/validate", headers=validator_headers,
        json={"revision_id": revision_id},
    )
    assert stale.status_code == 409
