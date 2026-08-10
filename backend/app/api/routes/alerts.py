from datetime import date
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.alert_acknowledgement_repository import AlertAcknowledgementRepository
from app.repositories.alert_rule_repository import AlertRuleRepository
from app.schemas.alerts import *
from app.services.alert_service import AlertService
from app.services.exceptions import BusinessRuleError,NotFoundError
from app.services.security_audit_service import SecurityAuditService

router=APIRouter(prefix="/campaigns/{campaign_id}/alerts",tags=["Alerts"])
def invoke(fn,*args,**kwargs):
    try:return fn(*args,**kwargs)
    except PermissionError as exc:raise HTTPException(403,str(exc)) from exc
    except NotFoundError as exc:raise HTTPException(404,str(exc)) from exc
    except BusinessRuleError as exc:raise HTTPException(400,str(exc)) from exc
def alert_read(db,alert):
    rule=db.get(__import__('app.models.alerts',fromlist=['AlertRule']).AlertRule,alert.alert_rule_id);acks=AlertAcknowledgementRepository(db).for_alert(alert.id)
    return {"id":alert.id,"rule_code":rule.code,"module":rule.module,"severity":alert.severity,"status":alert.status,"title":alert.title,"message":alert.message,"detected_date":alert.detected_date,"last_seen_date":alert.last_seen_date,"resolved_date":alert.resolved_date,"parish_id":alert.parish_id,"community_id":alert.community_id,"sector_id":alert.sector_id,"resource_type":alert.resource_type,"resource_id":alert.resource_id,"evidence":alert.evidence,"acknowledgements":[{"id":a.id,"action":a.action,"action_date":a.action_date,"note":a.note,"performed_by_user_id":a.performed_by_user_id} for a in acks]}
@router.post("/evaluate",response_model=AlertEvaluationResponse)
def evaluate(campaign_id:UUID,data:AlertEvaluationRequest,db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):return invoke(AlertService(db).evaluate,campaign_id,user,data)
@router.get("/summary",response_model=AlertSummaryRead)
def summary(campaign_id:UUID,date_from:date|None=None,date_to:date|None=None,db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):
    result=invoke(AlertService(db).summary,campaign_id,user,date_from,date_to);result["top_alerts"]=[alert_read(db,x) for x in result["top_alerts"]];return result
@router.get("",response_model=AlertListResponse)
def alerts(campaign_id:UUID,status:str|None=None,severity:str|None=None,module:str|None=None,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):
    items,total=invoke(AlertService(db).list,campaign_id,user,page,page_size,status=status,severity=severity,module=module);return {"items":[alert_read(db,x) for x in items],"page":page,"page_size":page_size,"total":total}
@router.get("/{alert_id}",response_model=OperationalAlertRead)
def detail(campaign_id:UUID,alert_id:UUID,db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):return alert_read(db,invoke(AlertService(db).get,campaign_id,alert_id,user))
def do_action(campaign_id,alert_id,action,data,db,user):
    alert=invoke(AlertService(db).action,campaign_id,alert_id,action,data,user);SecurityAuditService(db).record("ALERT_STATUS_CHANGED","SUCCESS","Estado de alerta actualizado",user_id=user.id,campaign_id=campaign_id,resource_type="OPERATIONAL_ALERT",resource_id=alert_id,metadata={"action":action});db.commit();return alert_read(db,alert)
@router.post("/{alert_id}/acknowledge",response_model=OperationalAlertRead)
def acknowledge(campaign_id:UUID,alert_id:UUID,data:AlertActionRequest,db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):return do_action(campaign_id,alert_id,"ACKNOWLEDGE",data,db,user)
@router.post("/{alert_id}/resolve",response_model=OperationalAlertRead)
def resolve(campaign_id:UUID,alert_id:UUID,data:AlertActionRequest,db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):return do_action(campaign_id,alert_id,"RESOLVE",data,db,user)
@router.post("/{alert_id}/dismiss",response_model=OperationalAlertRead)
def dismiss(campaign_id:UUID,alert_id:UUID,data:AlertActionRequest,db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):return do_action(campaign_id,alert_id,"DISMISS",data,db,user)
