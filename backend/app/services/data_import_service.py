import hashlib,json,re,tempfile
from datetime import date,datetime,timezone
from decimal import Decimal,InvalidOperation
from pathlib import Path
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.importers.csv_utils import parse_csv
from app.importers.mappings import DATASET_PROFILE
from app.models.election_day import ElectoralBoard,PollingPlace
from app.models.historical import *
from app.models.territory import Province,Canton,Parish
from app.services.data_source_service import DataSourceService
from app.services.exceptions import BusinessRuleError,ConflictError,NotFoundError
MASK=re.compile(r'(?i)([\w.+-]+@[\w.-]+|\b\d{10}\b|(?:\+?593|0)?9\d{8})')
def boolean(v):return str(v).strip().lower() in {'1','true','t','yes','si','sí'}
def integer(v,name):
 try:return int(v or 0)
 except ValueError:raise BusinessRuleError(f'{name}: entero inválido')
def decimal(v,name,optional=False):
 if optional and not v:return None
 try:return Decimal(v)
 except InvalidOperation:raise BusinessRuleError(f'{name}: decimal inválido')
def coordinate(v,name,lo,hi):
 if not v:return None
 try:value=float(v)
 except ValueError:raise BusinessRuleError(f'{name}: coordenada inválida')
 if not lo<=value<=hi:raise BusinessRuleError(f'{name}: fuera de rango')
 return value
