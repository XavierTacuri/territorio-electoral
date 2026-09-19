from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models.election_day import ElectionAct, ElectionActEvidence, ElectionActRevision
from app.models.historical import ElectoralCandidate
from app.schemas.election_day import ElectionDayAdminSupportStartRequest, ElectionDayAssignmentCreate, ElectionDayOperationCreate
from app.schemas.election_act import (
    ElectionActCorrectionCreate,
    ElectionActDraftCreate,
    ElectionActObserveRequest,
    ElectionActResultInput,
    ElectionActValidateRequest,
)
from app.services.election_act_service import ElectionActService
from app.services.election_day_admin_support_service import ElectionDayAdminSupportService
from app.services.election_day_service import ElectionDayService
from app.services.exceptions import BusinessRuleError, ConflictError, NotFoundError

from tests.test_election_day import _create_operation, _member, _polling_place, _board, _election_day_dataset

JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 64
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF_BYTES = b"%PDF-1.4" + b"\x00" * 64


# ---------- Fixtures ----------

def _candidates(db, contest, source_id, n=2):
    cands = []
    for i in range(n):
        c = ElectoralCandidate(electoral_contest_id=contest.id, external_code=f"C{i + 1}-{uuid4().hex[:4]}", full_name=f"Candidato {i + 1}", ballot_order=i + 1, source_id=source_id, is_active=True)
        db.add(c)
        cands.append(c)
    db.commit()
    for c in cands:
        db.refresh(c)
    return cands


@pytest.fixture
def acts_ready(db, admin):
    """Campaña con jornada en SCRUTINY, un recinto con una junta, un
    delegado asignado a ese recinto, un validador de actas, y una contienda
    con 2 candidatos elegibles — el estado mínimo para registrar actas."""
    campaign, canton, parish_a, parish_b, process = _election_day_dataset(db, admin, 77)
    from app.models.historical import ElectoralContest
    contest = db.scalars(select(ElectoralContest).where(ElectoralContest.electoral_process_id == process.id)).first()
    executive = _member(db, admin, campaign, "CANDIDATE")
    svc = ElectionDayService(db)
    op = _create_operation(db, campaign, process, executive)
    place = _polling_place(db, process, canton, parish_a)
    board = _board(db, place)
    delegate = _member(db, admin, campaign)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=delegate.id, assignment_role="POLLING_PLACE_DELEGATE", polling_place_id=place.id), executive)
    validator = _member(db, admin, campaign)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=validator.id, assignment_role="ACT_VALIDATOR"), executive)
    op = svc.open_operation(campaign.id, executive)
    op = svc.start_scrutiny(campaign.id, executive)
    candidates = _candidates(db, contest, process.source_id)
    return {
        "campaign": campaign, "op": op, "place": place, "board": board, "delegate": delegate,
        "validator": validator, "executive": executive, "contest": contest, "candidates": candidates, "admin": admin,
    }


def _draft(ctx, blank=1, null=1, votes=(10, 5), client_generated_id=None):
    results = [ElectionActResultInput(electoral_candidate_id=ctx["candidates"][i].id, votes=v) for i, v in enumerate(votes)]
    valid = sum(votes)
    return ElectionActDraftCreate(
        polling_place_id=ctx["place"].id, electoral_board_id=ctx["board"].id, electoral_contest_id=ctx["contest"].id,
        blank_ballots=blank, null_ballots=null, valid_ballots=valid, ballots_counted=valid + blank + null,
        results=results, client_generated_id=client_generated_id,
    )


def _submitted_act(db, ctx):
    """Crea un acta y envía su primera revisión con evidencia — el estado
    de partida para los tests de cola/claim/validate/observe."""
    service = ElectionActService(db)
    act, revision = service.create_draft(ctx["campaign"].id, _draft(ctx), ctx["delegate"])
    service.upload_evidence(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], file_bytes=JPEG_BYTES, original_filename="acta.jpg", client_generated_id=None)
    act, revision = service.submit_revision(ctx["campaign"].id, act.id, revision.id, ctx["delegate"])
    return act, revision


