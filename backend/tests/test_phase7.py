from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.schemas.campaign import CampaignCreate
from app.schemas.dashboard import DashboardFilters, DashboardPeriod
from app.schemas.operational import CommitmentCreate, CitizenNeedCreate, ParticipantSummaryUpsert, TerritorialActivityCreate
from app.scripts.seed_gualaceo import seed as seed_gualaceo
from app.services.campaign_service import CampaignService
from app.services.dashboard_filter_service import DashboardFilterService
from app.services.dashboard_service import DashboardService
from app.services.operational_service import OperationalService
from app.services.activity_catalog_service import seed as seed_catalogs
from app.core.security import hash_password
from app.models.assignments import CampaignUser, TerritorialAssignment
from app.models.user import User
from app.services.role_service import RoleService


@pytest.fixture
def dashboard_context(db: Session, admin):
    _, canton, parishes = seed_gualaceo(db)
    seed_catalogs(db); db.commit()
    campaign = CampaignService(db).create(CampaignCreate(
        name="Dashboard Gualaceo", slug="dashboard-gualaceo", canton_id=canton.id,
        office_type="MAYOR", election_name="Seccionales 2027",
        election_date=date(2027, 2, 14), start_date=date(2026, 7, 1), status="DRAFT",
    ), admin)
    return campaign, parishes


def test_dashboard_periods_and_previous(db, dashboard_context):
    campaign, _ = dashboard_context
    service = DashboardFilterService(db, lambda: date(2026, 8, 3))
    week = service.resolve_period(campaign, DashboardFilters(period=DashboardPeriod.THIS_WEEK))
    assert week.date_from == week.date_to == date(2026, 8, 3)
    seven = service.resolve_period(campaign, DashboardFilters(period=DashboardPeriod.LAST_7_DAYS, compare_previous_period=True))
    assert seven.date_from == date(2026, 7, 28) and seven.previous_date_from == date(2026, 7, 21)
    assert seven.previous_date_to == date(2026, 7, 27)


def test_dashboard_overview_empty_is_controlled(db, admin, dashboard_context):
    campaign, parishes = dashboard_context
    result = DashboardService(db, lambda: date(2026, 8, 3)).overview(campaign.id, admin, DashboardFilters())
    metrics = {x.code: x.value for x in result["metrics"]}
    assert metrics["completed_activities"] == 0
    assert metrics["parish_coverage_rate"] == 0
    assert result["period"].date_to == date(2026, 8, 3)
    assert "created_at" not in str(result) and "prediction" not in str(result).lower()


def test_dashboard_aggregates_operations(db, admin, dashboard_context):
    campaign, parishes = dashboard_context; ops = OperationalService(db, today_provider=lambda: date(2026,8,3))
    activity = ops.create_activity(campaign.id, TerritorialActivityCreate(activity_type_code="TOUR", title="Recorrido", activity_date=date(2026,8,3), status="COMPLETED", parish_id=parishes[0].id), admin)
    ops.participant(campaign.id, activity.id, admin, ParticipantSummaryUpsert(estimated_attendees=25))
    ops.create_need(campaign.id, activity.id, CitizenNeedCreate(need_category_code="ROADS", title="Vialidad", mentions_count=7, priority="HIGH"), admin)
    ops.create_commitment(campaign.id, CommitmentCreate(title="Pendiente", priority="HIGH", due_date=date(2026,8,2), parish_id=parishes[0].id), admin)
    result = DashboardService(db, lambda: date(2026,8,3)).overview(campaign.id, admin, DashboardFilters())
    values = {x.code:x.value for x in result["metrics"]}
    assert values["completed_activities"] == 1 and values["estimated_attendees"] == 25
    assert values["need_mentions"] == 7 and values["overdue_commitments"] == 1
    assert result["territorial_coverage"]["coverage_rate"] > 0


