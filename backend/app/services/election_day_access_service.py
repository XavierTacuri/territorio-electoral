from sqlalchemy import select

from app.models.election_day import ElectionDayAdminSupportSession, ElectionDayAssignment, ElectionDayOperation
from app.services.campaign_access_service import CampaignAccessService
from app.services.campaign_permissions import CAMPAIGN_EXECUTIVE_ROLES


class ElectionDayAccessService:
    """Modelo de autorización de Jornada Electoral (§7/§17). Nada aquí confía
    en el frontend: cada guarda re-verifica server-side.

    Reglas centrales:
    - CANDIDATE/CAMPAIGN_MANAGER son los únicos propietarios operativos
      (require_executive). El privilegio global de ADMIN nunca sustituye esto.
    - ADMIN solo entra al Centro de Control con una ElectionDayAdminSupportSession
      activa para esa campaña (require_control_center_access/require_admin_support).
    - Un usuario opera Jornada Electoral porque tiene una ElectionDayAssignment
      activa (require_delegate_assignment/require_validator_assignment), nunca
      porque sea TERRITORIAL_COORDINATOR — ese rol, y ANALYST, no tienen ningún
      acceso a este módulo.
    """

    def __init__(self, db):
        self.db = db
        self.access = CampaignAccessService(db)

    # ---------- Base campaign membership/suspension checks ----------
    def _campaign(self, campaign_id, user):
        # Reusa las comprobaciones de existencia/suspensión/suscripción de
        # CampaignAccessService. Para ADMIN esto pasa por su bypass general de
        # "cualquier campaña", lo cual es intencional: el bypass solo abre la
        # puerta a la comprobación específica de este módulo más abajo, nunca
        # concede acceso operativo por sí mismo.
        return self.access.require_access(campaign_id, user)

    def _campaign_open(self, campaign_id, user):
        # Fase 1B §18: variante sin CampaignUser/OrganizationMembership,
        # usada únicamente por las comprobaciones cuyo verdadero portón de
        # autorización es la posesión de una ElectionDayAssignment (no la
        # membresía general de campaña) — nunca por las rutas ejecutivo/
        # admin-support, que deben seguir exigiendo membresía vía _campaign.
        return self.access.require_campaign_open(campaign_id, user)

    @staticmethod
    def _codes(user):
        return {r.code for r in user.roles}

    @staticmethod
    def is_admin(user) -> bool:
        return bool(user.is_superuser or "ADMIN" in {r.code for r in user.roles})

    def _operation_or_none(self, campaign_id):
        return self.db.scalar(
            select(ElectionDayOperation)
            .where(ElectionDayOperation.campaign_id == campaign_id)
            .order_by(ElectionDayOperation.created_at.desc())
        )

    # ---------- Executive (owner) access ----------
    def is_executive(self, user) -> bool:
        return bool(CAMPAIGN_EXECUTIVE_ROLES & self._codes(user))

    def require_executive(self, campaign_id, user):
        campaign = self._campaign(campaign_id, user)
        if not self.is_executive(user):
            raise PermissionError("Solo Candidato o Jefe de Campaña puede administrar la Jornada Electoral")
        return campaign

    # ---------- Admin support mode ----------
    def has_active_support(self, campaign_id, user) -> bool:
        if not self.is_admin(user):
            return False
        return bool(
            self.db.scalar(
                select(ElectionDayAdminSupportSession).where(
                    ElectionDayAdminSupportSession.admin_user_id == user.id,
                    ElectionDayAdminSupportSession.campaign_id == campaign_id,
                    ElectionDayAdminSupportSession.ended_at.is_(None),
                )
            )
        )

    def require_admin_support(self, campaign_id, user):
        campaign = self._campaign(campaign_id, user)
        if not self.is_admin(user):
            raise PermissionError("Solo un ADMIN puede iniciar el modo soporte")
        return campaign

    # ---------- Control Center (executive-equivalent) access ----------
    def require_control_center_access(self, campaign_id, user):
        campaign = self._campaign(campaign_id, user)
        if self.is_executive(user):
            return campaign
        if self.is_admin(user) and self.has_active_support(campaign_id, user):
            return campaign
        raise PermissionError("Sin acceso al Centro de Control de la Jornada Electoral")

    # ---------- Delegate / validator operational access ----------
    def _operation_for_assignments(self, campaign_id):
        op = self._operation_or_none(campaign_id)
        return op

    def active_delegate_assignments(self, campaign_id, user):
        op = self._operation_for_assignments(campaign_id)
        if not op:
            return []
        return list(
            self.db.scalars(
                select(ElectionDayAssignment).where(
                    ElectionDayAssignment.operation_id == op.id,
                    ElectionDayAssignment.user_id == user.id,
                    ElectionDayAssignment.assignment_role == "POLLING_PLACE_DELEGATE",
                    ElectionDayAssignment.status != "REPLACED",
                )
            )
        )

    def active_validator_assignment(self, campaign_id, user):
        op = self._operation_for_assignments(campaign_id)
        if not op:
            return None
        return self.db.scalar(
            select(ElectionDayAssignment).where(
                ElectionDayAssignment.operation_id == op.id,
                ElectionDayAssignment.user_id == user.id,
                ElectionDayAssignment.assignment_role == "ACT_VALIDATOR",
                ElectionDayAssignment.status != "REPLACED",
            )
        )

    def allowed_polling_place_ids(self, campaign_id, user) -> set:
        return {a.polling_place_id for a in self.active_delegate_assignments(campaign_id, user)}

    def require_delegate_assignment(self, campaign_id, user, polling_place_id=None):
        # Fase 1B §18: la ElectionDayAssignment es el portón real — un
        # Delegado invitado sin CampaignUser debe poder operar su(s)
        # recinto(s), por eso la existencia de campaña usa la variante abierta.
        campaign = self._campaign_open(campaign_id, user)
        assignments = self.active_delegate_assignments(campaign_id, user)
        if not assignments:
            raise PermissionError("No tienes una asignación de delegado de recinto en esta jornada")
        if polling_place_id is not None and polling_place_id not in {a.polling_place_id for a in assignments}:
            raise PermissionError("Ese recinto no está entre tus asignaciones")
        return campaign

    def require_validator_assignment(self, campaign_id, user):
        campaign = self._campaign_open(campaign_id, user)
        if not self.active_validator_assignment(campaign_id, user):
            raise PermissionError("No tienes una asignación de validador de actas en esta jornada")
        return campaign

    def require_polling_place_access(self, campaign_id, user, polling_place_id):
        """Acceso de lectura a un recinto: el Centro de Control ve cualquier
        recinto de la campaña; un delegado solo ve el/los suyo(s)."""
        # Las rutas ejecutivo/admin-support siguen exigiendo membresía real
        # (is_executive/is_admin son comprobaciones de rol GLOBALES, no
        # ligadas a esta campaña — _campaign, no _campaign_open, es lo que
        # las ata a esta campaña concreta).
        if self.is_executive(user) or self.is_admin(user):
            campaign = self._campaign(campaign_id, user)
            if self.is_executive(user):
                return campaign
            if self.has_active_support(campaign_id, user):
                return campaign
        campaign = self._campaign_open(campaign_id, user)
        if polling_place_id in self.allowed_polling_place_ids(campaign_id, user):
            return campaign
        raise PermissionError("Recinto fuera de tu alcance")

    # ---------- Actas electorales (Fase 2) ----------
    def require_act_reviewer(self, campaign_id, user):
        """Quién puede validar/observar actas (§14): un ACT_VALIDATOR
        asignado a esta operación, o un ADMIN con soporte activo para esta
        campaña — nunca Candidate/Manager (supervisan, no validan) ni un
        ADMIN sin soporte. Devuelve (campaign, review_source) para que el
        llamador etiquete correctamente el ElectionActReview resultante."""
        if self.is_admin(user):
            campaign = self._campaign(campaign_id, user)
            if self.has_active_support(campaign_id, user):
                return campaign, "ADMIN_SUPPORT"
            raise PermissionError("Solo un ADMIN con soporte activo puede revisar actas")
        campaign = self._campaign_open(campaign_id, user)
        if self.active_validator_assignment(campaign_id, user):
            return campaign, "CAMPAIGN_VALIDATOR"
        raise PermissionError("No tienes una asignación de validador de actas en esta jornada")

    def require_act_viewer(self, campaign_id, user, polling_place_id):
        """Lectura de un acta/evidencia (§25/§29): además de quien ya ve el
        recinto (ejecutivo, admin-support, delegado del propio recinto), un
        ACT_VALIDATOR ve cualquier acta de SU operación — su trabajo es
        revisar actas de toda la jornada, no de un solo recinto."""
        if self.is_executive(user) or (self.is_admin(user) and self.has_active_support(campaign_id, user)):
            return self._campaign(campaign_id, user)
        campaign = self._campaign_open(campaign_id, user)
        if self.active_validator_assignment(campaign_id, user):
            return campaign
        if polling_place_id in self.allowed_polling_place_ids(campaign_id, user):
            return campaign
        raise PermissionError("Sin acceso a esta acta")

    # ---------- Generic helpers ----------
    def require_membership(self, campaign_id, user):
        """Solo la comprobación base de campaña (existe, organización activa).
        Usada por operaciones intrínsecamente autolimitadas al propio usuario
        (mis asignaciones, mi check-in) — por eso no exige CampaignUser
        (§18): la propia fila de ElectionDayAssignment, filtrada por
        user_id, es la que decide qué ve o puede hacer cada quien."""
        return self._campaign_open(campaign_id, user)

    def require_any_access(self, campaign_id, user):
        """Cualquier motivo legítimo para saber que la jornada existe y su
        estado: Centro de Control, o una asignación propia (delegado o
        validador) — incluyendo personal sin CampaignUser (§18). Usado por
        lecturas no sensibles (p. ej. GET /operation) que tanto el equipo
        ejecutivo como el personal de campo consultan."""
        try:
            return self.require_control_center_access(campaign_id, user)
        except PermissionError:
            pass
        campaign = self._campaign_open(campaign_id, user)
        if self.active_delegate_assignments(campaign_id, user) or self.active_validator_assignment(campaign_id, user):
            return campaign
        raise PermissionError("Sin acceso a la Jornada Electoral")

    def resolve_election_day_context(self, campaign_id, user):
        """Fase 1B §18: punto de entrada único para resolver si un usuario
        tiene motivo legítimo de acceso a esta Jornada Electoral — ejecutivo,
        ADMIN en soporte activo, o personal operativo con ElectionDayAssignment
        válida — sin exigir CampaignUser para el caso de personal operativo.
        Ese acceso resuelto solo sirve para las rutas de Jornada Electoral:
        nunca se reutiliza para autorizar otras APIs de Campaign."""
        return self.require_any_access(campaign_id, user)

    def require_incident_resolution_access(self, campaign_id, user):
        """Resolver una incidencia: equipo ejecutivo, o ADMIN en modo soporte
        activo (§9) — nunca el delegado que la reportó (§9)."""
        if self.is_executive(user):
            return self.require_executive(campaign_id, user)
        campaign = self._campaign(campaign_id, user)
        if self.is_admin(user) and self.has_active_support(campaign_id, user):
            return campaign
        raise PermissionError("Sin permisos para resolver incidencias de la jornada")
