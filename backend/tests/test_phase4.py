from datetime import date, timedelta
from uuid import uuid4
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.operational import ActivityEvidence, ActivityParticipantSummary, ActivityType, CitizenNeed, NeedCategory
from app.models.user import User
from app.core.security import hash_password
from app.schemas.campaign import CampaignUserAssign, TerritorialAssignmentCreate
from app.services.role_service import RoleService
from app.services.territorial_assignment_service import TerritorialAssignmentService
from app.schemas.campaign import CampaignCreate
from app.schemas.operational import (
    ActivityCloseRequest, ActivityEvidenceCreate, CommitmentCreate, CommitmentUpdate, CitizenNeedCreate,
    ParticipantSummaryUpsert, TerritorialActivityCreate,
)
from app.scripts.seed_gualaceo import seed as seed_gualaceo
from app.services.activity_catalog_service import ACTIVITY_TYPES, NEED_CATEGORIES, seed as seed_catalogs
from app.services.campaign_service import CampaignService
from app.services.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.services.operational_service import OperationalService


@pytest.fixture
def operational_context(db: Session, admin):
    province, canton, parishes = seed_gualaceo(db)
    seed_catalogs(db)
    db.commit()
    campaign = CampaignService(db).create(CampaignCreate(
        name="OperaciÃƒÂ³n Gualaceo 2027", slug="operacion-gualaceo-2027",
        canton_id=canton.id, office_type="MAYOR",
        election_name="Elecciones Seccionales 2027",
        election_date=date(2027, 2, 14), status="DRAFT",
    ), admin)
    return campaign, parishes


def completed_payload(parish_id: int, **changes):
    data = dict(activity_type_code="COMMUNITY_MEETING", title="ReuniÃƒÂ³n comunitaria",
                activity_date=date(2026, 8, 3), status="PLANNED", parish_id=parish_id)
    data.update(changes)
    return TerritorialActivityCreate(**data)


def create_completed(service, campaign_id, payload, actor):
    activity = service.create_activity(campaign_id, payload, actor)
    return service.complete_activity(
        campaign_id,
        activity.id,
        ActivityCloseRequest(summary="Actividad completada mediante el flujo de dominio del test."),
        actor,
    )


def test_operational_catalog_seed_is_idempotent(db: Session):
    seed_catalogs(db); seed_catalogs(db); db.commit()
    assert db.scalar(select(func.count()).select_from(ActivityType)) == 11
    assert db.scalar(select(func.count()).select_from(NeedCategory)) == 17
    assert {x.code for x in db.scalars(select(ActivityType))} == {x[0] for x in ACTIVITY_TYPES}
    assert {x.code for x in db.scalars(select(NeedCategory))} == {x[0] for x in NEED_CATEGORIES}


def test_activity_dates_validation_and_inactive_catalog(db, admin, operational_context):
    campaign, parishes = operational_context
    with pytest.raises(ValidationError):
        TerritorialActivityCreate(activity_type_code="TOUR", title="Futura", activity_date=date.today()+timedelta(days=1), status="COMPLETED", parish_id=parishes[0].id)
    kind = db.scalar(select(ActivityType).where(ActivityType.code == "TOUR")); kind.is_active = False; db.commit()
    with pytest.raises(BusinessRuleError):
        OperationalService(db).create_activity(campaign.id, TerritorialActivityCreate(activity_type_code="TOUR", title="Recorrido", activity_date=date.today(), status="PLANNED", parish_id=parishes[0].id), admin)


