from unittest.mock import patch
import pytest
from app.services.exceptions import BusinessRuleError
from app.services.public_fetch_security import validate_public_url
from app.services.public_source_adapters import JsonApiAdapter,RSSAdapter,plain
from datetime import date,datetime,timedelta,timezone
import httpx
from app.models.public_intelligence import PublicSource,PublicSourceFetchRun,PublicTopic,PublicItemRevision
from app.models.alerts import OperationalAlert
from app.schemas.campaign import CampaignCreate
from app.schemas.public_intelligence import PublicSourceCreate
from app.scripts.seed_gualaceo import seed as seed_territory
from app.services.campaign_service import CampaignService
from app.services.public_intelligence_service import PublicIntelligenceService
from app.schemas.reports import ReportGenerationRequest
from app.scripts.seed_reports_and_alerts import seed as seed_reports
from app.services.report_service import ReportService
from app.services.report_storage_service import LocalReportStorage

@pytest.mark.parametrize("url",["http://localhost/x","http://127.0.0.1/x","http://169.254.169.254/latest","file:///etc/passwd","javascript:alert(1)","data:text/plain,x"])
def test_ssrf_and_unsafe_schemes_are_blocked(url):
    with pytest.raises(BusinessRuleError):validate_public_url(url)

def test_public_url_resolves_only_public_addresses():
    with patch("socket.getaddrinfo",return_value=[(2,1,6,"",("8.8.8.8",443))]):assert validate_public_url("https://public.example/item").startswith("https://")
    with patch("socket.getaddrinfo",return_value=[(2,1,6,"",("10.0.0.2",80))]):
        with pytest.raises(BusinessRuleError):validate_public_url("http://internal.example")

def test_rss_normalization_sanitizes_and_hashes():
    xml=b'''<rss><channel><item><guid>1</guid><title>Boletin vial</title><link>https://public.example/a</link><description><![CDATA[<script>alert(1)</script><b>Via Jadan</b><img onerror=alert(2)>]]></description><pubDate>Thu, 13 Aug 2026 12:00:00 GMT</pubDate></item></channel></rss>'''
    rows=RSSAdapter().normalize(xml,"https://public.example/feed");assert len(rows)==1;assert "script" not in rows[0].summary.lower();assert "onerror" not in rows[0].summary.lower();assert len(rows[0].content_hash)==64

def test_json_adapter_uses_configured_canonical_fields():
    data=b'{"results":[{"id":"x","headline":"Agua potable","href":"/x","body":"Actualizacion"}]}'
    rows=JsonApiAdapter({"items_key":"results","external_id":"id","title":"headline","url":"href","summary":"body"}).normalize(data,"https://api.example/v1/");assert rows[0].external_id=="x";assert rows[0].url=="https://api.example/x";assert rows[0].title=="Agua potable"

def test_plain_removes_javascript_and_event_handlers():assert "javascript:" not in plain('<a href="javascript:x" onerror=boom>texto</a>').lower()

def test_fetch_dedup_revision_search_and_summary(db,admin):
    _,canton,_=seed_territory(db);campaign=CampaignService(db).create(CampaignCreate(name="Pública",slug="publica",canton_id=canton.id,office_type="MAYOR",election_name="Sintética",election_date=date(2027,2,14),status="ACTIVE"),admin)
    db.add_all([PublicTopic(code="VIALIDAD",name="Vialidad",keywords=["vial"]),PublicTopic(code="OTHER",name="Otro",keywords=[])]);source=PublicSource(campaign_id=campaign.id,code="RSS_TEST",name="Fuente Oficial Sintética",publisher="Municipio Sintético",source_type="RSS",base_url="https://public.example",feed_url="https://public.example/feed",official=True,retrieval_method="RSS");db.add(source);db.commit()
    version=[1]
    def handler(request):
        text=f'<rss><channel><item><guid>x</guid><title>Boletín vial</title><link>https://public.example/a</link><description>Versión {version[0]}</description></item></channel></rss>';return httpx.Response(200,content=text.encode(),request=request)
    service=PublicIntelligenceService(db,httpx.Client(transport=httpx.MockTransport(handler)))
    with patch("socket.getaddrinfo",return_value=[(2,1,6,"",("8.8.8.8",443))]):
        first=service.fetch(source.id,admin);second=service.fetch(source.id,admin);version[0]=2;third=service.fetch(source.id,admin)
    assert (first.items_created,second.items_unchanged,third.items_updated)==(1,1,1)
    item=service.items(campaign.id,admin,1,20,search="vial").items[0];assert item.source_name==source.name;assert len(item.revisions)==2;assert service.summary(campaign.id,admin).official_sources==1
    assert service.items(campaign.id,admin,1,20,search="vialidad").items[0].id==item.id
    assert db.query(PublicItemRevision).count()==2

