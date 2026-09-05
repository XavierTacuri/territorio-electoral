from sqlalchemy import select

from app.models.election_day import ElectionDayAssignment, ElectionDayOperation, PollingPlace
from app.services.campaign_access_service import CampaignAccessService
from app.services.campaign_permissions import CAMPAIGN_EXECUTIVE_ROLES


class ElectionDayAccessService:
    def __init__(self, db):
        self.db = db
        self.access = CampaignAccessService(db)

    def require_read(self, campaign_id, user):
        return self.access.require_access(campaign_id, user)

    def can_manage_operation(self, user):
        # Activar/cerrar jornada y administrar assignments (§7/§16/§64): rol
        # ejecutivo de campaña o ADMIN — nunca automático, nunca Coordinator.
        return self.access.admin(user) or bool(CAMPAIGN_EXECUTIVE_ROLES & {r.code for r in user.roles})

    def require_manage_operation(self, campaign_id, user):
        campaign = self.access.require_access(campaign_id, user)
        if not self.can_manage_operation(user):
            raise PermissionError("Sin permisos para administrar la jornada electoral")
        return campaign

    def can_operate(self, user):
        # Check-in, reportar incidencia, subir documento (§66): además de los
        # roles ejecutivos, el Coordinator opera dentro de su alcance.
        return self.access.admin(user) or bool({r.code for r in user.roles} & (CAMPAIGN_EXECUTIVE_ROLES | {"TERRITORIAL_COORDINATOR"}))

    def allowed_parish_ids(self, campaign_id, user):
        assignments = self.access.territorial_ids(campaign_id, user)
        if assignments is None:
            return None
        allowed = {a.parish_id for a in assignments if a.parish_id is not None}
        # Un Coordinator asignado a un recinto para la jornada (§12) tiene
        # alcance sobre ese recinto aunque no tenga un TerritorialAssignment
        # permanente cubriendo esa parroquia: la asignación de jornada es, por
        # sí misma, una forma de alcance territorial para este módulo.
        own_places = self.db.scalars(
            select(PollingPlace.parish_id)
            .join(ElectionDayAssignment, ElectionDayAssignment.polling_place_id == PollingPlace.id)
            .join(ElectionDayOperation, ElectionDayOperation.id == ElectionDayAssignment.operation_id)
            .where(
                ElectionDayOperation.campaign_id == campaign_id,
                ElectionDayAssignment.user_id == user.id,
                ElectionDayAssignment.status != "REPLACED",
            )
        )
        return allowed | set(own_places)

    def require_parish_scope(self, campaign_id, user, parish_id):
        allowed = self.allowed_parish_ids(campaign_id, user)
        if allowed is not None and parish_id not in allowed:
            raise PermissionError("Recinto fuera del alcance territorial asignado")
