import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.models.assignments import CampaignUser
from app.models.campaign import Campaign
from app.models.election_day import ElectionDayAssignment, ElectionDayDocument, ElectionDayIncident, ElectionDayOperation, ElectoralBoard, PollingPlace
from app.models.historical import ElectoralContest, ElectoralProcess
from app.models.user import User
from app.services.artifact_storage import S3ArtifactStorage
from app.services.artifact_storage_factory import build_evidence_storage
from app.services.dataset_version_service import DatasetVersionService
from app.services.election_day_access_service import ElectionDayAccessService
from app.services.evidence_security_service import EVIDENCE_EXTENSION_BY_MIME, safe_evidence_filename, sniff_evidence_mime
from app.services.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.services.security_audit_service import SecurityAuditService

logger = logging.getLogger("territorio.storage")

ASSIGNMENT_ROLES = {"POLLING_PLACE_DELEGATE", "ACT_VALIDATOR"}
INCIDENT_CATEGORIES = {"PERSONNEL", "ACCESS", "LOGISTICS", "DOCUMENTATION", "CONNECTIVITY", "OTHER"}
DOCUMENT_TYPES = {"ACTA_COPY", "INCIDENT_DOCUMENT", "OTHER"}
INCIDENT_STATUSES = {"OPEN", "IN_REVIEW", "RESOLVED"}
STATUS_LABELS = {"PREPARATION": "Preparación", "ACTIVE": "Jornada activa", "SCRUTINY": "Escrutinio", "CLOSED": "Jornada cerrada"}