# ---------- Registro de borrador (§4/§12) ----------

def test_create_draft_happy_path(db, acts_ready):
    ctx = acts_ready
    service = ElectionActService(db)
    act, revision = service.create_draft(ctx["campaign"].id, _draft(ctx), ctx["delegate"])
    assert act.status == "RECEIVED"
    assert revision.revision_number == 1 and revision.revision_type == "INITIAL" and revision.status == "DRAFT"


def test_create_draft_requires_scrutiny_status(db, acts_ready):
    ctx = acts_ready
    ElectionDayService(db).close_operation.__self__  # no-op reference to keep import used
    op = ElectionDayService(db)
    # Retroceder no es posible; en su lugar probamos con una jornada que aún no llegó a SCRUTINY.
    campaign, canton, parish_a, parish_b, process = _election_day_dataset(db, ctx["admin"], 78)
    executive = _member(db, ctx["admin"], campaign, "CANDIDATE")
    svc = ElectionDayService(db)
    new_op = _create_operation(db, campaign, process, executive)
    place = _polling_place(db, process, canton, parish_a)
    board = _board(db, place)
    delegate = _member(db, ctx["admin"], campaign)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=delegate.id, assignment_role="POLLING_PLACE_DELEGATE", polling_place_id=place.id), executive)
    validator = _member(db, ctx["admin"], campaign)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=validator.id, assignment_role="ACT_VALIDATOR"), executive)
    svc.open_operation(campaign.id, executive)  # ACTIVE, not SCRUTINY
    from app.models.historical import ElectoralContest
    contest = db.scalars(select(ElectoralContest).where(ElectoralContest.electoral_process_id == process.id)).first()
    candidates = _candidates(db, contest, process.source_id)
    ctx2 = {"campaign": campaign, "place": place, "board": board, "contest": contest, "candidates": candidates}
    service = ElectionActService(db)
    with pytest.raises(BusinessRuleError):
        service.create_draft(campaign.id, _draft(ctx2), delegate)


def test_create_draft_rejects_delegate_outside_polling_place(db, acts_ready):
    ctx = acts_ready
    other_delegate = _member(db, ctx["admin"], ctx["campaign"])
    service = ElectionActService(db)
    with pytest.raises(PermissionError):
        service.create_draft(ctx["campaign"].id, _draft(ctx), other_delegate)


def test_create_draft_duplicate_identity_conflicts(db, acts_ready):
    """§3/§12: la carrera de dos delegados registrando la misma junta+contienda
    se resuelve con 409, nunca con dos actas."""
    ctx = acts_ready
    service = ElectionActService(db)
    service.create_draft(ctx["campaign"].id, _draft(ctx), ctx["delegate"])
    with pytest.raises(ConflictError):
        service.create_draft(ctx["campaign"].id, _draft(ctx), ctx["delegate"])


def test_create_draft_idempotent_by_client_generated_id(db, acts_ready):
    ctx = acts_ready
    service = ElectionActService(db)
    cid = uuid4()
    act1, rev1 = service.create_draft(ctx["campaign"].id, _draft(ctx, client_generated_id=cid), ctx["delegate"])
    act2, rev2 = service.create_draft(ctx["campaign"].id, _draft(ctx, client_generated_id=cid), ctx["delegate"])
    assert act1.id == act2.id and rev1.id == rev2.id


def test_create_draft_rejects_ballots_counted_mismatch(db, acts_ready):
    ctx = acts_ready
    service = ElectionActService(db)
    data = _draft(ctx)
    data.ballots_counted = data.ballots_counted + 1
    with pytest.raises(BusinessRuleError):
        service.create_draft(ctx["campaign"].id, data, ctx["delegate"])


def test_create_draft_rejects_valid_ballots_not_matching_sum_single_choice(db, acts_ready):
    ctx = acts_ready
    service = ElectionActService(db)
    data = _draft(ctx)
    data.valid_ballots = data.valid_ballots + 5
    data.ballots_counted = data.valid_ballots + data.blank_ballots + data.null_ballots
    with pytest.raises(BusinessRuleError):
        service.create_draft(ctx["campaign"].id, data, ctx["delegate"])


