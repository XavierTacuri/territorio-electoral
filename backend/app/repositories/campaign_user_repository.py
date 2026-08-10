from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.assignments import CampaignUser
class CampaignUserRepository:
    def __init__(self,db:Session):self.db=db
    def get(self,campaign_id:UUID,user_id:UUID):return self.db.scalar(select(CampaignUser).where(CampaignUser.campaign_id==campaign_id,CampaignUser.user_id==user_id))
    def campaign_ids(self,user_id:UUID):return set(self.db.scalars(select(CampaignUser.campaign_id).where(CampaignUser.user_id==user_id,CampaignUser.is_active.is_(True))))
