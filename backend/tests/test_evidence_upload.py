from datetime import date
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.security import hash_password
from app.models.operational import ActivityEvidence
from app.models.security import SecurityAuditEvent
from app.models.user import User
from app.schemas.campaign import CampaignCreate, CampaignUserAssign, TerritorialAssignmentCreate
from app.schemas.operational import ActivityCloseRequest, TerritorialActivityCreate
from app.scripts.seed_gualaceo import seed as seed_gualaceo
from app.services.activity_catalog_service import seed as seed_catalogs
from app.services.campaign_service import CampaignService
from app.services.evidence_storage_service import LocalEvidenceStorage
from app.services.exceptions import BusinessRuleError
from app.services.operational_service import OperationalService
from app.services.role_service import RoleService
from app.services.territorial_assignment_service import TerritorialAssignmentService

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64
FAKE_JPEG_BYTES = b"this is not actually a jpeg file, just text" + b"\x00" * 20


@pytest.fixture
def evidence_context(db: Session, admin):
    _, canton, parishes = seed_gualaceo(db)
    seed_catalogs(db)
    db.commit()
    campaign = CampaignService(db).create(
        CampaignCreate(
            name="Evidencia Gualaceo",
            slug="evidencia-gualaceo",
            canton_id=canton.id,
            office_type="MAYOR",
            election_name="Elecciones Seccionales 2027",
            election_date=date(2027, 2, 14),
            status="ACTIVE",
        ),
        admin,
    )
    roles = RoleService(db)
    coordinator = User(
        email="coord-evidence@example.test",
        username="coord_evidence",
        first_name="Coord",
        last_name="Evidence",
        hashed_password=hash_password("Testing123"),
        is_active=True,
        roles=[roles.repository.get_by_code("TERRITORIAL_COORDINATOR")],
    )
    unassigned = User(
        email="unassigned-evidence@example.test",
        username="unassigned_evidence",
        first_name="No",
        last_name="Access",
        hashed_password=hash_password("Testing123"),
        is_active=True,
        roles=[roles.repository.get_by_code("TERRITORIAL_COORDINATOR")],
    )
    db.add_all([coordinator, unassigned])
    db.commit()
    assignments = TerritorialAssignmentService(db)
    assignments.assign_user(campaign.id, CampaignUserAssign(user_id=coordinator.id), admin)
    assignments.assign_user(campaign.id, CampaignUserAssign(user_id=unassigned.id), admin)
    assignments.create(campaign.id, TerritorialAssignmentCreate(user_id=coordinator.id, parish_id=parishes[0].id), admin)
    service = OperationalService(db)
    activity = service.create_activity(
        campaign.id,
        TerritorialActivityCreate(
            activity_type_code="COMMUNITY_MEETING",
            title="Reunión comunitaria",
            activity_date=date(2026, 8, 3),
            status="PLANNED",
            parish_id=parishes[0].id,
        ),
        admin,
    )
    approved = service.complete_activity(
        campaign.id, activity.id, ActivityCloseRequest(summary="Cierre de prueba."), admin
    )
    # complete_activity moves status to COMPLETED but approval_status was
    # already APPROVED for an admin-created activity; keep a second, still
    # PLANNED+APPROVED activity for the "requires approval" scenarios.
    pending_activity = service.create_activity(
        campaign.id,
        TerritorialActivityCreate(
            activity_type_code="COMMUNITY_MEETING",
            title="Reunión pendiente de aprobación",
            activity_date=date(2026, 8, 4),
            status="PLANNED",
            parish_id=parishes[0].id,
        ),
        coordinator,
    )
    return campaign, parishes, coordinator, unassigned, approved, pending_activity


