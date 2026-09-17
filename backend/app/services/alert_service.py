from datetime import date
from sqlalchemy import func,select
from app.core.config import settings
from app.models.alerts import AlertAcknowledgement,AlertRule,OperationalAlert
from app.repositories.alert_acknowledgement_repository import AlertAcknowledgementRepository
from app.repositories.alert_rule_repository import AlertRuleRepository
from app.repositories.operational_alert_repository import OperationalAlertRepository
from app.services.alert_access_service import AlertAccessService
from app.services.alert_evaluation_service import AlertEvaluationService
from app.services.exceptions import BusinessRuleError,NotFoundError

class AlertService:
    def __init__(self,db):self.db=db;self.access=AlertAccessService(db);self.rules=AlertRuleRepository(db);self.alerts=OperationalAlertRepository(db);self.actions=AlertAcknowledgementRepository(db)
    def evaluate(self,campaign_id,user,request):
        campaign=self.access.require_evaluate(campaign_id,user);rules=self.rules.active(request.rule_codes);created=updated=resolved=unchanged=0
        assignments=self.access.access.territorial_ids(campaign_id,user);allowed_parishes=None if assignments is None else {a.parish_id for a in assignments if a.parish_id is not None}
        open_count=self.db.scalar(select(func.count()).select_from(OperationalAlert).where(OperationalAlert.campaign_id==campaign_id,OperationalAlert.status.in_(["OPEN","ACKNOWLEDGED"]))) or 0
        seen=set()
        for rule in rules:
            findings=AlertEvaluationService(self.db).evaluate_rule(rule,campaign,request.as_of_date)
            if allowed_parishes is not None:findings=[f for f in findings if f["parish_id"] in allowed_parishes]
            for finding in findings:
                seen.add((rule.id,finding["fingerprint"]));alert=self.alerts.by_fingerprint(campaign_id,finding["fingerprint"])
                if alert:
                    changed=alert.last_seen_date!=request.as_of_date or alert.evidence!=finding["evidence"] or alert.status in {"RESOLVED","DISMISSED"};alert.last_seen_date=request.as_of_date;alert.evidence=finding["evidence"]
                    if alert.status in {"RESOLVED","DISMISSED"}:alert.status="OPEN";alert.resolved_date=None
                    updated+=int(changed);unchanged+=int(not changed)
                else:
                    if open_count+created>=settings.alert_max_open_per_campaign:raise BusinessRuleError("Se alcanzó el límite de alertas abiertas")
                    self.db.add(OperationalAlert(alert_rule_id=rule.id,campaign_id=campaign_id,severity=rule.default_severity,status="OPEN",title=finding["title"],message=finding["message"],detected_date=request.as_of_date,last_seen_date=request.as_of_date,parish_id=finding["parish_id"],resource_type=finding["resource_type"],resource_id=finding["resource_id"],fingerprint=finding["fingerprint"],evidence=finding["evidence"],is_active=True));created+=1
        rule_ids={r.id for r in rules}
        current=list(self.db.scalars(select(OperationalAlert).where(OperationalAlert.campaign_id==campaign_id,OperationalAlert.alert_rule_id.in_(rule_ids),OperationalAlert.status.in_(["OPEN","ACKNOWLEDGED"])))) if rule_ids else []
        for alert in current:
            if (alert.alert_rule_id,alert.fingerprint) not in seen:alert.status="RESOLVED";alert.resolved_date=request.as_of_date;resolved+=1
        self.db.commit();return {"evaluated_rules":len(rules),"created":created,"updated":updated,"resolved":resolved,"unchanged":unchanged}
    def _hide_unresolvable_approvals(self,items,user):
        # A coordinator can never approve an activity, so an approval-pending
        # alert is not actionable for them — showing it would just be noise
        # they cannot resolve (§19).
        if not items or "TERRITORIAL_COORDINATOR" not in {r.code for r in user.roles} or self.access.can_approve_activities(user):return items
        rule_ids={item.alert_rule_id for item in items}
        blocked={r.id for r in self.db.scalars(select(AlertRule).where(AlertRule.id.in_(rule_ids),AlertRule.condition_type=="ACTIVITY_PENDING_APPROVAL"))}
        return [item for item in items if item.alert_rule_id not in blocked]
    def list(self,campaign_id,user,page=1,page_size=20,restrict_family=True,**filters):
        # `restrict_family` gates the Candidate/Manager two-family restriction
        # (§23/§30): it applies to the Centro de Alertas page and the
        # Dashboard's alert card (both hit this through the HTTP route), but
        # NOT to Territorio IA's internal use of this same method as an
        # evidence source (§9-11 of Territorio IA never asked to narrow what
        # evidence the assistant can cite).
        self.access.require_read(campaign_id,user)
        if restrict_family and self.access.restrict_to_candidate_manager_families(user):filters["condition_types"]=self.access.AUTHORIZED_CONDITION_TYPES
        items,total=self.alerts.list(campaign_id,page,page_size,**filters);assignments=self.access.access.territorial_ids(campaign_id,user)
        if assignments is not None:
            allowed={a.parish_id for a in assignments if a.parish_id is not None};items=[item for item in items if item.parish_id in allowed];total=len(items)
        filtered=self._hide_unresolvable_approvals(items,user)
        if len(filtered)!=len(items):total=len(filtered)
        return filtered,total
    def get(self,campaign_id,alert_id,user):
        self.access.require_read(campaign_id,user);alert=self.alerts.by_id(alert_id)
        if not alert or alert.campaign_id!=campaign_id:raise NotFoundError("Alerta no encontrada")
        assignments=self.access.access.territorial_ids(campaign_id,user)
        if assignments is not None and alert.parish_id not in {a.parish_id for a in assignments if a.parish_id is not None}:raise PermissionError("Alerta fuera del alcance territorial")
        if not self._hide_unresolvable_approvals([alert],user):raise PermissionError("Alerta fuera del alcance territorial")
        if self.access.restrict_to_candidate_manager_families(user):
            rule=self.db.get(AlertRule,alert.alert_rule_id)
            if not rule or rule.condition_type not in self.access.AUTHORIZED_CONDITION_TYPES:raise PermissionError("Alerta fuera del alcance autorizado")
        return alert
    def action(self,campaign_id,alert_id,action,request,user):
        alert=self.get(campaign_id,alert_id,user)
        if not self.access.can_modify(user):raise PermissionError("Sin permisos para modificar alertas")
        if action=="DISMISS" and not self.access.can_dismiss(user):raise PermissionError("Sin permisos para descartar alertas")
        transitions={"ACKNOWLEDGE":({"OPEN"},"ACKNOWLEDGED"),"RESOLVE":({"OPEN","ACKNOWLEDGED"},"RESOLVED"),"DISMISS":({"OPEN","ACKNOWLEDGED"},"DISMISSED"),"REOPEN":({"RESOLVED","DISMISSED"},"OPEN")}
        allowed,target=transitions[action]
        if alert.status not in allowed:raise BusinessRuleError("Transición de alerta inválida")
        alert.status=target;alert.resolved_date=request.action_date if target=="RESOLVED" else None
        ack=AlertAcknowledgement(alert_id=alert.id,action=action,action_date=request.action_date,note=request.note,performed_by_user_id=user.id);self.db.add(ack);self.db.commit();return alert
    ACTIVE_STATUSES=("OPEN","ACKNOWLEDGED")
    def summary(self,campaign_id,user,date_from=None,date_to=None):
        # The bell badge (and any other counter fed by this method) must
        # respect exactly the same access boundary as the Centro de Alertas
        # list — otherwise a Candidate/Manager sees "3 resultados" on the
        # page but a badge counting every family/campaign-wide alert
        # regardless of their restriction (this was the literal cause of a
        # badge reading 31 while the page correctly showed 3: `list()` was
        # scoped, `summary()` never was). Family (§23/§30) and territorial
        # scoping mirror `list()` exactly.
        self.access.require_read(campaign_id,user)
        restrict_family=self.access.restrict_to_candidate_manager_families(user)
        assignments=self.access.access.territorial_ids(campaign_id,user);allowed_parishes=None if assignments is None else {a.parish_id for a in assignments if a.parish_id is not None}
        def scope(q):
            if restrict_family:q=q.where(OperationalAlert.alert_rule_id.in_(select(AlertRule.id).where(AlertRule.condition_type.in_(self.access.AUTHORIZED_CONDITION_TYPES))))
            if allowed_parishes is not None:q=q.where(OperationalAlert.parish_id.in_(allowed_parishes))
            return q
        rows=list(self.db.execute(scope(select(OperationalAlert.status,func.count()).where(OperationalAlert.campaign_id==campaign_id)).group_by(OperationalAlert.status)))
        statuses={k.lower():v for k,v in rows}
        # by_severity/by_module/top_alerts drive user-facing counters (the
        # notification bell badge, "requiere tu atención"-style blocks): they
        # must only ever reflect currently-active conditions, never resolved
        # or dismissed history, or a badge would keep growing forever instead
        # of tracking what actually needs attention right now.
        items,_=self.alerts.list(campaign_id,1,5,statuses=self.ACTIVE_STATUSES,condition_types=self.access.AUTHORIZED_CONDITION_TYPES if restrict_family else None)
        if allowed_parishes is not None:items=[i for i in items if i.parish_id in allowed_parishes]
        severity=[{"severity":k,"count":v} for k,v in self.db.execute(scope(select(OperationalAlert.severity,func.count()).where(OperationalAlert.campaign_id==campaign_id,OperationalAlert.status.in_(self.ACTIVE_STATUSES))).group_by(OperationalAlert.severity))]
        module=[{"module":k,"count":v} for k,v in self.db.execute(scope(select(AlertRule.module,func.count()).join(OperationalAlert).where(OperationalAlert.campaign_id==campaign_id,OperationalAlert.status.in_(self.ACTIVE_STATUSES))).group_by(AlertRule.module))]
        return {"statuses":{"OPEN":statuses.get("open",0),"ACKNOWLEDGED":statuses.get("acknowledged",0),"RESOLVED":statuses.get("resolved",0),"DISMISSED":statuses.get("dismissed",0)},"by_severity":severity,"by_module":module,"by_territory":[],"new_in_period":0,"overdue":0,"top_alerts":items}
