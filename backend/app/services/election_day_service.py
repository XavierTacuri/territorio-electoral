import tempfile
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import func, select
from app.core.config import settings
from app.models.assignments import CampaignUser
from app.models.campaign import Campaign
from app.models.election_day import ElectionDayAssignment, ElectionDayDocument, ElectionDayIncident, ElectionDayOperation, ElectoralBoard, PollingPlace
from app.models.historical import DataSource, ElectoralContest, ElectoralProcess
from app.models.territory import Canton, Parish
from app.models.user import User
from app.services.election_day_access_service import ElectionDayAccessService
from app.services.evidence_security_service import EVIDENCE_EXTENSION_BY_MIME, safe_evidence_filename, sniff_evidence_mime
from app.services.evidence_storage_service import LocalEvidenceStorage
from app.services.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.services.security_audit_service import SecurityAuditService

ASSIGNMENT_ROLES = {"POLLING_PLACE_COORDINATOR", "BOARD_DELEGATE", "MOBILE_SUPPORT"}
INCIDENT_CATEGORIES = {"PERSONNEL", "ACCESS", "LOGISTICS", "DOCUMENTATION", "CONNECTIVITY", "OTHER"}
DOCUMENT_TYPES = {"ACTA_COPY", "INCIDENT_DOCUMENT", "OTHER"}
INCIDENT_STATUSES = {"OPEN", "IN_REVIEW", "RESOLVED"}


