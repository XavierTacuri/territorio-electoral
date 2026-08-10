from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.campaign import Campaign
class CampaignRepository:
    def __init__(self,db:Session):self.db=db
    def get(self,id:UUID):return self.db.get(Campaign,id)
    def by_slug(self,slug:str):return self.db.scalar(select(Campaign).where(Campaign.slug==slug.lower().strip()))
    def by_ids(self,ids:set[UUID]):return list(self.db.scalars(select(Campaign).where(Campaign.id.in_(ids)).order_by(Campaign.election_date)))
