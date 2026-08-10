from datetime import date,timedelta
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.core.security import create_access_token,hash_password
from app.models.assignments import CampaignUser,TerritorialAssignment
from app.models.campaign import Campaign
from app.models.candidate import Candidate
from app.models.territory import Canton,Community,Parish,Province,Sector
from app.models.user import User
from app.schemas.campaign import CampaignCreate,CampaignUserAssign,CandidateCreate,TerritorialAssignmentCreate
from app.schemas.territory import CommunityCreate,SectorCreate
from app.scripts.seed_gualaceo import PARISHES,seed
from app.services.campaign_service import CampaignService
from app.services.candidate_service import CandidateService
from app.services.exceptions import BusinessRuleError,ConflictError
from app.services.role_service import RoleService
from app.services.territorial_assignment_service import TerritorialAssignmentService
from app.services.territory_service import TerritoryService

@pytest.fixture
def territory(db:Session):
    result=seed(db);db.commit();return result
@pytest.fixture
def campaign(db,admin,territory):
    return CampaignService(db).create(CampaignCreate(name="Elecciones Seccionales 2027 - Gualaceo",slug="seccionales-2027-gualaceo",canton_id=territory[1].id,office_type="MAYOR",election_name="Elecciones Seccionales 2027",election_date=date(2027,2,14),status="DRAFT"),admin)
def make_user(db,code,name):
    role=RoleService(db).repository.get_by_code(code);u=User(email=f"{name}@example.com",username=name,first_name=name,last_name="Test",hashed_password=hash_password("Testing123"),roles=[role]);db.add(u);db.commit();db.refresh(u);return u
def headers(user):return {"Authorization":f"Bearer {create_access_token(user.id)}"}

def test_seed_gualaceo_idempotent(db):
    seed(db);seed(db);db.commit()
    assert db.scalar(select(func.count()).select_from(Province))==1
    assert db.scalar(select(func.count()).select_from(Canton))==1
    assert db.scalar(select(func.count()).select_from(Parish))==9
    rows=list(db.scalars(select(Parish).order_by(Parish.dpa_code)))
    assert [r.dpa_code for r in rows]==[x[0] for x in PARISHES]
    assert rows[0].parish_type=="URBAN" and all(r.parish_type=="RURAL" for r in rows[1:])
    assert rows[0].dpa_code.startswith("0") and {r.dpa_code for r in rows}.isdisjoint({"010351","010355"})

def test_territory_endpoints_and_duplicates(client,admin_headers,territory):
    assert client.get("/api/v1/provinces",headers=admin_headers).json()[0]["code"]=="01"
    assert client.get("/api/v1/cantons",headers=admin_headers).json()[0]["dpa_code"]=="0103"
    assert len(client.get("/api/v1/parishes",headers=admin_headers).json())==9
    payload={"province_id":territory[0].id,"code":"03","dpa_code":"0103","name":"Gualaceo"}
    assert client.post("/api/v1/cantons",headers=admin_headers,json=payload).status_code==409
    p=territory[2][0];duplicate={"canton_id":p.canton_id,"code":p.code,"dpa_code":p.dpa_code,"name":p.name,"parish_type":p.parish_type}
    assert client.post("/api/v1/parishes",headers=admin_headers,json=duplicate).status_code==409

@pytest.mark.parametrize("lat,lon",[(91,0),(0,181),(None,1)])
def test_coordinate_validation(client,admin_headers,territory,lat,lon):
    response=client.post("/api/v1/communities",headers=admin_headers,json={"parish_id":territory[2][0].id,"name":"Centro","latitude":lat,"longitude":lon})
    assert response.status_code==422

def test_community_sector_duplicates(client,admin_headers,territory):
    p=territory[2][0];data={"parish_id":p.id,"name":"Centro","latitude":-2.9,"longitude":-78.78}
    first=client.post("/api/v1/communities",headers=admin_headers,json=data);assert first.status_code==201
    assert client.post("/api/v1/communities",headers=admin_headers,json={**data,"name":"centro"}).status_code==409
    community=first.json()["id"];sector={"community_id":community,"name":"Norte"}
    assert client.post("/api/v1/sectors",headers=admin_headers,json=sector).status_code==201
    assert client.post("/api/v1/sectors",headers=admin_headers,json={**sector,"name":"norte"}).status_code==409

