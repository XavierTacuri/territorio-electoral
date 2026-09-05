from datetime import date
from uuid import uuid4
import pytest
from sqlalchemy import func,select
from app.models.historical import DataImportJob,DatasetVersion,DemographicIndicator,DemographicObservation,ElectoralCandidateResult
from app.schemas.campaign import CampaignCreate
from app.schemas.historical import DataSourceCreate,DemographicIndicatorCreate,ElectoralContestCreate,ElectoralProcessCreate
from app.schemas.territory_ai import TerritoryAIEvidence,TerritoryAIQueryPlan,TerritoryAIIntent,TerritoryAISourceKind
from app.scripts.seed_gualaceo import seed as seed_gualaceo
from app.services.campaign_service import CampaignService
from app.services.data_import_service import DataImportService
from app.services.data_source_service import DataSourceService
from app.services.dataset_version_service import DatasetVersionService,version_kind,version_kind_label
from app.services.demographic_service import DemographicService
from app.services.electoral_service import ElectoralService
from app.services.territory_ai_retrieval import TerritoryAIEvidenceRetriever
from app.services.territory_ai_service import TerritoryAiService

# --- §2/§3: real classification of datasets, not assumed ---

def test_version_kind_classification_is_real_not_assumed():
 assert version_kind('CNE_ELECTORAL_ROLL_SNAPSHOT')=='SNAPSHOT_VERSIONED'
 assert version_kind_label('CNE_ELECTORAL_ROLL_SNAPSHOT')=='Histórico por corte'
 for upsert_type in ('CNE_TURNOUT','CNE_ELECTORAL_RESULTS','CNE_CANDIDATES','CNE_POLITICAL_ORGANIZATIONS','INEC_DEMOGRAPHIC_INDICATORS'):
  assert version_kind(upsert_type)=='UPSERT_GOVERNED',upsert_type
  assert version_kind_label(upsert_type)=='Versión administrativa'

def test_version_kind_exposed_in_catalog_and_detail_api(client,admin_headers,db,admin):
 seed_gualaceo(db);db.commit()
 DataSourceService(db).create(DataSourceCreate(code='CLOSURE_CNE_ROLL',institution='CNE',dataset_name='Registro',dataset_type='CNE_ELECTORAL_ROLL_SNAPSHOT'),admin)
 DataSourceService(db).create(DataSourceCreate(code='CLOSURE_CNE_TURNOUT',institution='CNE',dataset_name='Participación',dataset_type='CNE_TURNOUT'),admin)
 catalog=client.get('/api/v1/data-hub/catalog',headers=admin_headers).json()
 by_type={e['dataset_type']:e for e in catalog['entries']}
 assert by_type['CNE_ELECTORAL_ROLL_SNAPSHOT']['version_kind']=='SNAPSHOT_VERSIONED'
 assert by_type['CNE_ELECTORAL_ROLL_SNAPSHOT']['version_kind_label']=='Histórico por corte'
 assert by_type['CNE_TURNOUT']['version_kind']=='UPSERT_GOVERNED'
 assert by_type['CNE_TURNOUT']['version_kind_label']=='Versión administrativa'
 detail=client.get('/api/v1/data-hub/datasets/CNE_TURNOUT',headers=admin_headers).json()
 assert detail['version_kind']=='UPSERT_GOVERNED' and detail['version_kind_label']=='Versión administrativa'

# --- §7/§8: audit ElectoralCandidateResult reimport — demonstrate bug or its absence ---