class ElectionDayService:
    """Centro operativo del día de la elección. Nunca un sistema de resultados
    (§2): no existe ningún campo de votos/ganador/porcentaje aquí — solo
    cobertura, presencia, incidencias y documentación operativa.

    Ciclo de vida: PREPARATION -> ACTIVE -> SCRUTINY -> CLOSED, sin saltos ni
    retrocesos. CANDIDATE/CAMPAIGN_MANAGER son los únicos propietarios
    operativos (§5); ADMIN nunca administra por privilegio implícito — solo
    consulta en modo soporte explícito (ElectionDayAdminSupportService)."""

    def __init__(self, db, storage=None):
        self.db = db
        self.access = ElectionDayAccessService(db)
        self.audit = SecurityAuditService(db)
        self.storage = storage or build_evidence_storage()

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

    # ---------- Operation lifecycle ----------
    def get_operation(self, campaign_id, user):
        self.access.require_any_access(campaign_id, user)
        return self._require_operation(campaign_id)

    def create_operation(self, campaign_id, data, user):
        campaign = self.access.require_executive(campaign_id, user)
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

    def preflight(self, campaign_id, user):
        campaign = self.access.require_control_center_access(campaign_id, user)
        op = self._require_operation(campaign_id)
        blockers: list[str] = []
        warnings: list[str] = []

        contest_count = self.db.scalar(select(func.count()).select_from(ElectoralContest).where(ElectoralContest.electoral_process_id == op.electoral_process_id, ElectoralContest.canton_id == campaign.canton_id, ElectoralContest.office_type == campaign.office_type)) or 0
        if not contest_count:
            blockers.append("No existe una contienda electoral oficial para el cantón y el cargo de esta campaña en el proceso configurado.")

        places = list(self.db.scalars(select(PollingPlace).where(PollingPlace.electoral_process_id == op.electoral_process_id, PollingPlace.canton_id == campaign.canton_id, PollingPlace.is_active.is_(True))))
        if not places:
            blockers.append("No existen recintos electorales oficiales activos para este proceso y cantón.")
        place_ids = [p.id for p in places]

        boards = list(self.db.scalars(select(ElectoralBoard).where(ElectoralBoard.polling_place_id.in_(place_ids), ElectoralBoard.is_active.is_(True)))) if place_ids else []
        if place_ids and not boards:
            blockers.append("No existen juntas receptoras del voto oficiales activas para los recintos de este proceso.")

        active_assignments = list(self.db.scalars(select(ElectionDayAssignment).where(ElectionDayAssignment.operation_id == op.id, ElectionDayAssignment.status != "REPLACED")))
        delegate_assignments = [a for a in active_assignments if a.assignment_role == "POLLING_PLACE_DELEGATE"]
        validator_assignments = [a for a in active_assignments if a.assignment_role == "ACT_VALIDATOR"]
        if not delegate_assignments:
            blockers.append("No existe ningún delegado de recinto asignado.")
        if not validator_assignments:
            blockers.append("No existe ningún validador de actas asignado.")

        covered_place_ids = {a.polling_place_id for a in delegate_assignments}
        uncovered = [p for p in places if p.id not in covered_place_ids]
        if uncovered:
            warnings.append(f"Existen {len(uncovered)} recintos sin delegado asignado.")

        dvs = DatasetVersionService(self.db)
        stale_sources = {p.data_source_id for p in places if p.data_source_id} - {p.data_source_id for p in places if p.data_source_id and dvs.active_for(p.data_source_id, "CNE_POLLING_PLACES")}
        if stale_sources:
            warnings.append("Algunos recintos no corresponden a una versión activa del conjunto de datos de recintos.")

        summary = {
            "polling_places": len(places),
            "boards": len(boards),
            "delegates": len({a.user_id for a in delegate_assignments}),
            "validators": len({a.user_id for a in validator_assignments}),
            "uncovered_polling_places": len(uncovered),
        }
        return {"ready": not blockers, "blockers": blockers, "warnings": warnings, "summary": summary}

    def open_operation(self, campaign_id, user):
        self.access.require_executive(campaign_id, user)
        op = self._require_operation(campaign_id)
        if op.status == "ACTIVE":
            return op
        if op.status != "PREPARATION":
            raise BusinessRuleError("Solo una jornada en preparación puede activarse")
        result = self.preflight(campaign_id, user)
        if not result["ready"]:
            raise BusinessRuleError("No se puede activar la jornada: " + " ".join(result["blockers"]))
        op.status = "ACTIVE"
        op.opened_at = datetime.now(timezone.utc)
        op.opened_by_user_id = user.id
        self.audit.record("ELECTION_DAY_OPENED", "SUCCESS", "Jornada electoral activada", user_id=user.id, campaign_id=campaign_id, resource_type="ELECTION_DAY_OPERATION", resource_id=op.id)
        self.db.commit()
        return op

    def start_scrutiny(self, campaign_id, user):
        self.access.require_executive(campaign_id, user)
        op = self._require_operation(campaign_id)
        if op.status == "SCRUTINY":
            return op
        if op.status != "ACTIVE":
            raise BusinessRuleError("Solo una jornada activa puede pasar a escrutinio")
        op.status = "SCRUTINY"
        op.scrutiny_started_at = datetime.now(timezone.utc)
        op.scrutiny_started_by_user_id = user.id
        self.audit.record("ELECTION_DAY_SCRUTINY_STARTED", "SUCCESS", "Escrutinio de jornada iniciado", user_id=user.id, campaign_id=campaign_id, resource_type="ELECTION_DAY_OPERATION", resource_id=op.id)
        self.db.commit()
        return op

    def closure_preview(self, campaign_id, user):
        self.access.require_control_center_access(campaign_id, user)
        op = self._require_operation(campaign_id)
        return op, self._coverage(campaign_id, op)

    def close_operation(self, campaign_id, data, user):
        self.access.require_executive(campaign_id, user)
        op = self._require_operation(campaign_id)
        if op.status != "SCRUTINY":
            raise BusinessRuleError("Solo una jornada en escrutinio puede cerrarse")
        open_incidents = self.db.scalar(select(func.count()).select_from(ElectionDayIncident).where(ElectionDayIncident.operation_id == op.id, ElectionDayIncident.status != "RESOLVED", ElectionDayIncident.is_active.is_(True))) or 0
        # §55: advertir, no bloquear por defecto — las incidencias y documentos
        # pendientes pueden resolverse/recibirse administrativamente después
        # del cierre, auditados con su fecha real.
        op.status = "CLOSED"
        op.closed_at = datetime.now(timezone.utc)
        op.closed_by_user_id = user.id
        if data.notes:
            op.notes = (op.notes + "\n" if op.notes else "") + data.notes
        self.audit.record("ELECTION_DAY_CLOSED", "SUCCESS", "Jornada electoral cerrada", user_id=user.id, campaign_id=campaign_id, resource_type="ELECTION_DAY_OPERATION", resource_id=op.id, metadata={"open_incidents_at_close": open_incidents})
        self.db.commit()
        return op

    def control_center(self, campaign_id, user):
        self.access.require_control_center_access(campaign_id, user)
        op = self._require_operation(campaign_id)
        return op, self._coverage(campaign_id, op)

    def validation_status(self, campaign_id, user):
        self.access.require_validator_assignment(campaign_id, user)
        op = self._require_operation(campaign_id)
        # No existe todavía un modelo de actas (Fase 2): la cola siempre está
        # vacía, pero la ruta y la autorización ya quedan protegidas.
        return {"operation_status": op.status, "pending_reviews": 0}

    # ---------- Polling places / boards (solo lectura — datos oficiales del Data Hub) ----------
    def list_polling_places(self, campaign_id, user):
        campaign = self.access.require_any_access(campaign_id, user)
        op = self._require_operation(campaign_id)
        q = select(PollingPlace).where(PollingPlace.electoral_process_id == op.electoral_process_id, PollingPlace.canton_id == campaign.canton_id)
        items = list(self.db.scalars(q.order_by(PollingPlace.name)))
        if not self._has_control_center_access(campaign_id, user):
            allowed = self.access.allowed_polling_place_ids(campaign_id, user)
            items = [p for p in items if p.id in allowed]
        return items

    def _has_control_center_access(self, campaign_id, user):
        try:
            self.access.require_control_center_access(campaign_id, user)
            return True
        except PermissionError:
            return False

    def list_boards(self, campaign_id, user, polling_place_id):
        campaign = self.access.require_polling_place_access(campaign_id, user, polling_place_id)
        op = self._require_operation(campaign_id)
        place = self._polling_place(campaign, op, polling_place_id)
        return list(self.db.scalars(select(ElectoralBoard).where(ElectoralBoard.polling_place_id == place.id).order_by(ElectoralBoard.board_number)))

    def polling_place_detail(self, campaign_id, polling_place_id, user):
        campaign = self.access.require_polling_place_access(campaign_id, user, polling_place_id)
        op = self._require_operation(campaign_id)
        return self._polling_place(campaign, op, polling_place_id)

    # ---------- Coverage matrix ----------
    def _coverage(self, campaign_id, op):
        campaign = self._campaign(campaign_id)
        places = list(self.db.scalars(select(PollingPlace).where(PollingPlace.electoral_process_id == op.electoral_process_id, PollingPlace.canton_id == campaign.canton_id, PollingPlace.is_active.is_(True))))
        place_ids = [p.id for p in places]
        boards = list(self.db.scalars(select(ElectoralBoard).where(ElectoralBoard.polling_place_id.in_(place_ids), ElectoralBoard.is_active.is_(True)))) if place_ids else []
        assignments = list(self.db.scalars(select(ElectionDayAssignment).where(ElectionDayAssignment.operation_id == op.id, ElectionDayAssignment.status != "REPLACED")))
        delegate_assignments = [a for a in assignments if a.assignment_role == "POLLING_PLACE_DELEGATE"]
        covered_places = {a.polling_place_id for a in delegate_assignments} & set(place_ids)
        # Un delegado cubre TODO su recinto (§12): sus juntas se consideran
        # cubiertas en conjunto, no una por una.
        covered_boards = {b.id for b in boards if b.polling_place_id in covered_places}
        confirmed = sum(1 for a in assignments if a.status in {"CONFIRMED", "CHECKED_IN"})
        checked_in = sum(1 for a in assignments if a.status == "CHECKED_IN")
        open_incidents = self.db.scalar(select(func.count()).select_from(ElectionDayIncident).where(ElectionDayIncident.operation_id == op.id, ElectionDayIncident.status != "RESOLVED", ElectionDayIncident.is_active.is_(True))) or 0
        documents_received = self.db.scalar(select(func.count()).select_from(ElectionDayDocument).where(ElectionDayDocument.operation_id == op.id, ElectionDayDocument.is_active.is_(True))) or 0
        return {
            "total_polling_places": len(places), "covered_polling_places": len(covered_places),
            "total_boards": len(boards), "covered_boards": len(covered_boards),
            "personnel_confirmed": confirmed, "personnel_checked_in": checked_in,
            "open_incidents": open_incidents,
            "documents_received": documents_received, "expected_documents": len(boards),
        }

    def coverage(self, campaign_id, user):
        self.access.require_control_center_access(campaign_id, user)
        op = self._require_operation(campaign_id)
        return self._coverage(campaign_id, op)

    # ---------- Assignments (personal operativo: delegado de recinto / validador de actas) ----------
    def list_assignments(self, campaign_id, user, polling_place_id=None):
        self.access.require_control_center_access(campaign_id, user)
        op = self._require_operation(campaign_id)
        q = select(ElectionDayAssignment).where(ElectionDayAssignment.operation_id == op.id)
        if polling_place_id:
            q = q.where(ElectionDayAssignment.polling_place_id == polling_place_id)
        return list(self.db.scalars(q.order_by(ElectionDayAssignment.created_at.desc())))

    def my_assignments(self, campaign_id, user):
        self.access.require_membership(campaign_id, user)
        op = self._operation_or_none(campaign_id)
        if not op:
            return []
        return list(self.db.scalars(
            select(ElectionDayAssignment)
            .where(ElectionDayAssignment.operation_id == op.id, ElectionDayAssignment.user_id == user.id, ElectionDayAssignment.status != "REPLACED")
            .order_by(ElectionDayAssignment.created_at.desc())
        ))

    def my_assignment(self, campaign_id, user):
        """Legacy — devuelve una sola asignación (§8). Conservada solo por
        compatibilidad; el frontend nuevo usa my_assignments (plural)."""
        items = self.my_assignments(campaign_id, user)
        return items[0] if items else None

    def _validate_assignment_shape(self, data):
        if data.assignment_role not in ASSIGNMENT_ROLES:
            raise BusinessRuleError("Rol de asignación inválido")
        if data.assignment_role == "POLLING_PLACE_DELEGATE" and not data.polling_place_id:
            raise BusinessRuleError("El delegado de recinto requiere un recinto")
        if data.assignment_role == "ACT_VALIDATOR" and data.polling_place_id:
            raise BusinessRuleError("El validador de actas no se asigna a un recinto")

    def _require_campaign_member(self, campaign_id, user_id):
        if not self.db.get(User, user_id):
            raise NotFoundError("Usuario no encontrado")
        if not self.db.scalar(select(CampaignUser).where(CampaignUser.campaign_id == campaign_id, CampaignUser.user_id == user_id, CampaignUser.is_active.is_(True))):
            raise BusinessRuleError("El usuario no pertenece a esta campaña")

    def create_assignment(self, campaign_id, data, user):
        campaign = self.access.require_executive(campaign_id, user)
        op = self._require_operation(campaign_id)
        if op.status == "CLOSED":
            raise BusinessRuleError("La jornada está cerrada")
        self._validate_assignment_shape(data)
        self._require_campaign_member(campaign_id, data.user_id)
        place = None
        if data.polling_place_id:
            place = self._polling_place(campaign, op, data.polling_place_id)
        if data.assignment_role == "POLLING_PLACE_DELEGATE":
            if self.db.scalar(select(ElectionDayAssignment).where(ElectionDayAssignment.operation_id == op.id, ElectionDayAssignment.user_id == data.user_id, ElectionDayAssignment.polling_place_id == place.id, ElectionDayAssignment.status != "REPLACED")):
                raise ConflictError("Esta persona ya está asignada como delegado de ese recinto")
        else:
            if self.db.scalar(select(ElectionDayAssignment).where(ElectionDayAssignment.operation_id == op.id, ElectionDayAssignment.user_id == data.user_id, ElectionDayAssignment.assignment_role == "ACT_VALIDATOR", ElectionDayAssignment.status != "REPLACED")):
                raise ConflictError("Esta persona ya tiene una asignación de validador activa en esta jornada")
        assignment = ElectionDayAssignment(operation_id=op.id, user_id=data.user_id, polling_place_id=place.id if place else None, assignment_role=data.assignment_role, status="ASSIGNED", assigned_by_user_id=user.id)
        self.db.add(assignment)
        self.db.flush()
        self.audit.record("ASSIGNMENT_CREATED", "SUCCESS", "Asignación de jornada creada", user_id=user.id, campaign_id=campaign_id, resource_type="ELECTION_DAY_ASSIGNMENT", resource_id=assignment.id, metadata={"assignment_role": data.assignment_role})
        self.db.commit()
        return assignment

    def eligible_users(self, campaign_id, user):
        self.access.require_executive(campaign_id, user)
        rows = self.db.execute(select(User).join(CampaignUser, CampaignUser.user_id == User.id).where(CampaignUser.campaign_id == campaign_id, CampaignUser.is_active.is_(True)).order_by(User.first_name, User.last_name))
        return [r[0] for r in rows]

    def replace_assignment(self, campaign_id, assignment_id, data, user):
        self.access.require_executive(campaign_id, user)
        op = self._require_operation(campaign_id)
        old = self.db.get(ElectionDayAssignment, assignment_id)
        if not old or old.operation_id != op.id:
            raise NotFoundError("Asignación no encontrada")
        if old.status in {"REPLACED", "COMPLETED"}:
            raise BusinessRuleError("La asignación ya no está activa")
        if data.user_id == old.user_id:
            raise BusinessRuleError("El nuevo usuario debe ser distinto de la persona reemplazada")
        self._require_campaign_member(campaign_id, data.user_id)
        if old.assignment_role == "POLLING_PLACE_DELEGATE":
            if self.db.scalar(select(ElectionDayAssignment).where(ElectionDayAssignment.operation_id == op.id, ElectionDayAssignment.user_id == data.user_id, ElectionDayAssignment.polling_place_id == old.polling_place_id, ElectionDayAssignment.status != "REPLACED")):
                raise ConflictError("Esta persona ya está asignada como delegado de ese recinto")
        else:
            if self.db.scalar(select(ElectionDayAssignment).where(ElectionDayAssignment.operation_id == op.id, ElectionDayAssignment.user_id == data.user_id, ElectionDayAssignment.assignment_role == "ACT_VALIDATOR", ElectionDayAssignment.status != "REPLACED")):
                raise ConflictError("Esta persona ya tiene una asignación de validador activa en esta jornada")
        new = ElectionDayAssignment(operation_id=op.id, user_id=data.user_id, polling_place_id=old.polling_place_id, assignment_role=old.assignment_role, status="ASSIGNED", assigned_by_user_id=user.id)
        self.db.add(new)
        self.db.flush()
        old.status = "REPLACED"
        old.replaced_by_assignment_id = new.id
        self.audit.record("ASSIGNMENT_REPLACED", "SUCCESS", "Asignación de jornada reemplazada", user_id=user.id, campaign_id=campaign_id, resource_type="ELECTION_DAY_ASSIGNMENT", resource_id=old.id, metadata={"reason": data.reason, "new_assignment_id": str(new.id)})
        self.db.commit()
        return new

    # ---------- Check-in ----------
    def check_in(self, campaign_id, assignment_id, data, user):
        self.access.require_membership(campaign_id, user)
        op = self._require_operation(campaign_id)
        assignment = self.db.get(ElectionDayAssignment, assignment_id)
        if not assignment or assignment.operation_id != op.id:
            raise NotFoundError("Asignación no encontrada")
        if assignment.assignment_role != "POLLING_PLACE_DELEGATE":
            raise BusinessRuleError("Solo el delegado de recinto confirma presencia")
        if assignment.user_id != user.id:
            raise PermissionError("Solo el personal asignado puede confirmar su presencia")
        if assignment.status == "REPLACED":
            raise PermissionError("Tu asignación cambió. Este registro requiere revisión.")
        if data.client_generated_id and assignment.status == "CHECKED_IN" and assignment.checkin_client_generated_id == data.client_generated_id:
            return assignment
        if op.status != "ACTIVE":
            raise BusinessRuleError("El check-in solo se acepta mientras la jornada está activa")
        assignment.status = "CHECKED_IN"
        assignment.checked_in_at = datetime.now(timezone.utc)
        assignment.checkin_latitude = data.latitude
        assignment.checkin_longitude = data.longitude
        assignment.checkin_client_generated_id = data.client_generated_id
        assignment.checkin_offline_created_at = data.offline_created_at
        self.audit.record("CHECK_IN_RECORDED", "SUCCESS", "Presencia confirmada en jornada", user_id=user.id, campaign_id=campaign_id, resource_type="ELECTION_DAY_ASSIGNMENT", resource_id=assignment.id)
        self.db.commit()
        return assignment

    # ---------- Incidents ----------
    def list_incidents(self, campaign_id, user, status=None):
        self.access.require_any_access(campaign_id, user)
        op = self._require_operation(campaign_id)
        q = select(ElectionDayIncident).where(ElectionDayIncident.operation_id == op.id, ElectionDayIncident.is_active.is_(True))
        if status:
            q = q.where(ElectionDayIncident.status == status)
        items = list(self.db.scalars(q.order_by(ElectionDayIncident.reported_at.desc())))
        if not self._has_control_center_access(campaign_id, user):
            allowed = self.access.allowed_polling_place_ids(campaign_id, user)
            items = [i for i in items if i.polling_place_id in allowed]
        return items

    def create_incident(self, campaign_id, data, user):
        campaign = self.access.require_delegate_assignment(campaign_id, user, polling_place_id=data.polling_place_id)
        op = self._require_operation(campaign_id)
        if data.client_generated_id:
            existing = self.db.scalar(select(ElectionDayIncident).where(ElectionDayIncident.operation_id == op.id, ElectionDayIncident.reported_by_user_id == user.id, ElectionDayIncident.client_generated_id == data.client_generated_id))
            if existing:
                return existing
        if op.status != "ACTIVE":
            raise BusinessRuleError("Solo se pueden reportar incidencias mientras la jornada está activa")
        if data.category not in INCIDENT_CATEGORIES:
            raise BusinessRuleError("Categoría de incidencia inválida")
        place = self._polling_place(campaign, op, data.polling_place_id)
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
        self.access.require_incident_resolution_access(campaign_id, user)
        op = self._require_operation(campaign_id)
        if op.status == "CLOSED":
            raise BusinessRuleError("La jornada está cerrada; las incidencias quedan en solo lectura")
        incident = self.db.get(ElectionDayIncident, incident_id)
        if not incident or incident.operation_id != op.id or not incident.is_active:
            raise NotFoundError("Incidencia no encontrada")
        if data.status not in INCIDENT_STATUSES:
            raise BusinessRuleError("Estado de incidencia inválido")
        incident.status = data.status
        incident.resolution_notes = data.resolution_notes
        if data.status == "RESOLVED":
            incident.resolved_at = datetime.now(timezone.utc)
        self.audit.record("INCIDENT_RESOLVED" if data.status == "RESOLVED" else "INCIDENT_STATUS_CHANGED", "SUCCESS", "Estado de incidencia actualizado", user_id=user.id, campaign_id=campaign_id, resource_type="ELECTION_DAY_INCIDENT", resource_id=incident.id, metadata={"status": data.status})
        self.db.commit()
        return incident

    # ---------- Documents ----------
    def list_documents(self, campaign_id, user, polling_place_id=None):
        self.access.require_any_access(campaign_id, user)
        op = self._require_operation(campaign_id)
        q = select(ElectionDayDocument).where(ElectionDayDocument.operation_id == op.id, ElectionDayDocument.is_active.is_(True))
        if polling_place_id:
            q = q.where(ElectionDayDocument.polling_place_id == polling_place_id)
        items = list(self.db.scalars(q.order_by(ElectionDayDocument.created_at.desc())))
        if not self._has_control_center_access(campaign_id, user):
            allowed = self.access.allowed_polling_place_ids(campaign_id, user)
            items = [d for d in items if d.polling_place_id in allowed]
        return items

    def upload_document(self, campaign_id, user, *, polling_place_id, board_id, document_type, file_bytes, original_filename, client_generated_id):
        campaign = self.access.require_delegate_assignment(campaign_id, user, polling_place_id=polling_place_id)
        op = self._require_operation(campaign_id)
        if client_generated_id:
            existing = self.db.scalar(select(ElectionDayDocument).where(ElectionDayDocument.operation_id == op.id, ElectionDayDocument.uploaded_by_user_id == user.id, ElectionDayDocument.client_generated_id == client_generated_id))
            if existing:
                return existing
        if op.status != "ACTIVE":
            raise BusinessRuleError("Solo se puede adjuntar documentación mientras la jornada está activa")
        if document_type not in DOCUMENT_TYPES:
            raise BusinessRuleError("Tipo de documento inválido")
        place = self._polling_place(campaign, op, polling_place_id)
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
        self.access.require_executive(campaign_id, user)
        op = self._require_operation(campaign_id)
        doc = self.db.get(ElectionDayDocument, document_id)
        if not doc or doc.operation_id != op.id or not doc.is_active:
            raise NotFoundError("Documento no encontrado")
        if data.status not in {"RECEIVED", "REQUIRES_REVIEW", "VALIDATED"}:
            raise BusinessRuleError("Estado de documento inválido")
        doc.status = data.status
        self.db.commit()
        return doc

    def document_file(self, campaign_id, document_id, user):
        op = self._require_operation(campaign_id)
        doc = self.db.get(ElectionDayDocument, document_id)
        if not doc or doc.operation_id != op.id or not doc.is_active or not doc.storage_key:
            raise NotFoundError("Documento no encontrado")
        self.access.require_polling_place_access(campaign_id, user, doc.polling_place_id)
        download = self.storage.download(doc.storage_key, filename=doc.original_filename, content_type=doc.mime_type)
        logger.info(
            "ARTIFACT_DOWNLOAD_AUTHORIZED",
            extra={"provider": "s3" if isinstance(self.storage, S3ArtifactStorage) else "local", "operation_id": str(op.id)},
        )
        return download, doc
