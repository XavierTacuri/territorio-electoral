from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models.historical import ElectoralMilestone,ElectoralProcess
from app.services.exceptions import BusinessRuleError,ConflictError,NotFoundError
from app.services.security_audit_service import SecurityAuditService
class ElectoralMilestoneService:
 def __init__(self,db):self.db=db
 def get(self,id):
  o=self.db.get(ElectoralMilestone,id)
  if not o:raise NotFoundError('Hito electoral no encontrado')
  return o
 def list(self,electoral_process_id=None,status=None):
  q=select(ElectoralMilestone)
  if electoral_process_id:q=q.where(ElectoralMilestone.electoral_process_id==electoral_process_id)
  if status:q=q.where(ElectoralMilestone.status==status)
  return list(self.db.scalars(q.order_by(ElectoralMilestone.starts_at)))
 def create(self,data,user):
  if not self.db.get(ElectoralProcess,data.electoral_process_id):raise BusinessRuleError('Proceso electoral inexistente')
  values=data.model_dump();values['source_url']=str(values['source_url']) if values.get('source_url') else None
  obj=ElectoralMilestone(**values,created_by_user_id=user.id);self.db.add(obj)
  try:self.db.commit()
  except IntegrityError:self.db.rollback();raise ConflictError('Ya existe un hito idéntico para este proceso (mismo tipo, fecha y título)')
  self.db.refresh(obj)
  SecurityAuditService(self.db).record('OFFICIAL_MILESTONE_CREATED','SUCCESS','Hito electoral oficial creado',user_id=user.id,resource_type='ELECTORAL_MILESTONE',resource_id=obj.id,metadata={'milestone_type':obj.milestone_type});self.db.commit()
  return obj
 def update(self,id,data,user):
  obj=self.get(id)
  for k,v in data.model_dump(exclude_unset=True).items():setattr(obj,k,str(v) if k=='source_url' and v else v)
  try:self.db.commit()
  except IntegrityError:self.db.rollback();raise ConflictError('Ya existe un hito idéntico para este proceso (mismo tipo, fecha y título)')
  self.db.refresh(obj)
  SecurityAuditService(self.db).record('OFFICIAL_MILESTONE_UPDATED','SUCCESS','Hito electoral oficial actualizado',user_id=user.id,resource_type='ELECTORAL_MILESTONE',resource_id=obj.id,metadata={'milestone_type':obj.milestone_type});self.db.commit()
  return obj
 def set_status(self,id,status,user):
  obj=self.get(id);obj.status=status;self.db.commit();self.db.refresh(obj)
  SecurityAuditService(self.db).record('OFFICIAL_MILESTONE_UPDATED','SUCCESS',f'Hito electoral oficial marcado como {status}',user_id=user.id,resource_type='ELECTORAL_MILESTONE',resource_id=obj.id,metadata={'status':status});self.db.commit()
  return obj