def test_candidate_result_reimport_upserts_without_duplication_or_mixed_versions(db,admin):
 province,canton,parishes=seed_gualaceo(db);db.commit()
 source=DataSourceService(db).create(DataSourceCreate(code='CLOSURE_RESULT_SOURCE',institution='CNE',dataset_name='Resultados',dataset_type='CNE_ELECTORAL_RESULTS'),admin)
 service=ElectoralService(db)
 process=service.create_process(ElectoralProcessCreate(code='CLOSURE_PROC',name='Proceso cierre',process_type='SECTIONAL',election_date=date(2023,2,5),year=2023,status='VALIDATED',source_id=source.id))
 contest=service.create_contest(process.id,ElectoralContestCreate(office_type='MAYOR',name='MAYOR_CLOSURE',vote_method='SINGLE_CHOICE',canton_id=canton.id))
 imp=DataImportService(db)
 turnout=b'process_code,contest_code,geography_level,geography_code,province_dpa,canton_dpa,parish_dpa,zone_code,precinct_code,jrv_code,registered_voters,ballots_cast,valid_votes,blank_votes,null_votes,other_votes,is_final\nCLOSURE_PROC,MAYOR_CLOSURE,PARISH,010350,01,0103,010350,,,,100,80,70,5,5,0,1\n'
 imp.run(source.id,'CNE_TURNOUT','t.csv',turnout,admin,False,'CANONICAL_ELECTORAL_TURNOUT')
 candidates=b'process_code,office_type,contest_code,candidate_code,full_name,organization_code,list_number,ballot_order\nCLOSURE_PROC,MAYOR,MAYOR_CLOSURE,C1,Candidato Uno,,,1\nCLOSURE_PROC,MAYOR,MAYOR_CLOSURE,C2,Candidato Dos,,,2\n'
 imp.run(source.id,'CNE_CANDIDATES','c.csv',candidates,admin,False,'CANONICAL_ELECTORAL_CANDIDATE')
 v1=b'process_code,contest_code,geography_level,geography_code,candidate_code,votes,is_final\nCLOSURE_PROC,MAYOR_CLOSURE,PARISH,010350,C1,40,1\nCLOSURE_PROC,MAYOR_CLOSURE,PARISH,010350,C2,30,1\n'
 job1=imp.run(source.id,'CNE_ELECTORAL_RESULTS','r1.csv',v1,admin,False,'CANONICAL_ELECTORAL_CANDIDATE_RESULT');assert job1.status=='COMPLETED'
 ranked=service.results(process.id,contest.id,'PARISH');assert ranked[0].votes==40 and ranked[1].votes==30
 v2=b'process_code,contest_code,geography_level,geography_code,candidate_code,votes,is_final\nCLOSURE_PROC,MAYOR_CLOSURE,PARISH,010350,C1,45,1\nCLOSURE_PROC,MAYOR_CLOSURE,PARISH,010350,C2,25,1\n'
 job2=imp.run(source.id,'CNE_ELECTORAL_RESULTS','r2.csv',v2,admin,False,'CANONICAL_ELECTORAL_CANDIDATE_RESULT');assert job2.status=='COMPLETED' and job2.rows_updated==2 and job2.rows_inserted==0
 total_rows=db.scalar(select(func.count()).select_from(ElectoralCandidateResult))
 assert total_rows==2,'la reimportación no debe duplicar filas (una por candidatura/geografía)'
 ranked=service.results(process.id,contest.id,'PARISH')
 assert len(ranked)==2 and {r.votes for r in ranked}=={45,25},'debe reflejar únicamente los valores corregidos, no una mezcla de V1 y V2'
 summary=service.territorial_summary(process.id,contest.id)
 assert summary.items[0]['winner_votes']==45 and summary.items[0]['margin_votes']==20

# --- §9/§10: pin down that roll-snapshot consumption is keyed by snapshot_date, not DatasetVersion.ACTIVE ---

