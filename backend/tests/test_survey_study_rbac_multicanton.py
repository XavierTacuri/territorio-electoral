from datetime import date
from uuid import UUID, uuid4

import pytest

from app.core.security import hash_password
from app.models.assignments import CampaignUser
from app.models.campaign import Campaign
from app.models.organization import Organization, OrganizationMembership, OrganizationSubscription
from app.models.territory import Canton, Parish, Province
from app.models.user import User
from app.models.survey_study import SurveyStudy
from app.services.role_service import RoleService


def user_for(db, role_code, suffix):
    role = RoleService(db).repository.get_by_code(role_code)
    user = User(email=f"{suffix}@example.test", username=suffix, first_name=suffix, last_name="Test", hashed_password=hash_password("Pass123!x"), is_active=True, roles=[role])
    db.add(user); db.flush(); return user


def login(client, username):
    response = client.post("/api/v1/auth/login", data={"username": username, "password": "Pass123!x"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def general_payload(code="GENERAL_A"):
    return {"code": code, "name": "Encuesta general", "study_type": "GENERAL_SURVEY", "fieldwork_start_date": "2026-08-01", "fieldwork_end_date": "2026-08-05", "geography_level": "CANTON", "sample_size_total": 800, "universe_description": "Universo cantonal", "sampling_method": "Estudio agregado sintético", "collection_method": "Resultados agregados", "source_type": "ESTUDIO", "is_official": False}


def cne_payload():
    return {**general_payload("CNE_EXIT_A"), "name": "Exit poll sintético", "study_type": "CNE_EXIT_POLL", "publication_date": "2026-08-06", "election_process_id": str(uuid4()), "source_name": "Referencia CNE verificable", "source_url": "https://example.test/cne-exit", "source_document": "Documento sintético"}


def setup(db, admin):
    db.add_all([Province(id=1, code="01", name="Azuay"), Province(id=17, code="17", name="Pichincha")]); db.flush()
    db.add_all([Canton(id=103, province_id=1, code="03", dpa_code="0103", name="Gualaceo"), Canton(id=101, province_id=1, code="01", dpa_code="0101", name="Cuenca"), Canton(id=1701, province_id=17, code="01", dpa_code="1701", name="Distrito Metropolitano de Quito")]); db.flush()
    parishes=[Parish(id=10350,canton_id=103,code="50",dpa_code="010350",name="Gualaceo",parish_type="URBAN"),Parish(id=10150,canton_id=101,code="50",dpa_code="010150",name="Cuenca",parish_type="URBAN"),Parish(id=170150,canton_id=1701,code="50",dpa_code="170150",name="Quito",parish_type="URBAN")];db.add_all(parishes);db.flush()
    campaigns=[]
    for canton,slug in ((103,"gualaceo"),(101,"cuenca"),(1701,"quito")):
        campaign=Campaign(name=slug.title(),slug=slug,canton_id=canton,office_type="MAYOR",election_name="Elección sintética",election_date=date(2027,2,7),status="ACTIVE",created_by_user_id=admin.id);db.add(campaign);db.flush();campaigns.append(campaign)
    return campaigns,parishes


@pytest.mark.parametrize("role", ["CANDIDATE", "CAMPAIGN_MANAGER", "TERRITORIAL_COORDINATOR"])
def test_general_survey_write_forbidden_roles(client, db, admin, role):
    campaigns,_=setup(db,admin);user=user_for(db,role,f"user_{role.lower()}");db.add(CampaignUser(campaign_id=campaigns[0].id,user_id=user.id,assigned_by_user_id=admin.id));db.commit()
    assert client.post(f"/api/v1/campaigns/{campaigns[0].id}/survey-studies",json=general_payload(),headers=login(client,user.username)).status_code==403


def test_analyst_scope_and_cne_admin_only(client, db, admin, admin_headers):
    campaigns,_=setup(db,admin);analyst=user_for(db,"ANALYST","analyst_scope");db.add(CampaignUser(campaign_id=campaigns[0].id,user_id=analyst.id,assigned_by_user_id=admin.id));db.commit();headers=login(client,analyst.username)
    assert client.post(f"/api/v1/campaigns/{campaigns[0].id}/survey-studies",json=general_payload(),headers=headers).status_code==201
    assert client.post(f"/api/v1/campaigns/{campaigns[1].id}/survey-studies",json=general_payload("OUTSIDE"),headers=headers).status_code==403
    assert client.post(f"/api/v1/campaigns/{campaigns[0].id}/survey-studies",json=cne_payload(),headers=headers).status_code==403
    assert client.post(f"/api/v1/campaigns/{campaigns[0].id}/survey-studies",json=cne_payload(),headers=admin_headers).status_code==201


def test_multicanton_parish_rejected(client, db, admin, admin_headers):
    campaigns,parishes=setup(db,admin)
    for campaign in campaigns:
        response=client.post(f"/api/v1/campaigns/{campaign.id}/survey-studies",json={**general_payload(f"GENERAL_{campaign.slug.upper()}"),"geography_level":"PARISH"},headers=admin_headers);assert response.status_code==201
        wrong=parishes[1] if campaign.canton_id!=101 else parishes[0]
        assert client.post(f"/api/v1/survey-studies/{response.json()['id']}/territories",json={"parish_id":wrong.id,"sample_size":800},headers=admin_headers).status_code==400


def test_organization_admin_without_global_capability_cannot_write(client, db, admin):
    campaigns,_=setup(db,admin);organization=Organization(id=campaigns[0].organization_id,name="Organización sintética",slug="org-survey-rbac",status="ACTIVE");db.add(organization);db.flush();db.add(OrganizationSubscription(organization_id=organization.id,plan_code="PRO",status="ACTIVE"));member=user_for(db,"CANDIDATE","organization_admin_only");db.add(OrganizationMembership(organization_id=organization.id,user_id=member.id,organization_role="ADMIN",status="ACTIVE"));db.commit();headers=login(client,member.username)
    assert client.post(f"/api/v1/campaigns/{campaigns[0].id}/survey-studies",json=general_payload(),headers=headers).status_code==403
    assert client.post(f"/api/v1/campaigns/{campaigns[0].id}/survey-studies",json=cne_payload(),headers=headers).status_code==403


def test_candidate_reads_only_published_inside_campaign(client, db, admin, admin_headers):
    campaigns,_=setup(db,admin);published=client.post(f"/api/v1/campaigns/{campaigns[0].id}/survey-studies",json=general_payload("PUBLISHED"),headers=admin_headers).json();draft=client.post(f"/api/v1/campaigns/{campaigns[0].id}/survey-studies",json=general_payload("DRAFT"),headers=admin_headers).json();db.get(SurveyStudy,UUID(published["id"])).status="PUBLISHED";db.commit();candidate=user_for(db,"CANDIDATE","candidate_reader");db.add(CampaignUser(campaign_id=campaigns[0].id,user_id=candidate.id,assigned_by_user_id=admin.id));db.commit();headers=login(client,candidate.username)
    listing=client.get(f"/api/v1/campaigns/{campaigns[0].id}/survey-studies",headers=headers);assert listing.status_code==200;assert [item["id"] for item in listing.json()["items"]]==[published["id"]]
    assert client.get(f"/api/v1/survey-studies/{draft['id']}",headers=headers).status_code==403
    assert client.get(f"/api/v1/campaigns/{campaigns[1].id}/survey-studies",headers=headers).status_code==403