class DataImportService:
 def __init__(self,db:Session):self.db=db
 def run(self,source_id:UUID,dataset_type:str,filename:str,content:bytes,user,validation_only=False,profile=None,encoding=None,delimiter=None,mapping=None,force=False):
  source=DataSourceService(self.db).get(source_id)
  if not source.is_active:raise BusinessRuleError('Fuente inactiva')
  if Path(filename).suffix.lower()!='.csv':raise BusinessRuleError('Solo se permiten archivos CSV')
  if len(content)>settings.data_import_max_file_mb*1024*1024:raise BusinessRuleError('Archivo demasiado grande')
  sha=hashlib.sha256(content).hexdigest();existing=self.db.scalar(select(DataImportJob).where(DataImportJob.source_id==source_id,DataImportJob.dataset_type==dataset_type,DataImportJob.file_sha256==sha,DataImportJob.status=='COMPLETED'))
  if existing and not force:raise ConflictError('El archivo ya fue importado')
  profile=profile or DATASET_PROFILE.get(dataset_type)
  if not profile:raise BusinessRuleError('Tipo de conjunto sin perfil canónico')
  job=DataImportJob(source_id=source_id,dataset_type=dataset_type,original_filename=Path(filename).name[:255],file_sha256=sha,file_size_bytes=len(content),status='VALIDATING',validation_only=validation_only,mapping_profile=profile,executed_by_user_id=user.id);self.db.add(job);self.db.commit();self.db.refresh(job)
  temp=None
  try:
   with tempfile.NamedTemporaryFile(prefix='te-import-',suffix='.csv',delete=False) as handle:handle.write(content);temp=Path(handle.name)
   rows,used,delim=parse_csv(temp.read_bytes(),profile,encoding,delimiter,mapping);job.encoding_used=used;job.delimiter_used=delim;job.rows_read=len(rows)
   issues=self.validate(profile,rows,source)
   job.rows_failed=len(issues);job.rows_valid=max(0,len(rows)-len(issues))
   for issue in issues[:settings.data_import_max_errors]:self.db.add(DataImportError(import_job_id=job.id,row_number=issue[0],column_name=issue[1],error_code=issue[2],message=issue[3][:500],rejected_value_preview=MASK.sub('[REDACTED]',str(issue[4] or ''))[:120] or None))
   if issues:
    job.status='REJECTED';job.error_summary=f'{len(issues)} errores de validación';job.finished_at=datetime.now(timezone.utc);self.db.commit();return job
   if validation_only:job.status='VALIDATED';job.finished_at=datetime.now(timezone.utc);self.db.commit();return job
   job.status='IMPORTING';self.db.commit()
   inserted,updated=self.import_rows(profile,rows,source,job)
   job.rows_inserted=inserted;job.rows_updated=updated;job.status='COMPLETED';job.finished_at=datetime.now(timezone.utc);self.db.commit();return job
  except Exception as exc:
   self.db.rollback();job=self.db.get(DataImportJob,job.id);job.status='FAILED';job.error_summary='La importación no pudo completarse';job.finished_at=datetime.now(timezone.utc);self.db.commit();raise
  finally:
   if temp and temp.exists():temp.unlink()
 def validate(self,profile,rows,source=None):
  issues=[]
  candidate_codes=set();result_keys=set();turnout_keys=set();roll_keys=set();polling_place_keys=set();board_keys=set()
  for n,r in rows:
   try:
    if profile=='CANONICAL_ELECTORAL_PROCESS':
     date.fromisoformat(r['election_date'])
     if not r['process_code'] or not r['name']:raise BusinessRuleError('Código y nombre de proceso requeridos')
     if r['process_type'].upper() not in {'SECTIONAL','GENERAL','REFERENDUM','CONSULTATION','OTHER'}:raise BusinessRuleError('Tipo de proceso inválido')
     if r['status'].upper() not in {'DRAFT','IMPORTED','VALIDATED','PUBLISHED','ARCHIVED'}:raise BusinessRuleError('Estado de proceso inválido')
    elif profile=='CANONICAL_ELECTORAL_TURNOUT':
     process,contest=self.process_contest(r)
     level=r['geography_level'].upper()
     if level not in {'PROVINCE','CANTON','PARISH','ZONE','PRECINCT','JRV'}:raise BusinessRuleError('Nivel geográfico inválido')
     if not r['geography_code']:raise BusinessRuleError('Código territorial requerido')
     key=(contest.id,level,r['geography_code'])
     if key in turnout_keys:raise BusinessRuleError('Geografía duplicada en participación')
     turnout_keys.add(key)
     for field in ['registered_voters','ballots_cast','valid_votes','blank_votes','null_votes','other_votes']:
      if r[field]=='':raise BusinessRuleError(f'{field}: valor requerido')
     vals=[integer(r[x],x) for x in ['registered_voters','ballots_cast','valid_votes','blank_votes','null_votes','other_votes']]
     if any(x<0 for x in vals):raise BusinessRuleError('Valores negativos')
     if vals[1]>vals[0]:raise BusinessRuleError('Sufragantes superiores a electores')
     if sum(vals[2:])!=vals[1]:raise BusinessRuleError('Totales de papeletas inconsistentes')
     self.validate_geography_mapping(level,r)
    elif profile=='CANONICAL_POLITICAL_ORGANIZATION':
     if not r['name']:raise BusinessRuleError('Nombre de organización requerido')
    elif profile=='CANONICAL_ELECTORAL_CANDIDATE':
     _,contest=self.process_contest(r)
     if not r['candidate_code']:raise BusinessRuleError('Código de candidatura requerido')
     if not r['full_name']:raise BusinessRuleError('Nombre de candidatura requerido')
     if r['office_type'].upper() not in {'MAYOR','URBAN_COUNCILOR','RURAL_COUNCILOR','PARISH_BOARD','PREFECTURE','OTHER'}:raise BusinessRuleError('Dignidad inválida')
     if r['office_type'].upper()!=contest.office_type:raise BusinessRuleError('La dignidad no coincide con la contienda')
     key=(contest.id,r['candidate_code'])
     if key in candidate_codes:raise BusinessRuleError('Código de candidatura duplicado')
     candidate_codes.add(key)
     if r['ballot_order'] and integer(r['ballot_order'],'ballot_order')<1:raise BusinessRuleError('Orden de papeleta inválido')
     if r['organization_code']:
      if source is None:raise BusinessRuleError('Fuente requerida para validar la organización')
      organization=self.db.scalar(select(PoliticalOrganization).where(PoliticalOrganization.source_id==source.id,PoliticalOrganization.external_code==r['organization_code']))
      if not organization:raise BusinessRuleError(f'La organización {r["organization_code"]} no está registrada')
    elif profile=='CANONICAL_ELECTORAL_CANDIDATE_RESULT':
     process,contest=self.process_contest(r)
     level=r['geography_level'].upper()
     if level not in {'PROVINCE','CANTON','PARISH','ZONE','PRECINCT','JRV'}:raise BusinessRuleError('Nivel geográfico inválido')
     if not r['geography_code']:raise BusinessRuleError('Código territorial requerido')
     geo=self.db.scalar(select(ElectoralGeography).where(ElectoralGeography.electoral_process_id==process.id,ElectoralGeography.level==level,ElectoralGeography.external_code==r['geography_code']))
     if not geo:raise BusinessRuleError(f'El código territorial {r["geography_code"]} no tiene una geografía electoral registrada')
     if not geo.is_mapped:raise BusinessRuleError(f'El código territorial {r["geography_code"]} no tiene una geografía electoral mapeada')
     candidate=self.db.scalar(select(ElectoralCandidate).where(ElectoralCandidate.electoral_contest_id==contest.id,ElectoralCandidate.external_code==r['candidate_code']))
     if not candidate:raise BusinessRuleError(f'El candidato {r["candidate_code"]} no está registrado')
     key=(contest.id,geo.id,candidate.id)
     if key in result_keys:raise BusinessRuleError('Resultado duplicado para candidatura y geografía')
     result_keys.add(key)
     if integer(r['votes'],'votes')<0:raise BusinessRuleError('Votos negativos')
    elif profile=='CANONICAL_DEMOGRAPHIC_OBSERVATION':
     integer(r['reference_year'],'reference_year');decimal(r['value'],'value');den=decimal(r['denominator'],'denominator',True)
     if den is not None and den<=0:raise BusinessRuleError('Denominador inválido')
     if not self.db.scalar(select(DemographicIndicator).where(DemographicIndicator.code==r['indicator_code'].upper())):raise BusinessRuleError(f'El indicador {r["indicator_code"]} no está registrado')
     self.validate_geography_mapping(r['geography_level'].upper(),r)
    elif profile=='CANONICAL_DEMOGRAPHIC_INDICATOR' and not r['indicator_code']:raise BusinessRuleError('Código requerido')
    elif profile=='CANONICAL_ELECTORAL_ROLL_SNAPSHOT':
     process=self.db.scalar(select(ElectoralProcess).where(ElectoralProcess.code==r['process_code'].upper(),ElectoralProcess.is_active.is_(True))) if r['process_code'] else None
     if r['process_code'] and not process:raise BusinessRuleError('Proceso electoral inexistente')
     snapshot_date=date.fromisoformat(r['snapshot_date']);level=r['geography_level'].upper()
     if level not in {'PROVINCE','CANTON','PARISH'}:raise BusinessRuleError('Nivel geográfico inválido')
     if level=='PARISH' and (not r['province_dpa'] or not r['canton_dpa'] or not r['parish_dpa']):raise BusinessRuleError('DPA parroquial incompleto')
     province=self.db.scalar(select(Province).where(Province.code==r['province_dpa'])) if r['province_dpa'] else None;canton=self.db.scalar(select(Canton).where(Canton.dpa_code==r['canton_dpa'])) if r['canton_dpa'] else None;parish=self.db.scalar(select(Parish).where(Parish.dpa_code==r['parish_dpa'])) if r['parish_dpa'] else None
     target={'PROVINCE':province,'CANTON':canton,'PARISH':parish}[level]
     if not target:raise BusinessRuleError('Territorio no mapeado')
     if canton and province and canton.province_id!=province.id:raise BusinessRuleError('El cantón no pertenece a la provincia')
     if parish and canton and parish.canton_id!=canton.id:raise BusinessRuleError('La parroquia no pertenece al cantón')
     vals={x:integer(r[x],x) for x in ['registered_voters','male_voters','female_voters','electoral_zones','juntas'] if r[x] != ''}
     if 'registered_voters' not in vals:raise BusinessRuleError('Electores requeridos')
     if any(v<0 for v in vals.values()):raise BusinessRuleError('Conteos negativos')
     if {'male_voters','female_voters'}<=vals.keys() and vals['male_voters']+vals['female_voters']!=vals['registered_voters']:raise BusinessRuleError('Hombres y mujeres no suman electores')
     key=(r['process_code'].upper(),snapshot_date,level,province.id if province else None,canton.id if canton else None,parish.id if parish else None)
     if key in roll_keys:raise BusinessRuleError('Registro electoral duplicado')
     roll_keys.add(key)
    elif profile=='CANONICAL_POLLING_PLACE':
     if not self.db.scalar(select(ElectoralProcess).where(ElectoralProcess.code==r['process_code'].upper())):raise BusinessRuleError('Proceso electoral inexistente')
     if not r['polling_place_code'] or not r['polling_place_name']:raise BusinessRuleError('Código y nombre de recinto requeridos')
     province=self.db.scalar(select(Province).where(Province.code==r['province_dpa'])) if r['province_dpa'] else None
     canton=self.db.scalar(select(Canton).where(Canton.dpa_code==r['canton_dpa'])) if r['canton_dpa'] else None
     parish=self.db.scalar(select(Parish).where(Parish.dpa_code==r['parish_dpa'])) if r['parish_dpa'] else None
     if not province:raise BusinessRuleError('Provincia no encontrada para el DPA indicado')
     if not canton:raise BusinessRuleError('Cantón no encontrado para el DPA indicado')
     if not parish:raise BusinessRuleError('Parroquia no encontrada para el DPA indicado')
     if canton.province_id!=province.id:raise BusinessRuleError('El cantón no pertenece a la provincia indicada')
     if parish.canton_id!=canton.id:raise BusinessRuleError('La parroquia no pertenece al cantón indicado')
     coordinate(r['polling_place_latitude'],'polling_place_latitude',-90,90)
     coordinate(r['polling_place_longitude'],'polling_place_longitude',-180,180)
     key=(r['process_code'].upper(),r['polling_place_code'].upper())
     if key in polling_place_keys:raise BusinessRuleError('Código de recinto duplicado en el archivo')
     polling_place_keys.add(key)
    elif profile=='CANONICAL_ELECTORAL_BOARD':
     process=self.db.scalar(select(ElectoralProcess).where(ElectoralProcess.code==r['process_code'].upper()))
     if not process:raise BusinessRuleError('Proceso electoral inexistente')
     if not r['polling_place_code'] or not r['board_code']:raise BusinessRuleError('Código de recinto y de junta requeridos')
     place=self.db.scalar(select(PollingPlace).where(PollingPlace.electoral_process_id==process.id,PollingPlace.official_code==r['polling_place_code'].upper()))
     if not place:raise BusinessRuleError(f'El recinto {r["polling_place_code"]} no está registrado para este proceso')
     if integer(r['board_number'],'board_number')<1:raise BusinessRuleError('Número de junta inválido')
     if r['registered_voters'] and integer(r['registered_voters'],'registered_voters')<0:raise BusinessRuleError('Electores no pueden ser negativos')
     key=(place.id,r['board_code'].upper())
     if key in board_keys:raise BusinessRuleError('Código de junta duplicado en el archivo')
     board_keys.add(key)
   except (ValueError,BusinessRuleError) as e:issues.append((n,None,'INVALID_ROW',str(e),None))
  return issues
 def validate_geography_mapping(self,level,r):
  province=self.db.scalar(select(Province).where(Province.code==r.get('province_dpa'))) if r.get('province_dpa') else None
  canton=self.db.scalar(select(Canton).where(Canton.dpa_code==r.get('canton_dpa'))) if r.get('canton_dpa') else None
  parish=self.db.scalar(select(Parish).where(Parish.dpa_code==r.get('parish_dpa'))) if r.get('parish_dpa') else None
  target={'PROVINCE':province,'CANTON':canton,'PARISH':parish}.get(level,parish or canton)
  if target is None:raise BusinessRuleError('DPA sin mapear')
  if canton and province and canton.province_id!=province.id:raise BusinessRuleError('El cantón no pertenece a la provincia indicada')
  if parish and canton and parish.canton_id!=canton.id:raise BusinessRuleError('La parroquia no pertenece al cantón indicado')
 def import_rows(self,profile,rows,source,job):
  inserted=updated=0
  for _,r in rows:
   if profile=='CANONICAL_ELECTORAL_PROCESS':
    obj=self.db.scalar(select(ElectoralProcess).where(ElectoralProcess.code==r['process_code'].upper()));values=dict(name=r['name'],process_type=r['process_type'].upper(),election_date=date.fromisoformat(r['election_date']),year=date.fromisoformat(r['election_date']).year,status=r['status'].upper(),is_final=boolean(r['is_final']),source_id=source.id,is_active=True)
    if obj:
     for k,v in values.items():setattr(obj,k,v)
     updated+=1
    else:self.db.add(ElectoralProcess(code=r['process_code'].upper(),**values));inserted+=1
   elif profile=='CANONICAL_POLITICAL_ORGANIZATION':
    code=r['organization_code'] or re.sub(r'[^A-Z0-9]+','_',r['name'].upper()).strip('_');obj=self.db.scalar(select(PoliticalOrganization).where(PoliticalOrganization.source_id==source.id,PoliticalOrganization.external_code==code));values=dict(name=r['name'],short_name=r['short_name'] or None,organization_type=r['organization_type'] or None,list_number=r['list_number'] or None,scope=r['scope'] or None,is_active=True)
    if obj:
     for k,v in values.items():setattr(obj,k,v)
     updated+=1
    else:self.db.add(PoliticalOrganization(source_id=source.id,external_code=code,**values));inserted+=1
   elif profile=='CANONICAL_DEMOGRAPHIC_INDICATOR':
    obj=self.db.scalar(select(DemographicIndicator).where(DemographicIndicator.code==r['indicator_code'].upper()));values=dict(name=r['name'],description=r['description'] or None,category=r['category'].upper(),unit=r['unit'].upper(),value_type=r['value_type'].upper(),source_id=source.id,is_active=True)
    if obj:
     for k,v in values.items():setattr(obj,k,v)
     updated+=1
    else:self.db.add(DemographicIndicator(code=r['indicator_code'].upper(),**values));inserted+=1
   elif profile=='CANONICAL_ELECTORAL_TURNOUT':inserted,updated=self.upsert_turnout(r,source,job,inserted,updated)
   elif profile=='CANONICAL_ELECTORAL_CANDIDATE':inserted,updated=self.upsert_candidate(r,source,inserted,updated)
   elif profile=='CANONICAL_ELECTORAL_CANDIDATE_RESULT':inserted,updated=self.upsert_result(r,source,job,inserted,updated)
   elif profile=='CANONICAL_DEMOGRAPHIC_OBSERVATION':inserted,updated=self.upsert_observation(r,source,job,inserted,updated)
   elif profile=='CANONICAL_ELECTORAL_ROLL_SNAPSHOT':inserted,updated=self.upsert_roll_snapshot(r,source,job,inserted,updated)
   elif profile=='CANONICAL_POLLING_PLACE':inserted,updated=self.upsert_polling_place(r,source,job,inserted,updated)
   elif profile=='CANONICAL_ELECTORAL_BOARD':inserted,updated=self.upsert_electoral_board(r,source,job,inserted,updated)
  self.db.flush();return inserted,updated
 def upsert_polling_place(self,r,source,job,ins,upd):
  process=self.db.scalar(select(ElectoralProcess).where(ElectoralProcess.code==r['process_code'].upper()))
  parish=self.db.scalar(select(Parish).where(Parish.dpa_code==r['parish_dpa']));canton=self.db.get(Canton,parish.canton_id)
  code=r['polling_place_code'].upper();obj=self.db.scalar(select(PollingPlace).where(PollingPlace.electoral_process_id==process.id,PollingPlace.official_code==code))
  values=dict(name=r['polling_place_name'],address=r['polling_place_address'] or None,latitude=coordinate(r['polling_place_latitude'],'polling_place_latitude',-90,90),longitude=coordinate(r['polling_place_longitude'],'polling_place_longitude',-180,180),province_id=canton.province_id,canton_id=canton.id,parish_id=parish.id,data_source_id=source.id,import_job_id=job.id,is_active=True)
  if obj:
   for k,v in values.items():setattr(obj,k,v)
   return ins,upd+1
  self.db.add(PollingPlace(electoral_process_id=process.id,official_code=code,**values));return ins+1,upd
 def upsert_electoral_board(self,r,source,job,ins,upd):
  process=self.db.scalar(select(ElectoralProcess).where(ElectoralProcess.code==r['process_code'].upper()))
  place=self.db.scalar(select(PollingPlace).where(PollingPlace.electoral_process_id==process.id,PollingPlace.official_code==r['polling_place_code'].upper()))
  code=r['board_code'].upper();obj=self.db.scalar(select(ElectoralBoard).where(ElectoralBoard.polling_place_id==place.id,ElectoralBoard.official_code==code))
  values=dict(board_number=integer(r['board_number'],'board_number'),sex_category=r['sex_category'].upper() if r['sex_category'] else None,registered_voters=integer(r['registered_voters'],'registered_voters') if r['registered_voters'] else None,data_source_id=source.id,import_job_id=job.id,is_active=True)
  if obj:
   for k,v in values.items():setattr(obj,k,v)
   return ins,upd+1
  self.db.add(ElectoralBoard(polling_place_id=place.id,official_code=code,**values));return ins+1,upd
 def upsert_roll_snapshot(self,r,source,job,ins,upd):
  process=self.db.scalar(select(ElectoralProcess).where(ElectoralProcess.code==r['process_code'].upper())) if r['process_code'] else None
  snapshot_date=date.fromisoformat(r['snapshot_date']);snapshot=self.db.scalar(select(ElectoralRollSnapshot).where(ElectoralRollSnapshot.source_id==source.id,ElectoralRollSnapshot.snapshot_date==snapshot_date,ElectoralRollSnapshot.electoral_process_id==(process.id if process else None)))
  if not snapshot:
   snapshot=ElectoralRollSnapshot(source_id=source.id,electoral_process_id=process.id if process else None,snapshot_date=snapshot_date,name=f'Registro electoral CNE — {snapshot_date.isoformat()}',status='IMPORTED',is_final=True,created_by_user_id=job.executed_by_user_id);self.db.add(snapshot);self.db.flush()
  level=r['geography_level'].upper();province=self.db.scalar(select(Province).where(Province.code==r['province_dpa'])) if r['province_dpa'] else None;canton=self.db.scalar(select(Canton).where(Canton.dpa_code==r['canton_dpa'])) if r['canton_dpa'] else None;parish=self.db.scalar(select(Parish).where(Parish.dpa_code==r['parish_dpa'])) if r['parish_dpa'] else None
  cond=[ElectoralRollSnapshotEntry.snapshot_id==snapshot.id,ElectoralRollSnapshotEntry.geography_level==level,ElectoralRollSnapshotEntry.province_id==(province.id if province else None),ElectoralRollSnapshotEntry.canton_id==(canton.id if canton else None),ElectoralRollSnapshotEntry.parish_id==(parish.id if parish else None)];obj=self.db.scalar(select(ElectoralRollSnapshotEntry).where(*cond));values=dict(registered_voters=integer(r['registered_voters'],'registered_voters'),male_voters=integer(r['male_voters'],'male_voters') if r['male_voters'] else None,female_voters=integer(r['female_voters'],'female_voters') if r['female_voters'] else None,electoral_zones=integer(r['electoral_zones'],'electoral_zones') if r['electoral_zones'] else None,juntas=integer(r['juntas'],'juntas') if r['juntas'] else None,province_dpa=r['province_dpa'] or None,canton_dpa=r['canton_dpa'] or None,parish_dpa=r['parish_dpa'] or None)
  if obj:
   for k,v in values.items():setattr(obj,k,v)
   return ins,upd+1
  self.db.add(ElectoralRollSnapshotEntry(snapshot_id=snapshot.id,geography_level=level,province_id=province.id if province else None,canton_id=canton.id if canton else None,parish_id=parish.id if parish else None,**values));return ins+1,upd
 def process_contest(self,r):
  process=self.db.scalar(select(ElectoralProcess).where(ElectoralProcess.code==r['process_code'].upper()))
  if not process:raise BusinessRuleError('Proceso inexistente')
  contest=self.db.scalar(select(ElectoralContest).where(ElectoralContest.electoral_process_id==process.id,ElectoralContest.name==r['contest_code']))
  if not contest:raise BusinessRuleError('Contienda inexistente')
  return process,contest
 def geography(self,process,r):
  level=r['geography_level'].upper();code=r['geography_code'];geo=self.db.scalar(select(ElectoralGeography).where(ElectoralGeography.electoral_process_id==process.id,ElectoralGeography.level==level,ElectoralGeography.external_code==code))
  if geo:return geo
  province=self.db.scalar(select(Province).where(Province.code==r.get('province_dpa'))) if r.get('province_dpa') else None;canton=self.db.scalar(select(Canton).where(Canton.dpa_code==r.get('canton_dpa'))) if r.get('canton_dpa') else None;parish=self.db.scalar(select(Parish).where(Parish.dpa_code==r.get('parish_dpa'))) if r.get('parish_dpa') else None
  mapped={'PROVINCE':bool(province),'CANTON':bool(canton),'PARISH':bool(parish)}.get(level,bool(parish or canton))
  geo=ElectoralGeography(electoral_process_id=process.id,level=level,external_code=code,name=code,province_id=province.id if province else None,canton_id=canton.id if canton else None,parish_id=parish.id if parish else None,zone_code=r.get('zone_code') or None,precinct_code=r.get('precinct_code') or None,jrv_code=r.get('jrv_code') or None,is_mapped=mapped,is_active=True);self.db.add(geo);self.db.flush();return geo
 def upsert_turnout(self,r,source,job,ins,upd):
  process,contest=self.process_contest(r);geo=self.geography(process,r);obj=self.db.scalar(select(ElectoralTurnout).where(ElectoralTurnout.electoral_contest_id==contest.id,ElectoralTurnout.electoral_geography_id==geo.id));values={x:integer(r[x],x) for x in ['registered_voters','ballots_cast','valid_votes','blank_votes','null_votes','other_votes']};values.update(is_final=boolean(r['is_final']),source_id=source.id,import_job_id=job.id,is_active=True)
  if obj:
   for k,v in values.items():setattr(obj,k,v)
   return ins,upd+1
  self.db.add(ElectoralTurnout(electoral_contest_id=contest.id,electoral_geography_id=geo.id,**values));return ins+1,upd
 def upsert_candidate(self,r,source,ins,upd):
  process,contest=self.process_contest(r);org=self.db.scalar(select(PoliticalOrganization).where(PoliticalOrganization.source_id==source.id,PoliticalOrganization.external_code==r['organization_code'])) if r['organization_code'] else None;obj=self.db.scalar(select(ElectoralCandidate).where(ElectoralCandidate.electoral_contest_id==contest.id,ElectoralCandidate.external_code==r['candidate_code']));values=dict(full_name=r['full_name'],political_organization_id=org.id if org else None,list_number=r['list_number'] or None,ballot_order=integer(r['ballot_order'],'ballot_order') if r['ballot_order'] else None,source_id=source.id,is_active=True)
  if obj:
   for k,v in values.items():setattr(obj,k,v)
   return ins,upd+1
  self.db.add(ElectoralCandidate(electoral_contest_id=contest.id,external_code=r['candidate_code'],**values));return ins+1,upd
 def upsert_result(self,r,source,job,ins,upd):
  process,contest=self.process_contest(r);geo=self.geography(process,r);candidate=self.db.scalar(select(ElectoralCandidate).where(ElectoralCandidate.electoral_contest_id==contest.id,ElectoralCandidate.external_code==r['candidate_code']))
  if not candidate:raise BusinessRuleError('Candidatura inexistente')
  votes=integer(r['votes'],'votes');turnout=self.db.scalar(select(ElectoralTurnout).where(ElectoralTurnout.electoral_contest_id==contest.id,ElectoralTurnout.electoral_geography_id==geo.id))
  if contest.vote_method=='SINGLE_CHOICE' and turnout and votes>turnout.valid_votes:raise BusinessRuleError('Votos superiores a votos válidos')
  obj=self.db.scalar(select(ElectoralCandidateResult).where(ElectoralCandidateResult.electoral_contest_id==contest.id,ElectoralCandidateResult.electoral_geography_id==geo.id,ElectoralCandidateResult.electoral_candidate_id==candidate.id));values=dict(votes=votes,is_final=boolean(r['is_final']),source_id=source.id,import_job_id=job.id,is_active=True)
  if obj:
   for k,v in values.items():setattr(obj,k,v)
   return ins,upd+1
  self.db.add(ElectoralCandidateResult(electoral_contest_id=contest.id,electoral_geography_id=geo.id,electoral_candidate_id=candidate.id,**values));return ins+1,upd
 def upsert_observation(self,r,source,job,ins,upd):
  indicator=self.db.scalar(select(DemographicIndicator).where(DemographicIndicator.code==r['indicator_code'].upper()));
  if not indicator:raise BusinessRuleError('Indicador inexistente')
  level=r['geography_level'].upper();province=self.db.scalar(select(Province).where(Province.code==r['province_dpa'])) if r['province_dpa'] else None;canton=self.db.scalar(select(Canton).where(Canton.dpa_code==r['canton_dpa'])) if r['canton_dpa'] else None;parish=self.db.scalar(select(Parish).where(Parish.dpa_code==r['parish_dpa'])) if r['parish_dpa'] else None
  if {'PROVINCE':province,'CANTON':canton,'PARISH':parish}[level] is None:raise BusinessRuleError('Territorio no mapeado')
  value=decimal(r['value'],'value');num=decimal(r['numerator'],'numerator',True);den=decimal(r['denominator'],'denominator',True)
  if indicator.unit=='PERCENT' and not 0<=value<=100:raise BusinessRuleError('Porcentaje fuera de rango')
  if indicator.unit=='PERCENT' and num is not None and den is not None and abs(value-num/den*100)>Decimal('0.1'):raise BusinessRuleError('Porcentaje incoherente')
  cond=[DemographicObservation.demographic_indicator_id==indicator.id,DemographicObservation.geography_level==level,DemographicObservation.reference_year==integer(r['reference_year'],'year'),DemographicObservation.source_id==source.id,DemographicObservation.province_id==(province.id if province else None),DemographicObservation.canton_id==(canton.id if canton else None),DemographicObservation.parish_id==(parish.id if parish else None)];obj=self.db.scalar(select(DemographicObservation).where(*cond));values=dict(value=value,numerator=num,denominator=den,import_job_id=job.id,is_official=True,is_active=True)
  if obj:
   for k,v in values.items():setattr(obj,k,v)
   return ins,upd+1
  self.db.add(DemographicObservation(demographic_indicator_id=indicator.id,geography_level=level,province_id=province.id if province else None,canton_id=canton.id if canton else None,parish_id=parish.id if parish else None,reference_year=integer(r['reference_year'],'year'),source_id=source.id,**values));return ins+1,upd
