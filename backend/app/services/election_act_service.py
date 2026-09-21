import logging
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.observability import record_event
from app.core.security import TokenValidationError
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
from app.models.territory import Parish
from app.schemas.election_act import ElectionActEvidenceUploadIntentResponse
from app.services.artifact_storage import S3ArtifactStorage
from app.services.artifact_storage_factory import build_evidence_storage
from app.services.artifact_upload_token import create_artifact_upload_token, decode_artifact_upload_token
from app.services.election_day_access_service import ElectionDayAccessService
from app.services.evidence_security_service import EVIDENCE_EXTENSION_BY_MIME, safe_evidence_filename, sniff_evidence_mime
from app.services.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.services.security_audit_service import SecurityAuditService

logger = logging.getLogger("territorio.storage")

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


def _pct(numerator, denominator) -> float:
    """§6/§8 auditoría/Fase 3: nunca dividir por cero — 0.0 cuando el
    denominador es 0 (el frontend decide si mostrar "0%" o "Sin datos" según
    el propio denominador, que siempre viaja junto a este porcentaje)."""
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 1)
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
        self.storage = storage or build_evidence_storage()

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
        download = self.storage.download(evidence.storage_key, filename=evidence.original_filename, content_type=evidence.mime_type)
        logger.info(
            "ARTIFACT_DOWNLOAD_AUTHORIZED",
            extra={"provider": "s3" if isinstance(self.storage, S3ArtifactStorage) else "local", "act_id": str(act.id), "revision_id": str(revision.id)},
        )
        return download, evidence

    # ---------- Subida directa a S3 (§12-18 Fase 4A) ----------
    def _authorize_pending_evidence(self, campaign_id, act_id, revision_id, user):
        """Shared guard for create_upload_intent/complete_upload: same
        preconditions as the API_PROXY upload_evidence path (§26 — the
        transport mechanism never changes what's authorized)."""
        self.access.require_delegate_assignment(campaign_id, user)
        op = self._require_operation(campaign_id)
        if op.status == "CLOSED":
            raise BusinessRuleError("La jornada está cerrada; las actas quedan en solo lectura.")
        act = self._act_for_operation(op, act_id)
        self.access.require_delegate_assignment(campaign_id, user, polling_place_id=act.polling_place_id)
        revision = self._revision(act, revision_id)
        if revision.status == "SUBMITTED":
            raise BusinessRuleError("Esta revisión ya fue enviada; no se puede modificar su evidencia.")
        return op, act, revision

    def _existing_evidence_by_client_id(self, revision_id, user_id, client_generated_id):
        if not client_generated_id:
            return None
        return self.db.scalar(
            select(ElectionActEvidence).where(
                ElectionActEvidence.revision_id == revision_id,
                ElectionActEvidence.uploaded_by_user_id == user_id,
                ElectionActEvidence.client_generated_id == client_generated_id,
            )
        )

    def create_upload_intent(self, campaign_id, act_id, revision_id, user, *, client_generated_id, original_filename, mime_type, size_bytes, sha256):
        op, act, revision = self._authorize_pending_evidence(campaign_id, act_id, revision_id, user)
        if mime_type not in EVIDENCE_ALLOWED_MIME:
            raise BusinessRuleError("Formato de imagen no permitido. Usa JPEG o PNG.")
        max_bytes = settings.evidence_max_file_mb * 1024 * 1024
        if size_bytes > max_bytes:
            raise BusinessRuleError("El archivo supera el tamaño permitido")
        existing = self._existing_evidence_by_client_id(revision.id, user.id, client_generated_id)
        if existing:
            return ElectionActEvidenceUploadIntentResponse(
                mode="ALREADY_COMPLETED", max_file_mb=settings.evidence_max_file_mb,
                allowed_mime_types=sorted(EVIDENCE_ALLOWED_MIME), evidence_id=existing.id,
            )
        if not isinstance(self.storage, S3ArtifactStorage):
            return ElectionActEvidenceUploadIntentResponse(
                mode="API_PROXY", max_file_mb=settings.evidence_max_file_mb, allowed_mime_types=sorted(EVIDENCE_ALLOWED_MIME),
            )
        extension = EVIDENCE_EXTENSION_BY_MIME[mime_type]
        pending_key = self.storage.new_pending_key(extension)
        presigned = self.storage.presign_upload(pending_key, content_type=mime_type, max_bytes=max_bytes, sha256_hex=sha256)
        # Sanitized once, here — the token carries the already-safe name so
        # complete() never has to re-derive or re-trust anything from a
        # second hop of client input (§4 audit).
        safe_filename = safe_evidence_filename(original_filename or "acta", extension)
        upload_token = create_artifact_upload_token(
            campaign_id=campaign_id, operation_id=op.id, act_id=act.id, revision_id=revision.id, user_id=user.id,
            client_generated_id=client_generated_id, pending_key=pending_key, size_bytes=size_bytes, mime_type=mime_type,
            sha256=sha256, original_filename=safe_filename, expires_in_seconds=settings.s3_presign_expires_seconds,
        )
        logger.info(
            "ARTIFACT_UPLOAD_INTENT",
            extra={"provider": "s3", "operation_id": str(op.id), "act_id": str(act.id), "revision_id": str(revision.id), "size_bytes": size_bytes, "mime_type": mime_type},
        )
        return ElectionActEvidenceUploadIntentResponse(
            mode="PRESIGNED_S3", url=presigned.url, fields=presigned.fields, upload_token=upload_token,
            expires_at=presigned.expires_at, max_file_mb=settings.evidence_max_file_mb, allowed_mime_types=sorted(EVIDENCE_ALLOWED_MIME),
        )

    def complete_upload(self, campaign_id, act_id, revision_id, user, *, upload_token):
        try:
            payload = decode_artifact_upload_token(upload_token)
        except TokenValidationError as exc:
            raise BusinessRuleError("El token de carga es inválido o expiró") from exc
        if (str(campaign_id), str(act_id), str(revision_id), str(user.id)) != (
            payload["campaign_id"], payload["act_id"], payload["revision_id"], payload["user_id"],
        ):
            raise PermissionError("El token de carga no corresponde a esta solicitud")
        op, act, revision = self._authorize_pending_evidence(campaign_id, act_id, revision_id, user)
        if str(op.id) != payload["operation_id"]:
            raise PermissionError("El token de carga no corresponde a esta jornada")
        raw_client_generated_id = payload.get("client_generated_id")
        client_generated_id = UUID(raw_client_generated_id) if raw_client_generated_id else None
        existing = self._existing_evidence_by_client_id(revision.id, user.id, client_generated_id)
        if existing:
            return existing
        if not isinstance(self.storage, S3ArtifactStorage):
            raise BusinessRuleError("La carga directa no está disponible con el almacenamiento configurado")
        pending_key = payload["pending_key"]
        head = self.storage.head_metadata(pending_key)
        log_context = {"provider": "s3", "operation_id": str(op.id), "act_id": str(act.id), "revision_id": str(revision.id)}
        if not head:
            logger.warning("ARTIFACT_UPLOAD_FAILED", extra={**log_context, "outcome": "missing_object"})
            record_event("artifact_upload_failure_total")
            raise BusinessRuleError("No se encontró la fotografía cargada. Vuelve a intentarlo.")
        # checksum_sha256_hex is S3's own additional-checksum result (see
        # HeadResult docstring) — S3 already rejected the upload at POST time
        # if the bytes it received didn't hash to what presign_upload
        # declared, so this comparison catches a mismatched/tampered token
        # rather than trusting anything the client asserted independently of
        # the bytes it actually sent. We never re-download the object to
        # re-hash it ourselves — that would defeat the point of a direct
        # upload (§3 Fase 4A audit).
        if head.size_bytes != payload["size_bytes"] or head.content_type != payload["mime_type"] or head.checksum_sha256_hex != payload["sha256"]:
            logger.warning("ARTIFACT_UPLOAD_FAILED", extra={**log_context, "outcome": "checksum_or_metadata_mismatch"})
            record_event("artifact_upload_failure_total")
            try:
                self.storage.delete(pending_key)
            except Exception:
                logger.warning("ARTIFACT_DELETE_FAILED", extra={**log_context, "outcome": "pending_cleanup_failed"})
            raise BusinessRuleError("La fotografía cargada no coincide con lo autorizado. Vuelve a intentarlo.")
        final_key = self.storage.promote_pending(pending_key)
        evidence = ElectionActEvidence(
            revision_id=revision.id, storage_key=final_key, mime_type=payload["mime_type"], size_bytes=payload["size_bytes"],
            sha256=payload["sha256"], original_filename=payload["original_filename"],
            uploaded_by_user_id=user.id, client_generated_id=client_generated_id, is_active=True,
        )
        self.db.add(evidence)
        try:
            self.db.flush()
            self.audit.record(
                "ELECTION_ACT_EVIDENCE_UPLOADED", "SUCCESS", "Evidencia de acta cargada (S3 directo)", user_id=user.id, campaign_id=campaign_id,
                resource_type="ELECTION_ACT_EVIDENCE", resource_id=evidence.id,
                metadata={"operation_id": str(op.id), "act_id": str(act.id), "revision_id": str(revision.id), "mime_type": payload["mime_type"], "size_bytes": payload["size_bytes"], "provider": "s3"},
            )
            self.db.commit()
        except IntegrityError:
            # Idempotency race (§16/§24): two concurrent completes for the
            # same client_generated_id — the loser refetches instead of
            # erroring, and never deletes the winner's already-promoted object.
            self.db.rollback()
            existing = self._existing_evidence_by_client_id(revision.id, user.id, client_generated_id)
            if existing:
                return existing
            raise
        except Exception:
            # Unlike the losing side of the IntegrityError race above, this
            # branch means NOTHING else persisted this evidence — the
            # promoted object really is orphaned, so best-effort cleanup applies.
            self.db.rollback()
            try:
                self.storage.delete(final_key)
            except Exception:
                logger.warning("ARTIFACT_DELETE_FAILED", extra={**log_context, "outcome": "orphan_cleanup_failed"})
            raise
        logger.info("ARTIFACT_UPLOAD_COMPLETED", extra={**log_context, "size_bytes": payload["size_bytes"], "mime_type": payload["mime_type"]})
        record_event("artifact_upload_complete_total")
        return evidence

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
            record_event("act_submit_failure_total")
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
        record_event("act_submit_total")
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
            "received_coverage_pct": _pct(total_received, boards), "validated_coverage_pct": _pct(validated, boards),
        }

    # ---------- Centro de Control Electoral (Fase 3) ----------
    def control_center_summary(self, campaign_id, user):
        """Consolidado factual NO OFICIAL para CANDIDATE/CAMPAIGN_MANAGER/
        ADMIN-en-soporte (§3, misma puerta que coverage/list_acts). Fuente de
        verdad única: ElectionAct.status == 'VALIDATED' vía
        validated_revision_id — nunca RECEIVED/IN_REVIEW/OBSERVED, nunca una
        revisión vieja. Todo por agregación SQL (sin N+1, sin cargar
        evidence/revisions/reviews completas — §13)."""
        campaign = self.access.require_control_center_access(campaign_id, user)
        op = self._require_operation(campaign_id)

        # ---------- Recintos: JRV esperadas por recinto (agregación única) ----------
        boards_by_place = dict(
            self.db.execute(
                select(ElectoralBoard.polling_place_id, func.count(ElectoralBoard.id))
                .join(PollingPlace, PollingPlace.id == ElectoralBoard.polling_place_id)
                .where(
                    PollingPlace.electoral_process_id == op.electoral_process_id,
                    PollingPlace.canton_id == campaign.canton_id,
                    ElectoralBoard.is_active.is_(True),
                )
                .group_by(ElectoralBoard.polling_place_id)
            ).all()
        )
        total_expected_boards = sum(boards_by_place.values())

        places = list(
            self.db.scalars(
                select(PollingPlace)
                .where(PollingPlace.electoral_process_id == op.electoral_process_id, PollingPlace.canton_id == campaign.canton_id)
                .order_by(PollingPlace.name)
            )
        )

        acts_by_place_status: dict = {}
        for place_id, status, count in self.db.execute(
            select(ElectionAct.polling_place_id, ElectionAct.status, func.count())
            .where(ElectionAct.operation_id == op.id)
            .group_by(ElectionAct.polling_place_id, ElectionAct.status)
        ).all():
            acts_by_place_status.setdefault(place_id, {})[status] = count

        polling_places = []
        for place in places:
            expected = boards_by_place.get(place.id, 0)
            counts = acts_by_place_status.get(place.id, {})
            received_total = sum(counts.get(s, 0) for s in ("RECEIVED", "IN_REVIEW", "OBSERVED", "VALIDATED"))
            validated = counts.get("VALIDATED", 0)
            polling_places.append({
                "polling_place_id": place.id, "polling_place_name": place.name, "parish_id": place.parish_id,
                "expected_boards": expected, "received": received_total, "validated": validated,
                "in_review": counts.get("IN_REVIEW", 0), "observed": counts.get("OBSERVED", 0),
                "pending": max(expected - received_total, 0),
                "coverage_validated_pct": _pct(validated, expected),
            })

        # ---------- Parroquias: agregadas desde polling_places (sin query extra) ----------
        parish_agg: dict = {}
        for pp in polling_places:
            pid = pp["parish_id"]
            agg = parish_agg.setdefault(pid, {"expected_boards": 0, "validated": 0})
            agg["expected_boards"] += pp["expected_boards"]
            agg["validated"] += pp["validated"]
        parish_ids = list(parish_agg.keys())
        parish_names = dict(self.db.execute(select(Parish.id, Parish.name).where(Parish.id.in_(parish_ids))).all()) if parish_ids else {}

        votes_by_parish: dict = {}
        if parish_ids:
            for pid, valid, blank, null in self.db.execute(
                select(
                    PollingPlace.parish_id,
                    func.coalesce(func.sum(ElectionActRevision.valid_ballots), 0),
                    func.coalesce(func.sum(ElectionActRevision.blank_ballots), 0),
                    func.coalesce(func.sum(ElectionActRevision.null_ballots), 0),
                )
                .select_from(ElectionAct)
                .join(ElectionActRevision, ElectionActRevision.id == ElectionAct.validated_revision_id)
                .join(PollingPlace, PollingPlace.id == ElectionAct.polling_place_id)
                .where(ElectionAct.status == "VALIDATED", ElectionAct.operation_id == op.id)
                .group_by(PollingPlace.parish_id)
            ).all():
                votes_by_parish[pid] = (valid, blank, null)

        parishes = [
            {
                "parish_id": pid, "parish_name": parish_names.get(pid, "—"),
                "expected_boards": agg["expected_boards"], "validated": agg["validated"],
                "coverage_validated_pct": _pct(agg["validated"], agg["expected_boards"]),
                "valid_votes": votes_by_parish.get(pid, (0, 0, 0))[0],
                "blank_votes": votes_by_parish.get(pid, (0, 0, 0))[1],
                "null_votes": votes_by_parish.get(pid, (0, 0, 0))[2],
            }
            for pid, agg in sorted(parish_agg.items(), key=lambda kv: parish_names.get(kv[0], ""))
        ]

        # ---------- Contiendas: un bloque por ElectoralContest elegible, nunca mezclados (§22) ----------
        contest_ids = self._eligible_contest_ids(campaign, op)
        contests_meta = list(
            self.db.scalars(select(ElectoralContest).where(ElectoralContest.id.in_(contest_ids)).order_by(ElectoralContest.name))
        ) if contest_ids else []

        contests = []
        for contest in contests_meta:
            expected_for_contest = (
                parish_agg.get(contest.parish_id, {}).get("expected_boards", 0)
                if contest.parish_id is not None else total_expected_boards
            )
            validated_acts = self.db.scalar(
                select(func.count()).select_from(ElectionAct).where(
                    ElectionAct.operation_id == op.id, ElectionAct.electoral_contest_id == contest.id, ElectionAct.status == "VALIDATED",
                )
            ) or 0
            totals_row = self.db.execute(
                select(
                    func.coalesce(func.sum(ElectionActRevision.valid_ballots), 0),
                    func.coalesce(func.sum(ElectionActRevision.blank_ballots), 0),
                    func.coalesce(func.sum(ElectionActRevision.null_ballots), 0),
                    func.coalesce(func.sum(ElectionActRevision.ballots_counted), 0),
                )
                .select_from(ElectionAct)
                .join(ElectionActRevision, ElectionActRevision.id == ElectionAct.validated_revision_id)
                .where(ElectionAct.operation_id == op.id, ElectionAct.electoral_contest_id == contest.id, ElectionAct.status == "VALIDATED")
            ).first()
            valid_votes, blank_votes, null_votes, ballots_counted = totals_row if totals_row else (0, 0, 0, 0)

            votes_by_candidate = dict(
                self.db.execute(
                    select(ElectionActResult.electoral_candidate_id, func.coalesce(func.sum(ElectionActResult.votes), 0))
                    .select_from(ElectionActResult)
                    .join(ElectionAct, ElectionAct.validated_revision_id == ElectionActResult.revision_id)
                    .where(ElectionAct.operation_id == op.id, ElectionAct.electoral_contest_id == contest.id, ElectionAct.status == "VALIDATED")
                    .group_by(ElectionActResult.electoral_candidate_id)
                ).all()
            )
            candidates_meta = list(
                self.db.scalars(
                    select(ElectoralCandidate)
                    .where(ElectoralCandidate.electoral_contest_id == contest.id, ElectoralCandidate.is_active.is_(True))
                    .order_by(ElectoralCandidate.ballot_order, ElectoralCandidate.full_name)
                )
            )
            candidates = [
                {
                    "candidate_id": c.id, "display_name": c.display_name or c.full_name,
                    "list_number": c.list_number, "ballot_order": c.ballot_order,
                    "votes": votes_by_candidate.get(c.id, 0),
                    "pct_valid_votes": _pct(votes_by_candidate.get(c.id, 0), valid_votes),
                }
                for c in candidates_meta
            ]
            contests.append({
                "contest_id": contest.id, "contest_name": contest.name, "office_type": contest.office_type, "vote_method": contest.vote_method,
                "validated_acts": validated_acts, "expected_acts": expected_for_contest,
                "valid_votes": valid_votes, "blank_votes": blank_votes, "null_votes": null_votes, "ballots_counted": ballots_counted,
                "candidates": candidates,
            })

        # §33: cobertura reconstruida a partir de acts_by_place_status/
        # boards_by_place, ya calculados arriba — nunca una segunda llamada a
        # self.coverage(), que repetiría la verificación de acceso y las
        # mismas consultas agregadas por recinto.
        status_totals: dict[str, int] = {}
        for by_status in acts_by_place_status.values():
            for status, count in by_status.items():
                status_totals[status] = status_totals.get(status, 0) + count
        received = status_totals.get("RECEIVED", 0)
        in_review_total = status_totals.get("IN_REVIEW", 0)
        observed_total = status_totals.get("OBSERVED", 0)
        validated_total = status_totals.get("VALIDATED", 0)
        total_received = received + in_review_total + observed_total + validated_total
        acts_coverage = {
            "expected_boards": total_expected_boards, "received": total_received, "validated": validated_total,
            "in_review": in_review_total, "observed": observed_total, "pending": max(total_expected_boards - total_received, 0),
            "received_coverage_pct": _pct(total_received, total_expected_boards), "validated_coverage_pct": _pct(validated_total, total_expected_boards),
        }

        return {
            "acts_coverage": acts_coverage,
            "contests": contests, "polling_places": polling_places, "parishes": parishes,
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
            record_event("act_claim_conflict_total")
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
            record_event("act_validation_conflict_total")
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
        record_event("act_validation_total")
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
