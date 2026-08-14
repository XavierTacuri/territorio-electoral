from datetime import date,datetime,timezone,timedelta
from math import ceil
from uuid import UUID
from hashlib import sha256
from sqlalchemy import func,or_,select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.assignments import CampaignUser,TerritorialAssignment
from app.models.campaign import Campaign
from app.models.operational import *
from app.models.alerts import AlertRule,OperationalAlert
from app.models.territory import Community,Parish,Sector
from app.models.user import User
from app.schemas.operational import *
from app.services.campaign_access_service import CampaignAccessService
from app.services.exceptions import BusinessRuleError,ConflictError,NotFoundError
from app.services.security_audit_service import SecurityAuditService
class OperationalService:
    WRITERS={"CANDIDATE","CAMPAIGN_MANAGER","TERRITORIAL_COORDINATOR"};RESPONSIBLE=WRITERS|{"ANALYST"}
    def __init__(self,db:Session,today_provider=date.today):self.db=db;self.access=CampaignAccessService(db);self.today=today_provider
    def role_codes(self,user):return {r.code for r in user.roles}
    def can_approve(self,user):return self.access.admin(user) or bool(self.role_codes(user).intersection({"CANDIDATE","CAMPAIGN_MANAGER"}))
    def audit(self,event,obj,user,description,metadata=None):
        SecurityAuditService(self.db).record(event,"SUCCESS",description,user_id=user.id,campaign_id=obj.campaign_id,resource_type=obj.__class__.__name__,resource_id=obj.id,metadata=metadata)
    def workflow_alert(self,code,obj,title,message):
        rule=self.db.scalar(select(AlertRule).where(AlertRule.code==code,AlertRule.is_active.is_(True)))
        if not rule:return
        fingerprint=sha256(f"{code}:{obj.id}:{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()
        self.db.add(OperationalAlert(alert_rule_id=rule.id,campaign_id=obj.campaign_id,severity=rule.default_severity,status="OPEN",title=title,message=message,detected_date=self.today(),last_seen_date=self.today(),parish_id=obj.parish_id,resource_type="ACTIVITY",resource_id=obj.id,fingerprint=fingerprint,evidence={"approval_status":obj.approval_status},is_active=True))
    def campaign(self,id:UUID,user:User,write=False):
        c=self.access.require_access(id,user)
        if write:
            roles={r.code for r in user.roles}
            if not self.access.admin(user) and not roles.intersection(self.WRITERS):raise PermissionError("Sin permisos de escritura")
            if c.status not in {"DRAFT","ACTIVE"}:raise BusinessRuleError("La campaÃ±a es de solo lectura")
        return c
    def territory(self,campaign:Campaign,parish_id:int,community_id=None,sector_id=None):
        p=self.db.get(Parish,parish_id)
        if not p or p.canton_id!=campaign.canton_id:raise BusinessRuleError("Territorio invÃ¡lido")
        com=self.db.get(Community,community_id) if community_id else None
        if community_id and (not com or com.parish_id!=p.id):raise BusinessRuleError("Comunidad invÃ¡lida")
        sec=self.db.get(Sector,sector_id) if sector_id else None
        if sector_id and (not community_id or not sec or sec.community_id!=community_id):raise BusinessRuleError("Sector invÃ¡lido")
        return p,com,sec
    def territorial_access(self,user:User,campaign_id:UUID,parish_id:int,community_id=None,sector_id=None):
        roles={r.code for r in user.roles}
        if self.access.admin(user) or roles.intersection({"CANDIDATE","CAMPAIGN_MANAGER"}):return True
        if "TERRITORIAL_COORDINATOR" not in roles:return False
        q=select(TerritorialAssignment).where(TerritorialAssignment.campaign_id==campaign_id,TerritorialAssignment.user_id==user.id,TerritorialAssignment.parish_id==parish_id,TerritorialAssignment.is_active.is_(True))
        for a in self.db.scalars(q):
            if a.community_id and a.community_id!=community_id:continue
            if a.sector_id and a.sector_id!=sector_id:continue
            return True
        return False
    def responsible(self,campaign_id,user_id):
        if user_id is None:return
        u=self.db.get(User,user_id);member=self.db.scalar(select(CampaignUser).where(CampaignUser.campaign_id==campaign_id,CampaignUser.user_id==user_id,CampaignUser.is_active.is_(True)))
        if not u or not u.is_active or not member or not self.RESPONSIBLE.intersection(r.code for r in u.roles):raise BusinessRuleError("Responsable invÃ¡lido")
    def activity(self,campaign_id,id,user,write=False,active=True):
        self.campaign(campaign_id,user,write);obj=self.db.get(TerritorialActivity,id)
        if not obj or obj.campaign_id!=campaign_id or (active and not obj.is_active):raise NotFoundError("Actividad no encontrada")
        if not self.territorial_access(user,campaign_id,obj.parish_id,obj.community_id,obj.sector_id) and "CANDIDATE" not in {r.code for r in user.roles} and "ANALYST" not in {r.code for r in user.roles}:raise PermissionError("Sin acceso territorial")
        return obj
    def create_activity(self,campaign_id,data,user):
        c=self.campaign(campaign_id,user,True);self.territory(c,data.parish_id,data.community_id,data.sector_id)
        if not self.territorial_access(user,campaign_id,data.parish_id,data.community_id,data.sector_id):raise PermissionError("Sin acceso territorial")
        t=self.db.scalar(select(ActivityType).where(ActivityType.code==data.activity_type_code.upper(),ActivityType.is_active.is_(True)))
        if not t:raise BusinessRuleError("Tipo de actividad inexistente o inactivo")
        if data.activity_date>c.election_date and not self.access.admin(user):raise BusinessRuleError("Fecha posterior a la elecciÃ³n")
        self.responsible(campaign_id,data.responsible_user_id);v=data.model_dump();v.pop("activity_type_code");v["activity_type_id"]=t.id;v["campaign_id"]=campaign_id;v["created_by_user_id"]=user.id;v["location"]=f"SRID=4326;POINT({data.longitude} {data.latitude})" if data.latitude is not None else None
        if self.can_approve(user):
            v.update(approval_status="APPROVED",approved_by_user_id=user.id,approved_at=datetime.now(timezone.utc))
        else:v["approval_status"]="DRAFT"
        obj=TerritorialActivity(**v);self.db.add(obj);self.db.flush();self.audit("create",obj,user,"Actividad creada")
        if obj.approval_status=="APPROVED":self.audit("approve",obj,user,"Actividad aprobada al crear por usuario autorizado")
        self.db.commit();self.db.refresh(obj);return obj
    def list_activities(self,campaign_id,user,page,size,**filters):
        self.campaign(campaign_id,user);conds=[TerritorialActivity.campaign_id==campaign_id]
        if not filters.get("include_inactive"):conds.append(TerritorialActivity.is_active.is_(True))
        mapping={"status":TerritorialActivity.status,"approval_status":TerritorialActivity.approval_status,"parish_id":TerritorialActivity.parish_id,"community_id":TerritorialActivity.community_id,"sector_id":TerritorialActivity.sector_id,"responsible_user_id":TerritorialActivity.responsible_user_id}
        for k,col in mapping.items():
            if filters.get(k) is not None:conds.append(col==filters[k])
        if filters.get("search"):conds.append(func.lower(TerritorialActivity.title).like(f"%{filters['search'].lower()}%"))
        if filters.get("date_from"):conds.append(TerritorialActivity.activity_date>=filters["date_from"])
        if filters.get("date_to"):conds.append(TerritorialActivity.activity_date<=filters["date_to"])
        if filters.get("activity_type_code"):conds.append(TerritorialActivity.activity_type_id==select(ActivityType.id).where(ActivityType.code==filters["activity_type_code"]).scalar_subquery())
        items=list(self.db.scalars(select(TerritorialActivity).where(*conds).order_by(TerritorialActivity.activity_date.desc(),TerritorialActivity.title)))
        items=[x for x in items if self.territorial_access(user,campaign_id,x.parish_id,x.community_id,x.sector_id) or {"ADMIN","CANDIDATE","CAMPAIGN_MANAGER","ANALYST"}.intersection(r.code for r in user.roles) or user.is_superuser]
        total=len(items);items=items[(page-1)*size:page*size];return TerritorialActivityListResponse(items=items,page=page,page_size=size,total=total,total_pages=ceil(total/size) if total else 0)
    def update_activity(self,campaign_id,id,data,user):
        obj=self.activity(campaign_id,id,user,True);v=data.model_dump(exclude_unset=True);code=v.pop("activity_type_code",None);old_status=obj.status
        material=bool(set(v).intersection({"title","description","activity_date","start_time","end_time","parish_id","location_name"}) or code)
        if material and obj.approval_status=="PENDING_APPROVAL" and not self.can_approve(user):raise BusinessRuleError("Una actividad pendiente no admite cambios materiales")
        if "status" in v and v["status"]!=old_status:
            allowed={"PLANNED":{"IN_PROGRESS","CANCELLED"},"IN_PROGRESS":{"COMPLETED","CANCELLED"},"COMPLETED":set(),"CANCELLED":set()}
            if v["status"] not in allowed.get(old_status,set()):raise BusinessRuleError("Transición de ejecución inválida")
            if obj.approval_status!="APPROVED" and v["status"]!="CANCELLED":raise BusinessRuleError("Solo una actividad aprobada puede ejecutarse")
        if code:
            t=self.db.scalar(select(ActivityType).where(ActivityType.code==code.upper(),ActivityType.is_active.is_(True)))
            if not t:raise BusinessRuleError("Tipo inactivo");obj.activity_type_id=t.id
        for k,val in v.items():setattr(obj,k,val)
        c=self.db.get(Campaign,campaign_id);self.territory(c,obj.parish_id,obj.community_id,obj.sector_id)
        if not self.territorial_access(user,campaign_id,obj.parish_id,obj.community_id,obj.sector_id):raise PermissionError("Sin acceso territorial")
        if obj.activity_date>self.today() and obj.status=="COMPLETED":raise BusinessRuleError("Actividad futura completada")
        if material and obj.approval_status=="APPROVED" and not self.can_approve(user):
            obj.approval_status="PENDING_APPROVAL";obj.submitted_by_user_id=user.id;obj.submitted_for_approval_at=datetime.now(timezone.utc)
            self.audit("resubmit",obj,user,"Actividad modificada después de aprobación. Requiere nueva aprobación.")
        else:self.audit("status_change" if obj.status!=old_status else "update",obj,user,"Estado de ejecución actualizado" if obj.status!=old_status else "Actividad actualizada",{"material":material})
        self.db.commit();self.db.refresh(obj);return obj
    def submit_activity(self,campaign_id,id,user):
        obj=self.activity(campaign_id,id,user,True)
        if obj.approval_status not in {"DRAFT","REJECTED"}:raise BusinessRuleError("La actividad no puede enviarse a aprobación desde su estado actual")
        event="resubmit" if obj.approval_status=="REJECTED" else "submit_for_approval"
        obj.approval_status="PENDING_APPROVAL";obj.submitted_by_user_id=user.id;obj.submitted_for_approval_at=datetime.now(timezone.utc)
        self.audit(event,obj,user,"Actividad enviada a aprobación");self.workflow_alert("ACTIVITY_PENDING_APPROVAL",obj,"Actividad pendiente de aprobación",obj.title);self.db.commit();self.db.refresh(obj);return obj
    def approve_activity(self,campaign_id,id,user):
        obj=self.activity(campaign_id,id,user,True)
        if not self.can_approve(user):raise PermissionError("Sin permiso para aprobar actividades")
        if obj.created_by_user_id==user.id and not self.can_approve(user):raise PermissionError("No puede aprobar su propia actividad")
        if obj.approval_status=="APPROVED":return obj
        if obj.approval_status!="PENDING_APPROVAL":raise BusinessRuleError("Solo se aprueban actividades pendientes")
        obj.approval_status="APPROVED";obj.approved_by_user_id=user.id;obj.approved_at=datetime.now(timezone.utc);obj.rejection_reason=None
        self.audit("approve",obj,user,"Actividad aprobada");self.workflow_alert("ACTIVITY_APPROVED",obj,"Actividad aprobada",obj.title);self.db.commit();self.db.refresh(obj);return obj
    def reject_activity(self,campaign_id,id,user,reason):
        obj=self.activity(campaign_id,id,user,True)
        if not self.can_approve(user):raise PermissionError("Sin permiso para rechazar actividades")
        if obj.approval_status!="PENDING_APPROVAL":raise BusinessRuleError("Solo se rechazan actividades pendientes")
        reason=" ".join(reason.split())
        if not reason:raise BusinessRuleError("El motivo del rechazo es obligatorio")
        obj.approval_status="REJECTED";obj.rejected_by_user_id=user.id;obj.rejected_at=datetime.now(timezone.utc);obj.rejection_reason=reason
        self.audit("reject",obj,user,"Actividad rechazada",{"reason":reason});self.workflow_alert("ACTIVITY_REJECTED",obj,"Actividad rechazada",f"{obj.title}: {reason}");self.db.commit();self.db.refresh(obj);return obj
    def deactivate_activity(self,campaign_id,id,user):
        obj=self.activity(campaign_id,id,user,True)
        if not self.access.admin(user) and "CAMPAIGN_MANAGER" not in {r.code for r in user.roles}:raise PermissionError("Sin permisos")
        obj.is_active=False;self.db.commit()
    def participant(self,campaign_id,activity_id,user,data=None):
        act=self.activity(campaign_id,activity_id,user,data is not None);obj=self.db.scalar(select(ActivityParticipantSummary).where(ActivityParticipantSummary.activity_id==activity_id))
        if data is None:
            if not obj:raise NotFoundError("Resumen no encontrado")
            return obj
        if not obj:obj=ActivityParticipantSummary(activity_id=activity_id,created_by_user_id=user.id);self.db.add(obj)
        for k,v in data.model_dump().items():setattr(obj,k,v)
        self.db.commit();self.db.refresh(obj);return obj
    def create_need(self,campaign_id,activity_id,data,user):
        act=self.activity(campaign_id,activity_id,user,True) if activity_id else None
        if act and act.status=="CANCELLED":raise BusinessRuleError("Actividad cancelada")
        campaign=self.campaign(campaign_id,user,True);parish_id=act.parish_id if act else data.parish_id
        if not parish_id:raise BusinessRuleError("La parroquia es obligatoria")
        self.territory(campaign,parish_id)
        if not self.territorial_access(user,campaign_id,parish_id):raise PermissionError("Sin acceso territorial")
        cat=self.db.scalar(select(NeedCategory).where(NeedCategory.code==data.need_category_code.upper(),NeedCategory.is_active.is_(True)))
        if not cat:raise BusinessRuleError("CategorÃ­a inexistente o inactiva")
        title=" ".join(data.title.split())
        if activity_id and self.db.scalar(select(CitizenNeed.id).where(CitizenNeed.activity_id==activity_id,CitizenNeed.need_category_id==cat.id,func.lower(CitizenNeed.title)==title.lower(),CitizenNeed.is_active.is_(True))):raise ConflictError("Necesidad duplicada")
        v=data.model_dump();v.pop("need_category_code");v.pop("parish_id",None);v["title"]=title;v["urgency"]=v.pop("urgency") or v["priority"]
        obj=CitizenNeed(**v,campaign_id=campaign_id,activity_id=activity_id,need_category_id=cat.id,parish_id=parish_id,community_id=act.community_id if act else None,sector_id=act.sector_id if act else None,created_by_user_id=user.id,reported_by_user_id=user.id)
        self.responsible(campaign_id,obj.assigned_to_user_id);self.db.add(obj);self.db.flush();self.audit("create",obj,user,"Necesidad reportada");self.db.commit();self.db.refresh(obj);return obj
    def needs(self,campaign_id,user,page=1,size=20,activity_id=None,**filters):
        self.campaign(campaign_id,user);conds=[CitizenNeed.campaign_id==campaign_id,CitizenNeed.is_active.is_(True)]
        if activity_id:conds.append(CitizenNeed.activity_id==activity_id)
        for k,col in {"priority":CitizenNeed.priority,"status":CitizenNeed.status,"parish_id":CitizenNeed.parish_id,"community_id":CitizenNeed.community_id,"sector_id":CitizenNeed.sector_id,"need_category_id":CitizenNeed.need_category_id}.items():
            if filters.get(k) is not None:conds.append(col==filters[k])
        if filters.get("need_category_code"):conds.append(CitizenNeed.need_category_id==select(NeedCategory.id).where(NeedCategory.code==filters["need_category_code"].upper()).scalar_subquery())
        if filters.get("search"):conds.append(or_(func.lower(CitizenNeed.title).like(f"%{filters['search'].lower()}%"),func.lower(CitizenNeed.description).like(f"%{filters['search'].lower()}%")))
        if filters.get("date_from"):conds.append(CitizenNeed.activity_id.in_(select(TerritorialActivity.id).where(TerritorialActivity.activity_date>=filters["date_from"])))
        if filters.get("date_to"):conds.append(CitizenNeed.activity_id.in_(select(TerritorialActivity.id).where(TerritorialActivity.activity_date<=filters["date_to"])))
        items=list(self.db.scalars(select(CitizenNeed).where(*conds).order_by(CitizenNeed.mentions_count.desc(),CitizenNeed.title)))
        roles={r.code for r in user.roles}
        if not (self.access.admin(user) or roles.intersection({"CANDIDATE","CAMPAIGN_MANAGER","ANALYST"})):
            items=[x for x in items if self.territorial_access(user,campaign_id,x.parish_id,x.community_id,x.sector_id)]
        total=len(items);return CitizenNeedListResponse(items=items[(page-1)*size:page*size],page=page,page_size=size,total=total,total_pages=ceil(total/size) if total else 0)
    def need(self,campaign_id,id,user,write=False):
        self.campaign(campaign_id,user,write);obj=self.db.get(CitizenNeed,id)
        if not obj or obj.campaign_id!=campaign_id or not obj.is_active:raise NotFoundError("Necesidad no encontrada")
        if obj.activity_id:self.activity(campaign_id,obj.activity_id,user,write)
        elif not self.territorial_access(user,campaign_id,obj.parish_id) and not (self.access.admin(user) or self.role_codes(user).intersection({"CANDIDATE","CAMPAIGN_MANAGER","ANALYST"})):raise PermissionError("Sin acceso territorial")
        return obj
    def update_need(self,campaign_id,id,data,user):
        obj=self.need(campaign_id,id,user,True);v=data.model_dump(exclude_unset=True);code=v.pop("need_category_code",None)
        if code:
            cat=self.db.scalar(select(NeedCategory).where(NeedCategory.code==code.upper(),NeedCategory.is_active.is_(True)))
            if not cat:raise BusinessRuleError("CategorÃ­a inactiva");obj.need_category_id=cat.id
        old_assignee=obj.assigned_to_user_id
        for k,val in v.items():setattr(obj,k,val)
        self.responsible(campaign_id,obj.assigned_to_user_id)
        self.audit("assign" if old_assignee!=obj.assigned_to_user_id else "update",obj,user,"Responsable de necesidad actualizado" if old_assignee!=obj.assigned_to_user_id else "Necesidad actualizada")
        self.db.commit();self.db.refresh(obj);return obj
    def review_need(self,campaign_id,id,user):
        obj=self.need(campaign_id,id,user,True)
        if obj.status not in {"REPORTED","IDENTIFIED"}:raise BusinessRuleError("La necesidad no puede pasar a revisión")
        obj.status="UNDER_REVIEW";self.audit("status_change",obj,user,"Necesidad puesta en revisión");self.db.commit();self.db.refresh(obj);return obj
    def validate_need(self,campaign_id,id,user,notes=None):
        obj=self.need(campaign_id,id,user,True)
        if not self.can_approve(user):raise PermissionError("Sin permiso para validar necesidades")
        if obj.status!="UNDER_REVIEW":raise BusinessRuleError("Solo se validan necesidades en revisión")
        obj.status="VALIDATED";obj.validation_notes=notes;obj.validated_by_user_id=user.id;obj.validated_at=datetime.now(timezone.utc)
        self.audit("validate",obj,user,"Necesidad validada");self.db.commit();self.db.refresh(obj);return obj
    def create_commitment(self,campaign_id,data,user):
        c=self.campaign(campaign_id,user,True);v=data.model_dump()
        if data.need_id:
            need=self.need(campaign_id,data.need_id,user,True)
            if need.status!="VALIDATED":raise BusinessRuleError("Solo una necesidad validada puede generar compromiso")
            if (data.parish_id,data.community_id,data.sector_id)!=(need.parish_id,need.community_id,need.sector_id):raise BusinessRuleError("Territorio distinto a la necesidad")
        if data.activity_id:
            act=self.activity(campaign_id,data.activity_id,user,True)
            if (data.parish_id,data.community_id,data.sector_id)!=(act.parish_id,act.community_id,act.sector_id):raise BusinessRuleError("Territorio distinto a la actividad")
        else:self.territory(c,data.parish_id,data.community_id,data.sector_id)
        if not self.territorial_access(user,campaign_id,data.parish_id,data.community_id,data.sector_id):raise PermissionError("Sin acceso territorial")
        self.responsible(campaign_id,data.responsible_user_id)
        if data.status==CommitmentStatus.COMPLETED and not data.completed_date:v["completed_date"]=self.today()
        obj=Commitment(**v,campaign_id=campaign_id,created_by_user_id=user.id);self.db.add(obj);self.db.flush();self.audit("create_commitment",obj,user,"Compromiso creado",{"need_id":str(data.need_id) if data.need_id else None})
        if data.need_id:need.status="IN_PLAN"
        self.db.commit();self.db.refresh(obj);return obj
    def history(self,campaign_id,resource_type,resource_id,user):
        if resource_type=="TerritorialActivity":self.activity(campaign_id,resource_id,user)
        elif resource_type=="CitizenNeed":self.need(campaign_id,resource_id,user)
        else:raise BusinessRuleError("Tipo de recurso inválido")
        from app.models.security import SecurityAuditEvent
        return list(self.db.scalars(select(SecurityAuditEvent).where(SecurityAuditEvent.campaign_id==campaign_id,SecurityAuditEvent.resource_type==resource_type,SecurityAuditEvent.resource_id==resource_id).order_by(SecurityAuditEvent.created_at)))
    def operations_overview(self,campaign_id,user):
        campaign=self.campaign(campaign_id,user);today=self.today();roles=self.role_codes(user);broad=self.access.admin(user) or bool(roles.intersection({"CANDIDATE","CAMPAIGN_MANAGER","ANALYST"}))
        allowed=lambda item:broad or self.territorial_access(user,campaign_id,item.parish_id,item.community_id,item.sector_id)
        activities=[x for x in self.db.scalars(select(TerritorialActivity).where(TerritorialActivity.campaign_id==campaign_id,TerritorialActivity.is_active.is_(True))) if allowed(x)]
        needs=[x for x in self.db.scalars(select(CitizenNeed).where(CitizenNeed.campaign_id==campaign_id,CitizenNeed.is_active.is_(True))) if allowed(x)]
        commitments=[x for x in self.db.scalars(select(Commitment).where(Commitment.campaign_id==campaign_id,Commitment.is_active.is_(True))) if allowed(x)]
        total=self.db.scalar(select(func.count()).select_from(Parish).where(Parish.canton_id==campaign.canton_id,Parish.is_active.is_(True))) or 0
        open_states={"REPORTED","IDENTIFIED","UNDER_REVIEW","VALIDATED","IN_PLAN","INCLUDED_IN_PLAN"}
        return {"activities":{"upcoming":sum(x.approval_status=="APPROVED" and x.status=="PLANNED" and x.activity_date>=today for x in activities),"pending_approval":sum(x.approval_status=="PENDING_APPROVAL" for x in activities),"completed":sum(x.status=="COMPLETED" for x in activities)},"needs":{"open":sum(x.status in open_states for x in needs),"under_review":sum(x.status=="UNDER_REVIEW" for x in needs),"validated":sum(x.status=="VALIDATED" for x in needs),"critical_unassigned":sum(x.urgency=="CRITICAL" and x.assigned_to_user_id is None and x.status in open_states for x in needs)},"commitments":{"pending":sum(x.status=="PENDING" for x in commitments),"in_progress":sum(x.status=="IN_PROGRESS" for x in commitments),"overdue":sum(bool(x.due_date and x.due_date<today and x.status in {"PENDING","IN_PROGRESS"}) for x in commitments),"completed":sum(x.status=="COMPLETED" for x in commitments)},"coverage":{"total_parishes":total,"with_activities":len({x.parish_id for x in activities}),"with_needs":len({x.parish_id for x in needs}),"with_commitments":len({x.parish_id for x in commitments})},"can_approve":self.can_approve(user)}
    def agenda(self,campaign_id,user):
        self.campaign(campaign_id,user);today=self.today()
        activities=self.list_activities(campaign_id,user,1,100,include_inactive=False).items
        commitments=self.commitments(campaign_id,user,1,100).items
        return {"activities":[x for x in activities if x.approval_status=="APPROVED" and x.status in {"PLANNED","IN_PROGRESS"} and x.activity_date>=today],"pending_approval":[x for x in activities if x.approval_status=="PENDING_APPROVAL"],"commitments":[x for x in commitments if x.status in {"PENDING","IN_PROGRESS"} and x.due_date is not None]}
    def commitments(self,campaign_id,user,page=1,size=20,overdue=False,**filters):
        self.campaign(campaign_id,user);conds=[Commitment.campaign_id==campaign_id,Commitment.is_active.is_(True)]
        for k,col in {"status":Commitment.status,"priority":Commitment.priority,"responsible_user_id":Commitment.responsible_user_id,"parish_id":Commitment.parish_id,"community_id":Commitment.community_id,"sector_id":Commitment.sector_id,"activity_id":Commitment.activity_id}.items():
            if filters.get(k) is not None:conds.append(col==filters[k])
        if filters.get("due_date_from"):conds.append(Commitment.due_date>=filters["due_date_from"])
        if filters.get("due_date_to"):conds.append(Commitment.due_date<=filters["due_date_to"])
        if filters.get("search"):conds.append(or_(func.lower(Commitment.title).like(f"%{filters['search'].lower()}%"),func.lower(Commitment.description).like(f"%{filters['search'].lower()}%")))
        if overdue:conds.extend([Commitment.due_date<self.today(),Commitment.status.in_(["PENDING","IN_PROGRESS"])])
        items=list(self.db.scalars(select(Commitment).where(*conds).order_by(Commitment.due_date.is_(None),Commitment.due_date,Commitment.title)))
        roles={r.code for r in user.roles}
        if not (self.access.admin(user) or roles.intersection({"CANDIDATE","CAMPAIGN_MANAGER","ANALYST"})):
            items=[x for x in items if self.territorial_access(user,campaign_id,x.parish_id,x.community_id,x.sector_id)]
        total=len(items);return CommitmentListResponse(items=items[(page-1)*size:page*size],page=page,page_size=size,total=total,total_pages=ceil(total/size) if total else 0)
    def commitment(self,campaign_id,id,user,write=False):
        self.campaign(campaign_id,user,write);obj=self.db.get(Commitment,id)
        if not obj or obj.campaign_id!=campaign_id or not obj.is_active:raise NotFoundError("Compromiso no encontrado")
        if not self.territorial_access(user,campaign_id,obj.parish_id,obj.community_id,obj.sector_id) and not {"CANDIDATE","ANALYST"}.intersection(r.code for r in user.roles):raise PermissionError("Sin acceso")
        return obj
    def update_commitment(self,campaign_id,id,data,user):
        obj=self.commitment(campaign_id,id,user,True);v=data.model_dump(exclude_unset=True)
        for k,val in v.items():setattr(obj,k,val)
        if obj.status=="COMPLETED":obj.completed_date=obj.completed_date or self.today()
        else:obj.completed_date=None
        if obj.completed_date and obj.completed_date>self.today():raise BusinessRuleError("Fecha futura")
        self.db.commit();self.db.refresh(obj);return obj
    def evidence(self,campaign_id,activity_id,user,data=None,id=None):
        self.activity(campaign_id,activity_id,user,data is not None)
        if id:
            obj=self.db.get(ActivityEvidence,id)
            if not obj or obj.activity_id!=activity_id or not obj.is_active:raise NotFoundError("Evidencia no encontrada")
        elif data:
            v=data.model_dump();v["url"]=str(v["url"]);obj=ActivityEvidence(**v,activity_id=activity_id,uploaded_by_user_id=user.id);self.db.add(obj)
        else:return list(self.db.scalars(select(ActivityEvidence).where(ActivityEvidence.activity_id==activity_id,ActivityEvidence.is_active.is_(True))))
        if data and id:
            for k,v in data.model_dump(exclude_unset=True).items():setattr(obj,k,str(v) if k=="url" else v)
        self.db.commit();self.db.refresh(obj);return obj
    def summary(self,campaign_id,user,date_from=None,date_to=None):
        c=self.campaign(campaign_id,user);today=self.today();date_to=date_to or today;date_from=date_from or today-timedelta(days=today.weekday())
        acts=list(self.db.scalars(select(TerritorialActivity).where(TerritorialActivity.campaign_id==campaign_id,TerritorialActivity.is_active.is_(True),TerritorialActivity.activity_date.between(date_from,date_to))))
        acts=[a for a in acts if self.territorial_access(user,campaign_id,a.parish_id,a.community_id,a.sector_id) or self.access.admin(user) or {"CANDIDATE","CAMPAIGN_MANAGER","ANALYST"}.intersection(r.code for r in user.roles)]
        ids={a.id for a in acts};summaries=list(self.db.scalars(select(ActivityParticipantSummary).where(ActivityParticipantSummary.activity_id.in_(ids)))) if ids else []
        needs=list(self.db.scalars(select(CitizenNeed).where(CitizenNeed.campaign_id==campaign_id,CitizenNeed.activity_id.in_(ids),CitizenNeed.is_active.is_(True)))) if ids else []
        commitments=list(self.db.scalars(select(Commitment).where(Commitment.campaign_id==campaign_id,Commitment.is_active.is_(True))))
        roles={r.code for r in user.roles}
        if not (self.access.admin(user) or roles.intersection({"CANDIDATE","CAMPAIGN_MANAGER","ANALYST"})):
            commitments=[x for x in commitments if self.territorial_access(user,campaign_id,x.parish_id,x.community_id,x.sector_id)]
        types={x.id:x for x in self.db.scalars(select(ActivityType))};parishes={x.id:x for x in self.db.scalars(select(Parish).where(Parish.canton_id==c.canton_id,Parish.is_active.is_(True)))};cats={x.id:x for x in self.db.scalars(select(NeedCategory))}
        bytype=[]
        for tid in {a.activity_type_id for a in acts}:bytype.append(ActivityCountByType(code=types[tid].code,name=types[tid].name,count=sum(a.activity_type_id==tid for a in acts)))
        priority_rank={"LOW":0,"MEDIUM":1,"HIGH":2,"CRITICAL":3};top=[]
        for cid in {n.need_category_id for n in needs}:
            grouped=[n for n in needs if n.need_category_id==cid]
            top.append(NeedCountByCategory(code=cats[cid].code,name=cats[cid].name,mentions=sum(n.mentions_count for n in grouped),activities=len({n.activity_id for n in grouped}),max_priority=max((n.priority for n in grouped),key=lambda value:priority_rank[value],default="LOW")))
        top.sort(key=lambda x:(-x.mentions,-x.activities));done={a.parish_id for a in acts if a.status=="COMPLETED"};uncovered=[UncoveredParishRead(id=p.id,name=p.name) for p in parishes.values() if p.id not in done and (self.access.admin(user) or self.territorial_access(user,campaign_id,p.id))]
        attendees_by_activity={x.activity_id:x.estimated_attendees for x in summaries};byparish=[]
        for pid in {a.parish_id for a in acts}:
            grouped=[a for a in acts if a.parish_id==pid]
            byparish.append(ActivityCountByParish(parish_id=pid,name=parishes[pid].name,completed=sum(a.status=="COMPLETED" for a in grouped),planned=sum(a.status=="PLANNED" for a in grouped),estimated_attendees=sum(attendees_by_activity.get(a.id,0) for a in grouped)))
        needsbyparish=[]
        for pid in {n.parish_id for n in needs}:
            grouped=[n for n in needs if n.parish_id==pid]
            needsbyparish.append(NeedCountByParish(parish_id=pid,name=parishes[pid].name,mentions=sum(n.mentions_count for n in grouped)))
        counts={s:sum(x.status==s for x in commitments) for s in ["PENDING","IN_PROGRESS","COMPLETED","CANCELLED"]};over=sum(bool(x.due_date and x.due_date<today and x.status in {"PENDING","IN_PROGRESS"}) for x in commitments)
        completed=sum(a.status=="COMPLETED" for a in acts);text=f"Durante el perÃ­odo se realizaron {completed} actividades. Existen {len(uncovered)} parroquias sin actividades realizadas y {over} compromisos vencidos."
        return OperationalSummaryRead(date_from=date_from,date_to=date_to,completed_activities=completed,planned_activities=sum(a.status=="PLANNED" for a in acts),cancelled_activities=sum(a.status=="CANCELLED" for a in acts),total_activities=len(acts),open_needs=sum(n.status!="DISCARDED" for n in needs),parishes_with_commitments=len({x.parish_id for x in commitments}),estimated_attendees=sum(x.estimated_attendees for x in summaries),activities_by_type=bytype,activities_by_parish=byparish,top_needs=top,needs_by_parish=needsbyparish,commitments=CommitmentStatusSummary(pending=counts["PENDING"],in_progress=counts["IN_PROGRESS"],completed=counts["COMPLETED"],cancelled=counts["CANCELLED"],overdue=over),uncovered_parishes=uncovered,summary_text=text)

    def territory_summaries(self,campaign_id,user):
        """All-time aggregated operational context for every accessible parish."""
        campaign=self.campaign(campaign_id,user);roles={r.code for r in user.roles};broad=self.access.admin(user) or bool(roles.intersection({"CANDIDATE","CAMPAIGN_MANAGER","ANALYST"}))
        allowed=lambda item: broad or self.territorial_access(user,campaign_id,item.parish_id,item.community_id,item.sector_id)
        activities=[x for x in self.db.scalars(select(TerritorialActivity).where(TerritorialActivity.campaign_id==campaign_id,TerritorialActivity.is_active.is_(True))) if allowed(x)]
        needs=[x for x in self.db.scalars(select(CitizenNeed).where(CitizenNeed.campaign_id==campaign_id,CitizenNeed.is_active.is_(True))) if allowed(x)]
        commitments=[x for x in self.db.scalars(select(Commitment).where(Commitment.campaign_id==campaign_id,Commitment.is_active.is_(True))) if allowed(x)]
        parishes=list(self.db.scalars(select(Parish).where(Parish.canton_id==campaign.canton_id,Parish.is_active.is_(True)).order_by(Parish.name)))
        result=[];categories={x.id:x for x in self.db.scalars(select(NeedCategory))}
        for parish in parishes:
            pa=sorted((x for x in activities if x.parish_id==parish.id),key=lambda x:(x.activity_date,x.created_at),reverse=True);pn=sorted((x for x in needs if x.parish_id==parish.id),key=lambda x:x.created_at,reverse=True);pc=sorted((x for x in commitments if x.parish_id==parish.id),key=lambda x:x.created_at,reverse=True)
            category_counts=[{"category":categories[cid].name,"count":sum(x.need_category_id==cid for x in pn)} for cid in {x.need_category_id for x in pn}]
            result.append({"parish_id":parish.id,"activities":len(pa),"needs_open":sum(x.status in {"REPORTED","IDENTIFIED","UNDER_REVIEW","VALIDATED","IN_PLAN","INCLUDED_IN_PLAN"} for x in pn),"needs_under_review":sum(x.status=="UNDER_REVIEW" for x in pn),"needs_validated":sum(x.status=="VALIDATED" for x in pn),"needs_by_category":category_counts,"commitments_related":sum(x.need_id is not None for x in pc),"commitments_pending":sum(x.status in {"PENDING","IN_PROGRESS"} for x in pc),"commitments_completed":sum(x.status=="COMPLETED" for x in pc),"latest_activities":[{"id":str(x.id),"title":x.title,"date":x.activity_date,"status":x.status} for x in pa[:3]],"latest_needs":[{"id":str(x.id),"title":x.title,"status":x.status,"date":x.reported_date,"category":categories[x.need_category_id].name} for x in pn[:3]],"latest_commitments":[{"id":str(x.id),"title":x.title,"status":x.status,"due_date":x.due_date} for x in pc[:3]]})
        return {"parishes":result}
