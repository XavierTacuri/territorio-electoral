from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.models.campaign import Campaign
from app.models.historical import DataSource,ElectoralProcess,ElectoralRollSnapshot,ElectoralRollSnapshotEntry,ParticipationProjectionResult,ParticipationProjectionRun
from app.models.territory import Canton,Parish,Province
from app.models.assignments import CampaignUser
from app.models.user import User
from app.core.security import hash_password
from app.services.role_service import RoleService


def _campaign_dataset(db,admin,index,registered,central,snapshot_date):
    province=Province(id=70+index,code=f"{70+index:02}",name=f"Provincia {index}");db.add(province);db.flush()
    canton=Canton(id=70+index,province_id=province.id,code=f"{index:02}",dpa_code=f"{70+index:02}{index:02}",name=f"Cantón {index}");db.add(canton);db.flush()
    parish=Parish(id=700+index,canton_id=canton.id,code="01",dpa_code=f"{canton.dpa_code}01",name="Centro",parish_type="URBAN");db.add(parish);db.flush()
    campaign=Campaign(name=f"Campaña {index}",slug=f"campaign-{index}-{uuid4().hex[:4]}",canton_id=canton.id,office_type="MAYOR",election_name=f"Elección {index}",election_date=date(2027,1,index),status="ACTIVE",created_by_user_id=admin.id);db.add(campaign);db.flush()
    source=DataSource(code=f"V27-{index}-{uuid4().hex[:4]}",institution="Fuente sintética",dataset_name=f"Dataset {index}",dataset_type="CNE_ELECTORAL_ROLL_SNAPSHOT",created_by_user_id=admin.id);db.add(source);db.flush()
    process=ElectoralProcess(code=f"V27-P-{index}-{uuid4().hex[:4]}",name=f"Proceso {index}",process_type="SECTIONAL",election_date=date(2027,1,index),year=2027,status="VALIDATED",is_final=True,source_id=source.id,is_active=True);db.add(process);db.flush()
    snapshot=ElectoralRollSnapshot(source_id=source.id,electoral_process_id=process.id,snapshot_date=snapshot_date,name=f"Snapshot {index}",status="VALIDATED",is_final=True,created_by_user_id=admin.id);db.add(snapshot);db.flush()
    db.add(ElectoralRollSnapshotEntry(snapshot_id=snapshot.id,geography_level="PARISH",province_id=province.id,canton_id=canton.id,parish_id=parish.id,province_dpa=province.code,canton_dpa=canton.dpa_code,parish_dpa=parish.dpa_code,registered_voters=registered,male_voters=registered//2,female_voters=registered-registered//2,electoral_zones=1,juntas=2));db.flush()
    run=ParticipationProjectionRun(campaign_id=campaign.id,electoral_process_id=process.id,snapshot_id=snapshot.id,model_code="TURNOUT_HISTORICAL_WEIGHTED_V1",model_version="1.0",historical_process_ids=[],parameters={},run_date=snapshot_date,created_by_user_id=admin.id);db.add(run);db.flush()
    db.add(ParticipationProjectionResult(run_id=run.id,parish_id=parish.id,registered_voters=registered,turnout_rate_low=Decimal("0.60"),turnout_rate_central=Decimal(str(central/registered)),turnout_rate_high=Decimal("0.80"),expected_voters_low=min(registered,int(registered*.6)),expected_voters_central=central,expected_voters_high=min(registered,int(registered*.8)),data_quality_status="MEDIUM",explanation="Fixture V2.7"));db.commit()
    return campaign,canton,parish


def test_current_election_uses_campaign_run_snapshot_not_latest_global(client,db,admin,admin_headers):
    campaign_a,_,_=_campaign_dataset(db,admin,1,111,77,date(2026,1,1))
    campaign_b,_,_=_campaign_dataset(db,admin,2,999,700,date(2026,12,1))
    response_a=client.get(f"/api/v1/campaigns/{campaign_a.id}/current-election/analysis",headers=admin_headers)
    response_b=client.get(f"/api/v1/campaigns/{campaign_b.id}/current-election/analysis",headers=admin_headers)
    assert response_a.status_code==response_b.status_code==200
    assert response_a.json()["snapshot"]["registered_voters"]==111
    assert response_a.json()["projection"]["expected_voters_central"]==77
    assert response_b.json()["snapshot"]["registered_voters"]==999
    assert response_b.json()["projection"]["expected_voters_central"]==700
    assert response_a.json()["parishes"][0]["name"]==response_b.json()["parishes"][0]["name"]=="Centro"


def test_campaign_member_cannot_read_another_campaign_current_election(client,db,admin):
    campaign_a,_,_=_campaign_dataset(db,admin,3,333,230,date(2026,3,1))
    campaign_b,_,_=_campaign_dataset(db,admin,4,444,310,date(2026,4,1))
    role=RoleService(db).repository.get_by_code("ANALYST")
    user=User(email="v27-a@example.test",username="v27-a",first_name="V27",last_name="A",hashed_password=hash_password("MemberPass123"),is_active=True,roles=[role])
    db.add(user);db.flush()
    db.add(CampaignUser(campaign_id=campaign_a.id,user_id=user.id,assigned_by_user_id=admin.id,is_active=True));db.commit()
    login=client.post("/api/v1/auth/login",data={"username":"v27-a","password":"MemberPass123"})
    headers={"Authorization":f"Bearer {login.json()['access_token']}"}
    assert client.get(f"/api/v1/campaigns/{campaign_a.id}/current-election/analysis",headers=headers).status_code==200
    denied=client.get(f"/api/v1/campaigns/{campaign_b.id}/current-election/analysis",headers=headers)
    assert denied.status_code==403
