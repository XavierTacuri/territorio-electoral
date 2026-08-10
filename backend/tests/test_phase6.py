from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile
import pytest
from pydantic import ValidationError
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.importers.csv_utils import parse_csv
from app.models.historical import *
from app.schemas.historical import DataSourceCreate,ElectoralContestCreate,ElectoralProcessCreate,DemographicIndicatorCreate
from app.scripts.seed_gualaceo import seed as seed_gualaceo
from app.services.data_import_service import DataImportService
from app.services.data_source_service import DataSourceService
from app.services.electoral_service import ElectoralService,pct
from app.services.demographic_service import DemographicService
from app.services.exceptions import BusinessRuleError,ConflictError
@pytest.fixture
def historical_context(db:Session,admin):
 province,canton,parishes=seed_gualaceo(db);db.commit();source=DataSourceService(db).create(DataSourceCreate(code='TEST_CNE_SOURCE',institution='Consejo Nacional Electoral',dataset_name='Datos sintéticos de prueba',dataset_type='CNE_TURNOUT',official_url='https://example.gob.ec/datos.csv',publication_date=date(2026,1,2),reference_year=2023),admin);return source,province,canton,parishes

def test_source_create_dates_url_duplicate(db,admin,historical_context):
 source,*_=historical_context;assert source.publication_date==date(2026,1,2) and source.official_url.startswith('https://')
 with pytest.raises(ConflictError):DataSourceService(db).create(DataSourceCreate(code='test_cne_source',institution='CNE',dataset_name='Otro',dataset_type='CNE_TURNOUT'),admin)
 assert 'created_at' not in DataSourceCreate.model_fields

def test_csv_comma_semicolon_bom_latin1_and_microdata():
 header='process_code,name,process_type,election_date,status,is_final\n';rows,enc,delim=parse_csv(('\ufeff'+header+'P1,Proceso,SECTIONAL,2023-02-05,VALIDATED,1\n').encode(),'CANONICAL_ELECTORAL_PROCESS');assert enc=='utf-8-sig' and delim==',' and rows[0][1]['process_code']=='P1'
 semicolon=header.replace(',', ';')+'P2;Elección;SECTIONAL;2023-02-05;VALIDATED;1\n';assert parse_csv(semicolon.encode(),'CANONICAL_ELECTORAL_PROCESS')[2]==';'
 latin=('process_code,name,process_type,election_date,status,is_final\nP3,Elección,SECTIONAL,2023-02-05,VALIDATED,1\n').encode('latin-1');assert parse_csv(latin,'CANONICAL_ELECTORAL_PROCESS','latin-1')[1]=='latin-1'
 with pytest.raises(BusinessRuleError):parse_csv(b'cedula,name\n0102030405,A\n','CANONICAL_ELECTORAL_PROCESS')
 with pytest.raises(BusinessRuleError):parse_csv(b'','CANONICAL_ELECTORAL_PROCESS')

def test_validate_execute_checksum_force_and_temp_cleanup(db,admin,historical_context):
 source,*_=historical_context;svc=DataImportService(db);content=b'process_code,name,process_type,election_date,status,is_final\nTEST_2023,Seccionales 2023,SECTIONAL,2023-02-05,VALIDATED,1\n';before=set(Path(tempfile.gettempdir()).glob('te-import-*'))
 checked=svc.run(source.id,'CNE_TURNOUT','process.csv',content,admin,True,'CANONICAL_ELECTORAL_PROCESS');assert checked.status=='VALIDATED' and checked.rows_valid==1 and db.scalar(select(func.count()).select_from(ElectoralProcess))==0
 imported=svc.run(source.id,'CNE_TURNOUT','process.csv',content,admin,False,'CANONICAL_ELECTORAL_PROCESS');assert imported.status=='COMPLETED' and imported.file_sha256==checked.file_sha256 and imported.rows_inserted==1
 with pytest.raises(ConflictError):svc.run(source.id,'CNE_TURNOUT','process.csv',content,admin,False,'CANONICAL_ELECTORAL_PROCESS')
 forced=svc.run(source.id,'CNE_TURNOUT','process.csv',content,admin,False,'CANONICAL_ELECTORAL_PROCESS',force=True);assert forced.rows_updated==1 and db.scalar(select(func.count()).select_from(ElectoralProcess))==1
 assert set(Path(tempfile.gettempdir()).glob('te-import-*'))==before

