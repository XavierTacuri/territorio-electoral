from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from pydantic import ValidationError
from sqlalchemy import func,inspect,select
from sqlalchemy.orm import Session
from app.models.survey import Survey,SurveyAnswer,SurveyResponse
from app.schemas.campaign import CampaignCreate
from app.schemas.survey import *
from app.scripts.seed_gualaceo import seed as seed_gualaceo
from app.services.campaign_service import CampaignService
from app.services.exceptions import BusinessRuleError,ConflictError
from app.services.survey_service import SurveyService
from app.core.security import hash_password
from app.models.user import User
from app.schemas.campaign import CampaignUserAssign,TerritorialAssignmentCreate
from app.services.role_service import RoleService
from app.services.territorial_assignment_service import TerritorialAssignmentService

@pytest.fixture
def survey_context(db:Session,admin):
    _,canton,parishes=seed_gualaceo(db);db.commit()
    campaign=CampaignService(db).create(CampaignCreate(name='Encuestas Gualaceo',slug='encuestas-gualaceo',canton_id=canton.id,office_type='MAYOR',election_name='Seccionales 2027',election_date=date(2027,2,14),status='DRAFT'),admin)
    return campaign,parishes

def base_survey(**changes):
    data=dict(title='Necesidades cantonales',slug='necesidades-cantonales',start_date=date(2026,8,1),end_date=date(2026,8,31),target_scope='CANTON',anonymous_only=True)
    data.update(changes);return SurveyCreate(**data)
def build_published(db,admin,context,multiple=True):
    campaign,parishes=context;svc=SurveyService(db,today_provider=lambda:date(2026,8,3));survey=svc.create(campaign.id,base_survey(allow_multiple_submissions=multiple),admin);section=svc.add_section(campaign.id,survey.id,SurveySectionCreate(title='General',display_order=1),admin)
    choice=svc.add_question(campaign.id,survey.id,section.id,SurveyQuestionCreate(code='MAIN_PROBLEM',question_text='Problema principal',question_type='SINGLE_CHOICE',is_required=True,allow_other=True),admin)
    svc.add_option(campaign.id,survey.id,choice.id,SurveyOptionCreate(code='ROADS',label='Vialidad'),admin);svc.add_option(campaign.id,survey.id,choice.id,SurveyOptionCreate(code='WATER',label='Agua'),admin)
    rating=svc.add_question(campaign.id,survey.id,section.id,SurveyQuestionCreate(code='RATING',question_text='Valoración',question_type='RATING',rating_min=1,rating_max=5),admin)
    comments=svc.add_question(campaign.id,survey.id,section.id,SurveyQuestionCreate(code='COMMENTS',question_text='Comentarios',question_type='SHORT_TEXT',max_length=250),admin)
    svc.publish(campaign.id,survey.id,admin);return svc,survey,parishes,choice,rating,comments

def submission(parish_id,key='random-session-key',**changes):
    data=dict(response_date=date(2026,8,15),parish_id=parish_id,source_channel='FIELD',age_range='AGE_35_44',submission_key=key,answers=[SurveyAnswerInput(question_code='MAIN_PROBLEM',selected_option_codes=['ROADS']),SurveyAnswerInput(question_code='RATING',rating_value=2),SurveyAnswerInput(question_code='COMMENTS',text_value='Se requiere mantenimiento de la vía principal.')])
    data.update(changes);return SurveySubmissionCreate(**data)

def test_survey_model_has_no_personal_tracking_columns():
    forbidden={'respondent_name','email','phone','national_id','ip_address','user_agent','device_fingerprint','precise_location','political_preference'}
    assert forbidden.isdisjoint({c.name for c in SurveyResponse.__table__.columns})

def test_survey_schema_dates_anonymous_and_unknown_fields():
    value=base_survey();assert value.start_date==date(2026,8,1) and value.anonymous_only
    with pytest.raises(ValidationError):base_survey(anonymous_only=False)
    with pytest.raises(ValidationError):base_survey(start_date=date(2026,9,1))
    with pytest.raises(ValidationError):SurveyCreate(**{**base_survey().model_dump(),'respondent_name':'X'})

def test_create_unique_slug_and_draft_update(db,admin,survey_context):
    campaign,_=survey_context;svc=SurveyService(db);survey=svc.create(campaign.id,base_survey(),admin)
    assert survey.status=='DRAFT' and survey.start_date==date(2026,8,1)
    with pytest.raises(ConflictError):svc.create(campaign.id,base_survey(),admin)
    assert svc.update(campaign.id,survey.id,SurveyUpdate(title='Nueva encuesta'),admin).title=='Nueva encuesta'

