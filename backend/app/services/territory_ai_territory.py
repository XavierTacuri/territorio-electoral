import re
import unicodedata
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.campaign import Campaign
from app.models.territory import Canton,Parish,Province
from app.schemas.territory_ai import TerritoryReference

def normalize(value:str)->str:return "".join(c for c in unicodedata.normalize("NFKD",value.casefold()) if not unicodedata.combining(c))
class TerritoryAmbiguousError(Exception):
    def __init__(self,matches):self.matches=matches;super().__init__("Territorio ambiguo")
class TerritoryAIResolver:
    def __init__(self,db:Session):self.db=db
    def _reference(self,campaign,canton,**values):
        province=self.db.get(Province,canton.province_id)
        return TerritoryReference(campaign_id=campaign.id,canton_id=canton.id,province_id=province.id if province else canton.province_id,province_name=province.name if province else None,organization_id=campaign.organization_id,**values)
    def _canton(self,campaign,canton):return self._reference(campaign,canton,id=canton.id,name=canton.name,dpa_code=canton.dpa_code,level="CANTON")
    def _parish(self,campaign,parish):
        canton=self.db.get(Canton,parish.canton_id)
        return self._reference(campaign,canton,id=parish.id,name=parish.name,dpa_code=parish.dpa_code,level="PARISH")
    def resolve(self,campaign_id,question,parish_id=None):
        campaign=self.db.get(Campaign,campaign_id);canton=self.db.get(Canton,campaign.canton_id)
        parishes=list(self.db.scalars(select(Parish).where(Parish.canton_id==campaign.canton_id,Parish.is_active.is_(True))))
        if parish_id is not None:
            match=next((p for p in parishes if p.id==parish_id),None)
            if not match:raise PermissionError("Parroquia fuera de la campaña")
            return self._parish(campaign,match)
        if canton is None:return None
        q=normalize(question);canton_name=normalize(canton.name)
        canton_named=bool(re.search(rf"(?<!\w){re.escape(canton_name)}(?!\w)",q) or canton.dpa_code in question)
        explicit_canton=bool(re.search(rf"(?:canton\s+{re.escape(canton_name)}|{re.escape(canton_name)}\s+canton)",q))
        explicit_parish=bool(re.search(rf"(?:parroquia\s+{re.escape(canton_name)}|{re.escape(canton_name)}\s+parroquia)",q))
        if explicit_canton or (canton_named and not explicit_parish):return self._canton(campaign,canton)
        matches=[]
        for parish in parishes:
            name=normalize(parish.name)
            if re.search(rf"(?<!\w){re.escape(name)}(?!\w)",q) or parish.dpa_code in question:matches.append(parish)
        if len(matches)>1:raise TerritoryAmbiguousError([self._parish(campaign,p) for p in matches])
        return self._parish(campaign,matches[0]) if matches else self._canton(campaign,canton)