class ElectionDayService:
    """Centro operativo del día de la elección. Nunca un sistema de resultados
    (§2): no existe ningún campo de votos/ganador/porcentaje aquí — solo
    cobertura, presencia, incidencias y documentación operativa."""

    def __init__(self, db, storage=None):
        self.db = db
        self.access = ElectionDayAccessService(db)
        self.audit = SecurityAuditService(db)
        self.storage = storage or LocalEvidenceStorage(settings.evidence_output_dir, settings.evidence_max_file_mb)

    def _campaign(self, campaign_id):
        campaign = self.db.get(Campaign, campaign_id)
        if not campaign:
            raise NotFoundError("Campaña no encontrada")
        return campaign

    def _operation_or_none(self, campaign_id):
        return self.db.scalar(select(ElectionDayOperation).where(ElectionDayOperation.campaign_id == campaign_id).order_by(ElectionDayOperation.created_at.desc()))

    def _require_operation(self, campaign_id):
        op = self._operation_or_none(campaign_id)
        if not op:
            raise NotFoundError("No existe una jornada configurada para esta campaña")
        return op

    def _polling_place(self, campaign, op, polling_place_id):
        place = self.db.get(PollingPlace, polling_place_id)
        if not place or place.electoral_process_id != op.electoral_process_id or place.canton_id != campaign.canton_id:
            raise NotFoundError("Recinto no encontrado")
        return place

    # ---------- Operation lifecycle (§5-7, §55, §89) ----------
    def get_operation(self, campaign_id, user):
        self.access.require_read(campaign_id, user)
        return self._require_operation(campaign_id)

    def create_operation(self, campaign_id, data, user):
        campaign = self.access.require_manage_operation(campaign_id, user)
        process = self.db.get(ElectoralProcess, data.electoral_process_id)
        if not process:
            raise NotFoundError("Proceso electoral no encontrado")
        matches = self.db.scalar(select(func.count()).select_from(ElectoralContest).where(ElectoralContest.electoral_process_id == process.id, ElectoralContest.canton_id == campaign.canton_id, ElectoralContest.office_type == campaign.office_type)) or 0
        if not matches:
            raise BusinessRuleError("El proceso electoral no corresponde a esta campaña")
        if self.db.scalar(select(ElectionDayOperation).where(ElectionDayOperation.campaign_id == campaign_id, ElectionDayOperation.electoral_process_id == process.id)):
            raise ConflictError("Ya existe una jornada para esta campaña y proceso")
        op = ElectionDayOperation(organization_id=campaign.organization_id, campaign_id=campaign_id, electoral_process_id=process.id, election_date=data.election_date, status="PREPARATION", notes=data.notes)
        self.db.add(op)
        self.db.flush()
        self.audit.record("ELECTION_DAY_CREATED", "SUCCESS", "Jornada electoral creada", user_id=user.id, campaign_id=campaign_id, resource_type="ELECTION_DAY_OPERATION", resource_id=op.id)
        self.db.commit()
        return op

    def open_operation(self, campaign_id, user):
        self.access.require_manage_operation(campaign_id, user)
        op = self._require_operation(campaign_id)
        if op.status == "ACTIVE":
            return op
        if op.status == "CLOSED":
            raise BusinessRuleError("La jornada ya fue cerrada")
        # Defensa en profundidad (§6): el modelo ya garantiza un único row por
        # (campaign, process), así que esto es una segunda comprobación
        # explícita, no la única barrera.
        if self.db.scalar(select(func.count()).select_from(ElectionDayOperation).where(ElectionDayOperation.campaign_id == campaign_id, ElectionDayOperation.electoral_process_id == op.electoral_process_id, ElectionDayOperation.status == "ACTIVE", ElectionDayOperation.id != op.id)):
            raise ConflictError("Ya existe una jornada activa para este proceso")
        op.status = "ACTIVE"
        op.opened_at = datetime.now(timezone.utc)
        op.opened_by_user_id = user.id
        self.audit.record("ELECTION_DAY_OPENED", "SUCCESS", "Jornada electoral activada", user_id=user.id, campaign_id=campaign_id, resource_type="ELECTION_DAY_OPERATION", resource_id=op.id)
        self.db.commit()
        return op

    def closure_preview(self, campaign_id, user):
        self.access.require_read(campaign_id, user)
        op = self._require_operation(campaign_id)
        return op, self._coverage(campaign_id, op)

    def close_operation(self, campaign_id, data, user):
        self.access.require_manage_operation(campaign_id, user)
        op = self._require_operation(campaign_id)
        if op.status != "ACTIVE":
            raise BusinessRuleError("Solo una jornada activa puede cerrarse")
        open_incidents = self.db.scalar(select(func.count()).select_from(ElectionDayIncident).where(ElectionDayIncident.operation_id == op.id, ElectionDayIncident.status != "RESOLVED", ElectionDayIncident.is_active.is_(True))) or 0
        # §55: advertir, no bloquear por defecto — las incidencias y documentos
        # pendientes pueden resolverse/recibirse administrativamente después
        # del cierre (§89), auditados con su fecha real.
        op.status = "CLOSED"
        op.closed_at = datetime.now(timezone.utc)
        op.closed_by_user_id = user.id
        if data.notes:
            op.notes = (op.notes + "\n" if op.notes else "") + data.notes
        self.audit.record("ELECTION_DAY_CLOSED", "SUCCESS", "Jornada electoral cerrada", user_id=user.id, campaign_id=campaign_id, resource_type="ELECTION_DAY_OPERATION", resource_id=op.id, metadata={"open_incidents_at_close": open_incidents})
        self.db.commit()
        return op

    # ---------- Polling places / boards (§8-11) ----------
    def list_polling_places(self, campaign_id, user):
        campaign = self.access.require_read(campaign_id, user)
        op = self._require_operation(campaign_id)
        allowed = self.access.allowed_parish_ids(campaign_id, user)
        q = select(PollingPlace).where(PollingPlace.electoral_process_id == op.electoral_process_id, PollingPlace.canton_id == campaign.canton_id)
        if allowed is not None:
            q = q.where(PollingPlace.parish_id.in_(allowed)) if allowed else q.where(False)
        return list(self.db.scalars(q.order_by(PollingPlace.name)))

    def create_polling_place(self, campaign_id, data, user):
        campaign = self.access.require_manage_operation(campaign_id, user)
        op = self._require_operation(campaign_id)
        parish = self.db.get(Parish, data.parish_id)
        if not parish or parish.canton_id != campaign.canton_id:
            raise BusinessRuleError("La parroquia no pertenece al cantón de la campaña")
        if self.db.scalar(select(PollingPlace).where(PollingPlace.electoral_process_id == op.electoral_process_id, PollingPlace.official_code == data.official_code)):
            raise ConflictError("Ya existe un recinto con ese código para este proceso")
        canton = self.db.get(Canton, parish.canton_id)
        place = PollingPlace(electoral_process_id=op.electoral_process_id, province_id=canton.province_id, canton_id=canton.id, parish_id=parish.id, official_code=data.official_code, name=data.name, address=data.address, latitude=data.latitude, longitude=data.longitude, is_active=True)
        self.db.add(place)
        self.db.flush()
        self.db.commit()
        return place

    def list_boards(self, campaign_id, user, polling_place_id):
        campaign = self.access.require_read(campaign_id, user)
        op = self._require_operation(campaign_id)
        place = self._polling_place(campaign, op, polling_place_id)
        self.access.require_parish_scope(campaign_id, user, place.parish_id)
        return list(self.db.scalars(select(ElectoralBoard).where(ElectoralBoard.polling_place_id == place.id).order_by(ElectoralBoard.board_number)))

    def create_board(self, campaign_id, polling_place_id, data, user):
        campaign = self.access.require_manage_operation(campaign_id, user)
        op = self._require_operation(campaign_id)
        place = self._polling_place(campaign, op, polling_place_id)
        if self.db.scalar(select(ElectoralBoard).where(ElectoralBoard.polling_place_id == place.id, ElectoralBoard.official_code == data.official_code)):
            raise ConflictError("Ya existe una junta con ese código en este recinto")
        board = ElectoralBoard(polling_place_id=place.id, official_code=data.official_code, board_number=data.board_number, sex_category=data.sex_category, registered_voters=data.registered_voters, is_active=True)
        self.db.add(board)
        self.db.flush()
        self.db.commit()
        return board

    def polling_place_detail(self, campaign_id, polling_place_id, user):
        campaign = self.access.require_read(campaign_id, user)
        op = self._require_operation(campaign_id)
        place = self._polling_place(campaign, op, polling_place_id)
        self.access.require_parish_scope(campaign_id, user, place.parish_id)
        return place

    # ---------- Coverage matrix (§17-18, §40) ----------
    def _coverage(self, campaign_id, op):
        campaign = self._campaign(campaign_id)
        places = list(self.db.scalars(select(PollingPlace).where(PollingPlace.electoral_process_id == op.electoral_process_id, PollingPlace.canton_id == campaign.canton_id, PollingPlace.is_active.is_(True))))
        place_ids = [p.id for p in places]
        boards = list(self.db.scalars(select(ElectoralBoard).where(ElectoralBoard.polling_place_id.in_(place_ids), ElectoralBoard.is_active.is_(True)))) if place_ids else []
        assignments = list(self.db.scalars(select(ElectionDayAssignment).where(ElectionDayAssignment.operation_id == op.id, ElectionDayAssignment.status != "REPLACED")))
        covered_places = {a.polling_place_id for a in assignments} & set(place_ids)
        covered_boards = {a.board_id for a in assignments if a.board_id} & {b.id for b in boards}
        confirmed = sum(1 for a in assignments if a.status in {"CONFIRMED", "CHECKED_IN"})
        checked_in = sum(1 for a in assignments if a.status == "CHECKED_IN")
        open_incidents = self.db.scalar(select(func.count()).select_from(ElectionDayIncident).where(ElectionDayIncident.operation_id == op.id, ElectionDayIncident.status != "RESOLVED", ElectionDayIncident.is_active.is_(True))) or 0
        documents_received = self.db.scalar(select(func.count()).select_from(ElectionDayDocument).where(ElectionDayDocument.operation_id == op.id, ElectionDayDocument.is_active.is_(True))) or 0
        return {
            "total_polling_places": len(places), "covered_polling_places": len(covered_places),
            "total_boards": len(boards), "covered_boards": len(covered_boards),
            "personnel_confirmed": confirmed, "personnel_checked_in": checked_in,
            "open_incidents": open_incidents,
            # §39: expectativa mínima determinística de una copia por junta —
            # documentada como simplificación, no como regla oficial universal.
            "documents_received": documents_received, "expected_documents": len(boards),
        }

    def coverage(self, campaign_id, user):
        self.access.require_read(campaign_id, user)
        op = self._require_operation(campaign_id)
        return self._coverage(campaign_id, op)

    # ---------- Assignments (§12-17, §52) ----------
    def list_assignments(self, campaign_id, user, polling_place_id=None):
        campaign = self.access.require_read(campaign_id, user)
        op = self._require_operation(campaign_id)
        q = select(ElectionDayAssignment).where(ElectionDayAssignment.operation_id == op.id)
        if polling_place_id:
            q = q.where(ElectionDayAssignment.polling_place_id == polling_place_id)
        items = list(self.db.scalars(q.order_by(ElectionDayAssignment.created_at.desc())))
        allowed = self.access.allowed_parish_ids(campaign_id, user)
        if allowed is not None:
            place_ids = {p.id for p in self.db.scalars(select(PollingPlace).where(PollingPlace.canton_id == campaign.canton_id, PollingPlace.parish_id.in_(allowed)))} if allowed else set()
            items = [a for a in items if a.polling_place_id in place_ids]
        return items

    def create_assignment(self, campaign_id, data, user):
        campaign = self.access.require_manage_operation(campaign_id, user)
        op = self._require_operation(campaign_id)
        if op.status == "CLOSED":
            raise BusinessRuleError("La jornada está cerrada")
        if data.assignment_role not in ASSIGNMENT_ROLES:
            raise BusinessRuleError("Rol de asignación inválido")
        place = self._polling_place(campaign, op, data.polling_place_id)
        if data.board_id:
            board = self.db.get(ElectoralBoard, data.board_id)
            if not board or board.polling_place_id != place.id:
                raise NotFoundError("Junta no encontrada en este recinto")
        if not self.db.get(User, data.user_id):
            raise NotFoundError("Usuario no encontrado")
        if not self.db.scalar(select(CampaignUser).where(CampaignUser.campaign_id == campaign_id, CampaignUser.user_id == data.user_id, CampaignUser.is_active.is_(True))):
            raise BusinessRuleError("El usuario no pertenece a esta campaña")
        assignment = ElectionDayAssignment(operation_id=op.id, user_id=data.user_id, polling_place_id=place.id, board_id=data.board_id, assignment_role=data.assignment_role, status="ASSIGNED", assigned_by_user_id=user.id)
        self.db.add(assignment)
        self.db.flush()
        self.audit.record("ASSIGNMENT_CREATED", "SUCCESS", "Asignación de jornada creada", user_id=user.id, campaign_id=campaign_id, resource_type="ELECTION_DAY_ASSIGNMENT", resource_id=assignment.id, metadata={"assignment_role": data.assignment_role})
        self.db.commit()
        return assignment

    def eligible_users(self, campaign_id, user):
        self.access.require_manage_operation(campaign_id, user)
        rows = self.db.execute(select(User).join(CampaignUser, CampaignUser.user_id == User.id).where(CampaignUser.campaign_id == campaign_id, CampaignUser.is_active.is_(True)).order_by(User.first_name, User.last_name))
        return [r[0] for r in rows]

    def replace_assignment(self, campaign_id, assignment_id, data, user):
        self.access.require_manage_operation(campaign_id, user)
        op = self._require_operation(campaign_id)
        old = self.db.get(ElectionDayAssignment, assignment_id)
        if not old or old.operation_id != op.id:
            raise NotFoundError("Asignación no encontrada")
        if old.status in {"REPLACED", "COMPLETED"}:
            raise BusinessRuleError("La asignación ya no está activa")
        if data.user_id == old.user_id:
            raise BusinessRuleError("El nuevo usuario debe ser distinto de la persona reemplazada")
        if not self.db.scalar(select(CampaignUser).where(CampaignUser.campaign_id == campaign_id, CampaignUser.user_id == data.user_id, CampaignUser.is_active.is_(True))):
            raise BusinessRuleError("El usuario no pertenece a esta campaña")
        new = ElectionDayAssignment(operation_id=op.id, user_id=data.user_id, polling_place_id=old.polling_place_id, board_id=old.board_id, assignment_role=old.assignment_role, status="ASSIGNED", assigned_by_user_id=user.id)
        self.db.add(new)
        self.db.flush()
        old.status = "REPLACED"
        old.replaced_by_assignment_id = new.id
        self.audit.record("ASSIGNMENT_REPLACED", "SUCCESS", "Asignación de jornada reemplazada", user_id=user.id, campaign_id=campaign_id, resource_type="ELECTION_DAY_ASSIGNMENT", resource_id=old.id, metadata={"reason": data.reason, "new_assignment_id": str(new.id)})
        self.db.commit()
        return new

    # ---------- Check-in (§19-22, §51) ----------
    def check_in(self, campaign_id, assignment_id, data, user):
        self.access.require_read(campaign_id, user)
        op = self._require_operation(campaign_id)
        assignment = self.db.get(ElectionDayAssignment, assignment_id)
        if not assignment or assignment.operation_id != op.id:
            raise NotFoundError("Asignación no encontrada")
        if assignment.user_id != user.id and not self.access.can_manage_operation(user):
            raise PermissionError("Solo el personal asignado puede confirmar su presencia")
        if assignment.status == "REPLACED":
            raise PermissionError("Tu asignación cambió. Este registro requiere revisión.")
        if op.status == "CLOSED":
            raise BusinessRuleError("La jornada está cerrada; ya no se aceptan nuevas confirmaciones de presencia")
        if data.client_generated_id and assignment.status == "CHECKED_IN" and assignment.checkin_client_generated_id == data.client_generated_id:
            return assignment
        assignment.status = "CHECKED_IN"
        assignment.checked_in_at = datetime.now(timezone.utc)
        assignment.checkin_latitude = data.latitude
        assignment.checkin_longitude = data.longitude
        assignment.checkin_client_generated_id = data.client_generated_id
        assignment.checkin_offline_created_at = data.offline_created_at
        self.audit.record("CHECK_IN_RECORDED", "SUCCESS", "Presencia confirmada en jornada", user_id=user.id, campaign_id=campaign_id, resource_type="ELECTION_DAY_ASSIGNMENT", resource_id=assignment.id)
        self.db.commit()
        return assignment

    def my_assignment(self, campaign_id, user):
        op = self._require_operation(campaign_id)
        self.access.require_read(campaign_id, user)
        return self.db.scalar(select(ElectionDayAssignment).where(ElectionDayAssignment.operation_id == op.id, ElectionDayAssignment.user_id == user.id, ElectionDayAssignment.status != "REPLACED").order_by(ElectionDayAssignment.created_at.desc()))

    # ---------- Incidents (§30-34, §51, §85) ----------
    def list_incidents(self, campaign_id, user, status=None):
        campaign = self.access.require_read(campaign_id, user)
        op = self._require_operation(campaign_id)
        q = select(ElectionDayIncident).where(ElectionDayIncident.operation_id == op.id, ElectionDayIncident.is_active.is_(True))
        if status:
            q = q.where(ElectionDayIncident.status == status)
        items = list(self.db.scalars(q.order_by(ElectionDayIncident.reported_at.desc())))
        allowed = self.access.allowed_parish_ids(campaign_id, user)
        if allowed is not None:
            place_ids = {p.id for p in self.db.scalars(select(PollingPlace).where(PollingPlace.canton_id == campaign.canton_id, PollingPlace.parish_id.in_(allowed)))} if allowed else set()
            items = [i for i in items if i.polling_place_id in place_ids]
        return items

    def create_incident(self, campaign_id, data, user):
        campaign = self.access.require_read(campaign_id, user)
        if not self.access.can_operate(user):
            raise PermissionError("Sin permisos para reportar incidencias")
        op = self._require_operation(campaign_id)
        if data.client_generated_id:
            existing = self.db.scalar(select(ElectionDayIncident).where(ElectionDayIncident.operation_id == op.id, ElectionDayIncident.reported_by_user_id == user.id, ElectionDayIncident.client_generated_id == data.client_generated_id))
            if existing:
                return existing
        if data.category not in INCIDENT_CATEGORIES:
            raise BusinessRuleError("Categoría de incidencia inválida")
        place = self._polling_place(campaign, op, data.polling_place_id)
        self.access.require_parish_scope(campaign_id, user, place.parish_id)
        if data.board_id:
            board = self.db.get(ElectoralBoard, data.board_id)
            if not board or board.polling_place_id != place.id:
                raise NotFoundError("Junta no encontrada")
        incident = ElectionDayIncident(operation_id=op.id, polling_place_id=place.id, board_id=data.board_id, reported_by_user_id=user.id, category=data.category, description=data.description, status="OPEN", client_generated_id=data.client_generated_id, offline_created_at=data.offline_created_at, is_active=True)
        self.db.add(incident)
        self.db.flush()
        self.audit.record("INCIDENT_REPORTED", "SUCCESS", "Incidencia de jornada reportada", user_id=user.id, campaign_id=campaign_id, resource_type="ELECTION_DAY_INCIDENT", resource_id=incident.id, metadata={"category": data.category})
        self.db.commit()
        return incident

    def resolve_incident(self, campaign_id, incident_id, data, user):
        campaign = self.access.require_read(campaign_id, user)
        if not self.access.can_operate(user):
            raise PermissionError("Sin permisos para actualizar incidencias")
        op = self._require_operation(campaign_id)
        incident = self.db.get(ElectionDayIncident, incident_id)
        if not incident or incident.operation_id != op.id or not incident.is_active:
            raise NotFoundError("Incidencia no encontrada")
        place = self.db.get(PollingPlace, incident.polling_place_id)
        self.access.require_parish_scope(campaign_id, user, place.parish_id)
        if data.status not in INCIDENT_STATUSES:
            raise BusinessRuleError("Estado de incidencia inválido")
        incident.status = data.status
        incident.resolution_notes = data.resolution_notes
        if data.status == "RESOLVED":
            incident.resolved_at = datetime.now(timezone.utc)
        self.audit.record("INCIDENT_RESOLVED" if data.status == "RESOLVED" else "INCIDENT_STATUS_CHANGED", "SUCCESS", "Estado de incidencia actualizado", user_id=user.id, campaign_id=campaign_id, resource_type="ELECTION_DAY_INCIDENT", resource_id=incident.id, metadata={"status": data.status})
        self.db.commit()
        return incident

    # ---------- Documents (§35-39, §82-84) ----------
    def list_documents(self, campaign_id, user, polling_place_id=None):
        campaign = self.access.require_read(campaign_id, user)
        op = self._require_operation(campaign_id)
        q = select(ElectionDayDocument).where(ElectionDayDocument.operation_id == op.id, ElectionDayDocument.is_active.is_(True))
        if polling_place_id:
            q = q.where(ElectionDayDocument.polling_place_id == polling_place_id)
        items = list(self.db.scalars(q.order_by(ElectionDayDocument.created_at.desc())))
        allowed = self.access.allowed_parish_ids(campaign_id, user)
        if allowed is not None:
            place_ids = {p.id for p in self.db.scalars(select(PollingPlace).where(PollingPlace.canton_id == campaign.canton_id, PollingPlace.parish_id.in_(allowed)))} if allowed else set()
            items = [d for d in items if d.polling_place_id in place_ids]
        return items

    def upload_document(self, campaign_id, user, *, polling_place_id, board_id, document_type, file_bytes, original_filename, client_generated_id):
        campaign = self.access.require_read(campaign_id, user)
        if not self.access.can_operate(user):
            raise PermissionError("Sin permisos para subir documentación")
        op = self._require_operation(campaign_id)
        if client_generated_id:
            existing = self.db.scalar(select(ElectionDayDocument).where(ElectionDayDocument.operation_id == op.id, ElectionDayDocument.uploaded_by_user_id == user.id, ElectionDayDocument.client_generated_id == client_generated_id))
            if existing:
                return existing
        if document_type not in DOCUMENT_TYPES:
            raise BusinessRuleError("Tipo de documento inválido")
        place = self._polling_place(campaign, op, polling_place_id)
        self.access.require_parish_scope(campaign_id, user, place.parish_id)
        if board_id:
            board = self.db.get(ElectoralBoard, board_id)
            if not board or board.polling_place_id != place.id:
                raise NotFoundError("Junta no encontrada")
        mime = sniff_evidence_mime(file_bytes[:16])
        if not mime:
            raise BusinessRuleError("Formato de archivo no permitido")
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
                raise BusinessRuleError("No fue posible guardar el archivo. Intenta nuevamente.") from e
        finally:
            tmp.unlink(missing_ok=True)
        doc = ElectionDayDocument(operation_id=op.id, polling_place_id=place.id, board_id=board_id, document_type=document_type, storage_key=key, mime_type=mime, size_bytes=size, sha256=digest, original_filename=safe_evidence_filename(original_filename or document_type, extension), uploaded_by_user_id=user.id, status="RECEIVED", client_generated_id=client_generated_id, is_active=True)
        self.db.add(doc)
        self.db.flush()
        self.audit.record("DOCUMENT_UPLOADED", "SUCCESS", "Documento de jornada cargado", user_id=user.id, campaign_id=campaign_id, resource_type="ELECTION_DAY_DOCUMENT", resource_id=doc.id, metadata={"document_type": document_type, "mime_type": mime, "size_bytes": size})
        self.db.commit()
        return doc

    def update_document_status(self, campaign_id, document_id, data, user):
        campaign = self.access.require_read(campaign_id, user)
        if not self.access.can_operate(user):
            raise PermissionError("Sin permisos para actualizar documentos")
        op = self._require_operation(campaign_id)
        doc = self.db.get(ElectionDayDocument, document_id)
        if not doc or doc.operation_id != op.id or not doc.is_active:
            raise NotFoundError("Documento no encontrado")
        place = self.db.get(PollingPlace, doc.polling_place_id)
        self.access.require_parish_scope(campaign_id, user, place.parish_id)
        if data.status not in {"RECEIVED", "REQUIRES_REVIEW", "VALIDATED"}:
            raise BusinessRuleError("Estado de documento inválido")
        doc.status = data.status
        self.db.commit()
        return doc

    def document_file(self, campaign_id, document_id, user):
        campaign = self.access.require_read(campaign_id, user)
        op = self._require_operation(campaign_id)
        doc = self.db.get(ElectionDayDocument, document_id)
        if not doc or doc.operation_id != op.id or not doc.is_active or not doc.storage_key:
            raise NotFoundError("Documento no encontrado")
        place = self.db.get(PollingPlace, doc.polling_place_id)
        self.access.require_parish_scope(campaign_id, user, place.parish_id)
        return self.storage.resolve(doc.storage_key), doc