def test_invalid_extension_totals_and_no_partial_domain_data(db,admin,historical_context):
 source,*_=historical_context;svc=DataImportService(db)
 with pytest.raises(BusinessRuleError):svc.run(source.id,'CNE_TURNOUT','data.xlsx',b'x',admin)
 content=b'process_code,contest_code,geography_level,geography_code,province_dpa,canton_dpa,parish_dpa,zone_code,precinct_code,jrv_code,registered_voters,ballots_cast,valid_votes,blank_votes,null_votes,other_votes,is_final\nP,C,PARISH,010350,01,0103,010350,,,,100,101,90,5,6,0,1\n';job=svc.run(source.id,'CNE_TURNOUT','bad.csv',content,admin,False,'CANONICAL_ELECTORAL_TURNOUT');assert job.status=='REJECTED' and job.rows_failed==1 and db.scalar(select(func.count()).select_from(ElectoralTurnout))==0

def create_electoral(db,source,canton):
 service=ElectoralService(db);process=service.create_process(ElectoralProcessCreate(code='SEC_2023',name='Seccionales 2023',process_type='SECTIONAL',election_date=date(2023,2,5),year=2023,status='VALIDATED',source_id=source.id));contest=service.create_contest(process.id,ElectoralContestCreate(office_type='MAYOR',name='MAYOR_GUALACEO',vote_method='SINGLE_CHOICE',canton_id=canton.id));return service,process,contest

def test_process_contest_and_year_rules(db,admin,historical_context):
 source,_,canton,_=historical_context;service,process,contest=create_electoral(db,source,canton);assert process.election_date==date(2023,2,5) and contest.canton_id==canton.id
 with pytest.raises(ValidationError):ElectoralProcessCreate(code='BAD',name='Bad',process_type='SECTIONAL',election_date=date(2023,1,1),year=2024,source_id=source.id)
 with pytest.raises(ValidationError):ElectoralContestCreate(office_type='MAYOR',name='Sin cantón',vote_method='SINGLE_CHOICE')

def test_turnout_import_mapping_rates_and_zero_division(db,admin,historical_context):
 source,_,canton,parishes=historical_context;service,process,contest=create_electoral(db,source,canton);content=('process_code,contest_code,geography_level,geography_code,province_dpa,canton_dpa,parish_dpa,zone_code,precinct_code,jrv_code,registered_voters,ballots_cast,valid_votes,blank_votes,null_votes,other_votes,is_final\nSEC_2023,MAYOR_GUALACEO,PARISH,010350,01,0103,010350,,,,100,80,70,5,5,0,1\n').encode();job=DataImportService(db).run(source.id,'CNE_TURNOUT','turnout.csv',content,admin,False,'CANONICAL_ELECTORAL_TURNOUT');assert job.rows_inserted==1
 row=service.turnout(process.id,contest.id,'PARISH')[0];assert row.participation_rate==Decimal('80.00') and row.absentee_count==20 and row.blank_vote_rate==Decimal('6.25');assert pct(0,0) is None
 geo=db.scalar(select(ElectoralGeography));assert geo.external_code=='010350' and geo.parish_id==parishes[0].id and geo.is_mapped

