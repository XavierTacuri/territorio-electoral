from datetime import date
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.assignments import CampaignUser
from app.models.candidate import Candidate
from app.models.user import User
from app.schemas.campaign import CandidateCreate,CandidateUpdate
from app.services.campaign_access_service import CampaignAccessService
from app.services.exceptions import BusinessRuleError,ConflictError,NotFoundError

class CandidateService:
    def __init__(self,db:Session):self.db=db;self.access=CampaignAccessService(db)
    def get(self,campaign_id:UUID,user:User):
        self.access.require_access(campaign_id,user); obj=self.db.scalar(select(Candidate).where(Candidate.campaign_id==campaign_id))
        if not obj:raise NotFoundError("Candidato no encontrado")
        return obj
    def _validate_user(self,campaign_id,user_id):
        if user_id is None:return
        user=self.db.get(User,user_id)
        if not user or not user.is_active:raise BusinessRuleError("Usuario candidato inválido")
        if "CANDIDATE" not in {r.code for r in user.roles}:raise BusinessRuleError("El usuario no tiene rol CANDIDATE")
        assigned=self.db.scalar(select(CampaignUser).where(CampaignUser.campaign_id==campaign_id,CampaignUser.user_id==user_id,CampaignUser.is_active.is_(True)))
        if not assigned:raise BusinessRuleError("El candidato no está asignado a la campaña")
    def create(self,campaign_id:UUID,data:CandidateCreate,actor:User):
        self.access.require_access(campaign_id,actor);self._validate_user(campaign_id,data.user_id)
        values=data.model_dump(); values["photo_url"]=str(values["photo_url"]) if values.get("photo_url") else None
        obj=Candidate(campaign_id=campaign_id,**values);self.db.add(obj)
        try:self.db.commit();self.db.refresh(obj)
        except IntegrityError as e:self.db.rollback();raise ConflictError("La campaña ya tiene candidato") from e
        return obj
    def update(self,campaign_id:UUID,data:CandidateUpdate,actor:User):
        obj=self.get(campaign_id,actor);values=data.model_dump(exclude_unset=True)
        if "user_id" in values:self._validate_user(campaign_id,values["user_id"])
        for k,v in values.items():setattr(obj,k,v)
        if obj.birth_date and obj.birth_date>date.today():raise BusinessRuleError("Fecha de nacimiento inválida")
        self.db.commit();self.db.refresh(obj);return obj
