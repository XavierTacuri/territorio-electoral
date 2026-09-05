from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.election_day import *
from app.services.election_day_service import ElectionDayService
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


@router.post("/operation/open", response_model=ElectionDayOperationRead)
def open_operation(campaign_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayService(db).open_operation, campaign_id, user)


@router.get("/operation/closure-preview", response_model=CoverageSummary)
def closure_preview(campaign_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    _op, summary = invoke(ElectionDayService(db).closure_preview, campaign_id, user)
    return summary


@router.post("/operation/close", response_model=ElectionDayOperationRead)
def close_operation(campaign_id: UUID, data: ElectionDayCloseRequest, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayService(db).close_operation, campaign_id, data, user)


@router.get("/coverage", response_model=CoverageSummary)
def coverage(campaign_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayService(db).coverage, campaign_id, user)


@router.get("/polling-places", response_model=PollingPlaceListResponse)
def list_polling_places(campaign_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    items = invoke(ElectionDayService(db).list_polling_places, campaign_id, user)
    return {"items": items, "total": len(items)}


@router.post("/polling-places", response_model=PollingPlaceRead, status_code=201)
def create_polling_place(campaign_id: UUID, data: PollingPlaceCreate, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayService(db).create_polling_place, campaign_id, data, user)


@router.get("/polling-places/{polling_place_id}", response_model=PollingPlaceRead)
def polling_place_detail(campaign_id: UUID, polling_place_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayService(db).polling_place_detail, campaign_id, polling_place_id, user)


@router.get("/polling-places/{polling_place_id}/boards", response_model=list[ElectoralBoardRead])
def list_boards(campaign_id: UUID, polling_place_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayService(db).list_boards, campaign_id, user, polling_place_id)


@router.post("/polling-places/{polling_place_id}/boards", response_model=ElectoralBoardRead, status_code=201)
def create_board(campaign_id: UUID, polling_place_id: UUID, data: ElectoralBoardCreate, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionDayService(db).create_board, campaign_id, polling_place_id, data, user)


@router.get("/assignments", response_model=ElectionDayAssignmentListResponse)
def list_assignments(campaign_id: UUID, polling_place_id: UUID | None = Query(None), db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    items = invoke(ElectionDayService(db).list_assignments, campaign_id, user, polling_place_id)
    return {"items": items, "total": len(items)}


@router.get("/my-assignment", response_model=ElectionDayAssignmentRead | None)
def my_assignment(campaign_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
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
