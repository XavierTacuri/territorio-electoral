from math import ceil
from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.campaign import Campaign
from app.models.organization import Organization
from app.models.territory import Canton,Province
from app.models.user import User
from app.schemas.campaign import CampaignCreate, CampaignListResponse, CampaignSummary, CampaignUpdate
from app.services.campaign_access_service import CampaignAccessService
from app.services.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.services.organization_service import OrganizationAccessService,PlanLimitService


class CampaignService:
    def __init__(self,db:Session):self.db=db;self.access=CampaignAccessService(db)
    def create(self,data:CampaignCreate,actor:User):
        canton=self.db.get(Canton,data.canton_id)
        if not canton:raise NotFoundError("Cantón no encontrado")
        if not canton.is_active:raise BusinessRuleError("El cantón está inactivo")
        if data.province_id is not None:
            province=self.db.get(Province,data.province_id)
            if not province or not province.is_active:raise NotFoundError("Provincia no encontrada")
            if canton.province_id!=province.id:raise BusinessRuleError("El cantón seleccionado no pertenece a la provincia indicada.")
        values=data.model_dump();organization_id=values.pop("organization_id");values.pop("province_id")
        org_access=OrganizationAccessService(self.db)
        if organization_id is None:
            initial_id=UUID("00000000-0000-0000-0000-000000002801")
            accessible=org_access.accessible_ids(actor)
            if org_access.platform_admin(actor) and self.db.get(Organization,initial_id):organization_id=initial_id
            elif len(accessible)==1:organization_id=next(iter(accessible))
            elif not accessible and not self.db.scalar(select(func.count()).select_from(Organization)):organization_id=UUID("00000000-0000-0000-0000-000000002801")
            else:raise BusinessRuleError("Debe seleccionar una organizacion")
        organization=self.db.get(Organization,organization_id)
        if organization:
            org_access.require_access(organization_id,actor)
            if not org_access.platform_admin(actor):org_access.require_admin(organization_id,actor)
            PlanLimitService(self.db).require_campaign_slot(organization_id)
        elif self.db.scalar(select(func.count()).select_from(Organization)):
            raise NotFoundError("Organización no encontrada")
        obj=Campaign(**values,organization_id=organization_id,created_by_user_id=actor.id);self.db.add(obj)
        try:self.db.commit();self.db.refresh(obj)
        except IntegrityError as e:self.db.rollback();raise ConflictError("El slug ya existe") from e
        return obj
    def list(self,user:User,page:int,size:int,canton_id:int|None,status:str|None,office_type:str|None,is_active:bool|None,organization_id:UUID|None=None):
        filters=[]
        if not self.access.admin(user):filters.append(Campaign.id.in_(self.access.accessible_ids(user)))
        if canton_id:filters.append(Campaign.canton_id==canton_id)
        if status:filters.append(Campaign.status==status)
        if office_type:filters.append(Campaign.office_type==office_type)
        if is_active is not None:filters.append(Campaign.is_active.is_(is_active))
        if organization_id:filters.append(Campaign.organization_id==organization_id)
        total=self.db.scalar(select(func.count()).select_from(Campaign).where(*filters)) or 0
        rows=list(self.db.execute(select(Campaign,Canton,Province).join(Canton,Canton.id==Campaign.canton_id).join(Province,Province.id==Canton.province_id).where(*filters).order_by(Campaign.election_date,Campaign.slug).offset((page-1)*size).limit(size)))
        items=[CampaignSummary.model_validate({**{column.name:getattr(campaign,column.name) for column in campaign.__table__.columns},"canton_name":canton.name,"province_id":province.id,"province_name":province.name}) for campaign,canton,province in rows]
        return CampaignListResponse(items=items,page=page,page_size=size,total=total,total_pages=ceil(total/size) if total else 0)
    def get(self,id:UUID,user:User):return self.access.require_access(id,user)
    def update(self,id:UUID,data:CampaignUpdate,actor:User):
        obj=self.access.require_access(id,actor)
        organization_access=OrganizationAccessService(self.db)
        if self.db.get(Organization,obj.organization_id):organization_access.require_admin(obj.organization_id,actor)
        elif not organization_access.platform_admin(actor):raise PermissionError("Sin permisos de gestión")
        if obj.status=="ARCHIVED":raise BusinessRuleError("Una campaña archivada no puede modificarse")
        values=data.model_dump(exclude_unset=True)
        for k,v in values.items():setattr(obj,k,v)
        if obj.start_date and obj.end_date and obj.start_date>obj.end_date:raise BusinessRuleError("Rango de fechas inválido")
        if obj.start_date and obj.election_date<obj.start_date:raise BusinessRuleError("Fecha electoral inválida")
        try:self.db.commit();self.db.refresh(obj)
        except IntegrityError as e:self.db.rollback();raise ConflictError("El slug ya existe") from e
        return obj
