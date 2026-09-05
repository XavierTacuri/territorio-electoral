from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from app.core.security import hash_password
from app.models.assignments import CampaignUser
from app.models.campaign import Campaign
from app.models.organization import Organization, OrganizationMembership, OrganizationSubscription
from app.models.territory import Canton, Province
from app.models.user import User
from app.services.organization_service import OrganizationAccessService, OrganizationError, PlanLimitService, SubscriptionService
from app.services.campaign_access_service import CampaignAccessService
from app.services.role_service import RoleService
from app.schemas.campaign import CampaignUserAssign
from app.services.territorial_assignment_service import TerritorialAssignmentService


def _organization(db, name, plan="STANDARD", max_campaigns=None, max_users=None):
    organization = Organization(name=name, slug=f"{name.lower()}-{uuid4().hex[:6]}")
    db.add(organization); db.flush()
    db.add(OrganizationSubscription(
        organization_id=organization.id, plan_code=plan, status="ACTIVE",
        max_campaigns=max_campaigns, max_users=max_users,
    ))
    db.flush()
    return organization


def _user(db, username):
    role = RoleService(db).repository.get_by_code("ANALYST")
    user = User(
        email=f"{username}@example.test", username=username, first_name=username,
        last_name="V28", hashed_password=hash_password("MemberPass123"),
        is_active=True, roles=[role],
    )
    db.add(user); db.flush()
    return user


def _campaign(db, admin, organization, index):
    province = Province(id=800 + index, code=f"{80 + index:02}", name=f"Provincia SaaS {index}")
    db.add(province); db.flush()
    canton = Canton(id=800 + index, province_id=province.id, code=f"{index:02}", dpa_code=f"{80 + index:02}{index:02}", name=f"Cantón SaaS {index}")
    db.add(canton); db.flush()
    campaign = Campaign(
        organization_id=organization.id, name=f"Campaña SaaS {index}",
        slug=f"saas-{index}-{uuid4().hex[:6]}", canton_id=canton.id,
        office_type="MAYOR", election_name="Elección 2027",
        election_date=date(2027, 2, index), status="ACTIVE",
        created_by_user_id=admin.id,
    )
    db.add(campaign); db.flush()
    return campaign