def test_manual_official_website_refresh_is_rejected_without_run_or_ssrf_lookup(db,admin):
    _,canton,_=seed_territory(db);campaign=CampaignService(db).create(CampaignCreate(name="Manual",slug="manual-publica",canton_id=canton.id,office_type="MAYOR",election_name="Sintética",election_date=date(2027,2,14),status="ACTIVE"),admin)
    source=PublicSource(campaign_id=campaign.id,code="CNE_ECUADOR",name="Consejo Nacional Electoral del Ecuador",publisher="CNE",source_type="OFFICIAL_WEBSITE",base_url="https://www.cne.gob.ec",official=True,retrieval_method="MANUAL");db.add(source);db.commit()
    with patch("app.services.public_intelligence_service.validate_public_url") as validate:
        with pytest.raises(BusinessRuleError,match="SOURCE_REFRESH_NOT_SUPPORTED"):
            PublicIntelligenceService(db).fetch(source.id,admin)
    validate.assert_not_called();assert db.query(PublicSourceFetchRun).filter_by(source_id=source.id).count()==0
    assert PublicIntelligenceService(db).freshness(source)[0]=="MANUAL"

def test_manual_refresh_endpoint_returns_domain_error_without_history(db,admin,client,admin_headers):
    _,canton,_=seed_territory(db);campaign=CampaignService(db).create(CampaignCreate(name="Manual API",slug="manual-api",canton_id=canton.id,office_type="MAYOR",election_name="Sintética",election_date=date(2027,2,14),status="ACTIVE"),admin)
    source=PublicSource(campaign_id=campaign.id,code="MANUAL_API",name="Fuente manual",publisher="Entidad",source_type="OFFICIAL_WEBSITE",base_url="https://public.example",retrieval_method="MANUAL");db.add(source);db.commit()
    response=client.post(f"/api/v1/public-sources/{source.id}/fetch",headers=admin_headers)
    assert response.status_code==400 and "SOURCE_REFRESH_NOT_SUPPORTED" in response.json()["detail"]
    assert db.query(PublicSourceFetchRun).filter_by(source_id=source.id).count()==0

@pytest.mark.parametrize("method", ["WEB_PAGE", "FILE_DOWNLOAD"])
def test_legacy_scraping_methods_are_rejected_for_new_sources(db,admin,method):
    _,canton,_=seed_territory(db);campaign=CampaignService(db).create(CampaignCreate(name="Bloqueo scraping",slug=f"bloqueo-{method.lower()}",canton_id=canton.id,office_type="MAYOR",election_name="Sintética",election_date=date(2027,2,14),status="ACTIVE"),admin)
    data=PublicSourceCreate(code=f"LEGACY_{method}",name="Fuente legacy",publisher="Entidad",source_type="OFFICIAL_WEBSITE",base_url="https://public.example",retrieval_method=method)
    with pytest.raises(BusinessRuleError,match="disponible"):
        PublicIntelligenceService(db).create_source(campaign.id,admin,data)

