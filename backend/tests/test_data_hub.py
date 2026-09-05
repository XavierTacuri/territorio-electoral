from datetime import date
import pytest
from sqlalchemy import select
from app.core.security import hash_password
from app.models.historical import DataImportError,DatasetVersion
from app.models.territory import Canton,Province
from app.models.user import User
from app.schemas.historical import DataSourceCreate,DemographicIndicatorCreate
from app.scripts.seed_gualaceo import seed as seed_gualaceo
from app.services.data_import_service import DataImportService
from app.services.data_source_service import DataSourceService
from app.services.dataset_version_service import DatasetVersionService
from app.services.demographic_service import DemographicService
from app.services.exceptions import BusinessRuleError
from app.services.role_service import RoleService

@pytest.fixture
def ctx(db,admin):
 province,canton,parishes=seed_gualaceo(db);db.commit()
 source=DataSourceService(db).create(DataSourceCreate(code='DH_CNE_SOURCE',institution='Consejo Nacional Electoral',dataset_name='Registro electoral sintético',dataset_type='CNE_ELECTORAL_ROLL_SNAPSHOT',reference_date=date(2026,1,1)),admin)
 return source,province,canton,parishes

def user_for(db,role_code,suffix):
 role=RoleService(db).repository.get_by_code(role_code)
 user=User(email=f'{suffix}@example.test',username=suffix,first_name=suffix,last_name='Test',hashed_password=hash_password('Pass123!x'),is_active=True,roles=[role]);db.add(user);db.flush();return user

def login(client,username):
 r=client.post('/api/v1/auth/login',data={'username':username,'password':'Pass123!x'});return {'Authorization':f"Bearer {r.json()['access_token']}"}

# --- §17/§55: territorial (province⊃canton⊃parish) consistency for demographic observations ---

def test_demographic_observation_dpa_hierarchy_regression(db,admin,ctx):
 source,province,canton,parishes=ctx
 other_province=Province(code='02',name='OtraProvincia');db.add(other_province);db.flush()
 foreign_canton=Canton(province_id=other_province.id,code='99',dpa_code='0299',name='CantonAjeno');db.add(foreign_canton)
 sibling_canton=Canton(province_id=province.id,code='04',dpa_code='0104',name='CantonHermano');db.add(sibling_canton);db.flush()
 DemographicService(db).create(DemographicIndicatorCreate(code='POP_TOTAL',name='Población total',category='POPULATION',unit='COUNT',value_type='INTEGER',source_id=source.id))
 header='indicator_code,reference_year,geography_level,province_dpa,canton_dpa,parish_dpa,value,numerator,denominator\n'
 svc=DataImportService(db)
 good=(header+f'POP_TOTAL,2022,PARISH,01,0103,{parishes[0].dpa_code},1000,,\n').encode()
 assert svc.run(source.id,'INEC_DEMOGRAPHIC_INDICATORS','ok.csv',good,admin,True,'CANONICAL_DEMOGRAPHIC_OBSERVATION').status=='VALIDATED'
 wrong_province=(header+f'POP_TOTAL,2022,PARISH,01,0299,{parishes[0].dpa_code},1000,,\n').encode()
 job=svc.run(source.id,'INEC_DEMOGRAPHIC_INDICATORS','wp.csv',wrong_province,admin,True,'CANONICAL_DEMOGRAPHIC_OBSERVATION');assert job.status=='REJECTED'
 error=db.scalar(select(DataImportError).where(DataImportError.import_job_id==job.id));assert 'provincia' in error.message.lower()
 wrong_canton=(header+f'POP_TOTAL,2022,PARISH,01,0104,{parishes[0].dpa_code},1000,,\n').encode()
 job=svc.run(source.id,'INEC_DEMOGRAPHIC_INDICATORS','wc.csv',wrong_canton,admin,True,'CANONICAL_DEMOGRAPHIC_OBSERVATION');assert job.status=='REJECTED'
 error=db.scalar(select(DataImportError).where(DataImportError.import_job_id==job.id));assert 'cantón' in error.message.lower()
 missing_zero=(header+'POP_TOTAL,2022,CANTON,1,103,,1000,,\n').encode()
 job=svc.run(source.id,'INEC_DEMOGRAPHIC_INDICATORS','mz.csv',missing_zero,admin,True,'CANONICAL_DEMOGRAPHIC_OBSERVATION');assert job.status=='REJECTED'
 error=db.scalar(select(DataImportError).where(DataImportError.import_job_id==job.id));assert 'mapear' in error.message.lower()

