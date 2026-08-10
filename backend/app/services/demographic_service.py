from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.historical import DemographicIndicator,DemographicObservation
from app.services.exceptions import ConflictError,NotFoundError
class DemographicService:
 def __init__(self,db:Session):self.db=db
 def create(self,data):
  o=DemographicIndicator(**data.model_dump(),is_active=True);self.db.add(o)
  try:self.db.commit();self.db.refresh(o);return o
  except IntegrityError:self.db.rollback();raise ConflictError('Indicador duplicado')
 def list(self):return list(self.db.scalars(select(DemographicIndicator).where(DemographicIndicator.is_active.is_(True)).order_by(DemographicIndicator.code)))
 def update(self,id,data):
  o=self.db.get(DemographicIndicator,id)
  if not o:raise NotFoundError('Indicador inexistente')
  for k,v in data.model_dump(exclude_unset=True).items():setattr(o,k,v)
  self.db.commit();self.db.refresh(o);return o
 def observations(self,**f):
  q=select(DemographicObservation).where(DemographicObservation.is_active.is_(True),DemographicObservation.is_official.is_(True))
  for k,col in {'indicator_id':DemographicObservation.demographic_indicator_id,'reference_year':DemographicObservation.reference_year,'geography_level':DemographicObservation.geography_level,'province_id':DemographicObservation.province_id,'canton_id':DemographicObservation.canton_id,'parish_id':DemographicObservation.parish_id,'source_id':DemographicObservation.source_id}.items():
   if f.get(k) is not None:q=q.where(col==f[k])
  return list(self.db.scalars(q))
 def profile(self,canton_id,parish_id=None,reference_year=None,codes=None):
  q=select(DemographicObservation,DemographicIndicator).join(DemographicIndicator).where(DemographicObservation.canton_id==canton_id,DemographicObservation.is_official.is_(True),DemographicObservation.is_active.is_(True))
  if parish_id:q=q.where(DemographicObservation.parish_id==parish_id)
  if reference_year:q=q.where(DemographicObservation.reference_year==reference_year)
  if codes:q=q.where(DemographicIndicator.code.in_(codes))
  return {'canton_id':canton_id,'parish_id':parish_id,'reference_year':reference_year,'observations':[{'indicator_code':i.code,'name':i.name,'unit':i.unit,'value':str(o.value),'reference_year':o.reference_year,'source_id':str(o.source_id)} for o,i in self.db.execute(q)]}