def test_roll_snapshot_consumption_follows_latest_snapshot_date_not_active_dataset_version(db,admin):
 province,canton,parishes=seed_gualaceo(db);db.commit()
 source=DataSourceService(db).create(DataSourceCreate(code='CLOSURE_ROLL_SOURCE',institution='CNE',dataset_name='Registro',dataset_type='CNE_ELECTORAL_ROLL_SNAPSHOT'),admin)
 campaign=CampaignService(db).create(CampaignCreate(name='Cierre Data Hub',slug='cierre-data-hub',canton_id=canton.id,office_type='MAYOR',election_name='Elección cierre',election_date=date(2027,2,14),status='DRAFT'),admin)
 header='snapshot_date,process_code,geography_level,province_dpa,canton_dpa,parish_dpa,registered_voters,male_voters,female_voters,electoral_zones,juntas\n'
 imp=DataImportService(db)
 job_old=imp.run(source.id,'CNE_ELECTORAL_ROLL_SNAPSHOT','old.csv',(header+f'2026-01-01,,PARISH,01,0103,{parishes[0].dpa_code},1000,500,500,,\n').encode(),admin,False,'CANONICAL_ELECTORAL_ROLL_SNAPSHOT')
 job_new=imp.run(source.id,'CNE_ELECTORAL_ROLL_SNAPSHOT','new.csv',(header+f'2026-06-01,,PARISH,01,0103,{parishes[0].dpa_code},1200,600,600,,\n').encode(),admin,False,'CANONICAL_ELECTORAL_ROLL_SNAPSHOT')
 dvs=DatasetVersionService(db)
 v_old=dvs.create_from_job(job_old,source);v_new=dvs.create_from_job(job_new,source)
 dvs.activate(v_old.id,admin)  # deliberately activate the OLDER corte as the governance "reference"
 assert dvs.active_for(source.id,'CNE_ELECTORAL_ROLL_SNAPSHOT').id==v_old.id
 retriever=TerritoryAIEvidenceRetriever(db)
 plan=TerritoryAIQueryPlan(intent=TerritoryAIIntent.ELECTORAL_REGISTER,source_kinds=[TerritoryAISourceKind.CNE],territory=None)
 evidence=retriever._cne(campaign.id,admin,plan,None,'padrón')
 padron=[e for e in evidence if e.structured_data.get('registered_voters') is not None and e.freshness=='CURRENT']
 assert padron,'debe existir evidencia del padrón actual'
 assert padron[0].structured_data['registered_voters']==1200,(
  'el consumo real (Territorio IA/Panorama) usa el corte con snapshot_date más reciente; '
  'activar una DatasetVersion distinta en el Data Hub no cambia qué corte se consume, '
  'porque el contrato de selección sigue siendo snapshot_date, no DatasetVersion.ACTIVE'
 )

# --- §11: demographic observation consumption is still source/reference_year/is_active, not DatasetVersion ---

def test_demographic_consumption_uses_reference_year_not_dataset_version(db,admin):
 province,canton,parishes=seed_gualaceo(db);db.commit()
 source=DataSourceService(db).create(DataSourceCreate(code='CLOSURE_INEC_SOURCE',institution='INEC',dataset_name='Demografía',dataset_type='INEC_DEMOGRAPHIC_INDICATORS'),admin)
 DemographicService(db).create(DemographicIndicatorCreate(code='POP_TOTAL',name='Población total',category='POPULATION',unit='COUNT',value_type='INTEGER',source_id=source.id))
 imp=DataImportService(db)
 header='indicator_code,reference_year,geography_level,province_dpa,canton_dpa,parish_dpa,value,numerator,denominator\n'
 job2010=imp.run(source.id,'INEC_DEMOGRAPHIC_INDICATORS','y2010.csv',(header+'POP_TOTAL,2010,CANTON,01,0103,,38000,,\n').encode(),admin,False,'CANONICAL_DEMOGRAPHIC_OBSERVATION')
 job2022=imp.run(source.id,'INEC_DEMOGRAPHIC_INDICATORS','y2022.csv',(header+'POP_TOTAL,2022,CANTON,01,0103,,43188,,\n').encode(),admin,False,'CANONICAL_DEMOGRAPHIC_OBSERVATION')
 dvs=DatasetVersionService(db);v2010=dvs.create_from_job(job2010,source);dvs.create_from_job(job2022,source)
 dvs.activate(v2010.id,admin)  # ACTIVE points at the 2010 import; 2022 stays VALIDATED
 profile=DemographicService(db).profile(canton.id,reference_year=2022)
 assert profile['observations'][0]['value']=='43188.0000','el perfil por año sigue seleccionando por reference_year, no por la versión ACTIVE'
 profile_old=DemographicService(db).profile(canton.id,reference_year=2010)
 assert profile_old['observations'][0]['value']=='38000.0000'

# --- §12/§13: provenance must cite the exact import behind the row, not just "whichever version is ACTIVE" ---

