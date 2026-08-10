from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.historical import DataSource
from app.services.exceptions import BusinessRuleError,ConflictError,NotFoundError
class DataSourceService:
 def __init__(self,db:Session):self.db=db
 def create(self,data,user):
  values=data.model_dump();values['official_url']=str(values['official_url']) if values.get('official_url') else None;obj=DataSource(**values,created_by_user_id=user.id);self.db.add(obj)
  try:self.db.commit();self.db.refresh(obj);return obj
  except IntegrityError:self.db.rollback();raise ConflictError('Código de fuente duplicado')
 def get(self,id):
  obj=self.db.get(DataSource,id)
  if not obj:raise NotFoundError('Fuente no encontrada')
  return obj
 def by_code(self,code):
  obj=self.db.scalar(select(DataSource).where(DataSource.code==code.upper(),DataSource.is_active.is_(True)))
  if not obj:raise NotFoundError('Fuente no encontrada')
  return obj
 def list(self):return list(self.db.scalars(select(DataSource).order_by(DataSource.code)))
 def update(self,id,data):
  obj=self.get(id)
  for k,v in data.model_dump(exclude_unset=True).items():setattr(obj,k,str(v) if k=='official_url' and v else v)
  self.db.commit();self.db.refresh(obj);return obj
