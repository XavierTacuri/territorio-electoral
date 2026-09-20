from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_active_user
from app.api.routes._artifact_response import artifact_response
from app.db.session import get_db
from app.models.user import User
from app.schemas.election_act import (
    ElectionActContestOption,
    ElectionActCorrectionCreate,
    ElectionActCoverageSummary,
    ElectionActDetail,
    ElectionActDraftCreate,
    ElectionActDraftResponse,
    ElectionActEvidenceCompleteRequest,
    ElectionActEvidenceRead,
    ElectionActEvidenceUploadIntentRequest,
    ElectionActEvidenceUploadIntentResponse,
    ElectionActListResponse,
    ElectionActObserveRequest,
    ElectionActRead,
    ElectionActValidateRequest,
)
from app.services.election_act_service import ElectionActService
from app.services.exceptions import BusinessRuleError, ConflictError, NotFoundError

router = APIRouter(prefix="/campaigns/{campaign_id}/election-day/acts", tags=["Election Day - Actas"])


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


# ---------- Rutas estáticas: deben registrarse antes de /{act_id} ----------
@router.get("/contests", response_model=list[ElectionActContestOption])
def list_contests(campaign_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionActService(db).list_contests, campaign_id, user)


@router.get("/coverage", response_model=ElectionActCoverageSummary)
def coverage(campaign_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionActService(db).coverage, campaign_id, user)


@router.get("/validation/queue", response_model=ElectionActListResponse)
def validation_queue(
    campaign_id: UUID,
    status: str | None = Query(None),
    polling_place_id: UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    items, total = invoke(
        ElectionActService(db).validation_queue, campaign_id, user,
        status=status, polling_place_id=polling_place_id, page=page, page_size=page_size,
    )
    return {"items": items, "total": total}


@router.post("/drafts", response_model=ElectionActDraftResponse, status_code=201)
def create_draft(campaign_id: UUID, data: ElectionActDraftCreate, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    service = ElectionActService(db)
    act, revision = invoke(service.create_draft, campaign_id, data, user)
    return {"act": act, "revision": service.revision_detail(revision)}


@router.get("", response_model=ElectionActListResponse)
def list_acts(
    campaign_id: UUID,
    status: str | None = Query(None),
    polling_place_id: UUID | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    items = invoke(ElectionActService(db).list_acts, campaign_id, user, status=status, polling_place_id=polling_place_id)
    return {"items": items, "total": len(items)}


# ---------- Rutas por acta ----------
@router.get("/{act_id}", response_model=ElectionActDetail)
def act_detail(campaign_id: UUID, act_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    service = ElectionActService(db)
    act, place, board, contest, revisions, reviews = invoke(service.get_act_detail, campaign_id, act_id, user)
    return {
        "act": act,
        "polling_place_name": place.name,
        "electoral_board_code": board.official_code,
        "electoral_contest_name": contest.name,
        "revisions": [service.revision_detail(r) for r in revisions],
        "reviews": reviews,
    }


@router.post("/{act_id}/corrections", response_model=ElectionActDraftResponse, status_code=201)
def create_correction(campaign_id: UUID, act_id: UUID, data: ElectionActCorrectionCreate, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    service = ElectionActService(db)
    act, revision = invoke(service.create_correction, campaign_id, act_id, data, user)
    return {"act": act, "revision": service.revision_detail(revision)}


@router.post("/{act_id}/revisions/{revision_id}/evidence", response_model=ElectionActEvidenceRead, status_code=201)
async def upload_evidence(
    campaign_id: UUID,
    act_id: UUID,
    revision_id: UUID,
    file: UploadFile = File(),
    client_generated_id: UUID | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    content = await file.read()
    return invoke(
        ElectionActService(db).upload_evidence, campaign_id, act_id, revision_id, user,
        file_bytes=content, original_filename=file.filename, client_generated_id=client_generated_id,
    )


@router.get("/{act_id}/evidence/{evidence_id}/download")
def download_evidence(campaign_id: UUID, act_id: UUID, evidence_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    download, evidence = invoke(ElectionActService(db).evidence_file, campaign_id, act_id, evidence_id, user)
    return artifact_response(download, media_type=evidence.mime_type, filename=evidence.original_filename or "evidencia")


@router.post(
    "/{act_id}/revisions/{revision_id}/evidence/upload-intent",
    response_model=ElectionActEvidenceUploadIntentResponse,
)
def create_evidence_upload_intent(
    campaign_id: UUID, act_id: UUID, revision_id: UUID, data: ElectionActEvidenceUploadIntentRequest,
    db: Session = Depends(get_db), user: User = Depends(get_current_active_user),
):
    return invoke(
        ElectionActService(db).create_upload_intent, campaign_id, act_id, revision_id, user,
        client_generated_id=data.client_generated_id, original_filename=data.original_filename,
        mime_type=data.mime_type, size_bytes=data.size_bytes, sha256=data.sha256,
    )


@router.post(
    "/{act_id}/revisions/{revision_id}/evidence/complete",
    response_model=ElectionActEvidenceRead, status_code=201,
)
def complete_evidence_upload(
    campaign_id: UUID, act_id: UUID, revision_id: UUID, data: ElectionActEvidenceCompleteRequest,
    db: Session = Depends(get_db), user: User = Depends(get_current_active_user),
):
    return invoke(ElectionActService(db).complete_upload, campaign_id, act_id, revision_id, user, upload_token=data.upload_token)


@router.post("/{act_id}/revisions/{revision_id}/submit", response_model=ElectionActDraftResponse)
def submit_revision(campaign_id: UUID, act_id: UUID, revision_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    service = ElectionActService(db)
    act, revision = invoke(service.submit_revision, campaign_id, act_id, revision_id, user)
    return {"act": act, "revision": service.revision_detail(revision)}


@router.post("/{act_id}/claim", response_model=ElectionActRead)
def claim_act(campaign_id: UUID, act_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionActService(db).claim, campaign_id, act_id, user)


@router.post("/{act_id}/release", response_model=ElectionActRead)
def release_act(campaign_id: UUID, act_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionActService(db).release, campaign_id, act_id, user)


@router.post("/{act_id}/observe", response_model=ElectionActRead)
def observe_act(campaign_id: UUID, act_id: UUID, data: ElectionActObserveRequest, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionActService(db).observe_act, campaign_id, act_id, data, user)


@router.post("/{act_id}/validate", response_model=ElectionActRead)
def validate_act(campaign_id: UUID, act_id: UUID, data: ElectionActValidateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return invoke(ElectionActService(db).validate_act, campaign_id, act_id, data, user)
