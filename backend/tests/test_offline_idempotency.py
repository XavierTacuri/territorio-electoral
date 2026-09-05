from datetime import date
from uuid import uuid4
import pytest
from app.core.security import hash_password
from app.models.operational import CitizenNeed, TerritorialActivity
from app.models.user import User
from app.schemas.campaign import CampaignCreate, CampaignUserAssign, TerritorialAssignmentCreate
from app.schemas.operational import CitizenNeedCreate, TerritorialActivityCreate
from app.scripts.seed_gualaceo import seed as seed_territory
from app.services.activity_catalog_service import seed as seed_catalogs
from app.services.campaign_service import CampaignService
from app.services.operational_service import OperationalService
from app.services.role_service import RoleService
from app.services.territorial_assignment_service import TerritorialAssignmentService
from sqlalchemy import select


@pytest.fixture
def offline(db, admin):
    _, canton, parishes = seed_territory(db)
    seed_catalogs(db)
    db.commit()
    campaign_a = CampaignService(db).create(
        CampaignCreate(
            name="Offline A",
            slug="offline-idempotency-a",
            canton_id=canton.id,
            office_type="MAYOR",
            election_name="Elección sintética",
            election_date=date(2027, 2, 14),
            status="ACTIVE",
        ),
        admin,
    )
    campaign_b = CampaignService(db).create(
        CampaignCreate(
            name="Offline B",
            slug="offline-idempotency-b",
            canton_id=canton.id,
            office_type="MAYOR",
            election_name="Elección sintética",
            election_date=date(2027, 2, 14),
            status="ACTIVE",
        ),
        admin,
    )
    roles = RoleService(db)

    def user(code, name):
        obj = User(
            email=f"{name}@example.test",
            username=name,
            first_name=name,
            last_name="Offline",
            hashed_password=hash_password("Testing123"),
            roles=[roles.repository.get_by_code(code)],
        )
        db.add(obj)
        db.flush()
        return obj

    coordinator_1 = user("TERRITORIAL_COORDINATOR", "coord_offline_1")
    coordinator_2 = user("TERRITORIAL_COORDINATOR", "coord_offline_2")
    unassigned = user("TERRITORIAL_COORDINATOR", "coord_offline_unassigned")
    db.commit()
    assignments = TerritorialAssignmentService(db)
    for member in (coordinator_1, coordinator_2, unassigned):
        assignments.assign_user(campaign_a.id, CampaignUserAssign(user_id=member.id), admin)
        assignments.assign_user(campaign_b.id, CampaignUserAssign(user_id=member.id), admin)
    assignments.create(
        campaign_a.id, TerritorialAssignmentCreate(user_id=coordinator_1.id, parish_id=parishes[0].id), admin
    )
    assignments.create(
        campaign_a.id, TerritorialAssignmentCreate(user_id=coordinator_2.id, parish_id=parishes[0].id), admin
    )
    assignments.create(
        campaign_b.id, TerritorialAssignmentCreate(user_id=coordinator_1.id, parish_id=parishes[0].id), admin
    )
    return campaign_a, campaign_b, parishes, coordinator_1, coordinator_2, unassigned


def activity_payload(parish_id, client_generated_id, title="Asamblea offline"):
    return TerritorialActivityCreate(
        activity_type_code="ASSEMBLY",
        title=title,
        description="Registrada desde Operación de campo",
        activity_date=date(2026, 8, 20),
        parish_id=parish_id,
        status="PLANNED",
        client_generated_id=client_generated_id,
    )


def need_payload(parish_id, client_generated_id, title="Necesidad offline"):
    return CitizenNeedCreate(
        need_category_code="ROADS",
        title=title,
        description="Registrada desde Operación de campo",
        parish_id=parish_id,
        client_generated_id=client_generated_id,
    )


def test_duplicate_client_generated_id_activity_does_not_duplicate(db, offline):
    campaign_a, _, parishes, coordinator_1, _, _ = offline
    service = OperationalService(db)
    client_id = uuid4()
    first = service.create_activity(campaign_a.id, activity_payload(parishes[0].id, client_id), coordinator_1)
    second = service.create_activity(campaign_a.id, activity_payload(parishes[0].id, client_id), coordinator_1)
    assert first.id == second.id
    rows = list(
        db.scalars(
            select(TerritorialActivity).where(
                TerritorialActivity.campaign_id == campaign_a.id,
                TerritorialActivity.client_generated_id == client_id,
            )
        )
    )
    assert len(rows) == 1


def test_duplicate_client_generated_id_need_does_not_duplicate(db, offline):
    campaign_a, _, parishes, coordinator_1, _, _ = offline
    service = OperationalService(db)
    client_id = uuid4()
    first = service.create_need(campaign_a.id, None, need_payload(parishes[0].id, client_id), coordinator_1)
    second = service.create_need(campaign_a.id, None, need_payload(parishes[0].id, client_id), coordinator_1)
    assert first.id == second.id
    rows = list(
        db.scalars(
            select(CitizenNeed).where(
                CitizenNeed.campaign_id == campaign_a.id, CitizenNeed.client_generated_id == client_id
            )
        )
    )
    assert len(rows) == 1


def test_same_client_generated_id_different_user_no_leakage(db, offline):
    campaign_a, _, parishes, coordinator_1, coordinator_2, _ = offline
    service = OperationalService(db)
    client_id = uuid4()
    mine = service.create_activity(campaign_a.id, activity_payload(parishes[0].id, client_id), coordinator_1)
    other = service.create_activity(
        campaign_a.id, activity_payload(parishes[0].id, client_id, title="Otra asamblea"), coordinator_2
    )
    assert mine.id != other.id
    assert mine.created_by_user_id == coordinator_1.id
    assert other.created_by_user_id == coordinator_2.id


def test_same_client_generated_id_different_campaign_is_isolated(db, offline):
    campaign_a, campaign_b, parishes, coordinator_1, _, _ = offline
    service = OperationalService(db)
    client_id = uuid4()
    in_a = service.create_activity(campaign_a.id, activity_payload(parishes[0].id, client_id), coordinator_1)
    in_b = service.create_activity(
        campaign_b.id, activity_payload(parishes[0].id, client_id, title="Asamblea B"), coordinator_1
    )
    assert in_a.id != in_b.id
    assert in_a.campaign_id == campaign_a.id
    assert in_b.campaign_id == campaign_b.id


def test_coordinator_unassigned_parish_offline_retry_still_403(db, offline):
    campaign_a, _, parishes, _, _, unassigned = offline
    service = OperationalService(db)
    client_id = uuid4()
    with pytest.raises(PermissionError):
        service.create_activity(campaign_a.id, activity_payload(parishes[1].id, client_id), unassigned)
    with pytest.raises(PermissionError):
        service.create_activity(campaign_a.id, activity_payload(parishes[1].id, client_id), unassigned)
