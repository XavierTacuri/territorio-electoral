from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.election_day import *
from app.services.election_act_service import ElectionActService
from app.services.election_day_admin_support_service import ElectionDayAdminSupportService
from app.services.election_day_service import ElectionDayService
from app.services.election_day_staff_invitation_service import ElectionDayStaffInvitationService
from app.services.exceptions import BusinessRuleError, ConflictError, NotFoundError

router = APIRouter(prefix="/campaigns/{campaign_id}/election-day", tags=["Election Day"])


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


@router.get("/operation", response_model=ElectionDayOperationRead)
def get_operation(campaign_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayService(db).get_operation, campaign_id, user)


@router.post("/operation", response_model=ElectionDayOperationRead, status_code=201)
def create_operation(campaign_id: UUID, data: ElectionDayOperationCreate, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayService(db).create_operation, campaign_id, data, user)


@router.get("/operation/preflight", response_model=ElectionDayPreflightResponse)
def preflight(campaign_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayService(db).preflight, campaign_id, user)


@router.post("/operation/open", response_model=ElectionDayOperationRead)
def open_operation(campaign_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayService(db).open_operation, campaign_id, user)


@router.post("/operation/start-scrutiny", response_model=ElectionDayOperationRead)
def start_scrutiny(campaign_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayService(db).start_scrutiny, campaign_id, user)