# --- §18/§56: demographic indicator existence must fail at validate, never VALIDATED→FAILED ---

def test_demographic_observation_missing_indicator_rejected_at_validate_not_execute(db,admin,ctx):
 source,province,canton,parishes=ctx
 content=(f'indicator_code,reference_year,geography_level,province_dpa,canton_dpa,parish_dpa,value,numerator,denominator\nGHOST_INDICATOR,2022,CANTON,01,0103,,42000,,\n').encode()
 svc=DataImportService(db)
 preflight=svc.run(source.id,'INEC_DEMOGRAPHIC_INDICATORS','d.csv',content,admin,True,'CANONICAL_DEMOGRAPHIC_OBSERVATION')
 assert preflight.status=='REJECTED'
 error=db.scalar(select(DataImportError).where(DataImportError.import_job_id==preflight.id));assert 'GHOST_INDICATOR' in error.message
 executed=svc.run(source.id,'INEC_DEMOGRAPHIC_INDICATORS','d.csv',content,admin,False,'CANONICAL_DEMOGRAPHIC_OBSERVATION')
 assert executed.status=='REJECTED'

# --- DatasetVersion lifecycle, activation safety, RBAC, catalog, diff, template ---

def roll_csv(snapshot_date,parishes,values):
 header='snapshot_date,process_code,geography_level,province_dpa,canton_dpa,parish_dpa,registered_voters,male_voters,female_voters,electoral_zones,juntas\n'
 rows=''.join(f'{snapshot_date},,PARISH,01,0103,{p.dpa_code},{v},{v//2},{v-v//2},,\n' for p,v in zip(parishes,values))
 return (header+rows).encode()