def test_organizations_candidates_results_ranking_margin(db,admin,historical_context):
 source,_,canton,_=historical_context;service,process,contest=create_electoral(db,source,canton);imp=DataImportService(db)
 turnout=b'process_code,contest_code,geography_level,geography_code,province_dpa,canton_dpa,parish_dpa,zone_code,precinct_code,jrv_code,registered_voters,ballots_cast,valid_votes,blank_votes,null_votes,other_votes,is_final\nSEC_2023,MAYOR_GUALACEO,PARISH,010350,01,0103,010350,,,,100,80,70,5,5,0,1\n';imp.run(source.id,'CNE_TURNOUT','t.csv',turnout,admin,False,'CANONICAL_ELECTORAL_TURNOUT')
 org=b'organization_code,name,short_name,organization_type,list_number,scope\nORG1,Organizacion Uno,,MOVIMIENTO,10,CANTON\n';imp.run(source.id,'CNE_POLITICAL_ORGANIZATIONS','o.csv',org,admin,False,'CANONICAL_POLITICAL_ORGANIZATION')
 candidates=b'process_code,office_type,contest_code,candidate_code,full_name,organization_code,list_number,ballot_order\nSEC_2023,MAYOR,MAYOR_GUALACEO,C1,Candidatura Publica Uno,ORG1,10,1\nSEC_2023,MAYOR,MAYOR_GUALACEO,C2,Candidatura Publica Dos,ORG1,10,2\n';imp.run(source.id,'CNE_CANDIDATES','c.csv',candidates,admin,False,'CANONICAL_ELECTORAL_CANDIDATE')
 results=b'process_code,contest_code,geography_level,geography_code,candidate_code,votes,is_final\nSEC_2023,MAYOR_GUALACEO,PARISH,010350,C1,40,1\nSEC_2023,MAYOR_GUALACEO,PARISH,010350,C2,30,1\n';imp.run(source.id,'CNE_ELECTORAL_RESULTS','r.csv',results,admin,False,'CANONICAL_ELECTORAL_CANDIDATE_RESULT')
 ranked=service.results(process.id,contest.id,'PARISH');assert ranked[0].position==1 and ranked[0].vote_share==Decimal('57.14') and ranked[0].geography_code=='010350' and ranked[0].geography_level=='PARISH';summary=service.territorial_summary(process.id,contest.id);assert summary.items[0]['margin_votes']==10
 assert {'full_name','external_code'}.issubset(ElectoralCandidate.__table__.columns.keys()) and 'national_id' not in ElectoralCandidate.__table__.columns.keys()

def test_demographic_indicator_observation_profile(db,admin,historical_context):
 source,_,canton,parishes=historical_context;indicator=DemographicService(db).create(DemographicIndicatorCreate(code='POP_TOTAL',name='Población total',category='POPULATION',unit='COUNT',value_type='INTEGER',source_id=source.id));content=b'indicator_code,reference_year,geography_level,province_dpa,canton_dpa,parish_dpa,value,numerator,denominator\nPOP_TOTAL,2022,CANTON,01,0103,,42000,,\n';job=DataImportService(db).run(source.id,'INEC_DEMOGRAPHIC_INDICATORS','d.csv',content,admin,False,'CANONICAL_DEMOGRAPHIC_OBSERVATION');assert job.rows_inserted==1;profile=DemographicService(db).profile(canton.id,reference_year=2022);assert profile['observations'][0]['value']=='42000.0000'

def test_data_source_and_import_http_security(client,admin_headers,historical_context):
 source,*_=historical_context;assert client.get('/api/v1/data-sources').status_code==401;assert client.get('/api/v1/data-sources',headers=admin_headers).status_code==200
 files={'file':('process.csv',b'process_code,name,process_type,election_date,status,is_final\nHTTP_2023,Proceso HTTP,SECTIONAL,2023-02-05,VALIDATED,1\n','text/csv')};data={'source_id':str(source.id),'dataset_type':'CNE_TURNOUT','mapping_profile':'CANONICAL_ELECTORAL_PROCESS'};response=client.post('/api/v1/data-imports/validate',headers=admin_headers,data=data,files=files);assert response.status_code==200 and response.json()['status']=='VALIDATED' and 'started_at' not in response.text

