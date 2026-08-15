from datetime import date, datetime, timedelta, timezone
from app.main import app
from app.models.campaign import Campaign
from app.schemas.entitlement import EntitlementType, EntitlementUpsert, FeatureCode
from app.services.feature_entitlement_service import FeatureEntitlementService
from app.services.territory_ai_service import ProviderResult, get_ai_provider

class FakeProvider:
    name="fake";available=True
    def __init__(self):self.calls=[]
    def generate(self,question,context):self.calls.append((question,context));return ProviderResult("Respuesta grounded","fake-model",4,3)

def campaign(db,admin,name):
    obj=Campaign(name=name,slug=name.lower().replace(" ","-"),canton_id=1,office_type="MAYOR",election_name="Elección",election_date=date(2027,1,1),status="ACTIVE",created_by_user_id=admin.id)
    db.add(obj);db.commit();return obj

def entitlement(db,admin,campaign_id,kind="LICENSE",starts=None,expires=None):
    return FeatureEntitlementService(db).upsert(campaign_id,EntitlementUpsert(feature_code=FeatureCode.TERRITORY_AI,enabled=True,entitlement_type=EntitlementType(kind),starts_at=starts,expires_at=expires),admin)

def test_standard_api_denied_without_calling_provider(client,db,admin,admin_headers):
    c=campaign(db,admin,"Standard");fake=FakeProvider();app.dependency_overrides[get_ai_provider]=lambda:fake
    response=client.post(f"/api/v1/campaigns/{c.id}/territory-ai/query",headers=admin_headers,json={"question":"¿Qué ocurre?"})
    assert response.status_code==403
    assert response.json()["detail"]["code"]=="FEATURE_NOT_ENTITLED"
    assert fake.calls==[]

def test_license_and_active_trial_call_provider(client,db,admin,admin_headers):
    fake=FakeProvider();app.dependency_overrides[get_ai_provider]=lambda:fake
    for name,kind,expires in (("Pro","LICENSE",None),("Trial","TRIAL",datetime.now(timezone.utc)+timedelta(days=2))):
        c=campaign(db,admin,name);entitlement(db,admin,c.id,kind,expires=expires)
        response=client.post(f"/api/v1/campaigns/{c.id}/territory-ai/query",headers=admin_headers,json={"question":"¿Cuál es la fuente y corte de datos?"})
        assert response.status_code==200
    assert len(fake.calls)==2

def test_expired_trial_is_denied_and_preserves_provider(client,db,admin,admin_headers):
    c=campaign(db,admin,"Expired");now=datetime.now(timezone.utc);entitlement(db,admin,c.id,"TRIAL",now-timedelta(days=2),now-timedelta(days=1));fake=FakeProvider();app.dependency_overrides[get_ai_provider]=lambda:fake
    response=client.post(f"/api/v1/campaigns/{c.id}/territory-ai/query",headers=admin_headers,json={"question":"Consulta vencida"})
    assert response.status_code==403 and response.json()["detail"]["code"]=="FEATURE_NOT_ENTITLED"
    assert not fake.calls

def test_entitlement_isolated_by_campaign(client,db,admin,admin_headers):
    pro=campaign(db,admin,"Campaign A");standard=campaign(db,admin,"Campaign B");entitlement(db,admin,pro.id);fake=FakeProvider();app.dependency_overrides[get_ai_provider]=lambda:fake
    assert client.post(f"/api/v1/campaigns/{pro.id}/territory-ai/query",headers=admin_headers,json={"question":"¿Cuál es la fuente de datos?"}).status_code==200
    assert client.post(f"/api/v1/campaigns/{standard.id}/territory-ai/query",headers=admin_headers,json={"question":"Bloqueada"}).status_code==403
    assert len(fake.calls)==1
