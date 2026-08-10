import json
from datetime import date
from uuid import UUID
from sqlalchemy import case,func,select
from sqlalchemy.orm import Session
from app.models.operational import ActivityParticipantSummary,ActivityType,CitizenNeed,Commitment,TerritorialActivity
from app.models.survey import SurveyResponse
from app.models.territory import Canton,Community,Parish,Sector

class MapRepository:
 def __init__(self,db:Session):self.db=db
 @property
 def postgres(self):return self.db.bind is not None and self.db.bind.dialect.name=='postgresql'
 def geometry_expr(self,column,simplify,tolerance):
  geom=func.ST_SimplifyPreserveTopology(column,tolerance) if simplify else column
  return func.ST_AsGeoJSON(geom)
 def geometry_rows(self,model,column,ids,simplify=True,tolerance=.0001,bbox=None):
  if not ids:return []
  if not self.postgres:
   return [(o,None) for o in self.db.scalars(select(model).where(model.id.in_(ids),column.is_not(None)))]
  q=select(model,self.geometry_expr(column,simplify,tolerance)).where(model.id.in_(ids),column.is_not(None),func.ST_IsEmpty(column).is_(False),func.ST_SRID(column)==4326)
  if bbox:q=q.where(func.ST_Intersects(column,func.ST_MakeEnvelope(*bbox,4326)))
  return list(self.db.execute(q))
 def extent(self,column,conditions):
  if not self.postgres:return None
  text=self.db.scalar(select(func.ST_Extent(column)).where(*conditions,column.is_not(None)))
  if not text:return None
  values=text.removeprefix('BOX(').removesuffix(')').replace(',',' ').split();return [float(x) for x in values]
 def activity_points(self,campaign_id,start,end,parish_ids,bbox=None):
  if not self.postgres:return []
  need_count=select(func.count()).select_from(CitizenNeed).where(CitizenNeed.activity_id==TerritorialActivity.id,CitizenNeed.is_active.is_(True)).correlate(TerritorialActivity).scalar_subquery();commitment_count=select(func.count()).select_from(Commitment).where(Commitment.activity_id==TerritorialActivity.id,Commitment.is_active.is_(True)).correlate(TerritorialActivity).scalar_subquery()
  q=select(TerritorialActivity,ActivityType.code,func.coalesce(ActivityParticipantSummary.estimated_attendees,0),need_count,commitment_count,func.ST_AsGeoJSON(TerritorialActivity.location)).join(ActivityType).outerjoin(ActivityParticipantSummary).where(TerritorialActivity.campaign_id==campaign_id,TerritorialActivity.is_active.is_(True),TerritorialActivity.activity_date.between(start,end),TerritorialActivity.parish_id.in_(parish_ids),TerritorialActivity.location.is_not(None),func.ST_SRID(TerritorialActivity.location)==4326)
  if bbox:q=q.where(func.ST_Intersects(TerritorialActivity.location,func.ST_MakeEnvelope(*bbox,4326)))
  return list(self.db.execute(q))
 def activity_clusters(self,campaign_id,start,end,parish_ids,zoom,bbox=None):
  if not self.postgres:return []
  precision=max(1,min(12,zoom//2+1));geohash=func.ST_GeoHash(TerritorialActivity.location,precision);point=func.ST_Centroid(func.ST_Collect(TerritorialActivity.location));extent=func.ST_Extent(TerritorialActivity.location)
  q=select(geohash,func.count(),func.count().filter(TerritorialActivity.status=='COMPLETED'),func.count().filter(TerritorialActivity.status=='PLANNED'),func.count().filter(TerritorialActivity.status=='CANCELLED'),func.coalesce(func.sum(ActivityParticipantSummary.estimated_attendees).filter(TerritorialActivity.status=='COMPLETED'),0),func.ST_AsGeoJSON(point),extent).outerjoin(ActivityParticipantSummary).where(TerritorialActivity.campaign_id==campaign_id,TerritorialActivity.is_active.is_(True),TerritorialActivity.activity_date.between(start,end),TerritorialActivity.parish_id.in_(parish_ids),TerritorialActivity.location.is_not(None))
  if bbox:q=q.where(func.ST_Intersects(TerritorialActivity.location,func.ST_MakeEnvelope(*bbox,4326)))
  return list(self.db.execute(q.group_by(geohash)))
