import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.security import hash_password
from app.models.campaign import Campaign
from app.models.election_day import (
    ElectionDayAssignment,
    ElectionDayOperation,
    ElectionDayStaffInvitation,
    ElectionDayStaffInvitationPollingPlace,
    PollingPlace,
)
from app.models.organization import Organization
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.election_day_access_service import ElectionDayAccessService
from app.services.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.services.security_audit_service import SecurityAuditService

STAFF_TYPES = {"POLLING_PLACE_DELEGATE", "ACT_VALIDATOR"}


class ElectionDayStaffInvitationService:
    """Alta e invitación de personal operativo de Jornada Electoral — Delegados
    de recinto y Validadores de actas (Fase 1B).

    Principio central (§2): este personal NUNCA se convierte automáticamente
    en CampaignUser/OrganizationMembership/TerritorialAssignment/UserRole. Su
    único acceso proviene de una ElectionDayAssignment ligada a la
    ElectionDayOperation de esta campaña — nunca acceso general de campaña.

    Seguridad del token (§4): se genera con secrets.token_urlsafe (alta
    entropía), se persiste únicamente su SHA-256 (token_hash) y el valor en
    texto plano se devuelve una única vez, al crear o reemitir — nunca se
    recupera ni se registra en auditoría o logs."""

    def __init__(self, db):
        self.db = db
        self.access = ElectionDayAccessService(db)
        self.audit = SecurityAuditService(db)

    # ---------- Helpers ----------
    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _new_token(self) -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        return token, self._hash_token(token)

    def _expiry(self) -> datetime:
        return self._now() + timedelta(hours=settings.election_day_staff_invitation_expires_hours)

    def _require_operation(self, campaign_id: UUID) -> ElectionDayOperation:
        op = self.db.scalar(
            select(ElectionDayOperation)
            .where(ElectionDayOperation.campaign_id == campaign_id)
            .order_by(ElectionDayOperation.created_at.desc())
        )
        if not op:
            raise NotFoundError("No existe una jornada configurada para esta campaña")
        return op

    def _polling_place_ids(self, invitation_id: UUID) -> list[UUID]:
        return list(
            self.db.scalars(
                select(ElectionDayStaffInvitationPollingPlace.polling_place_id)
                .where(ElectionDayStaffInvitationPollingPlace.invitation_id == invitation_id)
                .order_by(ElectionDayStaffInvitationPollingPlace.created_at)
            )
        )

    def to_read_dict(self, invitation: ElectionDayStaffInvitation) -> dict:
        return {
            "id": invitation.id,
            "campaign_id": invitation.campaign_id,
            "operation_id": invitation.operation_id,
            "email": invitation.email,
            "first_name": invitation.first_name,
            "last_name": invitation.last_name,
            "staff_type": invitation.staff_type,
            "status": self.effective_status(invitation),
            "invited_by_user_id": invitation.invited_by_user_id,
            "accepted_user_id": invitation.accepted_user_id,
            "expires_at": invitation.expires_at,
            "accepted_at": invitation.accepted_at,
            "revoked_at": invitation.revoked_at,
            "created_at": invitation.created_at,
            "polling_place_ids": self._polling_place_ids(invitation.id),
        }

    def effective_status(self, invitation: ElectionDayStaffInvitation) -> str:
        """§6: EXPIRED se resuelve determinísticamente a partir de expires_at
        — no requiere un job en segundo plano."""
        if invitation.status == "PENDING" and invitation.expires_at <= self._now():
            return "EXPIRED"
        return invitation.status

    def _get_invitation(self, campaign_id: UUID, invitation_id: UUID) -> ElectionDayStaffInvitation:
        invitation = self.db.get(ElectionDayStaffInvitation, invitation_id)
        if not invitation or invitation.campaign_id != campaign_id:
            raise NotFoundError("Invitación no encontrada")
        return invitation

    def _generate_username(self, email: str, first_name: str, last_name: str) -> str:
        base = re.sub(r"[^a-z0-9]", "", f"{first_name}{last_name}".lower())
        if not base:
            base = re.sub(r"[^a-z0-9]", "", email.split("@", 1)[0].lower())
        base = (base or "usuario")[:40]
        repository = UserRepository(self.db)
        candidate = base
        suffix = 1
        while repository.get_by_username(candidate):
            suffix += 1
            candidate = f"{base}{suffix}"
        return candidate

    # ---------- Create / list / revoke / reissue (equipo ejecutivo) ----------
    def create(self, campaign_id: UUID, data, user: User) -> tuple[ElectionDayStaffInvitation, str]:
        campaign = self.access.require_executive(campaign_id, user)
        op = self._require_operation(campaign_id)
        if op.status == "CLOSED":
            raise BusinessRuleError("La jornada está cerrada; no se pueden crear invitaciones")
        if data.staff_type not in STAFF_TYPES:
            raise BusinessRuleError("Perfil de personal de jornada inválido")
        places: list[PollingPlace] = []
        for place_id in data.polling_place_ids:
            place = self.db.get(PollingPlace, place_id)
            if (
                not place
                or place.electoral_process_id != op.electoral_process_id
                or place.canton_id != campaign.canton_id
                or not place.is_active
            ):
                raise NotFoundError("Recinto no encontrado")
            places.append(place)
        token, token_hash = self._new_token()
        invitation = ElectionDayStaffInvitation(
            organization_id=campaign.organization_id,
            campaign_id=campaign_id,
            operation_id=op.id,
            email=str(data.email),
            first_name=data.first_name,
            last_name=data.last_name,
            staff_type=data.staff_type,
            status="PENDING",
            invited_by_user_id=user.id,
            token_hash=token_hash,
            expires_at=self._expiry(),
        )
        self.db.add(invitation)
        self.db.flush()
        for place in places:
            self.db.add(ElectionDayStaffInvitationPollingPlace(invitation_id=invitation.id, polling_place_id=place.id))
        self.db.flush()
        self.audit.record(
            "ELECTION_DAY_STAFF_INVITED", "SUCCESS", "Invitación de personal de jornada creada",
            user_id=user.id, campaign_id=campaign_id, resource_type="ELECTION_DAY_STAFF_INVITATION",
            resource_id=invitation.id,
            metadata={"operation_id": str(op.id), "staff_type": data.staff_type, "polling_place_count": len(places), "invitation_id": str(invitation.id)},
        )
        self.db.commit()
        return invitation, token

    def list_invitations(self, campaign_id: UUID, user: User) -> list[ElectionDayStaffInvitation]:
        self.access.require_executive(campaign_id, user)
        return list(
            self.db.scalars(
                select(ElectionDayStaffInvitation)
                .where(ElectionDayStaffInvitation.campaign_id == campaign_id)
                .order_by(ElectionDayStaffInvitation.created_at.desc())
            )
        )

    def revoke(self, campaign_id: UUID, invitation_id: UUID, user: User) -> ElectionDayStaffInvitation:
        self.access.require_executive(campaign_id, user)
        invitation = self._get_invitation(campaign_id, invitation_id)
        if self.effective_status(invitation) != "PENDING":
            raise BusinessRuleError("Solo se puede revocar una invitación pendiente")
        invitation.status = "REVOKED"
        invitation.revoked_at = self._now()
        invitation.revoked_by_user_id = user.id
        self.audit.record(
            "ELECTION_DAY_STAFF_INVITATION_REVOKED", "SUCCESS", "Invitación de personal de jornada revocada",
            user_id=user.id, campaign_id=campaign_id, resource_type="ELECTION_DAY_STAFF_INVITATION",
            resource_id=invitation.id,
            metadata={"operation_id": str(invitation.operation_id), "staff_type": invitation.staff_type, "invitation_id": str(invitation.id)},
        )
        self.db.commit()
        return invitation

    def reissue(self, campaign_id: UUID, invitation_id: UUID, user: User) -> tuple[ElectionDayStaffInvitation, str]:
        self.access.require_executive(campaign_id, user)
        invitation = self._get_invitation(campaign_id, invitation_id)
        op = self.db.get(ElectionDayOperation, invitation.operation_id)
        if op and op.status == "CLOSED":
            raise BusinessRuleError("La jornada está cerrada; no se pueden reemitir invitaciones")
        if self.effective_status(invitation) != "PENDING":
            raise BusinessRuleError("Solo se puede reemitir una invitación pendiente")
        token, token_hash = self._new_token()
        invitation.token_hash = token_hash
        invitation.expires_at = self._expiry()
        invitation.status = "PENDING"
        self.audit.record(
            "ELECTION_DAY_STAFF_INVITATION_REISSUED", "SUCCESS", "Invitación de personal de jornada reemitida",
            user_id=user.id, campaign_id=campaign_id, resource_type="ELECTION_DAY_STAFF_INVITATION",
            resource_id=invitation.id,
            metadata={"operation_id": str(invitation.operation_id), "staff_type": invitation.staff_type, "invitation_id": str(invitation.id)},
        )
        self.db.commit()
        return invitation, token

    # ---------- Public preview / acceptance ----------
    def preview(self, token: str) -> dict:
        invitation = self.db.scalar(
            select(ElectionDayStaffInvitation).where(ElectionDayStaffInvitation.token_hash == self._hash_token(token))
        )
        if not invitation:
            raise NotFoundError("Invitación no encontrada")
        campaign = self.db.get(Campaign, invitation.campaign_id)
        op = self.db.get(ElectionDayOperation, invitation.operation_id)
        places = self._polling_place_ids(invitation.id)
        place_rows = list(self.db.scalars(select(PollingPlace).where(PollingPlace.id.in_(places)))) if places else []
        requires_login = self.db.scalar(select(User.id).where(User.email == invitation.email)) is not None
        return {
            "campaign_name": campaign.name if campaign else "",
            "election_date": op.election_date if op else None,
            "staff_type": invitation.staff_type,
            "email": invitation.email,
            "first_name": invitation.first_name,
            "last_name": invitation.last_name,
            "polling_places": [{"id": p.id, "name": p.name} for p in place_rows],
            "expires_at": invitation.expires_at,
            "requires_login": requires_login,
            "status": self.effective_status(invitation),
        }

    def _lock_for_accept(self, token: str) -> ElectionDayStaffInvitation:
        invitation = self.db.scalar(
            select(ElectionDayStaffInvitation)
            .where(ElectionDayStaffInvitation.token_hash == self._hash_token(token))
            .with_for_update()
        )
        if not invitation:
            raise NotFoundError("Invitación no encontrada")
        return invitation

    def _validate_acceptable(self, invitation: ElectionDayStaffInvitation, op: ElectionDayOperation) -> None:
        effective = self.effective_status(invitation)
        if effective == "EXPIRED":
            if invitation.status == "PENDING":
                invitation.status = "EXPIRED"
                self.db.commit()
            raise BusinessRuleError("Esta invitación expiró. Solicita una nueva al equipo de campaña.")
        if effective == "REVOKED":
            raise BusinessRuleError("Esta invitación fue revocada.")
        if op.status == "CLOSED":
            raise BusinessRuleError("La jornada está cerrada; ya no se pueden aceptar invitaciones.")

    def _finalize_acceptance(self, invitation: ElectionDayStaffInvitation, op: ElectionDayOperation, user: User) -> None:
        place_ids = self._polling_place_ids(invitation.id)
        if invitation.staff_type == "POLLING_PLACE_DELEGATE":
            for place_id in place_ids:
                exists = self.db.scalar(
                    select(ElectionDayAssignment).where(
                        ElectionDayAssignment.operation_id == op.id,
                        ElectionDayAssignment.user_id == user.id,
                        ElectionDayAssignment.polling_place_id == place_id,
                        ElectionDayAssignment.status != "REPLACED",
                    )
                )
                if not exists:
                    self.db.add(ElectionDayAssignment(
                        operation_id=op.id, user_id=user.id, polling_place_id=place_id,
                        assignment_role="POLLING_PLACE_DELEGATE", status="ASSIGNED",
                        assigned_by_user_id=invitation.invited_by_user_id,
                    ))
        else:
            exists = self.db.scalar(
                select(ElectionDayAssignment).where(
                    ElectionDayAssignment.operation_id == op.id,
                    ElectionDayAssignment.user_id == user.id,
                    ElectionDayAssignment.assignment_role == "ACT_VALIDATOR",
                    ElectionDayAssignment.status != "REPLACED",
                )
            )
            if not exists:
                self.db.add(ElectionDayAssignment(
                    operation_id=op.id, user_id=user.id, polling_place_id=None,
                    assignment_role="ACT_VALIDATOR", status="ASSIGNED",
                    assigned_by_user_id=invitation.invited_by_user_id,
                ))
        invitation.status = "ACCEPTED"
        invitation.accepted_user_id = user.id
        invitation.accepted_at = self._now()
        self.db.flush()
        self.audit.record(
            "ELECTION_DAY_STAFF_INVITATION_ACCEPTED", "SUCCESS", "Invitación de personal de jornada aceptada",
            user_id=user.id, campaign_id=invitation.campaign_id, resource_type="ELECTION_DAY_STAFF_INVITATION",
            resource_id=invitation.id,
            metadata={
                "campaign_id": str(invitation.campaign_id), "operation_id": str(op.id),
                "staff_type": invitation.staff_type, "invitation_id": str(invitation.id),
                "accepted_user_id": str(user.id),
            },
        )

    def accept_existing(self, token: str, current_user: User) -> ElectionDayStaffInvitation:
        invitation = self._lock_for_accept(token)
        op = self.db.get(ElectionDayOperation, invitation.operation_id)
        if invitation.status == "ACCEPTED":
            self.db.commit()
            if invitation.accepted_user_id == current_user.id:
                return invitation
            raise PermissionError("Esta invitación ya fue aceptada por otra cuenta.")
        if current_user.email != invitation.email:
            self.db.commit()
            raise PermissionError("Debes iniciar sesión con la cuenta que recibió esta invitación.")
        self._validate_acceptable(invitation, op)
        try:
            self._finalize_acceptance(invitation, op, current_user)
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise ConflictError("Esta invitación ya fue procesada.")
        return invitation

    def accept_new_account(self, token: str, data) -> ElectionDayStaffInvitation:
        invitation = self._lock_for_accept(token)
        op = self.db.get(ElectionDayOperation, invitation.operation_id)
        if invitation.status == "ACCEPTED":
            self.db.commit()
            return invitation
        self._validate_acceptable(invitation, op)
        if UserRepository(self.db).get_by_email(invitation.email):
            self.db.commit()
            raise BusinessRuleError("Ya existe una cuenta con este correo. Inicia sesión para aceptar la invitación.")
        username = self._generate_username(invitation.email, data.first_name, data.last_name)
        user = UserRepository(self.db).create(
            email=invitation.email, username=username,
            first_name=data.first_name, last_name=data.last_name,
            hashed_password=hash_password(data.password), is_active=True, is_superuser=False,
        )
        self.db.flush()
        try:
            self._finalize_acceptance(invitation, op, user)
            self.audit.record(
                "ELECTION_DAY_STAFF_ACCOUNT_CREATED", "SUCCESS", "Cuenta de personal de jornada creada",
                user_id=user.id, campaign_id=invitation.campaign_id, resource_type="USER", resource_id=user.id,
                metadata={"campaign_id": str(invitation.campaign_id), "operation_id": str(op.id), "invitation_id": str(invitation.id)},
            )
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise ConflictError("Esta invitación ya fue procesada.")
        return invitation

    # ---------- Mi contexto de Jornada Electoral (§19/§20) ----------
    def my_context(self, campaign_id: UUID, user: User) -> dict:
        campaign = self.access.resolve_election_day_context(campaign_id, user)
        op = self._require_operation(campaign_id)
        delegate_assignments = self.access.active_delegate_assignments(campaign_id, user)
        validator_assignment = self.access.active_validator_assignment(campaign_id, user)
        staff_types = []
        if delegate_assignments:
            staff_types.append("POLLING_PLACE_DELEGATE")
        if validator_assignment:
            staff_types.append("ACT_VALIDATOR")
        place_ids = [a.polling_place_id for a in delegate_assignments]
        places = list(self.db.scalars(select(PollingPlace).where(PollingPlace.id.in_(place_ids)))) if place_ids else []
        return {
            "campaign_id": campaign.id,
            "campaign_name": campaign.name,
            "organization_id": campaign.organization_id,
            "operation_id": op.id,
            "election_date": op.election_date,
            "operation_status": op.status,
            "staff_types": staff_types,
            "polling_places": [{"id": p.id, "name": p.name} for p in places],
        }

    def my_contexts(self, user: User) -> list[dict]:
        assignments = list(
            self.db.scalars(
                select(ElectionDayAssignment).where(
                    ElectionDayAssignment.user_id == user.id,
                    ElectionDayAssignment.status != "REPLACED",
                )
            )
        )
        by_operation: dict[UUID, list[ElectionDayAssignment]] = {}
        for assignment in assignments:
            by_operation.setdefault(assignment.operation_id, []).append(assignment)
        results = []
        for operation_id, items in by_operation.items():
            op = self.db.get(ElectionDayOperation, operation_id)
            if not op:
                continue
            campaign = self.db.get(Campaign, op.campaign_id)
            if not campaign:
                continue
            organization = self.db.get(Organization, campaign.organization_id)
            if organization and organization.status == "SUSPENDED":
                continue
            results.append({
                "campaign_id": campaign.id,
                "campaign_name": campaign.name,
                "operation_id": op.id,
                "election_date": op.election_date,
                "operation_status": op.status,
                "staff_types": sorted({a.assignment_role for a in items}),
            })
        results.sort(key=lambda r: r["campaign_name"])
        return results
