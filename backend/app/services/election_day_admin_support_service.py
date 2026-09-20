from datetime import datetime, timezone

from sqlalchemy import case, func, select

from app.models.campaign import Campaign
from app.models.election_day import ElectionDayAdminSupportSession, ElectionDayOperation
from app.models.organization import Organization
from app.services.election_day_access_service import ElectionDayAccessService
from app.services.exceptions import BusinessRuleError, NotFoundError
from app.services.security_audit_service import SecurityAuditService


class ElectionDayAdminSupportService:
    """Modo soporte administrativo explícito (§6). Un ADMIN global nunca es
    propietario operativo de una Jornada Electoral: solo puede consultar el
    Centro de Control mientras mantiene abierta, para una única campaña a la
    vez, una fila aquí — persistida en base de datos (nunca en memoria del
    proceso, §18), auditada al abrir y al cerrar."""

    def __init__(self, db):
        self.db = db
        self.access = ElectionDayAccessService(db)
        self.audit = SecurityAuditService(db)

    def _operation(self, campaign_id):
        op = self.db.scalar(
            select(ElectionDayOperation)
            .where(ElectionDayOperation.campaign_id == campaign_id)
            .order_by(ElectionDayOperation.created_at.desc())
        )
        if not op:
            raise NotFoundError("No existe una jornada configurada para esta campaña")
        return op

    def _active_session_for_admin(self, user):
        return self.db.scalar(
            select(ElectionDayAdminSupportSession).where(
                ElectionDayAdminSupportSession.admin_user_id == user.id,
                ElectionDayAdminSupportSession.ended_at.is_(None),
            )
        )

    def start(self, campaign_id, data, user):
        campaign = self.access.require_admin_support(campaign_id, user)
        op = self._operation(campaign_id)
        existing = self._active_session_for_admin(user)
        if existing:
            if existing.campaign_id == campaign_id:
                return existing  # Reabrir soporte sobre la misma campaña es idempotente.
            other = self.db.get(Campaign, existing.campaign_id)
            raise BusinessRuleError(
                f"Ya tienes una sesión de soporte activa en la campaña «{other.name if other else existing.campaign_id}». "
                "Ciérrala antes de iniciar soporte en otra campaña."
            )
        session = ElectionDayAdminSupportSession(
            admin_user_id=user.id, organization_id=campaign.organization_id,
            campaign_id=campaign_id, operation_id=op.id, reason=data.reason,
        )
        self.db.add(session)
        self.db.flush()
        self.audit.record(
            "ELECTION_DAY_ADMIN_SUPPORT_STARTED", "SUCCESS", "Modo soporte administrativo iniciado",
            user_id=user.id, campaign_id=campaign_id, resource_type="ELECTION_DAY_ADMIN_SUPPORT_SESSION",
            resource_id=session.id, metadata={"reason": data.reason} if data.reason else {},
        )
        self.db.commit()
        return session

    def list_campaigns_with_operation(self, user):
        """Fase 3.1 §7: listado mínimo, solo-ADMIN, de campañas que ya tienen
        una Jornada Electoral configurada — reemplaza el GET /campaigns?
        page_size=200 genérico que usaba ElectionDaySupportPage, que exponía
        campañas sin jornada y dependía de la organización activa del ADMIN
        en el conmutador global. Nunca requiere soporte activo: es solo el
        listado para DECIDIR en qué campaña iniciarlo."""
        if not self.access.is_admin(user):
            raise PermissionError("Solo un ADMIN puede consultar este listado")
        # Una campaña puede, en teoría, tener más de una fila de operación
        # (una por proceso electoral distinto) — nos quedamos con la más
        # reciente por campaña, igual que _operation_or_none.
        latest = (
            select(
                ElectionDayOperation.campaign_id,
                func.max(ElectionDayOperation.created_at).label("latest_created_at"),
            )
            .group_by(ElectionDayOperation.campaign_id)
            .subquery()
        )
        status_order = case(
            (ElectionDayOperation.status == "ACTIVE", 0),
            (ElectionDayOperation.status == "SCRUTINY", 1),
            (ElectionDayOperation.status == "PREPARATION", 2),
            (ElectionDayOperation.status == "CLOSED", 3),
            else_=4,
        )
        rows = self.db.execute(
            select(
                Campaign.id, Campaign.name, func.coalesce(Organization.name, "Organización principal"),
                ElectionDayOperation.id, ElectionDayOperation.status, ElectionDayOperation.election_date,
            )
            .select_from(ElectionDayOperation)
            .join(
                latest,
                (latest.c.campaign_id == ElectionDayOperation.campaign_id)
                & (latest.c.latest_created_at == ElectionDayOperation.created_at),
            )
            .join(Campaign, Campaign.id == ElectionDayOperation.campaign_id)
            # LEFT JOIN, no INNER: Campaign.organization_id puede apuntar al id
            # de bootstrap por defecto (§ CampaignService.create) sin que esa
            # fila de Organization exista todavía — nunca debe hacer
            # desaparecer la campaña de este listado administrativo.
            .outerjoin(Organization, Organization.id == Campaign.organization_id)
            .order_by(status_order, Campaign.name)
        ).all()
        return [
            {
                "campaign_id": r[0], "campaign_name": r[1], "organization_name": r[2],
                "operation_id": r[3], "operation_status": r[4], "election_date": r[5],
            }
            for r in rows
        ]

    def current(self, campaign_id, user):
        self.access.require_admin_support(campaign_id, user)
        return self.db.scalar(
            select(ElectionDayAdminSupportSession).where(
                ElectionDayAdminSupportSession.admin_user_id == user.id,
                ElectionDayAdminSupportSession.campaign_id == campaign_id,
                ElectionDayAdminSupportSession.ended_at.is_(None),
            )
        )

    def end(self, campaign_id, user):
        self.access.require_admin_support(campaign_id, user)
        session = self.db.scalar(
            select(ElectionDayAdminSupportSession).where(
                ElectionDayAdminSupportSession.admin_user_id == user.id,
                ElectionDayAdminSupportSession.campaign_id == campaign_id,
                ElectionDayAdminSupportSession.ended_at.is_(None),
            )
        )
        if not session:
            raise NotFoundError("No tienes una sesión de soporte activa en esta campaña")
        session.ended_at = datetime.now(timezone.utc)
        self.audit.record(
            "ELECTION_DAY_ADMIN_SUPPORT_ENDED", "SUCCESS", "Modo soporte administrativo finalizado",
            user_id=user.id, campaign_id=campaign_id, resource_type="ELECTION_DAY_ADMIN_SUPPORT_SESSION",
            resource_id=session.id,
        )
        self.db.commit()
        return session