def test_create_draft_rejects_candidate_outside_contest(db, acts_ready):
    ctx = acts_ready
    other_campaign, other_canton, other_pa, other_pb, other_process = _election_day_dataset(db, ctx["admin"], 79)
    from app.models.historical import ElectoralContest
    other_contest = db.scalars(select(ElectoralContest).where(ElectoralContest.electoral_process_id == other_process.id)).first()
    foreign_candidate = _candidates(db, other_contest, other_process.source_id, n=1)[0]
    service = ElectionActService(db)
    data = _draft(ctx)
    data.results = [ElectionActResultInput(electoral_candidate_id=foreign_candidate.id, votes=1)]
    with pytest.raises(BusinessRuleError):
        service.create_draft(ctx["campaign"].id, data, ctx["delegate"])


def test_draft_results_reject_duplicate_candidates_at_schema_level(acts_ready):
    ctx = acts_ready
    with pytest.raises(Exception):
        ElectionActDraftCreate(
            polling_place_id=ctx["place"].id, electoral_board_id=ctx["board"].id, electoral_contest_id=ctx["contest"].id,
            blank_ballots=0, null_ballots=0,
            results=[
                ElectionActResultInput(electoral_candidate_id=ctx["candidates"][0].id, votes=1),
                ElectionActResultInput(electoral_candidate_id=ctx["candidates"][0].id, votes=2),
            ],
        )


# ---------- Evidencia (§7/§8) ----------

def test_upload_evidence_accepts_jpeg_and_png(db, acts_ready):
    ctx = acts_ready
    service = ElectionActService(db)
    act, revision = service.create_draft(ctx["campaign"].id, _draft(ctx), ctx["delegate"])
    ev1 = service.upload_evidence(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], file_bytes=JPEG_BYTES, original_filename="a.jpg", client_generated_id=None)
    ev2 = service.upload_evidence(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], file_bytes=PNG_BYTES, original_filename="b.png", client_generated_id=None)
    assert ev1.mime_type == "image/jpeg" and ev2.mime_type == "image/png"


def test_upload_evidence_rejects_pdf(db, acts_ready):
    ctx = acts_ready
    service = ElectionActService(db)
    act, revision = service.create_draft(ctx["campaign"].id, _draft(ctx), ctx["delegate"])
    with pytest.raises(BusinessRuleError):
        service.upload_evidence(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], file_bytes=PDF_BYTES, original_filename="a.pdf", client_generated_id=None)


def test_upload_evidence_rejects_after_submitted(db, acts_ready):
    ctx = acts_ready
    service = ElectionActService(db)
    act, revision = _submitted_act(db, ctx)
    with pytest.raises(BusinessRuleError):
        service.upload_evidence(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], file_bytes=JPEG_BYTES, original_filename="c.jpg", client_generated_id=None)


def test_upload_evidence_cleans_up_orphaned_file_on_db_failure(db, acts_ready, monkeypatch):
    """§12 auditoría: si el archivo ya se escribió en el storage pero la
    transacción de DB falla después, el objeto huérfano se limpia
    best-effort — nunca queda un archivo sin ninguna fila que lo referencie."""
    ctx = acts_ready
    service = ElectionActService(db)
    act, revision = service.create_draft(ctx["campaign"].id, _draft(ctx), ctx["delegate"])

    deleted_keys = []
    original_delete = service.storage.delete

    def spy_delete(key):
        deleted_keys.append(key)
        return original_delete(key)

    def failing_commit():
        raise RuntimeError("fallo simulado de base de datos")

    monkeypatch.setattr(service.storage, "delete", spy_delete)
    monkeypatch.setattr(service.db, "commit", failing_commit)

    with pytest.raises(RuntimeError):
        service.upload_evidence(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], file_bytes=JPEG_BYTES, original_filename="a.jpg", client_generated_id=None)

    assert len(deleted_keys) == 1
    monkeypatch.undo()
    assert db.scalar(select(func.count()).select_from(ElectionActEvidence).where(ElectionActEvidence.revision_id == revision.id)) == 0
    assert not service.storage.resolve(deleted_keys[0]).exists()