def test_campaign_dates_and_duplicate(db,admin,territory,campaign):
    assert campaign.election_date==date(2027,2,14)
    with pytest.raises(ConflictError):CampaignService(db).create(CampaignCreate(name="Otra",slug=campaign.slug,canton_id=territory[1].id,office_type="MAYOR",election_name="Elección",election_date=date(2027,2,14)),admin)
    with pytest.raises(ValueError):CampaignCreate(name="X",slug="x",canton_id=territory[1].id,office_type="MAYOR",election_name="E",election_date=date(2027,2,14),start_date=date(2027,3,1),end_date=date(2027,2,1))

def test_campaign_access_idor(client,db,admin,admin_headers,campaign):
    analyst=make_user(db,"ANALYST","analyst3");other=make_user(db,"ANALYST","other3")
    TerritorialAssignmentService(db).assign_user(campaign.id,CampaignUserAssign(user_id=analyst.id),admin)
    assert client.get(f"/api/v1/campaigns/{campaign.id}",headers=headers(analyst)).status_code==200
    assert client.get(f"/api/v1/campaigns/{campaign.id}",headers=headers(other)).status_code==403
    assert client.patch(f"/api/v1/campaigns/{campaign.id}",headers=headers(analyst),json={"name":"Hack"}).status_code==403
    assert client.get("/api/v1/campaigns",headers=headers(analyst)).json()["total"]==1
    assert client.get("/api/v1/campaigns",headers=headers(other)).json()["total"]==0

def test_candidate_rules_and_dates(client,db,admin,admin_headers,campaign):
    candidate=make_user(db,"CANDIDATE","candidate3")
    TerritorialAssignmentService(db).assign_user(campaign.id,CampaignUserAssign(user_id=candidate.id),admin)
    data={"user_id":str(candidate.id),"first_name":"María","last_name":"Pérez","display_name":"María Pérez","birth_date":"1980-04-03","photo_url":"https://example.com/photo.jpg"}
    response=client.post(f"/api/v1/campaigns/{campaign.id}/candidate",headers=admin_headers,json=data)
    assert response.status_code==201 and response.json()["birth_date"]=="1980-04-03"
    assert "created_at" not in response.text and "updated_at" not in response.text
    assert client.post(f"/api/v1/campaigns/{campaign.id}/candidate",headers=admin_headers,json={**data,"user_id":None}).status_code==409
    assert client.post(f"/api/v1/campaigns/{campaign.id}/candidate",headers=admin_headers,json={**data,"birth_date":str(date.today()+timedelta(days=1))}).status_code==422

def test_candidate_user_requires_role(db,admin,campaign):
    analyst=make_user(db,"ANALYST","wrongcandidate");TerritorialAssignmentService(db).assign_user(campaign.id,CampaignUserAssign(user_id=analyst.id),admin)
    with pytest.raises(BusinessRuleError):CandidateService(db).create(campaign.id,CandidateCreate(user_id=analyst.id,first_name="A",last_name="B",display_name="A B"),admin)

def test_territorial_hierarchy_and_removal(db,admin,territory,campaign):
    coordinator=make_user(db,"TERRITORIAL_COORDINATOR","coord3");svc=TerritorialAssignmentService(db);svc.assign_user(campaign.id,CampaignUserAssign(user_id=coordinator.id),admin)
    community=TerritoryService(db).create_community(CommunityCreate(parish_id=territory[2][0].id,name="Comunidad Uno"));sector=TerritoryService(db).create_sector(SectorCreate(community_id=community.id,name="Sector Uno"))
    assignment=svc.create(campaign.id,TerritorialAssignmentCreate(user_id=coordinator.id,parish_id=territory[2][0].id,community_id=community.id,sector_id=sector.id),admin)
    assert svc.list(campaign.id,coordinator)[0].id==assignment.id
    with pytest.raises(ConflictError):svc.create(campaign.id,TerritorialAssignmentCreate(user_id=coordinator.id,parish_id=territory[2][0].id,community_id=community.id,sector_id=sector.id),admin)
    with pytest.raises(BusinessRuleError):svc.create(campaign.id,TerritorialAssignmentCreate(user_id=coordinator.id,parish_id=territory[2][0].id,sector_id=sector.id),admin)
    svc.remove(campaign.id,assignment.id,admin);reactivated=svc.create(campaign.id,TerritorialAssignmentCreate(user_id=coordinator.id,parish_id=territory[2][0].id,community_id=community.id,sector_id=sector.id),admin)
    assert reactivated.id==assignment.id and reactivated.is_active
    svc.remove_user(campaign.id,coordinator.id,admin);assert not assignment.is_active

def test_campaign_requires_auth(client):assert client.get("/api/v1/campaigns").status_code==401
