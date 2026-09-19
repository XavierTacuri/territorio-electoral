from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_active_user
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.election_day import (
    ElectionDayInvitationAcceptNewAccount,
    ElectionDayInvitationAcceptResponse,
    ElectionDayInvitationPreview,
    ElectionDayInvitationTokenRequest,
    ElectionDayMyContextSummary,
    ElectionDayStaffInvitationCreate,
    ElectionDayStaffInvitationCreatedResponse,
    ElectionDayStaffInvitationListResponse,
    ElectionDayStaffInvitationRead,
)
from app.services.election_day_staff_invitation_service import ElectionDayStaffInvitationService
from app.services.exceptions import BusinessRuleError, ConflictError, NotFoundError

router = APIRouter(prefix="/campaigns/{campaign_id}/election-day/staff/invitations", tags=["Election Day Staff"])
public_router = APIRouter(prefix="/election-day", tags=["Election Day Staff"])


def invoke(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except BusinessRuleError as exc:
        raise HTTPException(400, str(exc)) from exc


def _invite_url(token: str) -> str:
    # El token viaja en el fragment (#token=...), nunca en el path ni en un
    # query param: el fragment jamás se envía al servidor HTTP (no aparece
    # en logs de acceso, Referer headers ni proxies/caches intermedios).
    origins = settings.frontend_origin_list
    base = origins[0] if origins else ""
    return f"{base}/invite/election-day#token={token}"


# ---------- Gestión (equipo ejecutivo de campaña) ----------
@router.post("", response_model=ElectionDayStaffInvitationCreatedResponse, status_code=201)
def create_invitation(campaign_id: UUID, data: ElectionDayStaffInvitationCreate, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    service = ElectionDayStaffInvitationService(db)
    invitation, token = invoke(service.create, campaign_id, data, user)
    return {
        "invitation": ElectionDayStaffInvitationRead(**service.to_read_dict(invitation)),
        "invite_token": token,
        "invite_url": _invite_url(token),
    }


@router.get("", response_model=ElectionDayStaffInvitationListResponse)
def list_invitations(campaign_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    service = ElectionDayStaffInvitationService(db)
    items = invoke(service.list_invitations, campaign_id, user)
    reads = [ElectionDayStaffInvitationRead(**service.to_read_dict(i)) for i in items]
    return {"items": reads, "total": len(reads)}


@router.post("/{invitation_id}/revoke", response_model=ElectionDayStaffInvitationRead)
def revoke_invitation(campaign_id: UUID, invitation_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    service = ElectionDayStaffInvitationService(db)
    invitation = invoke(service.revoke, campaign_id, invitation_id, user)
    return ElectionDayStaffInvitationRead(**service.to_read_dict(invitation))


@router.post("/{invitation_id}/reissue", response_model=ElectionDayStaffInvitationCreatedResponse)
def reissue_invitation(campaign_id: UUID, invitation_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    service = ElectionDayStaffInvitationService(db)
    invitation, token = invoke(service.reissue, campaign_id, invitation_id, user)
    return {
        "invitation": ElectionDayStaffInvitationRead(**service.to_read_dict(invitation)),
        "invite_token": token,
        "invite_url": _invite_url(token),
    }


# ---------- Público: preview y aceptación de invitación ----------
# El token SIEMPRE viaja en el body JSON de un POST — nunca como path ni
# query param — para que no quede en la URL, el historial del navegador,
# logs de acceso del servidor/proxy, Referer headers ni caches HTTP.
@public_router.post("/invitations/preview", response_model=ElectionDayInvitationPreview)
def preview_invitation(data: ElectionDayInvitationTokenRequest, response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return invoke(ElectionDayStaffInvitationService(db).preview, data.token)


@public_router.post("/invitations/accept-new-account", response_model=ElectionDayInvitationAcceptResponse)
def accept_invitation_new_account(data: ElectionDayInvitationAcceptNewAccount, response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    invitation = invoke(ElectionDayStaffInvitationService(db).accept_new_account, data.token, data)
    return {
        "campaign_id": invitation.campaign_id,
        "operation_id": invitation.operation_id,
        "message": "Tu acceso a la Jornada Electoral está listo.",
    }


@public_router.post("/invitations/accept", response_model=ElectionDayInvitationAcceptResponse)
def accept_invitation_existing_account(data: ElectionDayInvitationTokenRequest, response: Response, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    response.headers["Cache-Control"] = "no-store"
    invitation = invoke(ElectionDayStaffInvitationService(db).accept_existing, data.token, user)
    return {
        "campaign_id": invitation.campaign_id,
        "operation_id": invitation.operation_id,
        "message": "Tu acceso a la Jornada Electoral está listo.",
    }


# ---------- Mis jornadas (personal operativo, §20) ----------
@public_router.get("/my-contexts", response_model=list[ElectionDayMyContextSummary])
def my_contexts(db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayStaffInvitationService(db).my_contexts, user)