def test_structure_validation_and_publication(db,admin,survey_context):
    campaign,_=survey_context;svc=SurveyService(db,today_provider=lambda:date(2026,8,3));survey=svc.create(campaign.id,base_survey(),admin)
    with pytest.raises(BusinessRuleError):svc.publish(campaign.id,survey.id,admin)
    section=svc.add_section(campaign.id,survey.id,SurveySectionCreate(title='Sección',display_order=2),admin)
    q=svc.add_question(campaign.id,survey.id,section.id,SurveyQuestionCreate(code='CHOICE',question_text='Seleccione',question_type='SINGLE_CHOICE'),admin)
    with pytest.raises(BusinessRuleError):svc.publish(campaign.id,survey.id,admin)
    svc.add_option(campaign.id,survey.id,q.id,SurveyOptionCreate(code='A',label='A'),admin);svc.add_option(campaign.id,survey.id,q.id,SurveyOptionCreate(code='B',label='B'),admin)
    published=svc.publish(campaign.id,survey.id,admin);assert published.status=='PUBLISHED' and published.published_date==date(2026,8,3)
    with pytest.raises(BusinessRuleError):svc.add_section(campaign.id,survey.id,SurveySectionCreate(title='Tarde'),admin)
    closed=svc.transition(campaign.id,survey.id,admin,'CLOSED');assert closed.closed_date==date(2026,8,3)
    with pytest.raises(BusinessRuleError):svc.publish(campaign.id,survey.id,admin)

def test_question_type_configuration():
    for kind in ['SINGLE_CHOICE','MULTIPLE_CHOICE','YES_NO','SHORT_TEXT','LONG_TEXT','INTEGER','DECIMAL']:
        assert SurveyQuestionCreate(code=kind,question_text='Pregunta',question_type=kind).question_type==kind
    assert SurveyQuestionCreate(code='R',question_text='Rating',question_type='RATING',rating_min=1,rating_max=10).rating_max==10
    with pytest.raises(ValidationError):SurveyQuestionCreate(code='R',question_text='Rating',question_type='RATING',rating_min=5,rating_max=1)
    with pytest.raises(ValidationError):SurveyQuestionCreate(code='T',question_text='Texto',question_type='SHORT_TEXT',max_length=501)

def test_valid_anonymous_submission_hmac_and_no_exposure(db,admin,survey_context):
    svc,survey,parishes,*_=build_published(db,admin,survey_context,multiple=False);payload=submission(parishes[0].id)
    response=svc.submit(survey.campaign_id,survey.id,payload,admin);assert response.response_date==date(2026,8,15) and len(response.answers)==3
    assert response.submission_key_hash and response.submission_key_hash!=payload.submission_key and len(response.submission_key_hash)==64
    assert svc.digest(payload.submission_key)==response.submission_key_hash
    public=SurveyResponseSummary.model_validate(response).model_dump();assert 'submission_key_hash' not in public and 'created_at' not in public
    with pytest.raises(ConflictError):svc.submit(survey.campaign_id,survey.id,payload,admin)

def test_multiple_submissions_do_not_store_key(db,admin,survey_context):
    svc,survey,parishes,*_=build_published(db,admin,survey_context,multiple=True);payload=submission(parishes[0].id)
    first=svc.submit(survey.campaign_id,survey.id,payload,admin);second=svc.submit(survey.campaign_id,survey.id,payload,admin)
    assert first.submission_key_hash is None and second.submission_key_hash is None

def test_required_range_options_and_atomicity(db,admin,survey_context):
    svc,survey,parishes,*_=build_published(db,admin,survey_context)
    missing=submission(parishes[0].id,answers=[SurveyAnswerInput(question_code='RATING',rating_value=2)])
    with pytest.raises(BusinessRuleError):svc.submit(survey.campaign_id,survey.id,missing,admin)
    invalid=submission(parishes[0].id,key='different-session-key',answers=[SurveyAnswerInput(question_code='MAIN_PROBLEM',selected_option_codes=['OTHER_QUESTION']),SurveyAnswerInput(question_code='RATING',rating_value=8)])
    with pytest.raises(BusinessRuleError):svc.submit(survey.campaign_id,survey.id,invalid,admin)
    assert db.scalar(select(func.count()).select_from(SurveyResponse))==0 and db.scalar(select(func.count()).select_from(SurveyAnswer))==0

def test_privacy_text_detection(db,admin,survey_context):
    svc,survey,parishes,*_=build_published(db,admin,survey_context)
    for text in ['Mi correo es persona@example.com','Mi teléfono es 0991234567','Mi cédula es 0102030405']:
        data=submission(parishes[0].id,key='key-'+str(uuid4()),answers=[SurveyAnswerInput(question_code='MAIN_PROBLEM',selected_option_codes=['ROADS']),SurveyAnswerInput(question_code='COMMENTS',text_value=text)])
        with pytest.raises(BusinessRuleError):svc.submit(survey.campaign_id,survey.id,data,admin)
    assert db.scalar(select(func.count()).select_from(SurveyResponse))==0