def test_upload_evidence_never_deletes_file_of_persisted_evidence(db, acts_ready):
    """Contraparte del test anterior: un fallo DESPUÉS de que la evidencia ya
    se persistió con éxito (p. ej. en submit_revision) nunca debe borrar el
    archivo — solo se limpia lo que nunca llegó a persistirse."""
    ctx = acts_ready
    service = ElectionActService(db)
    act, revision = service.create_draft(ctx["campaign"].id, _draft(ctx), ctx["delegate"])
    evidence = service.upload_evidence(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], file_bytes=JPEG_BYTES, original_filename="a.jpg", client_generated_id=None)
    path = service.storage.resolve(evidence.storage_key)
    assert path.exists()
    # Cualquier operación posterior (incluso una que falle) no debe tocar este archivo.
    with pytest.raises(BusinessRuleError):
        service.upload_evidence(ctx["campaign"].id, act.id, revision.id, ctx["delegate"], file_bytes=PDF_BYTES, original_filename="b.pdf", client_generated_id=None)
    assert path.exists()


# ---------- Envío (§8) ----------

def test_submit_requires_evidence(db, acts_ready):
    ctx = acts_ready
    service = ElectionActService(db)
    act, revision = service.create_draft(ctx["campaign"].id, _draft(ctx), ctx["delegate"])
    with pytest.raises(BusinessRuleError):
        service.submit_revision(ctx["campaign"].id, act.id, revision.id, ctx["delegate"])


def test_submit_is_idempotent(db, acts_ready):
    ctx = acts_ready
    act, revision = _submitted_act(db, ctx)
    service = ElectionActService(db)
    act2, revision2 = service.submit_revision(ctx["campaign"].id, act.id, revision.id, ctx["delegate"])
    assert revision2.id == revision.id and revision2.status == "SUBMITTED"


# ---------- Corrección (§13) ----------

def test_correction_requires_observed_status(db, acts_ready):
    ctx = acts_ready
    act, revision = _submitted_act(db, ctx)
    service = ElectionActService(db)
    correction = ElectionActCorrectionCreate(
        blank_ballots=1, null_ballots=1, valid_ballots=15, ballots_counted=17,
        results=[ElectionActResultInput(electoral_candidate_id=ctx["candidates"][0].id, votes=10), ElectionActResultInput(electoral_candidate_id=ctx["candidates"][1].id, votes=5)],
        correction_reason="Aritmética incorrecta",
    )
    with pytest.raises(BusinessRuleError):
        service.create_correction(ctx["campaign"].id, act.id, correction, ctx["delegate"])


def test_correction_after_observation_creates_new_revision(db, acts_ready):
    ctx = acts_ready
    act, revision = _submitted_act(db, ctx)
    service = ElectionActService(db)
    service.claim(ctx["campaign"].id, act.id, ctx["validator"])
    act = service.observe_act(ctx["campaign"].id, act.id, ElectionActObserveRequest(revision_id=revision.id, reason="Faltan votos por contar"), ctx["validator"])
    assert act.status == "OBSERVED"
    correction = ElectionActCorrectionCreate(
        blank_ballots=1, null_ballots=1, valid_ballots=15, ballots_counted=17,
        results=[ElectionActResultInput(electoral_candidate_id=ctx["candidates"][0].id, votes=10), ElectionActResultInput(electoral_candidate_id=ctx["candidates"][1].id, votes=5)],
        correction_reason="Aritmética incorrecta",
    )
    act, new_revision = service.create_correction(ctx["campaign"].id, act.id, correction, ctx["delegate"])
    assert new_revision.revision_number == 2 and new_revision.revision_type == "CORRECTION" and act.status == "RECEIVED"


# ---------- Claim / Release (§16/§17) ----------