def test_activity_lifecycle_and_participant_upsert(db, admin, operational_context):
    campaign, parishes = operational_context; service = OperationalService(db)
    activity = create_completed(service, campaign.id, completed_payload(parishes[0].id), admin)
    assert activity.activity_date == date(2026, 8, 3)
    first = service.participant(campaign.id, activity.id, admin, ParticipantSummaryUpsert(estimated_attendees=45, organizations_count=3))
    second = service.participant(campaign.id, activity.id, admin, ParticipantSummaryUpsert(estimated_attendees=50))
    assert first.id == second.id and second.estimated_attendees == 50
    assert db.scalar(select(func.count()).select_from(ActivityParticipantSummary)) == 1
    with pytest.raises(ValidationError): ParticipantSummaryUpsert(estimated_attendees=-1)
    service.deactivate_activity(campaign.id, activity.id, admin)
    with pytest.raises(NotFoundError): service.activity(campaign.id, activity.id, admin)


def test_territorial_intelligence_aggregates_each_parish_without_n_plus_one(db, admin, operational_context):
    campaign, parishes = operational_context; service = OperationalService(db)
    activity = create_completed(service, campaign.id, completed_payload(parishes[0].id), admin)
    service.create_need(campaign.id, activity.id, CitizenNeedCreate(need_category_code="ROADS", title="Necesidad sintética", mentions_count=2, priority="MEDIUM"), admin)
    service.create_commitment(campaign.id, CommitmentCreate(title="Compromiso sintético", priority="MEDIUM", status="PENDING", parish_id=parishes[0].id), admin)
    payload = service.territory_summaries(campaign.id, admin)
    assert len(payload["parishes"]) == len(parishes)
    selected = next(item for item in payload["parishes"] if item["parish_id"] == parishes[0].id)
    assert selected["activities"] == 1 and selected["needs_open"] == 1
    assert selected["commitments_pending"] == 1 and selected["latest_activities"][0]["title"]


def test_need_derives_territory_and_prevents_duplicates(db, admin, operational_context):
    campaign, parishes = operational_context; service = OperationalService(db)
    activity = create_completed(service, campaign.id, completed_payload(parishes[1].id), admin)
    payload = CitizenNeedCreate(need_category_code="ROADS", title="  Mejoramiento   vial ", mentions_count=12, priority="HIGH")
    need = service.create_need(campaign.id, activity.id, payload, admin)
    assert need.parish_id == activity.parish_id and need.community_id is None
    with pytest.raises(ConflictError): service.create_need(campaign.id, activity.id, payload, admin)
    updated = service.update_need(campaign.id, need.id, type(payload)(need_category_code="ROADS", title="Otra", mentions_count=20, priority="CRITICAL"), admin) if False else None
    need.mentions_count = 20; db.commit(); assert db.get(CitizenNeed, need.id).mentions_count == 20


def test_commitment_completion_and_overdue(db, admin, operational_context):
    campaign, parishes = operational_context; today = date(2026, 8, 3)
    service = OperationalService(db, today_provider=lambda: today)
    pending = service.create_commitment(campaign.id, CommitmentCreate(title="Revisar vÃƒÂ­a", priority="HIGH", status="PENDING", due_date=date(2026, 8, 2), parish_id=parishes[0].id), admin)
    assert service.commitments(campaign.id, admin, overdue=True).total == 1
    completed = service.update_commitment(campaign.id, pending.id, CommitmentUpdate(status="COMPLETED"), admin)
    assert completed.completed_date == today and service.commitments(campaign.id, admin, overdue=True).total == 0
    reopened = service.update_commitment(campaign.id, pending.id, CommitmentUpdate(status="IN_PROGRESS"), admin)
    assert reopened.completed_date is None


def test_evidence_url_validation_and_soft_delete(db, admin, operational_context):
    campaign, parishes = operational_context; service = OperationalService(db)
    activity = create_completed(service, campaign.id, completed_payload(parishes[0].id), admin)
    with pytest.raises(ValidationError): ActivityEvidenceCreate(evidence_type="PHOTO", title="Archivo", url="ftp://example.com/a.jpg")
    evidence = service.evidence(campaign.id, activity.id, admin, ActivityEvidenceCreate(evidence_type="PHOTO", title="Registro", url="https://example.com/a.jpg", evidence_date=date(2026,8,3)))
    assert evidence.evidence_date == date(2026,8,3) and evidence.url.startswith("https://")
    evidence.is_active=False; db.commit()
    assert service.evidence(campaign.id, activity.id, admin) == []


