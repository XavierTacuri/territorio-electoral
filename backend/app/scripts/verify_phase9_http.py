"""Controlled local HTTP verification for Phase 9; never prints credentials or tokens."""
import httpx
from sqlalchemy import select
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.campaign import Campaign
from app.models.reports import ReportArtifact

def main():
    with SessionLocal() as db:
        campaign_id=str(db.scalar(select(Campaign.id).order_by(Campaign.created_at)))
    client=httpx.Client(base_url="http://127.0.0.1:8000")
    login=client.post("/api/v1/auth/login",data={"username":settings.initial_admin_username,"password":settings.initial_admin_password})
    login.raise_for_status();headers={"Authorization":"Bearer "+login.json()["access_token"]}
    specs=[("CAMPAIGN_EXECUTIVE_SUMMARY","PDF","Resumen ejecutivo"),("OPERATIONAL_ACTIVITY","XLSX","Informe operativo"),("SURVEY_RESULTS","PDF","Informe de encuestas"),("DATA_QUALITY","XLSX","Informe de calidad")]
    results=[]
    for template,format_,title in specs:
        response=client.post(f"/api/v1/campaigns/{campaign_id}/reports/generate",headers=headers,json={"template_code":template,"format":format_,"title":title,"report_date":"2026-08-03","date_from":"2026-07-05","date_to":"2026-08-03","period":"CUSTOM","survey_ids":[],"electoral_process_ids":[],"demographic_indicator_codes":[],"include_comparisons":True})
        results.append(response)
    print("generation",[(item.status_code,item.json().get("status"),item.json().get("requested_format")) for item in results])
    if not all(item.status_code==201 for item in results):raise RuntimeError([item.text for item in results])
    downloads=[client.get(f"/api/v1/campaigns/{campaign_id}/reports/{item.json()['id']}/download",headers=headers) for item in results]
    print("downloads",[(item.status_code,item.headers.get("content-type"),item.content[:4].hex(),item.headers.get("cache-control"),item.headers.get("x-content-type-options")) for item in downloads])
    assert downloads[0].content.startswith(b"%PDF") and downloads[1].content.startswith(b"PK")
    expired_id=results[0].json()["id"]
    with SessionLocal() as db:
        artifact=db.scalar(select(ReportArtifact).where(ReportArtifact.report_run_id==expired_id));artifact.expires_on=__import__("datetime").date(2026,8,2);db.commit()
    expired=client.get(f"/api/v1/campaigns/{campaign_id}/reports/{expired_id}/download",headers=headers);print("expired",expired.status_code);assert expired.status_code==410
    alerts=client.post(f"/api/v1/campaigns/{campaign_id}/alerts/evaluate",headers=headers,json={"rule_codes":[],"as_of_date":"2026-08-03"})
    print("alerts",alerts.status_code,alerts.json())
    print("documentation",{"openapi":client.get("/openapi.json").status_code,"docs":client.get("/docs").status_code,"redoc":client.get("/redoc").status_code})
if __name__=="__main__":main()
