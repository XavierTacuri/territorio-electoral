from datetime import date
from decimal import Decimal
from app.models.campaign import Campaign
from app.models.territory import Province,Canton,Parish
from app.models.survey_study import SurveyStudyResult
from sqlalchemy import func,select

def setup_campaign(db,admin):
    p=Province(id=1,code="01",name="Provincia");c=Canton(id=1,province_id=1,code="01",dpa_code="0101",name="Cantón");r=Parish(id=1,canton_id=1,code="01",dpa_code="010101",name="Parroquia Alfa",parish_type="RURAL")
    db.add_all([p,c,r]);db.flush();campaign=Campaign(name="Campaña sintética",slug="sintetica",canton_id=1,office_type="MAYOR",election_name="Elección sintética",election_date=date(2027,2,7),status="ACTIVE",created_by_user_id=admin.id);db.add(campaign);db.commit();return campaign,r
def payload(**extra):
    data=dict(code="ESTUDIO_A",name="Estudio A",study_type="GENERAL_SURVEY",fieldwork_start_date="2026-10-01",fieldwork_end_date="2026-10-03",geography_level="PARISH",sample_size_total=420,universe_description="Electores del cantón",sampling_method="Muestreo estratificado",collection_method="Entrevista presencial",margin_of_error="0.048",pollster_name="Instituto sintético",source_type="ESTUDIO",question_code="VOTE_INTENTION",is_official=False)
    data.update(extra);return data
def test_crud_validation_publish_and_no_political_scores(client,db,admin,admin_headers):
    campaign,parish=setup_campaign(db,admin);base=f"/api/v1/campaigns/{campaign.id}/survey-studies"
    created=client.post(base,json=payload(),headers=admin_headers);assert created.status_code==201;study=created.json();assert study["status"]=="DRAFT"
    forbidden={"win_probability","persuasion_score","support_score","priority_score","favorability_score"};assert not forbidden.intersection(study)
    sid=study["id"];territory=client.post(f"/api/v1/survey-studies/{sid}/territories",json={"parish_id":parish.id,"sample_size":420},headers=admin_headers).json()
    options=[]
    for i,(code,label,kind) in enumerate((("ALFA","Opción Alfa","CANDIDATE"),("BETA","Opción Beta","CANDIDATE"),("UNDECIDED","Indecisos","UNDECIDED"))):
        options.append(client.post(f"/api/v1/survey-studies/{sid}/options",json={"code":code,"label":label,"option_type":kind,"display_order":i},headers=admin_headers).json())
    rows=[{"study_territory_id":territory["id"],"option_id":options[i]["id"],"response_count":count,"percentage":pct} for i,(count,pct) in enumerate(((144,"0.342"),(121,"0.287"),(155,"0.371")))]
    assert client.put(f"/api/v1/survey-studies/{sid}/results",json=rows,headers=admin_headers).status_code==200
    checked=client.post(f"/api/v1/survey-studies/{sid}/validate",headers=admin_headers);assert checked.json()["valid"] is True
    published=client.post(f"/api/v1/survey-studies/{sid}/publish",headers=admin_headers);assert published.status_code==200;assert published.json()["status"]=="PUBLISHED"
    assert client.delete(f"/api/v1/survey-studies/{sid}",headers=admin_headers).status_code==400
def test_rejects_bad_sum(client,db,admin,admin_headers):
    campaign,parish=setup_campaign(db,admin);s=client.post(f"/api/v1/campaigns/{campaign.id}/survey-studies",json=payload(),headers=admin_headers).json();sid=s["id"]
    t=client.post(f"/api/v1/survey-studies/{sid}/territories",json={"parish_id":parish.id,"sample_size":100},headers=admin_headers).json();opts=[]
    for code in ("A","B"):opts.append(client.post(f"/api/v1/survey-studies/{sid}/options",json={"code":code,"label":code,"option_type":"CANDIDATE"},headers=admin_headers).json())
    client.put(f"/api/v1/survey-studies/{sid}/results",json=[{"study_territory_id":t["id"],"option_id":o["id"],"response_count":80,"percentage":"0.65"} for o in opts],headers=admin_headers)
    issues=client.post(f"/api/v1/survey-studies/{sid}/validate",headers=admin_headers).json()["issues"];assert {x["code"] for x in issues}>={"PERCENTAGE_SUM"}
def test_tracking_requires_series_and_exit_requires_process(client,db,admin,admin_headers):
    campaign,_=setup_campaign(db,admin);url=f"/api/v1/campaigns/{campaign.id}/survey-studies"
    assert client.post(url,json=payload(study_type="TRACKING_POLL"),headers=admin_headers).status_code==422
    assert client.post(url,json=payload(study_type="EXIT_POLL"),headers=admin_headers).status_code==422
    assert client.post(url,json=payload(study_type="POLL"),headers=admin_headers).status_code==400
def test_csv_validate_is_read_only_then_execute(client,db,admin,admin_headers):
    campaign,parish=setup_campaign(db,admin);data=payload(code="STUDY_E2E");study=client.post(f"/api/v1/campaigns/{campaign.id}/survey-studies",json=data,headers=admin_headers).json()
    csv=("study_code,question_code,question_text,question_type,option_code,option_label,percentage,base_n,parish_dpa\n"+f"STUDY_E2E,Q1,Intención agregada,VOTE_INTENTION,ALFA,Opción Alfa,0.40,420,{parish.dpa_code}\n"+f"STUDY_E2E,Q1,Intención agregada,VOTE_INTENTION,BETA,Opción Beta,0.35,420,{parish.dpa_code}\n"+f"STUDY_E2E,Q1,Intención agregada,VOTE_INTENTION,UNDECIDED,Indecisos,0.25,420,{parish.dpa_code}\n").encode()
    before=db.scalar(select(func.count()).select_from(SurveyStudyResult));validated=client.post(f"/api/v1/campaigns/{campaign.id}/survey-imports/validate",files={"file":("results.csv",csv,"text/csv")},headers=admin_headers)
    assert validated.status_code==200;assert validated.json()["status"]=="VALIDATED";assert validated.json()["rows_valid"]==3;assert db.scalar(select(func.count()).select_from(SurveyStudyResult))==before
    executed=client.post(f"/api/v1/campaigns/{campaign.id}/survey-imports/execute",files={"file":("results.csv",csv,"text/csv")},headers=admin_headers);assert executed.status_code==200;assert executed.json()["status"]=="COMPLETED";assert len(client.get(f"/api/v1/survey-studies/{study['id']}/results",headers=admin_headers).json())==3
def test_survey_study_contract_has_no_personal_or_political_scoring_fields():
    from app.models.survey_study import SurveyStudy,SurveyStudyTerritory,SurveyStudyOption,SurveyStudyResult
    forbidden={"respondent_name","national_id","phone","email","address","latitude","longitude","device_id","individual_vote_choice","win_probability","support_score","persuasion_score","priority_score","favorability_score"}
    for model in (SurveyStudy,SurveyStudyTerritory,SurveyStudyOption,SurveyStudyResult):assert not forbidden.intersection(model.__table__.columns.keys())