def test_citation_resolves_exact_import_version_not_merely_active_source_version(db,admin):
 province,canton,parishes=seed_gualaceo(db);db.commit()
 source=DataSourceService(db).create(DataSourceCreate(code='CLOSURE_PROVENANCE_SOURCE',institution='INEC',dataset_name='Demografía',dataset_type='INEC_DEMOGRAPHIC_INDICATORS'),admin)
 DemographicService(db).create(DemographicIndicatorCreate(code='POP_TOTAL',name='Población total',category='POPULATION',unit='COUNT',value_type='INTEGER',source_id=source.id))
 imp=DataImportService(db)
 header='indicator_code,reference_year,geography_level,province_dpa,canton_dpa,parish_dpa,value,numerator,denominator\n'
 job1=imp.run(source.id,'INEC_DEMOGRAPHIC_INDICATORS','v1.csv',(header+'POP_TOTAL,2022,CANTON,01,0103,,40000,,\n').encode(),admin,False,'CANONICAL_DEMOGRAPHIC_OBSERVATION')
 job2=imp.run(source.id,'INEC_DEMOGRAPHIC_INDICATORS','v2.csv',(header+'POP_TOTAL,2022,CANTON,01,0103,,43188,,\n').encode(),admin,False,'CANONICAL_DEMOGRAPHIC_OBSERVATION')
 dvs=DatasetVersionService(db);v1=dvs.create_from_job(job1,source);v2=dvs.create_from_job(job2,source)
 dvs.activate(v1.id,admin)  # ACTIVE = v1, even though the live row now comes from job2
 obs=db.scalar(select(DemographicObservation))
 assert obs.import_job_id==job2.id and obs.value==43188
 assert v1.version_label!=v2.version_label
 evidence=TerritoryAIEvidence(evidence_id='1',source_kind=TerritoryAISourceKind.INEC,title='Población total',source_name='INEC',campaign_id=uuid4(),data_source_id=source.id,import_job_id=obs.import_job_id,record_date=date(2022,1,1))
 svc=TerritoryAiService(db,provider=None)
 citation=svc._citation(evidence)
 assert citation.dataset_version_label==v2.version_label,'debe citar la versión de la importación real (job2), no la versión ACTIVE (v1) que no corresponde al dato citado'

def test_padron_citation_includes_institution_dataset_cutoff_and_correct_version(db,admin):
 province,canton,parishes=seed_gualaceo(db);db.commit()
 source=DataSourceService(db).create(DataSourceCreate(code='CLOSURE_PADRON_SOURCE',institution='Consejo Nacional Electoral',dataset_name='Registro electoral',dataset_type='CNE_ELECTORAL_ROLL_SNAPSHOT',official_url='https://cne.gob.ec/registro.csv'),admin)
 campaign=CampaignService(db).create(CampaignCreate(name='Cierre Padrón',slug='cierre-padron',canton_id=canton.id,office_type='MAYOR',election_name='Elección cierre padrón',election_date=date(2027,2,14),status='DRAFT'),admin)
 header='snapshot_date,process_code,geography_level,province_dpa,canton_dpa,parish_dpa,registered_voters,male_voters,female_voters,electoral_zones,juntas\n'
 job=DataImportService(db).run(source.id,'CNE_ELECTORAL_ROLL_SNAPSHOT','corte.csv',(header+f'2026-07-16,,PARISH,01,0103,{parishes[0].dpa_code},34784,17000,17784,,\n').encode(),admin,False,'CANONICAL_ELECTORAL_ROLL_SNAPSHOT')
 version=DatasetVersionService(db).create_from_job(job,source)
 retriever=TerritoryAIEvidenceRetriever(db)
 plan=TerritoryAIQueryPlan(intent=TerritoryAIIntent.ELECTORAL_REGISTER,source_kinds=[TerritoryAISourceKind.CNE],territory=None)
 evidence=retriever._cne(campaign.id,admin,plan,None,'¿de qué fecha es el padrón electoral utilizado?')
 padron=[e for e in evidence if e.freshness=='CURRENT' and e.structured_data.get('registered_voters')==34784][0]
 svc=TerritoryAiService(db,provider=None)
 citation=svc._citation(padron)
 assert citation.source_name=='Consejo Nacional Electoral'
 assert citation.reference_date==date(2026,7,16)
 assert citation.dataset_version_label==version.version_label=='Corte 2026-07-16'