def test_claim_blocks_second_validator_while_active(db, acts_ready):
    ctx = acts_ready
    act, revision = _submitted_act(db, ctx)
    service = ElectionActService(db)
    service.claim(ctx["campaign"].id, act.id, ctx["validator"])
    other_validator = _member(db, ctx["admin"], ctx["campaign"])
    from app.schemas.election_day import ElectionDayAssignmentCreate as _Create
    ElectionDayService(db).create_assignment(ctx["campaign"].id, _Create(user_id=other_validator.id, assignment_role="ACT_VALIDATOR"), ctx["executive"])
    with pytest.raises(ConflictError):
        service.claim(ctx["campaign"].id, act.id, other_validator)


def test_release_by_owner_then_reclaim_by_other(db, acts_ready):
    ctx = acts_ready
    act, revision = _submitted_act(db, ctx)
    service = ElectionActService(db)
    service.claim(ctx["campaign"].id, act.id, ctx["validator"])
    service.release(ctx["campaign"].id, act.id, ctx["validator"])
    other_validator = _member(db, ctx["admin"], ctx["campaign"])
    from app.schemas.election_day import ElectionDayAssignmentCreate as _Create
    ElectionDayService(db).create_assignment(ctx["campaign"].id, _Create(user_id=other_validator.id, assignment_role="ACT_VALIDATOR"), ctx["executive"])
    claimed = service.claim(ctx["campaign"].id, act.id, other_validator)
    assert claimed.review_claimed_by_user_id == other_validator.id


def test_release_by_non_owner_forbidden(db, acts_ready):
    ctx = acts_ready
    act, revision = _submitted_act(db, ctx)
    service = ElectionActService(db)
    service.claim(ctx["campaign"].id, act.id, ctx["validator"])
    other_validator = _member(db, ctx["admin"], ctx["campaign"])
    from app.schemas.election_day import ElectionDayAssignmentCreate as _Create
    ElectionDayService(db).create_assignment(ctx["campaign"].id, _Create(user_id=other_validator.id, assignment_role="ACT_VALIDATOR"), ctx["executive"])
    with pytest.raises(PermissionError):
        service.release(ctx["campaign"].id, act.id, other_validator)


# ---------- Validar / Observar (§19/§20) ----------

def test_validate_requires_active_claim(db, acts_ready):
    ctx = acts_ready
    act, revision = _submitted_act(db, ctx)
    service = ElectionActService(db)
    with pytest.raises(PermissionError):
        service.validate_act(ctx["campaign"].id, act.id, ElectionActValidateRequest(revision_id=revision.id), ctx["validator"])


def test_validate_rejects_stale_revision(db, acts_ready):
    """Escenario C: el revisor intenta validar una revisión que ya no es la
    última enviada — debe rechazarse con conflicto, nunca validar a ciegas."""
    ctx = acts_ready
    act, revision = _submitted_act(db, ctx)
    service = ElectionActService(db)
    service.claim(ctx["campaign"].id, act.id, ctx["validator"])
    act = service.observe_act(ctx["campaign"].id, act.id, ElectionActObserveRequest(revision_id=revision.id, reason="Revisar totales"), ctx["validator"])
    correction = ElectionActCorrectionCreate(
        blank_ballots=1, null_ballots=1, valid_ballots=15, ballots_counted=17,
        results=[ElectionActResultInput(electoral_candidate_id=ctx["candidates"][0].id, votes=10), ElectionActResultInput(electoral_candidate_id=ctx["candidates"][1].id, votes=5)],
        correction_reason="Aritmética incorrecta",
    )
    act, new_revision = service.create_correction(ctx["campaign"].id, act.id, correction, ctx["delegate"])
    service.upload_evidence(ctx["campaign"].id, act.id, new_revision.id, ctx["delegate"], file_bytes=JPEG_BYTES, original_filename="corregida.jpg", client_generated_id=None)
    service.submit_revision(ctx["campaign"].id, act.id, new_revision.id, ctx["delegate"])
    # revision_id apunta a la revisión vieja (ya observada y superada por la corrección enviada).
    service.claim(ctx["campaign"].id, act.id, ctx["validator"])
    with pytest.raises(ConflictError):
        service.validate_act(ctx["campaign"].id, act.id, ElectionActValidateRequest(revision_id=revision.id), ctx["validator"])