def test_results_invalidation_numeric_and_threshold(db,admin,survey_context):
    svc,survey,parishes,*_=build_published(db,admin,survey_context)
    rows=[]
    for i in range(5):rows.append(svc.submit(survey.campaign_id,survey.id,submission(parishes[0].id,key=f'session-key-{i}',answers=[SurveyAnswerInput(question_code='MAIN_PROBLEM',selected_option_codes=['ROADS']),SurveyAnswerInput(question_code='RATING',rating_value=i%5+1)]),admin))
    svc.invalidate(survey.campaign_id,survey.id,rows[0].id,'Registro de prueba inválido',admin)
    result=svc.results(survey.campaign_id,survey.id,admin);assert result.total_responses==5 and result.valid_responses==4 and result.invalid_responses==1
    rating=next(x for x in result.question_results if x.code=='RATING');assert rating.numeric.count==4 and rating.numeric.median is not None
    comparison=svc.comparison(survey.campaign_id,survey.id,admin,'PARISH','RATING');assert comparison.items[0].suppressed is True and comparison.items[0].result is None
    participation=svc.participation(survey.campaign_id,survey.id,admin);assert participation.valid_responses==4 and participation.territories_below_threshold

def test_closed_survey_and_invalid_territory(db,admin,survey_context):
    svc,survey,parishes,*_=build_published(db,admin,survey_context)
    with pytest.raises(BusinessRuleError):svc.submit(survey.campaign_id,survey.id,submission(999999),admin)
    svc.transition(survey.campaign_id,survey.id,admin,'CLOSED')
    with pytest.raises(BusinessRuleError):svc.submit(survey.campaign_id,survey.id,submission(parishes[0].id),admin)

def test_survey_http_flow_and_contract(client,admin_headers,admin,survey_context):
    campaign,parishes=survey_context;base=f'/api/v1/campaigns/{campaign.id}/surveys'
    assert client.get(base).status_code==401
    survey=client.post(base,headers=admin_headers,json={'title':'Encuesta HTTP','slug':'encuesta-http','target_scope':'CANTON','anonymous_only':True}).json();assert survey['status']=='DRAFT' and 'created_at' not in survey
    section=client.post(f"{base}/{survey['id']}/sections",headers=admin_headers,json={'title':'General'}).json()
    q=client.post(f"{base}/{survey['id']}/sections/{section['id']}/questions",headers=admin_headers,json={'code':'YES_NO','question_text':'¿Mejorar servicios?','question_type':'YES_NO','is_required':True}).json()
    assert client.post(f"{base}/{survey['id']}/publish",headers=admin_headers).status_code==200
    response=client.post(f"{base}/{survey['id']}/responses",headers=admin_headers,json={'response_date':'2026-08-03','parish_id':parishes[0].id,'source_channel':'FIELD','answers':[{'question_code':'YES_NO','boolean_value':True} ]})
    assert response.status_code==201 and 'submission_key_hash' not in response.text and 'created_at' not in response.text
    rid=response.json()['id'];assert client.get(f"{base}/{survey['id']}/responses/{rid}",headers=admin_headers).status_code==200
    assert client.get(f"{base}/{survey['id']}/results",headers=admin_headers).status_code==200
    assert client.get(f"{base}/{uuid4()}",headers=admin_headers).status_code==404


def test_survey_role_and_territorial_access(db,admin,survey_context):
    campaign,parishes=survey_context;assignments=TerritorialAssignmentService(db)
    def member(role_code,name):
        role=RoleService(db).repository.get_by_code(role_code);user=User(email=f"{name}@example.com",username=name,first_name=name,last_name="Test",hashed_password=hash_password("Testing123"),roles=[role]);db.add(user);db.commit();db.refresh(user);assignments.assign_user(campaign.id,CampaignUserAssign(user_id=user.id),admin);return user
    manager=member("CAMPAIGN_MANAGER","manager5");coordinator=member("TERRITORIAL_COORDINATOR","coord5");analyst=member("ANALYST","analyst5");candidate=member("CANDIDATE","candidate5")
    assignments.create(campaign.id,TerritorialAssignmentCreate(user_id=coordinator.id,parish_id=parishes[0].id),admin)
    svc,survey,_,*_=build_published(db,admin,survey_context)
    assert SurveyService(db).create(campaign.id,base_survey(slug="manager-survey"),manager).status=="DRAFT"
    created=svc.submit(campaign.id,survey.id,submission(parishes[0].id),coordinator);assert created.parish_id==parishes[0].id
    with pytest.raises(PermissionError):svc.submit(campaign.id,survey.id,submission(parishes[1].id,key="outside-territory"),coordinator)
    with pytest.raises(PermissionError):svc.submit(campaign.id,survey.id,submission(parishes[0].id,key="analyst-session"),analyst)
    with pytest.raises(PermissionError):svc.response(campaign.id,survey.id,created.id,candidate)
    assert svc.results(campaign.id,survey.id,candidate).total_responses==1
