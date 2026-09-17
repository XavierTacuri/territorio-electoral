from datetime import date

import pytest

from app.core.security import hash_password
from app.models.survey_study import SurveyStudy
from app.models.user import User
from app.schemas.alerts import AlertEvaluationRequest
from app.schemas.campaign import CampaignCreate, CampaignUserAssign, TerritorialAssignmentCreate
from app.schemas.operational import TerritorialActivityCreate
from app.scripts.seed_gualaceo import seed as seed_territory
from app.scripts.seed_reports_and_alerts import seed as seed_alert_rules
from app.services.activity_catalog_service import seed as seed_catalogs
from app.services.alert_service import AlertService
from app.services.campaign_service import CampaignService
from app.services.operational_service import OperationalService
from app.services.role_service import RoleService
from app.services.territorial_assignment_service import TerritorialAssignmentService


@pytest.fixture
def ctx(db, admin):
    province, canton, parishes = seed_territory(db)
    seed_catalogs(db)
    db.commit()
    campaign = CampaignService(db).create(
        CampaignCreate(
            name="Alertas Candidate/Manager",
            slug="alertas-candidate-manager",
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
            last_name="Test",
            hashed_password=hash_password("Testing123"),
            roles=[roles.repository.get_by_code(code)],
        )
        db.add(obj)
        db.flush()
        return obj

    candidate = user("CANDIDATE", "cma_candidate")
    manager = user("CAMPAIGN_MANAGER", "cma_manager")
    analyst = user("ANALYST", "cma_analyst")
    # A coordinator is needed to actually produce a PENDING_APPROVAL activity:
    # CANDIDATE/CAMPAIGN_MANAGER auto-approve on create (can_approve), so they
    # can never be the ones whose activity generates this alert.
    coordinator = user("TERRITORIAL_COORDINATOR", "cma_coordinator")
    db.commit()
    assignments = TerritorialAssignmentService(db)
    for member in (candidate, manager, analyst, coordinator):
        assignments.assign_user(campaign.id, CampaignUserAssign(user_id=member.id), admin)
    assignments.create(campaign.id, TerritorialAssignmentCreate(user_id=coordinator.id, parish_id=parishes[0].id), admin)
    seed_alert_rules(db)
    db.commit()
    return campaign, parishes, candidate, manager, analyst, coordinator


def _published_study(db, admin, campaign, code, study_type="GENERAL_SURVEY"):
    study = SurveyStudy(
        campaign_id=campaign.id,
        code=code,
        name=f"Estudio {code}",
        study_type=study_type,
        status="PUBLISHED",
        fieldwork_start_date=date(2027, 1, 1),
        fieldwork_end_date=date(2027, 1, 3),
        publication_date=date(2027, 1, 4),
        geography_level="CANTON",
        sample_size_total=400,
        universe_description="Universo cantonal",
        sampling_method="Aleatorio simple",
        collection_method="Telefónica",
        source_type="ESTUDIO",
        created_by_user_id=admin.id,
    )
    db.add(study)
    db.commit()
    return study


def test_survey_published_by_analyst_alerts_candidate_and_manager(db, admin, ctx):
    campaign, parishes, candidate, manager, analyst, coordinator = ctx
    _published_study(db, admin, campaign, "CMA_GENERAL", study_type="GENERAL_SURVEY")
    svc = AlertService(db)
    req = AlertEvaluationRequest(rule_codes=["SURVEY_STUDY_PUBLISHED"], as_of_date=date(2027, 1, 4))
    result = svc.evaluate(campaign.id, admin, req)
    assert result["created"] == 1
    for viewer in (candidate, manager):
        items, total = svc.list(campaign.id, viewer, status="OPEN")
        assert total == 1 and items[0].evidence["name"] == "Estudio CMA_GENERAL"


def test_cne_exit_poll_published_by_admin_also_alerts_candidate_and_manager(db, admin, ctx):
    campaign, parishes, candidate, manager, analyst, coordinator = ctx
    _published_study(db, admin, campaign, "CMA_EXITPOLL", study_type="CNE_EXIT_POLL")
    svc = AlertService(db)
    req = AlertEvaluationRequest(rule_codes=["SURVEY_STUDY_PUBLISHED"], as_of_date=date(2027, 1, 4))
    # The publisher role is irrelevant: PUBLISHED is a state, not a
    # publisher-role check (§25/§26) — evaluated here as admin.
    result = svc.evaluate(campaign.id, admin, req)
    assert result["created"] == 1
    items, _ = svc.list(campaign.id, candidate, status="OPEN")
    assert items[0].evidence["study_type"] == "CNE_EXIT_POLL"


def test_same_publication_reevaluated_does_not_duplicate(db, admin, ctx):
    campaign, parishes, candidate, manager, analyst, coordinator = ctx
    _published_study(db, admin, campaign, "CMA_DEDUP", study_type="GENERAL_SURVEY")
    svc = AlertService(db)
    req = AlertEvaluationRequest(rule_codes=["SURVEY_STUDY_PUBLISHED"], as_of_date=date(2027, 1, 4))
    first = svc.evaluate(campaign.id, admin, req)
    second = svc.evaluate(campaign.id, admin, req)
    assert first["created"] == 1 and second["created"] == 0 and second["unchanged"] == 1
    items, total = svc.list(campaign.id, manager, status="OPEN")
    assert total == 1


def test_candidate_and_manager_never_receive_technical_data_hub_alerts(db, admin, ctx):
    campaign, parishes, candidate, manager, analyst, coordinator = ctx
    svc = AlertService(db)
    # CAMPAIGN_WITHOUT_ACTIVE_ROLL is a Data Hub/data-quality technical
    # condition (§28): it should evaluate and be visible to Admin/Analyst,
    # but never reach Candidate/Manager's Centro de Alertas.
    req = AlertEvaluationRequest(rule_codes=["CAMPAIGN_WITHOUT_ACTIVE_ROLL"], as_of_date=date.today())
    result = svc.evaluate(campaign.id, admin, req)
    assert result["created"] == 1
    admin_items, admin_total = svc.list(campaign.id, admin, status="OPEN")
    assert admin_total == 1
    for viewer in (candidate, manager):
        items, total = svc.list(campaign.id, viewer, status="OPEN")
        assert total == 0 and items == []


def test_candidate_and_manager_see_activity_pending_approval_and_it_resolves(db, admin, ctx):
    campaign, parishes, candidate, manager, analyst, coordinator = ctx
    ops = OperationalService(db)
    activity = ops.create_activity(
        campaign.id,
        TerritorialActivityCreate(
            activity_type_code="ASSEMBLY",
            title="Asamblea sintética",
            description="Objetivo",
            activity_date=date(2027, 1, 10),
            parish_id=parishes[0].id,
            status="PLANNED",
        ),
        coordinator,
    )
    svc = AlertService(db)
    req = AlertEvaluationRequest(rule_codes=["ACTIVITY_PENDING_APPROVAL"], as_of_date=date(2027, 1, 1))
    result = svc.evaluate(campaign.id, manager, req)
    assert result["created"] == 1
    for viewer in (candidate, manager):
        items, total = svc.list(campaign.id, viewer, status="OPEN")
        assert total == 1 and items[0].resource_id == activity.id
    ops.approve_activity(campaign.id, activity.id, manager)
    result2 = svc.evaluate(campaign.id, manager, req)
    assert result2["resolved"] == 1
    items, total = svc.list(campaign.id, candidate, status="OPEN")
    assert total == 0


def test_candidate_manager_alerts_filters_are_limited_to_two_families(db, admin, ctx):
    campaign, parishes, candidate, manager, analyst, coordinator = ctx
    ops = OperationalService(db)
    ops.create_activity(
        campaign.id,
        TerritorialActivityCreate(
            activity_type_code="ASSEMBLY",
            title="Asamblea filtro",
            description="Objetivo",
            activity_date=date(2027, 1, 10),
            parish_id=parishes[0].id,
            status="PLANNED",
        ),
        coordinator,
    )
    _published_study(db, admin, campaign, "CMA_FILTER", study_type="GENERAL_SURVEY")
    svc = AlertService(db)
    svc.evaluate(
        campaign.id,
        admin,
        AlertEvaluationRequest(
            rule_codes=["ACTIVITY_PENDING_APPROVAL", "SURVEY_STUDY_PUBLISHED", "CAMPAIGN_WITHOUT_ACTIVE_ROLL"],
            as_of_date=date(2027, 1, 4),
        ),
    )
    all_items, all_total = svc.list(campaign.id, candidate, status="OPEN")
    assert all_total == 2
    approvals, approvals_total = svc.list(campaign.id, candidate, status="OPEN", condition_type="ACTIVITY_PENDING_APPROVAL")
    assert approvals_total == 1
    studies, studies_total = svc.list(campaign.id, candidate, status="OPEN", condition_type="SURVEY_STUDY_PUBLISHED")
    assert studies_total == 1