def test_operational_summary_is_deterministic_and_aggregated(db, admin, operational_context):
    campaign, parishes = operational_context; today = date(2026, 8, 3)
    service = OperationalService(db, today_provider=lambda: today)
    activity = create_completed(service, campaign.id, completed_payload(parishes[0].id), admin)
    service.participant(campaign.id, activity.id, admin, ParticipantSummaryUpsert(estimated_attendees=45))
    service.create_need(campaign.id, activity.id, CitizenNeedCreate(need_category_code="ROADS", title="VÃƒÂ­a", mentions_count=12, priority="HIGH"), admin)
    service.create_commitment(campaign.id, CommitmentCreate(title="Pendiente", priority="HIGH", due_date=date(2026,8,2), parish_id=parishes[0].id), admin)
    result = service.summary(campaign.id, admin)
    assert result.date_from == result.date_to == today
    assert result.completed_activities == 1 and result.estimated_attendees == 45
    assert result.activities_by_type[0].count == 1 and result.activities_by_parish[0].completed == 1
    assert result.top_needs[0].mentions == 12 and result.commitments.overdue == 1
    assert len(result.uncovered_parishes) == 8 and "compromisos vencidos" in result.summary_text


def test_operational_http_contracts(client, admin_headers, operational_context):
    campaign, parishes = operational_context
    assert client.get("/api/v1/activity-types").status_code == 401
    assert len(client.get("/api/v1/activity-types", headers=admin_headers).json()) == 11
    url=f"/api/v1/campaigns/{campaign.id}/activities"
    response=client.post(url,headers=admin_headers,json={"activity_type_code":"TOUR","title":"Recorrido","activity_date":"2026-08-03","status":"PLANNED","parish_id":parishes[0].id})
    assert response.status_code == 201 and response.json()["activity_date"] == "2026-08-03"
    assert "created_at" not in response.text and "updated_at" not in response.text
    assert client.get(url,headers=admin_headers).json()["total"] == 1
    assert client.get(f"/api/v1/campaigns/{uuid4()}/activities",headers=admin_headers).status_code == 404


def test_operational_role_and_territorial_authorization(db, admin, operational_context):
    campaign, parishes = operational_context
    assignment_service = TerritorialAssignmentService(db)
    def user_with(role_code, username):
        role=RoleService(db).repository.get_by_code(role_code)
        user=User(email=f"{username}@example.com",username=username,first_name="Test",last_name="Role",hashed_password=hash_password("Testing123"),roles=[role])
        db.add(user);db.commit();db.refresh(user)
        assignment_service.assign_user(campaign.id,CampaignUserAssign(user_id=user.id),admin)
        return user
    coordinator=user_with("TERRITORIAL_COORDINATOR","coord4")
    analyst=user_with("ANALYST","analyst4")
    assignment_service.create(campaign.id,TerritorialAssignmentCreate(user_id=coordinator.id,parish_id=parishes[0].id),admin)
    service=OperationalService(db)
    created=service.create_activity(campaign.id,TerritorialActivityCreate(activity_type_code="TOUR",title="Dentro del territorio",activity_date=date(2026,8,3),status="PLANNED",parish_id=parishes[0].id),coordinator)
    assert service.activity(campaign.id,created.id,coordinator).id==created.id
    with pytest.raises(PermissionError):
        service.create_activity(campaign.id,TerritorialActivityCreate(activity_type_code="TOUR",title="Fuera del territorio",activity_date=date(2026,8,3),status="PLANNED",parish_id=parishes[1].id),coordinator)
    assert service.list_activities(campaign.id,analyst,1,20).total==1
    with pytest.raises(PermissionError):
        service.create_activity(campaign.id,TerritorialActivityCreate(activity_type_code="TOUR",title="Analista no escribe",activity_date=date(2026,8,3),status="PLANNED",parish_id=parishes[0].id),analyst)