@pytest.mark.parametrize(
    "method,url_field,payload",
    [
        ("RSS","feed_url",b'<rss><channel><item><guid>rss</guid><title>RSS</title><link>https://public.example/rss</link></item></channel></rss>'),
        ("API","api_url",b'[{"id":"api","title":"API","url":"https://public.example/api"}]'),
    ],
)
def test_refresh_selects_only_configured_rss_or_api_adapter(db,admin,method,url_field,payload):
    _,canton,_=seed_territory(db);campaign=CampaignService(db).create(CampaignCreate(name=f"Adapter {method}",slug=f"adapter-{method.lower()}",canton_id=canton.id,office_type="MAYOR",election_name="Sintética",election_date=date(2027,2,14),status="ACTIVE"),admin)
    values={url_field:f"https://public.example/{method.lower()}"};source=PublicSource(campaign_id=campaign.id,code=f"{method}_ADAPTER",name=f"Fuente {method}",publisher="Entidad",source_type=method,base_url="https://public.example",retrieval_method=method,**values);db.add(source);db.commit()
    def handler(request):return httpx.Response(200,content=payload,request=request)
    service=PublicIntelligenceService(db,httpx.Client(transport=httpx.MockTransport(handler)))
    with patch("socket.getaddrinfo",return_value=[(2,1,6,"",("8.8.8.8",443))]):run=service.fetch(source.id,admin)
    assert run.status=="SUCCESS" and run.items_created==1

@pytest.mark.parametrize("report_format,magic",[("PDF",b"%PDF"),("XLSX",b"PK")])
def test_public_intelligence_report_is_generated(db,admin,tmp_path,report_format,magic):
    _,canton,_=seed_territory(db);campaign=CampaignService(db).create(CampaignCreate(name="Informe público",slug=f"informe-{report_format.lower()}",canton_id=canton.id,office_type="MAYOR",election_name="Sintética",election_date=date(2027,2,14),status="ACTIVE"),admin)
    seed_reports(db)
    run=ReportService(db,LocalReportStorage(str(tmp_path),10)).generate(campaign.id,ReportGenerationRequest(template_code="PUBLIC_INTELLIGENCE_REPORT",format=report_format,title="Inteligencia pública",report_date=date(2026,8,14)),admin)
    artifact=ReportService(db,LocalReportStorage(str(tmp_path),10)).artifact(run)
    assert run.status=="COMPLETED" and artifact.original_download_name.startswith("inteligencia-publica-")
    assert (tmp_path/artifact.storage_key).read_bytes().startswith(magic)

def test_source_stale_threshold_and_resolution(db,admin):
    _,canton,_=seed_territory(db);campaign=CampaignService(db).create(CampaignCreate(name="Frescura",slug="frescura",canton_id=canton.id,office_type="MAYOR",election_name="Sintética",election_date=date(2027,2,14),status="ACTIVE"),admin);seed_reports(db)
    now=datetime(2026,8,14,12,tzinfo=timezone.utc);source=PublicSource(campaign_id=campaign.id,code="STALE",name="Fuente fresca",publisher="Publicador",source_type="RSS",base_url="https://public.example",feed_url="https://public.example/feed",official=True,retrieval_method="RSS",refresh_interval_minutes=60,last_success_at=now-timedelta(minutes=30));db.add(source);db.commit();service=PublicIntelligenceService(db)
    assert service.freshness(source,now)[0]=="CURRENT";assert service.evaluate_stale_sources(campaign.id,admin,now)["created"]==0
    source.last_success_at=now-timedelta(minutes=90);db.commit();assert service.freshness(source,now)[0]=="STALE";assert service.evaluate_stale_sources(campaign.id,admin,now)["created"]==1
    alert=db.query(OperationalAlert).filter_by(resource_id=source.id,status="OPEN").one();source.last_success_at=now;service._resolve_stale(source,now);db.commit();db.refresh(alert);assert alert.status=="RESOLVED" and not alert.is_active

def test_public_map_returns_all_parishes_with_zero_values(db,admin):
    _,canton,parishes=seed_territory(db);campaign=CampaignService(db).create(CampaignCreate(name="Mapa público",slug="mapa-publico",canton_id=canton.id,office_type="MAYOR",election_name="Sintética",election_date=date(2027,2,14),status="ACTIVE"),admin)
    rows=PublicIntelligenceService(db).map_metrics(campaign.id,admin,"total");assert len(rows)==len(parishes)==9;assert all(row.value==0 for row in rows)