def _headers(client, user):
    response = client.post("/api/v1/auth/login", data={"username": user.username, "password": "MemberPass123"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_cross_organization_campaign_access_is_denied(client, db, admin):
    alpha = _organization(db, "Alpha", "PRO")
    beta = _organization(db, "Beta")
    alpha_user = _user(db, "alpha-owner")
    db.add(OrganizationMembership(organization_id=alpha.id, user_id=alpha_user.id, organization_role="OWNER"))
    campaign_a = _campaign(db, admin, alpha, 1)
    campaign_b = _campaign(db, admin, beta, 2)
    db.add(CampaignUser(campaign_id=campaign_a.id, user_id=alpha_user.id, assigned_by_user_id=admin.id))
    db.commit()

    headers = _headers(client, alpha_user)
    listing = client.get("/api/v1/campaigns", headers=headers)
    assert listing.status_code == 200
    assert {row["id"] for row in listing.json()["items"]} == {str(campaign_a.id)}
    denied = client.get(f"/api/v1/campaigns/{campaign_b.id}", headers=headers)
    assert denied.status_code == 403


def test_organization_admin_cannot_forge_campaign_organization(client, db, admin):
    alpha = _organization(db, "Alpha Create", max_campaigns=2)
    beta = _organization(db, "Beta Create")
    owner = _user(db, "alpha-create-owner")
    db.add(OrganizationMembership(organization_id=alpha.id, user_id=owner.id, organization_role="OWNER"))
    _campaign(db, admin, alpha, 3)
    beta_campaign = _campaign(db, admin, beta, 4)
    db.commit()
    payload = {
        "organization_id": str(beta.id), "name": "Campaña forjada", "slug": "forged-v28",
        "canton_id": beta_campaign.canton_id, "office_type": "MAYOR",
        "election_name": "Elección", "election_date": "2027-03-01", "status": "DRAFT",
    }
    denied = client.post("/api/v1/campaigns", json=payload, headers=_headers(client, owner))
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "ORGANIZATION_ACCESS_DENIED"


def test_plan_campaign_and_user_limits_are_enforced(db, admin):
    organization = _organization(db, "Limited", max_campaigns=1, max_users=1)
    first = _user(db, "limited-first")
    second = _user(db, "limited-second")
    db.add(OrganizationMembership(organization_id=organization.id, user_id=first.id, organization_role="OWNER"))
    _campaign(db, admin, organization, 5); db.commit()
    limits = PlanLimitService(db)
    try:
        limits.require_campaign_slot(organization.id)
        assert False, "campaign limit was not enforced"
    except OrganizationError as exc:
        assert exc.code == "PLAN_CAMPAIGN_LIMIT_REACHED" and exc.status_code == 409
    try:
        limits.require_user_slot(organization.id, second.id)
        assert False, "user limit was not enforced"
    except OrganizationError as exc:
        assert exc.code == "PLAN_USER_LIMIT_REACHED" and exc.status_code == 409


def test_suspended_organization_blocks_member_but_not_platform_admin(db, admin):
    organization = _organization(db, "Suspended")
    member = _user(db, "suspended-member")
    db.add(OrganizationMembership(organization_id=organization.id, user_id=member.id, organization_role="MEMBER"))
    organization.status = "SUSPENDED"; db.commit()
    try:
        OrganizationAccessService(db).require_access(organization.id, member)
        assert False, "suspended organization remained operational"
    except OrganizationError as exc:
        assert exc.code == "ORGANIZATION_SUSPENDED"
    assert OrganizationAccessService(db).require_access(organization.id, admin).id == organization.id


def test_organization_owner_has_full_territorial_scope_in_own_campaign(db, admin):
    organization = _organization(db, "Territorial owner")
    owner = _user(db, "territorial-owner")
    db.add(OrganizationMembership(organization_id=organization.id, user_id=owner.id, organization_role="OWNER"))
    campaign = _campaign(db, admin, organization, 6); db.commit()
    assert CampaignAccessService(db).territorial_ids(campaign.id, owner) is None


def test_trial_expiration_is_evaluated_dynamically(db):
    organization = _organization(db, "Trial", "PRO")
    subscription = SubscriptionService(db).get(organization.id)
    subscription.status = "TRIAL"
    subscription.trial_ends_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert SubscriptionService(db).effective(subscription) is False


def test_campaign_assignment_creates_minimum_membership_and_grants_access(client, db, admin):
    organization = _organization(db, "Assignment membership", max_users=2)
    user = _user(db, "assignment-member")
    campaign = _campaign(db, admin, organization, 7); db.commit()

    assigned = TerritorialAssignmentService(db).assign_user(
        campaign.id, CampaignUserAssign(user_id=user.id), admin,
    )

    membership = db.scalar(select(OrganizationMembership).where(
        OrganizationMembership.organization_id == organization.id,
        OrganizationMembership.user_id == user.id,
    ))
    assert assigned.is_active is True
    assert membership is not None
    assert membership.organization_role == "MEMBER"
    assert membership.status == "ACTIVE"
    assert campaign.id in CampaignAccessService(db).accessible_ids(user)
    listing = client.get("/api/v1/campaigns", headers=_headers(client, user))
    assert listing.status_code == 200
    assert str(campaign.id) in {item["id"] for item in listing.json()["items"]}


def test_campaign_assignment_preserves_admin_membership_and_removal_keeps_it(db, admin):
    organization = _organization(db, "Assignment admin")
    user = _user(db, "assignment-admin")
    membership = OrganizationMembership(
        organization_id=organization.id, user_id=user.id,
        organization_role="ADMIN", status="ACTIVE",
    )
    db.add(membership)
    campaign = _campaign(db, admin, organization, 8); db.commit()

    TerritorialAssignmentService(db).assign_user(
        campaign.id, CampaignUserAssign(user_id=user.id), admin,
    )
    assert membership.organization_role == "ADMIN"
    TerritorialAssignmentService(db).remove_user(campaign.id, user.id, admin)
    assert membership.status == "ACTIVE"
    assert membership.organization_role == "ADMIN"


def test_platform_admin_cross_org_assignment_creates_beta_membership(client, db, admin):
    alpha = _organization(db, "Assignment Alpha")
    beta = _organization(db, "Assignment Beta")
    user = _user(db, "assignment-cross-org")
    db.add(OrganizationMembership(
        organization_id=alpha.id, user_id=user.id,
        organization_role="MEMBER", status="ACTIVE",
    ))
    campaign = _campaign(db, admin, beta, 9); db.commit()

    denied = client.post(
        f"/api/v1/campaigns/{campaign.id}/users",
        json={"user_id": str(user.id)}, headers=_headers(client, user),
    )
    assert denied.status_code == 403

    TerritorialAssignmentService(db).assign_user(
        campaign.id, CampaignUserAssign(user_id=user.id), admin,
    )

    beta_membership = db.scalar(select(OrganizationMembership).where(
        OrganizationMembership.organization_id == beta.id,
        OrganizationMembership.user_id == user.id,
    ))
    assert beta_membership.organization_role == "MEMBER"
    assert beta_membership.status == "ACTIVE"
    assert campaign.id in CampaignAccessService(db).accessible_ids(user)


def test_campaign_assignment_honors_user_limit_without_orphan(client, db, admin, admin_headers):
    organization = _organization(db, "Assignment limit", max_users=1)
    existing = _user(db, "assignment-existing")
    external = _user(db, "assignment-external")
    db.add(OrganizationMembership(
        organization_id=organization.id, user_id=existing.id,
        organization_role="MEMBER", status="ACTIVE",
    ))
    campaign = _campaign(db, admin, organization, 10); db.commit()

    response = client.post(
        f"/api/v1/campaigns/{campaign.id}/users",
        json={"user_id": str(external.id)}, headers=admin_headers,
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PLAN_USER_LIMIT_REACHED"

    assert db.scalar(select(CampaignUser).where(
        CampaignUser.campaign_id == campaign.id,
        CampaignUser.user_id == external.id,
    )) is None