@router.get("/operation/closure-preview", response_model=CoverageSummary)
def closure_preview(campaign_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    _op, summary = invoke(ElectionDayService(db).closure_preview, campaign_id, user)
    return summary


@router.post("/operation/close", response_model=ElectionDayOperationRead)
def close_operation(campaign_id: UUID, data: ElectionDayCloseRequest, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayService(db).close_operation, campaign_id, data, user)


@router.get("/control-center", response_model=ElectionDayControlCenterResponse)
def control_center(campaign_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    op, summary = invoke(ElectionDayService(db).control_center, campaign_id, user)
    # Fase 3: consolidado factual de actas VALIDATED — misma puerta de
    # acceso (require_control_center_access), la operación ya se confirmó
    # arriba así que esta segunda llamada nunca puede fallar por "sin
    # jornada configurada".
    acts_summary = invoke(ElectionActService(db).control_center_summary, campaign_id, user)
    return {"operation": op, "coverage": summary, "control_center": acts_summary}


@router.get("/validation", response_model=ElectionDayValidationStatus)
def validation_status(campaign_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayService(db).validation_status, campaign_id, user)


@router.get("/coverage", response_model=CoverageSummary)
def coverage(campaign_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayService(db).coverage, campaign_id, user)


@router.get("/polling-places", response_model=PollingPlaceListResponse)
def list_polling_places(campaign_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    items = invoke(ElectionDayService(db).list_polling_places, campaign_id, user)
    return {"items": items, "total": len(items)}


@router.get("/polling-places/{polling_place_id}", response_model=PollingPlaceRead)
def polling_place_detail(campaign_id: UUID, polling_place_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayService(db).polling_place_detail, campaign_id, polling_place_id, user)


@router.get("/polling-places/{polling_place_id}/boards", response_model=list[ElectoralBoardRead])
def list_boards(campaign_id: UUID, polling_place_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayService(db).list_boards, campaign_id, user, polling_place_id)


@router.get("/assignments", response_model=ElectionDayAssignmentListResponse)
def list_assignments(campaign_id: UUID, polling_place_id: UUID | None = Query(None), db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    items = invoke(ElectionDayService(db).list_assignments, campaign_id, user, polling_place_id)
    return {"items": items, "total": len(items)}


@router.get("/my-assignments", response_model=list[ElectionDayAssignmentRead])
def my_assignments(campaign_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayService(db).my_assignments, campaign_id, user)


@router.get("/my-context", response_model=ElectionDayMyContextResponse)
def my_context(campaign_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    """§19: contexto mínimo de Jornada Electoral para personal operativo que
    puede NO tener CampaignUser — nunca depende de GET /campaigns/{id}."""
    return invoke(ElectionDayStaffInvitationService(db).my_context, campaign_id, user)


@router.get("/my-assignment", response_model=ElectionDayAssignmentRead | None, deprecated=True)
def my_assignment(campaign_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    """Legacy (§8): devuelve una sola asignación. El frontend nuevo usa
    /my-assignments (plural), ya que un delegado puede cubrir más de un
    recinto."""
    return invoke(ElectionDayService(db).my_assignment, campaign_id, user)


@router.post("/assignments", response_model=ElectionDayAssignmentRead, status_code=201)
def create_assignment(campaign_id: UUID, data: ElectionDayAssignmentCreate, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayService(db).create_assignment, campaign_id, data, user)


@router.post("/assignments/{assignment_id}/replace", response_model=ElectionDayAssignmentRead)
def replace_assignment(campaign_id: UUID, assignment_id: UUID, data: ElectionDayAssignmentReplace, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayService(db).replace_assignment, campaign_id, assignment_id, data, user)


@router.get("/eligible-users", response_model=list[ElectionDayEligibleUser])
def eligible_users(campaign_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayService(db).eligible_users, campaign_id, user)


@router.post("/assignments/{assignment_id}/check-in", response_model=ElectionDayAssignmentRead)
def check_in(campaign_id: UUID, assignment_id: UUID, data: CheckInRequest, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayService(db).check_in, campaign_id, assignment_id, data, user)


@router.get("/incidents", response_model=ElectionDayIncidentListResponse)
def list_incidents(campaign_id: UUID, status: str | None = Query(None), db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    items = invoke(ElectionDayService(db).list_incidents, campaign_id, user, status)
    return {"items": items, "total": len(items)}


@router.post("/incidents", response_model=ElectionDayIncidentRead, status_code=201)
def create_incident(campaign_id: UUID, data: ElectionDayIncidentCreate, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayService(db).create_incident, campaign_id, data, user)


@router.post("/incidents/{incident_id}/resolve", response_model=ElectionDayIncidentRead)
def resolve_incident(campaign_id: UUID, incident_id: UUID, data: ElectionDayIncidentResolve, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayService(db).resolve_incident, campaign_id, incident_id, data, user)


@router.get("/documents", response_model=ElectionDayDocumentListResponse)
def list_documents(campaign_id: UUID, polling_place_id: UUID | None = Query(None), db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    items = invoke(ElectionDayService(db).list_documents, campaign_id, user, polling_place_id)
    return {"items": items, "total": len(items)}


@router.post("/documents/upload", response_model=ElectionDayDocumentRead, status_code=201)
async def upload_document(campaign_id: UUID, file: UploadFile = File(), polling_place_id: UUID = Form(), board_id: UUID | None = Form(None), document_type: str = Form(), client_generated_id: UUID | None = Form(None), db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    content = await file.read()
    return invoke(ElectionDayService(db).upload_document, campaign_id, user, polling_place_id=polling_place_id, board_id=board_id, document_type=document_type, file_bytes=content, original_filename=file.filename, client_generated_id=client_generated_id)


@router.patch("/documents/{document_id}/status", response_model=ElectionDayDocumentRead)
def update_document_status(campaign_id: UUID, document_id: UUID, data: ElectionDayDocumentStatusUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayService(db).update_document_status, campaign_id, document_id, data, user)


@router.get("/documents/{document_id}/download")
def download_document(campaign_id: UUID, document_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    path, doc = invoke(ElectionDayService(db).document_file, campaign_id, document_id, user)
    return FileResponse(path, media_type=doc.mime_type or "application/octet-stream", filename=doc.original_filename or "documento", headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


# ---------- Admin support mode (§6) ----------
@router.post("/admin-support/start", response_model=ElectionDayAdminSupportSessionRead, status_code=201)
def start_admin_support(campaign_id: UUID, data: ElectionDayAdminSupportStartRequest, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayAdminSupportService(db).start, campaign_id, data, user)


@router.get("/admin-support/current", response_model=ElectionDayAdminSupportSessionRead | None)
def current_admin_support(campaign_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayAdminSupportService(db).current, campaign_id, user)


@router.post("/admin-support/end", response_model=ElectionDayAdminSupportSessionRead)
def end_admin_support(campaign_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayAdminSupportService(db).end, campaign_id, user)
