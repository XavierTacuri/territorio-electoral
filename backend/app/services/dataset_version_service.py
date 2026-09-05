from datetime import datetime,timezone
from sqlalchemy import func,select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.importers.mappings import DATASET_VERSION_KIND,DATASET_VERSION_KIND_LABELS
from app.models.historical import DataImportJob,DatasetVersion,ElectoralRollSnapshot,ElectoralRollSnapshotEntry
from app.services.exceptions import BusinessRuleError,ConflictError,NotFoundError
from app.services.security_audit_service import SecurityAuditService
REGISTRATION_SERIES_BREAK={'code':'REGISTRATION_SERIES_BREAK','message':'Se detectó una variación elevada del registro electoral entre cortes. Esta diferencia puede responder a cambios administrativos, metodológicos, territoriales o del registro electoral y no debe interpretarse automáticamente como una tendencia demográfica.'}
NO_HISTORICAL_SNAPSHOT='No existe una instantánea histórica suficiente para comparar los valores fila por fila.'
ACTIVATABLE={'VALIDATED','SUPERSEDED','ARCHIVED'}
def version_kind(dataset_type):return DATASET_VERSION_KIND.get(dataset_type,'UPSERT_GOVERNED')
def version_kind_label(dataset_type):return DATASET_VERSION_KIND_LABELS.get(version_kind(dataset_type),version_kind(dataset_type))
class DatasetVersionService:
 def __init__(self,db:Session):self.db=db
 def _latest_roll_snapshot_date(self,source_id):
  snap=self.db.scalar(select(ElectoralRollSnapshot).where(ElectoralRollSnapshot.source_id==source_id).order_by(ElectoralRollSnapshot.snapshot_date.desc()))
  return snap.snapshot_date if snap else None
 def create_from_job(self,job:DataImportJob,source):
  if job.status!='COMPLETED':raise BusinessRuleError('Solo se puede versionar una importación completada')
  stamp=job.finished_at or job.started_at
  # "Corte {fecha}" is only used for the snapshot-versioned dataset, where the
  # date is derived from the imported data itself (a real, distinct corte).
  # Every other (upsert-governed) dataset stores reference_date purely as
  # informational metadata copied from the source, which can be identical
  # across several distinct imports on the same day — using it alone as the
  # version_label would make those versions indistinguishable in the UI, so
  # they are always labeled by import timestamp + filename instead.
  if job.dataset_type=='CNE_ELECTORAL_ROLL_SNAPSHOT':
   reference_date=self._latest_roll_snapshot_date(source.id) or source.reference_date
   label=f'Corte {reference_date.isoformat()}' if reference_date else f"Importación {stamp.strftime('%Y-%m-%d %H:%M')} · {job.original_filename}"
  else:
   reference_date=source.reference_date
   label=f"Importación {stamp.strftime('%Y-%m-%d %H:%M')} · {job.original_filename}"
  version=DatasetVersion(data_source_id=source.id,dataset_type=job.dataset_type,reference_date=reference_date,version_label=label,checksum=job.file_sha256,import_job_id=job.id,status='VALIDATED')
  self.db.add(version)
  try:self.db.commit()
  except IntegrityError:self.db.rollback();raise ConflictError('Ya existe una versión registrada para esta importación')
  self.db.refresh(version);return version
 def get(self,id):
  v=self.db.get(DatasetVersion,id)
  if not v:raise NotFoundError('Versión no encontrada')
  return v
 def list(self,dataset_type=None,data_source_id=None):
  q=select(DatasetVersion)
  if dataset_type:q=q.where(DatasetVersion.dataset_type==dataset_type)
  if data_source_id:q=q.where(DatasetVersion.data_source_id==data_source_id)
  return list(self.db.scalars(q.order_by(DatasetVersion.created_at.desc())))
 def active_for(self,data_source_id,dataset_type):
  return self.db.scalar(select(DatasetVersion).where(DatasetVersion.data_source_id==data_source_id,DatasetVersion.dataset_type==dataset_type,DatasetVersion.status=='ACTIVE'))
 def resolve_for_evidence(self,data_source_id=None,import_job_id=None,reference_date=None):
  """Provenance lookup for a specific cited row/fact: prefer the exact import
  that produced it (import_job_id, when the domain table tracks one) over the
  source's currently ACTIVE version, since those can differ — the ACTIVE
  version is an administrative pointer, not necessarily the import behind any
  given row for upsert-governed datasets."""
  if import_job_id:
   version=self.db.scalar(select(DatasetVersion).where(DatasetVersion.import_job_id==import_job_id))
   if version:return version
  if data_source_id and reference_date:
   return self.db.scalar(select(DatasetVersion).where(DatasetVersion.data_source_id==data_source_id,DatasetVersion.reference_date==reference_date).order_by(DatasetVersion.created_at.desc()))
  return None
 def activate(self,id,user):
  version=self.get(id)
  if version.status=='ACTIVE':raise ConflictError('La versión ya está activa')
  if version.status not in ACTIVATABLE:raise BusinessRuleError('Esta versión no puede activarse')
  job=self.db.get(DataImportJob,version.import_job_id)
  if not job or job.status!='COMPLETED':raise BusinessRuleError('La importación asociada no está completada; no se puede activar')
  audit=SecurityAuditService(self.db)
  previous=self.active_for(version.data_source_id,version.dataset_type)
  if previous and previous.id!=version.id:
   previous.status='SUPERSEDED';previous.superseded_by_id=version.id;self.db.flush()
   audit.record('DATASET_VERSION_SUPERSEDED','SUCCESS','Versión reemplazada por una nueva activación',user_id=user.id,resource_type='DATASET_VERSION',resource_id=previous.id,metadata={'dataset_type':previous.dataset_type,'version_kind':version_kind(previous.dataset_type),'superseded_by':str(version.id)})
  version.status='ACTIVE';version.activated_at=datetime.now(timezone.utc);version.activated_by_user_id=user.id
  audit.record('DATASET_VERSION_ACTIVATED','SUCCESS','Versión activada como vigente',user_id=user.id,resource_type='DATASET_VERSION',resource_id=version.id,metadata={'dataset_type':version.dataset_type,'version_kind':version_kind(version.dataset_type)})
  self.db.commit();self.db.refresh(version);return version
 def archive(self,id,user):
  version=self.get(id)
  if version.status not in ('ACTIVE','SUPERSEDED'):raise BusinessRuleError('Solo se archivan versiones activas o reemplazadas')
  version.status='ARCHIVED'
  SecurityAuditService(self.db).record('DATASET_VERSION_ARCHIVED','SUCCESS','Versión archivada',user_id=user.id,resource_type='DATASET_VERSION',resource_id=version.id,metadata={'dataset_type':version.dataset_type})
  self.db.commit();self.db.refresh(version);return version
 def _previous_of(self,version):
  return self.db.scalar(select(DatasetVersion).where(DatasetVersion.data_source_id==version.data_source_id,DatasetVersion.dataset_type==version.dataset_type,DatasetVersion.id!=version.id,DatasetVersion.created_at<version.created_at).order_by(DatasetVersion.created_at.desc()))
 def _roll_snapshot_totals(self,source_id,snapshot_date):
  snapshot=self.db.scalar(select(ElectoralRollSnapshot).where(ElectoralRollSnapshot.source_id==source_id,ElectoralRollSnapshot.snapshot_date==snapshot_date))
  if not snapshot:return None
  total=self.db.scalar(select(func.sum(ElectoralRollSnapshotEntry.registered_voters)).where(ElectoralRollSnapshotEntry.snapshot_id==snapshot.id)) or 0
  parish_rows=list(self.db.scalars(select(ElectoralRollSnapshotEntry).where(ElectoralRollSnapshotEntry.snapshot_id==snapshot.id,ElectoralRollSnapshotEntry.geography_level=='PARISH')))
  return {'snapshot_id':snapshot.id,'total':total,'by_parish':{r.parish_id:r.registered_voters for r in parish_rows}}
 def diff(self,id):
  version=self.get(id);previous=self._previous_of(version)
  base={'version_id':version.id,'compared_to_id':previous.id if previous else None,'comparable':False,'metric':None,'previous_value':None,'new_value':None,'delta':None,'items':[],'warnings':[]}
  if not previous:base['warnings']=['No existe una versión anterior para comparar.'];return base
  if version.dataset_type=='CNE_ELECTORAL_ROLL_SNAPSHOT':
   cur=self._roll_snapshot_totals(version.data_source_id,version.reference_date) if version.reference_date else None
   prev=self._roll_snapshot_totals(previous.data_source_id,previous.reference_date) if previous.reference_date else None
   if not cur or not prev:base['warnings']=['No se encontró el corte del registro electoral asociado a alguna de las versiones.'];return base
   delta=cur['total']-prev['total'];items=[{'parish_id':pid,'previous':prev['by_parish'][pid],'new':cur['by_parish'][pid],'delta':cur['by_parish'][pid]-prev['by_parish'][pid]} for pid in cur['by_parish'] if pid in prev['by_parish']]
   warnings=[]
   if prev['total'] and abs(delta)/prev['total']>0.10:warnings.append(REGISTRATION_SERIES_BREAK)
   return {'version_id':version.id,'compared_to_id':previous.id,'comparable':True,'metric':'registered_voters','previous_value':prev['total'],'new_value':cur['total'],'delta':delta,'items':items,'warnings':warnings}
  # Every other dataset type is UPSERT_GOVERNED: DataImportService upserts rows
  # in place (unique key per contest/geography/candidate or indicator/year/
  # territory), so the previous values are not retained anywhere once a newer
  # import overwrites them — a row-by-row diff cannot be reconstructed, and
  # this must not be presented as if it could.
  warnings=[]
  if version.dataset_type=='INEC_DEMOGRAPHIC_INDICATORS' and version.reference_date and previous.reference_date and version.reference_date.year!=previous.reference_date.year:
   warnings.append('Las versiones corresponden a años de referencia distintos; es una comparación histórica, no una actualización directa del mismo indicador.')
  warnings.append(NO_HISTORICAL_SNAPSHOT)
  base['warnings']=warnings;return base