def test_upload_evidence_success_and_download(client: TestClient, admin_headers, evidence_context):
    campaign, _, _, _, activity, _ = evidence_context
    response = client.post(
        f"/api/v1/campaigns/{campaign.id}/activities/{activity.id}/evidence/upload",
        headers=admin_headers,
        files={"file": ("foto.jpg", JPEG_BYTES, "image/jpeg")},
        data={"evidence_type": "PHOTO", "title": "Evidencia de campo"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["mime_type"] == "image/jpeg"
    assert body["size_bytes"] == len(JPEG_BYTES)
    assert body["url"] is None

    download = client.get(
        f"/api/v1/campaigns/{campaign.id}/activities/{activity.id}/evidence/{body['id']}/download",
        headers=admin_headers,
    )
    assert download.status_code == 200
    assert download.content == JPEG_BYTES
    assert download.headers["cache-control"] == "private, no-store"


def test_upload_evidence_duplicate_client_generated_id_no_duplicate(client: TestClient, admin_headers, evidence_context, db: Session):
    campaign, _, _, _, activity, _ = evidence_context
    client_id = str(uuid4())
    for _ in range(2):
        response = client.post(
            f"/api/v1/campaigns/{campaign.id}/activities/{activity.id}/evidence/upload",
            headers=admin_headers,
            files={"file": ("foto.jpg", JPEG_BYTES, "image/jpeg")},
            data={"evidence_type": "PHOTO", "title": "Evidencia retry", "client_generated_id": client_id},
        )
        assert response.status_code == 201, response.text
    rows = list(db.scalars(select(ActivityEvidence).where(ActivityEvidence.activity_id == activity.id)))
    assert len(rows) == 1
    audit_events = list(db.scalars(select(SecurityAuditEvent).where(SecurityAuditEvent.event_type == "evidence_upload")))
    assert len(audit_events) == 1


def test_upload_evidence_rejects_content_that_does_not_match_declared_type(client: TestClient, admin_headers, evidence_context):
    campaign, _, _, _, activity, _ = evidence_context
    response = client.post(
        f"/api/v1/campaigns/{campaign.id}/activities/{activity.id}/evidence/upload",
        headers=admin_headers,
        files={"file": ("foto.jpg", FAKE_JPEG_BYTES, "image/jpeg")},
        data={"evidence_type": "PHOTO", "title": "Evidencia falsa"},
    )
    assert response.status_code == 400
    assert "AxiosError" not in response.text
    assert "Traceback" not in response.text


def test_upload_evidence_rejects_oversized_file(db: Session, admin, evidence_context, tmp_path):
    campaign, _, _, _, activity, _ = evidence_context
    tiny_storage = LocalEvidenceStorage(str(tmp_path), max_file_mb=1)
    tiny_storage.max_bytes = 10  # force a small cap without writing 1MB in the test
    service = OperationalService(db, storage=tiny_storage)
    with pytest.raises(BusinessRuleError):
        service.upload_evidence(
            campaign.id,
            activity.id,
            admin,
            file_bytes=JPEG_BYTES,
            original_filename="foto.jpg",
            evidence_type="PHOTO",
            title="Muy grande",
            description=None,
            evidence_date=None,
            client_generated_id=None,
        )


def test_upload_evidence_requires_approved_activity_then_retries_after_approval(client: TestClient, admin_headers, evidence_context, db: Session, admin):
    campaign, _, coordinator, _, _, pending_activity = evidence_context
    coordinator_login = client.post("/api/v1/auth/login", data={"username": "coord_evidence", "password": "Testing123"})
    coordinator_headers = {"Authorization": f"Bearer {coordinator_login.json()['access_token']}"}
    client_id = str(uuid4())

    first = client.post(
        f"/api/v1/campaigns/{campaign.id}/activities/{pending_activity.id}/evidence/upload",
        headers=coordinator_headers,
        files={"file": ("foto.jpg", JPEG_BYTES, "image/jpeg")},
        data={"evidence_type": "PHOTO", "title": "Evidencia previa a aprobación", "client_generated_id": client_id},
    )
    assert first.status_code == 400
    assert "aprobada" in first.json()["detail"]

    # Approve via an executive actor (coordinators cannot self-approve).
    OperationalService(db).approve_activity(campaign.id, pending_activity.id, admin)

    retry = client.post(
        f"/api/v1/campaigns/{campaign.id}/activities/{pending_activity.id}/evidence/upload",
        headers=coordinator_headers,
        files={"file": ("foto.jpg", JPEG_BYTES, "image/jpeg")},
        data={"evidence_type": "PHOTO", "title": "Evidencia previa a aprobación", "client_generated_id": client_id},
    )
    assert retry.status_code == 201, retry.text
    rows = list(db.scalars(select(ActivityEvidence).where(ActivityEvidence.activity_id == pending_activity.id)))
    assert len(rows) == 1


def test_upload_evidence_denied_for_coordinator_without_territorial_access(client: TestClient, admin_headers, evidence_context):
    campaign, _, _, unassigned, activity, _ = evidence_context
    login = client.post("/api/v1/auth/login", data={"username": "unassigned_evidence", "password": "Testing123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = client.post(
        f"/api/v1/campaigns/{campaign.id}/activities/{activity.id}/evidence/upload",
        headers=headers,
        files={"file": ("foto.jpg", JPEG_BYTES, "image/jpeg")},
        data={"evidence_type": "PHOTO", "title": "Evidencia sin acceso"},
    )
    assert response.status_code == 403


def test_download_evidence_denied_for_coordinator_without_territorial_access(client: TestClient, admin_headers, evidence_context):
    campaign, _, _, unassigned, activity, _ = evidence_context
    upload = client.post(
        f"/api/v1/campaigns/{campaign.id}/activities/{activity.id}/evidence/upload",
        headers=admin_headers,
        files={"file": ("foto.jpg", JPEG_BYTES, "image/jpeg")},
        data={"evidence_type": "PHOTO", "title": "Evidencia protegida"},
    )
    evidence_id = upload.json()["id"]
    login = client.post("/api/v1/auth/login", data={"username": "unassigned_evidence", "password": "Testing123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = client.get(
        f"/api/v1/campaigns/{campaign.id}/activities/{activity.id}/evidence/{evidence_id}/download",
        headers=headers,
    )
    assert response.status_code == 403