def test_dashboard_trends_day_week_month(db, admin, dashboard_context):
    campaign, parishes = dashboard_context; ops=OperationalService(db)
    ops.create_activity(campaign.id, TerritorialActivityCreate(activity_type_code="TOUR",title="A",activity_date=date(2026,8,3),status="COMPLETED",parish_id=parishes[0].id),admin)
    service=DashboardService(db,lambda:date(2026,8,3));filters=DashboardFilters(period="LAST_7_DAYS")
    assert service.activity_trends(campaign.id,admin,filters,"DAY",True)["points"][0]["period_start"] == date(2026,7,28)
    assert service.activity_trends(campaign.id,admin,filters,"WEEK")["points"][0]["period_start"] == date(2026,8,3)
    assert service.activity_trends(campaign.id,admin,filters,"MONTH")["points"][0]["period_start"] == date(2026,8,1)


def test_dashboard_http_endpoints_and_auth(client:TestClient, admin_headers, dashboard_context):
    campaign,_=dashboard_context;base=f"/api/v1/campaigns/{campaign.id}/dashboard"
    endpoints=["/filter-options","/overview","/territories","/activity-trends","/needs","/commitments","/surveys","/electoral-history","/demographics","/data-quality",""]
    for endpoint in endpoints:
        response=client.get(base+endpoint,headers=admin_headers)
        assert response.status_code==200,(endpoint,response.text)
        body=response.text
        assert "created_at" not in body and "submission_key_hash" not in body and "response_id" not in body
    assert client.get(base+"/overview").status_code==401


def test_custom_period_validation(client,admin_headers,dashboard_context):
    campaign,_=dashboard_context;base=f"/api/v1/campaigns/{campaign.id}/dashboard/overview"
    assert client.get(base+"?period=CUSTOM",headers=admin_headers).status_code==422
    assert client.get(base+"?date_from=2026-08-03&date_to=2026-08-01",headers=admin_headers).status_code==422


def test_survey_dashboard_contains_only_aggregates(db,admin,dashboard_context):
    campaign,_=dashboard_context
    result=DashboardService(db,lambda:date(2026,8,3)).surveys(campaign.id,admin,DashboardFilters())
    assert result["contains_individual_responses"] is False
    assert result["contains_open_text"] is False
    assert "hash" not in str(result).lower()


def test_data_quality_uses_explicit_issues_not_score(db,admin,dashboard_context):
    campaign,_=dashboard_context
    result=DashboardService(db,lambda:date(2026,8,3)).data_quality(campaign.id,admin,DashboardFilters())
    assert result["status"] in {"OK","WARNING"}
    assert "score" not in result


def test_unassigned_user_is_forbidden(db, dashboard_context):
    campaign,_=dashboard_context;role=RoleService(db).repository.get_by_code("ANALYST")
    user=User(email="outside@example.com",username="outside",first_name="Out",last_name="Side",hashed_password=hash_password("Outside123"),is_active=True,is_superuser=False,roles=[role]);db.add(user);db.commit()
    with pytest.raises(PermissionError):DashboardService(db).overview(campaign.id,user,DashboardFilters())


def test_coordinator_scope_is_limited_to_assigned_parish(db,admin,dashboard_context):
    campaign,parishes=dashboard_context;role=RoleService(db).repository.get_by_code("TERRITORIAL_COORDINATOR")
    user=User(email="coord@example.com",username="coord",first_name="Co",last_name="Ord",hashed_password=hash_password("Coord123"),is_active=True,is_superuser=False,roles=[role]);db.add(user);db.flush()
    db.add(CampaignUser(campaign_id=campaign.id,user_id=user.id,assigned_by_user_id=admin.id,is_active=True));db.add(TerritorialAssignment(campaign_id=campaign.id,user_id=user.id,parish_id=parishes[1].id,assigned_by_user_id=admin.id,is_active=True));db.commit()
    result=DashboardService(db,lambda:date(2026,8,3)).territories(campaign.id,user,DashboardFilters(),"PARISH")
    assert result["total"]==1 and result["items"][0]["id"]==parishes[1].id
    with pytest.raises(PermissionError):DashboardService(db).overview(campaign.id,user,DashboardFilters(parish_id=parishes[0].id))