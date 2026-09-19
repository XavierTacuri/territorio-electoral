import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.models.campaign import Campaign
from app.models.election_day import (
    ElectionAct,
    ElectionActEvidence,
    ElectionActResult,
    ElectionActReview,
    ElectionActRevision,
    ElectionDayOperation,
    ElectoralBoard,
    PollingPlace,
)
from app.models.historical import ElectoralCandidate, ElectoralContest
from app.services.election_day_access_service import ElectionDayAccessService
from app.services.evidence_security_service import EVIDENCE_EXTENSION_BY_MIME, safe_evidence_filename, sniff_evidence_mime
from app.services.evidence_storage_service import LocalEvidenceStorage
from app.services.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.services.security_audit_service import SecurityAuditService

ACT_STATUSES = {"RECEIVED", "IN_REVIEW", "OBSERVED", "VALIDATED"}
SINGLE_TOTAL_VOTE_METHODS = {"SINGLE_CHOICE", "LIST_VOTE"}
EVIDENCE_ALLOWED_MIME = {"image/jpeg", "image/png"}


def _aware(dt):
    """Normaliza a timezone-aware (asumiendo UTC, que es lo único que este
    servicio escribe) antes de comparar contra datetime.now(timezone.utc).
    Necesario porque una columna DateTime(timezone=True) puede volver naive
    tras una recarga (p. ej. SQLite siempre; algunos drivers/rutas en
    Postgres también) — comparar naive contra aware lanza TypeError y
    tumbaba /claim, /observe y /validate con un 500 real (auditoría §10)."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class ElectionActService:
    """Actas electorales de escrutinio (Fase 2). Identidad canónica (§3): a
    lo sumo UNA ElectionAct por (operation, board, contest) — impuesta por un
    UNIQUE real en DB, nunca solo por lógica de aplicación. Una revisión
    SUBMITTED es inmutable (§5): toda corrección crea una revisión nueva.
    Este servicio nunca agrega votos entre recintos ni calcula ganador — eso
    es Fase 3."""

    def __init__(self, db, storage=None):
        self.db = db
        self.access = ElectionDayAccessService(db)
        self.audit = SecurityAuditService(db)
        self.storage = storage or LocalEvidenceStorage(settings.evidence_output_dir, settings.evidence_max_file_mb)

    # ---------- Helpers de identidad/alcance ----------
    def _campaign(self, campaign_id):
        campaign = self.db.get(Campaign, campaign_id)
        if not campaign:
            raise NotFoundError("Campaña no encontrada")
        return campaign

    def _require_operation(self, campaign_id):
        op = self.db.scalar(
            select(ElectionDayOperation)
            .where(ElectionDayOperation.campaign_id == campaign_id)
            .order_by(ElectionDayOperation.created_at.desc())
        )
        if not op:
            raise NotFoundError("No existe una jornada configurada para esta campaña")
        return op

    def _polling_place(self, campaign, op, polling_place_id):
        place = self.db.get(PollingPlace, polling_place_id)
        if not place or place.electoral_process_id != op.electoral_process_id or place.canton_id != campaign.canton_id:
            raise NotFoundError("Recinto no encontrado")
        return place

    def _board(self, place, board_id):
        board = self.db.get(ElectoralBoard, board_id)
        if not board or board.polling_place_id != place.id or not board.is_active:
            raise NotFoundError("Junta no encontrada")
        return board

    def _eligible_contest_ids(self, campaign, op):
        return set(
            self.db.scalars(
                select(ElectoralContest.id).where(
                    ElectoralContest.electoral_process_id == op.electoral_process_id,
                    ElectoralContest.canton_id == campaign.canton_id,
                    ElectoralContest.office_type == campaign.office_type,
                    ElectoralContest.is_active.is_(True),
                )
            )
        )

    def _contest(self, campaign, op, contest_id):
        contest = self.db.get(ElectoralContest, contest_id)
        if not contest or contest.id not in self._eligible_contest_ids(campaign, op):
            raise NotFoundError("Contienda no encontrada")
        return contest

    def _act_for_operation(self, op, act_id):
        act = self.db.get(ElectionAct, act_id)
        if not act or act.operation_id != op.id:
            raise NotFoundError("Acta no encontrada")
        return act

    def _act_for_operation_locked(self, op, act_id):
        act = self.db.scalar(select(ElectionAct).where(ElectionAct.id == act_id, ElectionAct.operation_id == op.id).with_for_update())
        if not act:
            raise NotFoundError("Acta no encontrada")
        return act

    def _revision(self, act, revision_id):
        revision = self.db.get(ElectionActRevision, revision_id)
        if not revision or revision.act_id != act.id:
            raise NotFoundError("Revisión no encontrada")
        return revision

    def _latest_submitted_revision(self, act):
        return self.db.scalar(
            select(ElectionActRevision)
            .where(ElectionActRevision.act_id == act.id, ElectionActRevision.status == "SUBMITTED")
            .order_by(ElectionActRevision.revision_number.desc())
        )

    # ---------- Contiendas/candidatos elegibles (formulario del Delegado) ----------
    def list_contests(self, campaign_id, user):
        campaign = self.access.require_delegate_assignment(campaign_id, user)
        op = self._require_operation(campaign_id)
        contests = list(
            self.db.scalars(
                select(ElectoralContest)
                .where(ElectoralContest.id.in_(self._eligible_contest_ids(campaign, op)))
                .order_by(ElectoralContest.name)
            )
        )
        result = []
        for contest in contests:
            candidates = list(
                self.db.scalars(
                    select(ElectoralCandidate)
                    .where(ElectoralCandidate.electoral_contest_id == contest.id, ElectoralCandidate.is_active.is_(True))
                    .order_by(ElectoralCandidate.ballot_order, ElectoralCandidate.full_name)
                )
            )
            result.append({
                "id": contest.id, "name": contest.name, "office_type": contest.office_type,
                "vote_method": contest.vote_method, "candidates": candidates,
            })
        return result

    # ---------- Validación aritmética explícita por vote_method (§10) ----------
    def _validate_arithmetic(self, contest, board, data):
        total_votes = sum(r.votes for r in data.results)
        if data.ballots_counted is not None:
            expected = (data.valid_ballots or 0) + data.blank_ballots + data.null_ballots
            if data.ballots_counted != expected:
                raise BusinessRuleError(
                    "Los totales no cuadran: votos válidos + blancos + nulos debe ser igual al total de actas escrutadas."
                )
            if board.registered_voters is not None and data.ballots_counted > board.registered_voters:
                raise BusinessRuleError(
                    "El total de actas escrutadas no puede superar los electores registrados en la junta."
                )
        if contest.vote_method in SINGLE_TOTAL_VOTE_METHODS:
            if data.valid_ballots is not None and total_votes != data.valid_ballots:
                raise BusinessRuleError("La suma de votos por candidato debe ser igual a los votos válidos.")
        else:
            # MULTI_VOTE/OTHER: una boleta puede aportar más de un voto (p. ej.
            # concejales con varios escaños) — la suma total puede superar los
            # votos válidos, pero ningún candidato individual puede.
            if data.valid_ballots is not None:
                for r in data.results:
                    if r.votes > data.valid_ballots:
                        raise BusinessRuleError("Un candidato no puede tener más votos que el total de votos válidos.")

    def _validate_results(self, contest, results):
        if not results:
            return
        candidate_ids = {r.electoral_candidate_id for r in results}
        valid = set(
            self.db.scalars(
                select(ElectoralCandidate.id).where(
                    ElectoralCandidate.electoral_contest_id == contest.id, ElectoralCandidate.is_active.is_(True)
                )
            )
        )
        if candidate_ids - valid:
            raise BusinessRuleError("Uno o más candidatos no pertenecen a esta contienda o no están activos.")

    # ---------- Borrador inicial (§4/§12) ----------
    def create_draft(self, campaign_id, data, user):
        campaign = self.access.require_delegate_assignment(campaign_id, user, polling_place_id=data.polling_place_id)
        op = self._require_operation(campaign_id)
        if op.status != "SCRUTINY":
            raise BusinessRuleError("Las actas solo se registran durante el escrutinio de la jornada.")
        place = self._polling_place(campaign, op, data.polling_place_id)
        board = self._board(place, data.electoral_board_id)
        contest = self._contest(campaign, op, data.electoral_contest_id)

        if data.client_generated_id:
            existing = self.db.scalar(
                select(ElectionActRevision)
                .join(ElectionAct, ElectionAct.id == ElectionActRevision.act_id)
                .where(
                    ElectionAct.operation_id == op.id,
                    ElectionActRevision.submitted_by_user_id == user.id,
                    ElectionActRevision.client_generated_id == data.client_generated_id,
                )
            )
            if existing:
                return self.db.get(ElectionAct, existing.act_id), existing

        self._validate_arithmetic(contest, board, data)
        self._validate_results(contest, data.results)

        act = ElectionAct(
            organization_id=campaign.organization_id, campaign_id=campaign_id, operation_id=op.id,
            polling_place_id=place.id, electoral_board_id=board.id, electoral_contest_id=contest.id,
            status="RECEIVED", latest_revision_number=1,
        )
        self.db.add(act)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError("Ya existe un acta recibida para esta junta y contienda.") from exc

        revision = ElectionActRevision(
            act_id=act.id, revision_number=1, revision_type="INITIAL", status="DRAFT",
            submitted_by_user_id=user.id, client_generated_id=data.client_generated_id,
            offline_created_at=data.offline_created_at, blank_ballots=data.blank_ballots,
            null_ballots=data.null_ballots, valid_ballots=data.valid_ballots, ballots_counted=data.ballots_counted,
        )
        self.db.add(revision)
        self.db.flush()
        for r in data.results:
            self.db.add(ElectionActResult(revision_id=revision.id, electoral_candidate_id=r.electoral_candidate_id, votes=r.votes))
        self.audit.record(
            "ELECTION_ACT_DRAFT_CREATED", "SUCCESS", "Borrador de acta creado", user_id=user.id, campaign_id=campaign_id,
            resource_type="ELECTION_ACT", resource_id=act.id,
            metadata={
                "operation_id": str(op.id), "polling_place_id": str(place.id), "board_id": str(board.id),
                "contest_id": str(contest.id), "act_id": str(act.id), "revision_id": str(revision.id), "revision_number": 1,
            },
        )
        self.db.commit()
        return act, revision

    # ---------- Evidencia obligatoria (§7/§8) ----------
    def upload_evidence(self, campaign_id, act_id, revision_id, user, *, file_bytes, original_filename, client_generated_id):
        campaign = self.access.require_delegate_assignment(campaign_id, user)
        op = self._require_operation(campaign_id)
        if op.status == "CLOSED":
            raise BusinessRuleError("La jornada está cerrada; las actas quedan en solo lectura.")
        act = self._act_for_operation(op, act_id)
        self.access.require_delegate_assignment(campaign_id, user, polling_place_id=act.polling_place_id)
        revision = self._revision(act, revision_id)
        if revision.status == "SUBMITTED":
            raise BusinessRuleError("Esta revisión ya fue enviada; no se puede modificar su evidencia.")
        if client_generated_id:
            existing = self.db.scalar(
                select(ElectionActEvidence).where(
                    ElectionActEvidence.revision_id == revision.id,
                    ElectionActEvidence.uploaded_by_user_id == user.id,
                    ElectionActEvidence.client_generated_id == client_generated_id,
                )
            )
            if existing:
                return existing
        mime = sniff_evidence_mime(file_bytes[:16])
        if mime not in EVIDENCE_ALLOWED_MIME:
            raise BusinessRuleError("Formato de imagen no permitido. Usa JPEG o PNG.")
        extension = EVIDENCE_EXTENSION_BY_MIME[mime]
        handle, tmp_name = tempfile.mkstemp(suffix=f".{extension}")
        tmp = Path(tmp_name)
        try:
            with open(handle, "wb") as fh:
                fh.write(file_bytes)
            try:
                key, size, digest = self.storage.store(tmp, extension)
            except ValueError as e:
                raise BusinessRuleError(str(e)) from e
            except OSError as e:
                raise BusinessRuleError("No fue posible guardar la fotografía. Intenta nuevamente.") from e
        finally:
            tmp.unlink(missing_ok=True)
        evidence = ElectionActEvidence(
            revision_id=revision.id, storage_key=key, mime_type=mime, size_bytes=size, sha256=digest,
            original_filename=safe_evidence_filename(original_filename or "acta", extension),
            uploaded_by_user_id=user.id, client_generated_id=client_generated_id, is_active=True,
        )
        self.db.add(evidence)
        try:
            self.db.flush()
            self.audit.record(
                "ELECTION_ACT_EVIDENCE_UPLOADED", "SUCCESS", "Evidencia de acta cargada", user_id=user.id, campaign_id=campaign_id,
                resource_type="ELECTION_ACT_EVIDENCE", resource_id=evidence.id,
                metadata={
                    "operation_id": str(op.id), "act_id": str(act.id), "revision_id": str(revision.id),
                    "mime_type": mime, "size_bytes": size,
                },
            )
            self.db.commit()
        except Exception:
            # §12 auditoría: el archivo ya se escribió en el storage antes de
            # este punto — si la escritura en DB falla, el objeto queda
            # huérfano (nunca referenciado por ninguna evidencia persistida)
            # y se limpia best-effort. Nunca se llama a storage.delete si la
            # fila SÍ llegó a persistirse (ese caso ya retornó arriba).
            self.db.rollback()
            try:
                self.storage.delete(key)
            except Exception:
                pass
            raise
        return evidence

    def evidence_file(self, campaign_id, act_id, evidence_id, user):
        op = self._require_operation(campaign_id)
        act = self._act_for_operation(op, act_id)
        self.access.require_act_viewer(campaign_id, user, act.polling_place_id)
        evidence = self.db.get(ElectionActEvidence, evidence_id)
        if not evidence or not evidence.is_active:
            raise NotFoundError("Evidencia no encontrada")
        revision = self.db.get(ElectionActRevision, evidence.revision_id)
        if not revision or revision.act_id != act.id:
            raise NotFoundError("Evidencia no encontrada")
        return self.storage.resolve(evidence.storage_key), evidence

    # ---------- Envío (DRAFT -> SUBMITTED, §8/§32-D) ----------
    def submit_revision(self, campaign_id, act_id, revision_id, user):
        campaign = self.access.require_delegate_assignment(campaign_id, user)
        op = self._require_operation(campaign_id)
        if op.status != "SCRUTINY":
            raise BusinessRuleError("Las actas solo se envían durante el escrutinio de la jornada.")
        act = self._act_for_operation(op, act_id)
        self.access.require_delegate_assignment(campaign_id, user, polling_place_id=act.polling_place_id)
        revision = self._revision(act, revision_id)
        if revision.status == "SUBMITTED":
            return act, revision  # idempotente: doble envío no duplica (§32-D)
        has_evidence = self.db.scalar(
            select(func.count()).select_from(ElectionActEvidence).where(
                ElectionActEvidence.revision_id == revision.id, ElectionActEvidence.is_active.is_(True)
            )
        ) or 0
        if not has_evidence:
            raise BusinessRuleError("Debes adjuntar al menos una fotografía del acta antes de enviarla.")
        revision.status = "SUBMITTED"
        revision.submitted_at = datetime.now(timezone.utc)
        act.status = "RECEIVED"
        self.audit.record(
            "ELECTION_ACT_SUBMITTED", "SUCCESS", "Acta enviada para revisión", user_id=user.id, campaign_id=campaign_id,
            resource_type="ELECTION_ACT", resource_id=act.id,
            metadata={"operation_id": str(op.id), "act_id": str(act.id), "revision_id": str(revision.id), "revision_number": revision.revision_number},
        )
        self.db.commit()
        return act, revision

    # ---------- Corrección (§13) ----------
    def create_correction(self, campaign_id, act_id, data, user):
        campaign = self.access.require_delegate_assignment(campaign_id, user)
        op = self._require_operation(campaign_id)
        if op.status != "SCRUTINY":
            raise BusinessRuleError("Las correcciones solo se registran durante el escrutinio de la jornada.")
        act = self._act_for_operation_locked(op, act_id)
        self.access.require_delegate_assignment(campaign_id, user, polling_place_id=act.polling_place_id)
        if act.status != "OBSERVED":
            raise BusinessRuleError("Solo se puede corregir un acta observada.")

        if data.client_generated_id:
            existing = self.db.scalar(
                select(ElectionActRevision).where(
                    ElectionActRevision.act_id == act.id,
                    ElectionActRevision.submitted_by_user_id == user.id,
                    ElectionActRevision.client_generated_id == data.client_generated_id,
                )
            )
            if existing:
                return act, existing

        contest = self.db.get(ElectoralContest, act.electoral_contest_id)
        board = self.db.get(ElectoralBoard, act.electoral_board_id)
        self._validate_arithmetic(contest, board, data)
        self._validate_results(contest, data.results)

        next_number = act.latest_revision_number + 1
        revision = ElectionActRevision(
            act_id=act.id, revision_number=next_number, revision_type="CORRECTION", status="DRAFT",
            submitted_by_user_id=user.id, client_generated_id=data.client_generated_id,
            offline_created_at=data.offline_created_at, blank_ballots=data.blank_ballots,
            null_ballots=data.null_ballots, valid_ballots=data.valid_ballots, ballots_counted=data.ballots_counted,
            correction_reason=data.correction_reason,
        )
        self.db.add(revision)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError("Ya existe una revisión con ese número; vuelve a intentarlo.") from exc
        for r in data.results:
            self.db.add(ElectionActResult(revision_id=revision.id, electoral_candidate_id=r.electoral_candidate_id, votes=r.votes))
        act.latest_revision_number = next_number
        act.status = "RECEIVED"
        self.audit.record(
            "ELECTION_ACT_CORRECTION_CREATED", "SUCCESS", "Corrección de acta creada", user_id=user.id, campaign_id=campaign_id,
            resource_type="ELECTION_ACT", resource_id=act.id,
            metadata={"operation_id": str(op.id), "act_id": str(act.id), "revision_id": str(revision.id), "revision_number": next_number},
        )
        self.db.commit()
        return act, revision

    # ---------- Cola de validación (§15) ----------
    def validation_queue(self, campaign_id, user, *, status=None, polling_place_id=None, page=1, page_size=20):
        campaign, _source = self.access.require_act_reviewer(campaign_id, user)
        op = self._require_operation(campaign_id)
        submitted_acts = select(ElectionActRevision.act_id).where(ElectionActRevision.status == "SUBMITTED").distinct()
        q = select(ElectionAct).where(ElectionAct.operation_id == op.id, ElectionAct.id.in_(submitted_acts))
        if status:
            q = q.where(ElectionAct.status == status)
        else:
            # Por defecto la cola es "lo que aún requiere acción" — un acta ya
            # VALIDATED es un estado terminal y no debe seguir apareciendo
            # aquí; quien quiera auditar las validadas pasa status=VALIDATED.
            q = q.where(ElectionAct.status != "VALIDATED")
        if polling_place_id:
            q = q.where(ElectionAct.polling_place_id == polling_place_id)
        total = self.db.scalar(select(func.count()).select_from(q.subquery())) or 0
        priority = case((ElectionAct.status == "RECEIVED", 0), else_=1)
        items = list(
            self.db.scalars(
                q.order_by(priority, ElectionAct.created_at.asc()).offset((page - 1) * page_size).limit(page_size)
            )
        )
        return items, total

    def coverage(self, campaign_id, user):
        self.access.require_control_center_access(campaign_id, user)
        op = self._require_operation(campaign_id)
        campaign = self._campaign(campaign_id)
        boards = self.db.scalar(
            select(func.count()).select_from(ElectoralBoard).join(PollingPlace, PollingPlace.id == ElectoralBoard.polling_place_id).where(
                PollingPlace.electoral_process_id == op.electoral_process_id, PollingPlace.canton_id == campaign.canton_id,
                ElectoralBoard.is_active.is_(True),
            )
        ) or 0
        counts = dict(
            self.db.execute(
                select(ElectionAct.status, func.count()).where(ElectionAct.operation_id == op.id).group_by(ElectionAct.status)
            ).all()
        )
        received = counts.get("RECEIVED", 0)
        in_review = counts.get("IN_REVIEW", 0)
        observed = counts.get("OBSERVED", 0)
        validated = counts.get("VALIDATED", 0)
        total_received = received + in_review + observed + validated
        return {
            "expected_boards": boards, "received": total_received, "validated": validated,
            "in_review": in_review, "observed": observed, "pending": max(boards - total_received, 0),
        }

    # ---------- Serialización de revisión (resultados + evidencia) ----------
    def revision_detail(self, revision):
        """ElectionActRevision no declara relaciones ORM (patrón del resto
        del código base: todo se consulta explícitamente) — este helper arma
        el dict que ElectionActRevisionRead espera, con resultados y
        evidencia activa consultados aparte."""
        results = list(self.db.scalars(select(ElectionActResult).where(ElectionActResult.revision_id == revision.id)))
        evidence = list(
            self.db.scalars(
                select(ElectionActEvidence).where(
                    ElectionActEvidence.revision_id == revision.id, ElectionActEvidence.is_active.is_(True)
                )
            )
        )
        return {
            "id": revision.id, "act_id": revision.act_id, "revision_number": revision.revision_number,
            "revision_type": revision.revision_type, "status": revision.status,
            "submitted_by_user_id": revision.submitted_by_user_id, "blank_ballots": revision.blank_ballots,
            "null_ballots": revision.null_ballots, "valid_ballots": revision.valid_ballots,
            "ballots_counted": revision.ballots_counted, "correction_reason": revision.correction_reason,
            "notes": revision.notes, "created_at": revision.created_at, "submitted_at": revision.submitted_at,
            "results": results, "evidence": evidence,
        }

    # ---------- Lectura (§24/§29) ----------
    def list_acts(self, campaign_id, user, *, status=None, polling_place_id=None):
        op = self._require_operation(campaign_id)
        if self.access.is_executive(user) or (self.access.is_admin(user) and self.access.has_active_support(campaign_id, user)):
            self.access.require_control_center_access(campaign_id, user)
            q = select(ElectionAct).where(ElectionAct.operation_id == op.id)
        elif self.access.active_validator_assignment(campaign_id, user):
            q = select(ElectionAct).where(ElectionAct.operation_id == op.id)
        else:
            allowed = self.access.allowed_polling_place_ids(campaign_id, user)
            if not allowed:
                raise PermissionError("Sin acceso a las actas de esta jornada")
            q = select(ElectionAct).where(ElectionAct.operation_id == op.id, ElectionAct.polling_place_id.in_(allowed))
        if status:
            q = q.where(ElectionAct.status == status)
        if polling_place_id:
            q = q.where(ElectionAct.polling_place_id == polling_place_id)
        return list(self.db.scalars(q.order_by(ElectionAct.created_at.desc())))

    def get_act_detail(self, campaign_id, act_id, user):
        op = self._require_operation(campaign_id)
        act = self._act_for_operation(op, act_id)
        self.access.require_act_viewer(campaign_id, user, act.polling_place_id)
        place = self.db.get(PollingPlace, act.polling_place_id)
        board = self.db.get(ElectoralBoard, act.electoral_board_id)
        contest = self.db.get(ElectoralContest, act.electoral_contest_id)
        revisions = list(
            self.db.scalars(select(ElectionActRevision).where(ElectionActRevision.act_id == act.id).order_by(ElectionActRevision.revision_number))
        )
        reviews = list(
            self.db.scalars(select(ElectionActReview).where(ElectionActReview.act_id == act.id).order_by(ElectionActReview.created_at))
        )
        return act, place, board, contest, revisions, reviews

    # ---------- Claim/Release (§16/§17) ----------
    def claim(self, campaign_id, act_id, user):
        campaign, review_source = self.access.require_act_reviewer(campaign_id, user)
        op = self._require_operation(campaign_id)
        if op.status == "CLOSED":
            raise BusinessRuleError("La jornada está cerrada; las actas quedan en solo lectura.")
        act = self._act_for_operation_locked(op, act_id)
        if not self._latest_submitted_revision(act):
            raise NotFoundError("Acta no encontrada")
        now = datetime.now(timezone.utc)
        active_claim = (
            act.review_claimed_by_user_id is not None
            and act.review_claim_expires_at is not None
            and _aware(act.review_claim_expires_at) > now
        )
        if active_claim and act.review_claimed_by_user_id != user.id:
            raise ConflictError("Esta acta está siendo revisada por otro validador.")
        act.review_claimed_by_user_id = user.id
        act.review_claimed_at = now
        act.review_claim_expires_at = now + timedelta(minutes=settings.election_act_review_claim_minutes)
        if act.status == "RECEIVED":
            act.status = "IN_REVIEW"
        self.audit.record(
            "ELECTION_ACT_REVIEW_CLAIMED", "SUCCESS", "Acta reclamada para revisión", user_id=user.id, campaign_id=campaign_id,
            resource_type="ELECTION_ACT", resource_id=act.id,
            metadata={"operation_id": str(op.id), "act_id": str(act.id), "review_source": review_source},
        )
        self.db.commit()
        return act

    def release(self, campaign_id, act_id, user):
        campaign, review_source = self.access.require_act_reviewer(campaign_id, user)
        op = self._require_operation(campaign_id)
        if op.status == "CLOSED":
            raise BusinessRuleError("La jornada está cerrada; las actas quedan en solo lectura.")
        act = self._act_for_operation_locked(op, act_id)
        if not act.review_claimed_by_user_id:
            raise BusinessRuleError("Esta acta no tiene una revisión en curso.")
        is_owner = act.review_claimed_by_user_id == user.id
        if not is_owner and review_source != "ADMIN_SUPPORT":
            raise PermissionError("Solo quien reclamó esta acta puede liberarla.")
        act.review_claimed_by_user_id = None
        act.review_claimed_at = None
        act.review_claim_expires_at = None
        if act.status == "IN_REVIEW":
            act.status = "RECEIVED"
        self.audit.record(
            "ELECTION_ACT_REVIEW_RELEASED", "SUCCESS", "Reclamo de revisión liberado", user_id=user.id, campaign_id=campaign_id,
            resource_type="ELECTION_ACT", resource_id=act.id,
            metadata={"operation_id": str(op.id), "act_id": str(act.id), "review_source": review_source, "released_by_admin_support": not is_owner},
        )
        self.db.commit()
        return act

    # ---------- Validar / Observar (§19/§20) ----------
    def _require_active_claim(self, act, user):
        now = datetime.now(timezone.utc)
        if not (
            act.review_claimed_by_user_id == user.id
            and act.review_claim_expires_at is not None
            and _aware(act.review_claim_expires_at) > now
        ):
            raise PermissionError("Debes tener un reclamo vigente sobre esta acta para poder revisarla.")

    def validate_act(self, campaign_id, act_id, data, user):
        campaign, review_source = self.access.require_act_reviewer(campaign_id, user)
        op = self._require_operation(campaign_id)
        if op.status == "CLOSED":
            raise BusinessRuleError("La jornada está cerrada; las actas quedan en solo lectura.")
        act = self._act_for_operation_locked(op, act_id)
        self._require_active_claim(act, user)
        latest = self._latest_submitted_revision(act)
        if not latest or latest.id != data.revision_id:
            raise ConflictError("La revisión cambió desde que la revisaste. Actualiza antes de continuar.")
        contest = self.db.get(ElectoralContest, act.electoral_contest_id)
        board = self.db.get(ElectoralBoard, act.electoral_board_id)
        results = list(self.db.scalars(select(ElectionActResult).where(ElectionActResult.revision_id == latest.id)))
        self._validate_arithmetic(contest, board, _RevisionArithmeticView(latest, results))
        review = ElectionActReview(
            act_id=act.id, revision_id=latest.id, reviewer_user_id=user.id, review_source=review_source, action="VALIDATED", reason=None,
        )
        self.db.add(review)
        act.status = "VALIDATED"
        act.validated_revision_id = latest.id
        act.review_claimed_by_user_id = None
        act.review_claimed_at = None
        act.review_claim_expires_at = None
        self.audit.record(
            "ELECTION_ACT_VALIDATED", "SUCCESS", "Acta validada", user_id=user.id, campaign_id=campaign_id,
            resource_type="ELECTION_ACT", resource_id=act.id,
            metadata={"operation_id": str(op.id), "act_id": str(act.id), "revision_id": str(latest.id), "review_source": review_source},
        )
        self.db.commit()
        return act

    def observe_act(self, campaign_id, act_id, data, user):
        campaign, review_source = self.access.require_act_reviewer(campaign_id, user)
        op = self._require_operation(campaign_id)
        if op.status == "CLOSED":
            raise BusinessRuleError("La jornada está cerrada; las actas quedan en solo lectura.")
        act = self._act_for_operation_locked(op, act_id)
        self._require_active_claim(act, user)
        latest = self._latest_submitted_revision(act)
        if not latest or latest.id != data.revision_id:
            raise ConflictError("La revisión cambió desde que la revisaste. Actualiza antes de continuar.")
        review = ElectionActReview(
            act_id=act.id, revision_id=latest.id, reviewer_user_id=user.id, review_source=review_source,
            action="OBSERVED", reason=data.reason,
        )
        self.db.add(review)
        act.status = "OBSERVED"
        act.review_claimed_by_user_id = None
        act.review_claimed_at = None
        act.review_claim_expires_at = None
        self.audit.record(
            "ELECTION_ACT_OBSERVED", "SUCCESS", "Acta observada", user_id=user.id, campaign_id=campaign_id,
            resource_type="ELECTION_ACT", resource_id=act.id,
            metadata={"operation_id": str(op.id), "act_id": str(act.id), "revision_id": str(latest.id), "review_source": review_source},
        )
        self.db.commit()
        return act


class _RevisionArithmeticView:
    """Adapta una ElectionActRevision + sus resultados ya persistidos a la
    misma forma que espera _validate_arithmetic (que normalmente recibe el
    payload de entrada), para revalidar la aritmética al momento de VALIDAR
    (§19) sin duplicar la lógica."""

    def __init__(self, revision, results):
        self.blank_ballots = revision.blank_ballots
        self.null_ballots = revision.null_ballots
        self.valid_ballots = revision.valid_ballots
        self.ballots_counted = revision.ballots_counted
        self.results = results