def test_wizard_preflight_reports_missing_registered_voters(db,admin,historical_context):
 source,_,canton,_=historical_context;create_electoral(db,source,canton)
 content=b'process_code,contest_code,geography_level,geography_code,province_dpa,canton_dpa,parish_dpa,zone_code,precinct_code,jrv_code,registered_voters,ballots_cast,valid_votes,blank_votes,null_votes,other_votes,is_final\nSEC_2023,MAYOR_GUALACEO,PARISH,010350,01,0103,010350,,,,,80,70,5,5,0,1\n'
 job=DataImportService(db).run(source.id,'CNE_TURNOUT','missing-registered.csv',content,admin,True)
 error=db.scalar(select(DataImportError).where(DataImportError.import_job_id==job.id))
 assert job.status=='REJECTED' and 'registered_voters: valor requerido' in error.message

def test_wizard_preflight_checks_organization_candidate_and_geography(db,admin,historical_context):
 source,_,canton,_=historical_context;_,process,contest=create_electoral(db,source,canton);service=DataImportService(db)
 candidates=b'process_code,office_type,contest_code,candidate_code,full_name,organization_code,list_number,ballot_order\nSEC_2023,MAYOR,MAYOR_GUALACEO,C1,Candidatura Uno,ORG_MISSING,10,1\n'
 candidate_job=service.run(source.id,'CNE_CANDIDATES','candidate-missing-org.csv',candidates,admin,True)
 candidate_error=db.scalar(select(DataImportError).where(DataImportError.import_job_id==candidate_job.id))
 assert candidate_job.status=='REJECTED' and 'ORG_MISSING' in candidate_error.message
 results=b'process_code,contest_code,geography_level,geography_code,candidate_code,votes,is_final\nSEC_2023,MAYOR_GUALACEO,PARISH,010350,C1,40,1\n'
 result_job=service.run(source.id,'CNE_ELECTORAL_RESULTS','result-missing-dependencies.csv',results,admin,True)
 result_error=db.scalar(select(DataImportError).where(DataImportError.import_job_id==result_job.id))
 assert result_job.status=='REJECTED' and '010350' in result_error.message
 assert not service.db.scalar(select(ElectoralCandidate).where(ElectoralCandidate.electoral_contest_id==contest.id))

def test_wizard_read_endpoints_reconstruct_import_state(client,admin_headers,db,admin,historical_context):
 source,_,canton,_=historical_context;_,process,contest=create_electoral(db,source,canton);imp=DataImportService(db)
 turnout=b'process_code,contest_code,geography_level,geography_code,province_dpa,canton_dpa,parish_dpa,zone_code,precinct_code,jrv_code,registered_voters,ballots_cast,valid_votes,blank_votes,null_votes,other_votes,is_final\nSEC_2023,MAYOR_GUALACEO,PARISH,010350,01,0103,010350,,,,100,80,70,5,5,0,1\n';imp.run(source.id,'CNE_TURNOUT','wizard-turnout.csv',turnout,admin)
 org=b'organization_code,name,short_name,organization_type,list_number,scope\nORG1,Organizacion Uno,,MOVIMIENTO,10,CANTON\n';imp.run(source.id,'CNE_POLITICAL_ORGANIZATIONS','wizard-org.csv',org,admin)
 candidates=b'process_code,office_type,contest_code,candidate_code,full_name,organization_code,list_number,ballot_order\nSEC_2023,MAYOR,MAYOR_GUALACEO,C1,Candidatura Uno,ORG1,10,1\n';imp.run(source.id,'CNE_CANDIDATES','wizard-candidates.csv',candidates,admin)
 organizations=client.get(f'/api/v1/political-organizations?source_id={source.id}',headers=admin_headers)
 candidate_rows=client.get(f'/api/v1/electoral-processes/{process.id}/contests/{contest.id}/candidates',headers=admin_headers)
 geography_rows=client.get(f'/api/v1/electoral-processes/{process.id}/geographies?aggregation_level=PARISH&canton_id={canton.id}&is_mapped=true',headers=admin_headers)
 assert organizations.status_code==200 and organizations.json()[0]['external_code']=='ORG1'
 assert candidate_rows.status_code==200 and candidate_rows.json()[0]['external_code']=='C1'
 assert geography_rows.status_code==200 and geography_rows.json()[0]['external_code']=='010350'