def test_dataset_version_lifecycle_rbac_diff_and_template(client,db,admin,admin_headers,ctx):
 source,province,canton,parishes=ctx
 user_for(db,'ANALYST','dh_analyst');user_for(db,'CANDIDATE','dh_candidate');db.commit()
 analyst_headers=login(client,'dh_analyst');candidate_headers=login(client,'dh_candidate')
 data={'source_id':str(source.id),'dataset_type':'CNE_ELECTORAL_ROLL_SNAPSHOT','mapping_profile':'CANONICAL_ELECTORAL_ROLL_SNAPSHOT'}
 v1_csv=roll_csv('2026-06-01',parishes[:2],[600,400]);v2_csv=roll_csv('2026-07-16',parishes[:2],[500,200])
 assert client.post('/api/v1/data-imports/execute',data=data,files={'file':('v1.csv',v1_csv,'text/csv')}).status_code==401
 assert client.post('/api/v1/data-imports/execute',headers=analyst_headers,data=data,files={'file':('v1.csv',v1_csv,'text/csv')}).status_code==403
 r1=client.post('/api/v1/data-imports/execute',headers=admin_headers,data=data,files={'file':('v1.csv',v1_csv,'text/csv')});assert r1.status_code==200 and r1.json()['status']=='COMPLETED'
 r2=client.post('/api/v1/data-imports/execute',headers=admin_headers,data=data,files={'file':('v2.csv',v2_csv,'text/csv')});assert r2.status_code==200 and r2.json()['status']=='COMPLETED'
 detail=client.get('/api/v1/data-hub/datasets/CNE_ELECTORAL_ROLL_SNAPSHOT',headers=admin_headers).json()
 assert len(detail['versions'])==2 and detail['active_version'] is None
 v1=next(v for v in detail['versions'] if v['reference_date']=='2026-06-01')
 v2=next(v for v in detail['versions'] if v['reference_date']=='2026-07-16')
 assert v1['status']=='VALIDATED' and v2['status']=='VALIDATED'
 assert client.post(f"/api/v1/data-hub/versions/{v2['id']}/activate",headers=analyst_headers).status_code==403
 act=client.post(f"/api/v1/data-hub/versions/{v2['id']}/activate",headers=admin_headers);assert act.status_code==200 and act.json()['status']=='ACTIVE'
 detail2=client.get('/api/v1/data-hub/datasets/CNE_ELECTORAL_ROLL_SNAPSHOT',headers=admin_headers).json()
 assert detail2['active_version']['id']==v2['id'] and len(detail2['versions'])==2
 assert next(v for v in detail2['versions'] if v['id']==v1['id'])['status']=='VALIDATED'
 act1=client.post(f"/api/v1/data-hub/versions/{v1['id']}/activate",headers=admin_headers);assert act1.status_code==200 and act1.json()['status']=='ACTIVE'
 detail3=client.get('/api/v1/data-hub/datasets/CNE_ELECTORAL_ROLL_SNAPSHOT',headers=admin_headers).json()
 assert detail3['active_version']['id']==v1['id']
 assert next(v for v in detail3['versions'] if v['id']==v2['id'])['status']=='SUPERSEDED'
 rollback=client.post(f"/api/v1/data-hub/versions/{v2['id']}/activate",headers=admin_headers);assert rollback.status_code==200
 assert client.post(f"/api/v1/data-hub/versions/{v2['id']}/activate",headers=admin_headers).status_code==409
 diff=client.get(f"/api/v1/data-hub/versions/{v2['id']}/diff",headers=analyst_headers);assert diff.status_code==200
 body=diff.json();assert body['comparable'] and body['delta']==-300 and body['warnings'] and len(body['items'])==2
 assert client.get('/api/v1/data-hub/catalog',headers=candidate_headers).status_code==403
 catalog=client.get('/api/v1/data-hub/catalog',headers=analyst_headers);assert catalog.status_code==200 and catalog.json()['summary']['datasets']>=1
 tmpl=client.get('/api/v1/data-import-profiles/CNE_TURNOUT/template',headers=admin_headers);assert tmpl.status_code==200 and 'province_dpa' in tmpl.text
 assert client.get('/api/v1/data-import-profiles/CNE_TURNOUT/template',headers=analyst_headers).status_code==403

def test_activate_refuses_version_whose_job_is_not_completed(db,admin,ctx):
 source,province,canton,parishes=ctx
 content=roll_csv('2026-01-01',parishes[:1],[100])
 job=DataImportService(db).run(source.id,'CNE_ELECTORAL_ROLL_SNAPSHOT','r.csv',content,admin,False,'CANONICAL_ELECTORAL_ROLL_SNAPSHOT');assert job.status=='COMPLETED'
 version=DatasetVersionService(db).create_from_job(job,source)
 job.status='FAILED';db.commit()
 with pytest.raises(BusinessRuleError):DatasetVersionService(db).activate(version.id,admin)

def test_only_one_active_version_per_scope_at_db_level(db,admin,ctx):
 source,province,canton,parishes=ctx
 job1=DataImportService(db).run(source.id,'CNE_ELECTORAL_ROLL_SNAPSHOT','a.csv',roll_csv('2026-02-01',parishes[:1],[10]),admin,False,'CANONICAL_ELECTORAL_ROLL_SNAPSHOT')
 job2=DataImportService(db).run(source.id,'CNE_ELECTORAL_ROLL_SNAPSHOT','b.csv',roll_csv('2026-03-01',parishes[:1],[20]),admin,False,'CANONICAL_ELECTORAL_ROLL_SNAPSHOT')
 svc=DatasetVersionService(db);v1=svc.create_from_job(job1,source);v2=svc.create_from_job(job2,source)
 svc.activate(v1.id,admin);svc.activate(v2.id,admin)
 actives=list(db.scalars(select(DatasetVersion).where(DatasetVersion.data_source_id==source.id,DatasetVersion.dataset_type=='CNE_ELECTORAL_ROLL_SNAPSHOT',DatasetVersion.status=='ACTIVE')))
 assert len(actives)==1 and actives[0].id==v2.id