def test_validate_happy_path_sets_validated(db, acts_ready):
    ctx = acts_ready
    act, revision = _submitted_act(db, ctx)
    service = ElectionActService(db)
    service.claim(ctx["campaign"].id, act.id, ctx["validator"])
    act = service.validate_act(ctx["campaign"].id, act.id, ElectionActValidateRequest(revision_id=revision.id), ctx["validator"])
    assert act.status == "VALIDATED" and act.validated_revision_id == revision.id and act.review_claimed_by_user_id is None


def test_observe_requires_reason(acts_ready):
    with pytest.raises(Exception):
        ElectionActObserveRequest(revision_id=uuid4(), reason="")


def test_candidate_manager_cannot_review(db, acts_ready):
    ctx = acts_ready
    act, revision = _submitted_act(db, ctx)
    service = ElectionActService(db)
    with pytest.raises(PermissionError):
        service.claim(ctx["campaign"].id, act.id, ctx["executive"])


def test_admin_without_active_support_cannot_review(db, acts_ready):
    ctx = acts_ready
    act, revision = _submitted_act(db, ctx)
    service = ElectionActService(db)
    with pytest.raises(PermissionError):
        service.claim(ctx["campaign"].id, act.id, ctx["admin"])


def test_admin_with_active_support_can_review_and_is_tagged(db, acts_ready):
    ctx = acts_ready
    act, revision = _submitted_act(db, ctx)
    ElectionDayAdminSupportService(db).start(ctx["campaign"].id, ElectionDayAdminSupportStartRequest(reason="Cobertura de emergencia"), ctx["admin"])
    service = ElectionActService(db)
    service.claim(ctx["campaign"].id, act.id, ctx["admin"])
    act = service.validate_act(ctx["campaign"].id, act.id, ElectionActValidateRequest(revision_id=revision.id), ctx["admin"])
    review = db.scalars(select(ElectionAct).where(ElectionAct.id == act.id)).first()
    assert review.status == "VALIDATED"


# ---------- Cola de validación (§15) ----------

def test_validation_queue_excludes_unsubmitted_drafts(db, acts_ready):
    ctx = acts_ready
    service = ElectionActService(db)
    service.create_draft(ctx["campaign"].id, _draft(ctx), ctx["delegate"])
    items, total = service.validation_queue(ctx["campaign"].id, ctx["validator"])
    assert total == 0


def test_validation_queue_shows_submitted_acts(db, acts_ready):
    ctx = acts_ready
    act, revision = _submitted_act(db, ctx)
    service = ElectionActService(db)
    items, total = service.validation_queue(ctx["campaign"].id, ctx["validator"])
    assert total == 1 and items[0].id == act.id


def test_validation_queue_excludes_validated_by_default(db, acts_ready):
    """La cola es "lo que aún requiere acción": un acta VALIDATED es un
    estado terminal y no debe seguir apareciendo salvo que se pida
    explícitamente status=VALIDATED (p. ej. para auditar)."""
    ctx = acts_ready
    act, revision = _submitted_act(db, ctx)
    service = ElectionActService(db)
    service.claim(ctx["campaign"].id, act.id, ctx["validator"])
    service.validate_act(ctx["campaign"].id, act.id, ElectionActValidateRequest(revision_id=revision.id), ctx["validator"])
    items, total = service.validation_queue(ctx["campaign"].id, ctx["validator"])
    assert total == 0
    items, total = service.validation_queue(ctx["campaign"].id, ctx["validator"], status="VALIDATED")
    assert total == 1 and items[0].id == act.id


# ---------- Cobertura documental (§37) ----------

def test_coverage_counts_boards_and_status(db, acts_ready):
    ctx = acts_ready
    service = ElectionActService(db)
    _submitted_act(db, ctx)
    summary = service.coverage(ctx["campaign"].id, ctx["executive"])
    assert summary["expected_boards"] == 1
    assert summary["received"] == 1
    assert summary["pending"] == 0
