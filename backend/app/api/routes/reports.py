from datetime import date
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query,Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.reports import *
from app.services.exceptions import BusinessRuleError,ConflictError,NotFoundError
from app.services.report_service import ReportService
from app.services.security_audit_service import SecurityAuditService

router=APIRouter(tags=["Reports"])
def invoke(fn,*args,**kwargs):
    try:return fn(*args,**kwargs)
    except PermissionError as exc:raise HTTPException(403,str(exc)) from exc
    except NotFoundError as exc:raise HTTPException(404,str(exc)) from exc
    except ConflictError as exc:raise HTTPException(409,str(exc)) from exc
    except BusinessRuleError as exc:
        if str(exc)=="ARTEFACT_EXPIRED":raise HTTPException(410,"El artefacto expiró o no está disponible") from exc
        raise HTTPException(400,str(exc)) from exc
def template_read(x):return {"id":x.id,"code":x.code,"name":x.name,"description":x.description,"report_type":x.report_type,"allowed_formats":x.allowed_formats,"definition":x.definition,"is_system":x.is_system,"is_active":x.is_active}
def run_read(service,run,user):
    template=service.templates.by_id(run.report_template_id);artifact=service.artifact(run);show_hash=service.admin(user) or "ANALYST" in {r.code for r in user.roles}
    a=None if not artifact else {"id":artifact.id,"format":artifact.format,"original_download_name":artifact.original_download_name,"mime_type":artifact.mime_type,"size_bytes":artifact.size_bytes,"expires_on":artifact.expires_on,"is_available":artifact.is_available,"sha256":artifact.sha256 if show_hash else None}
    return {"id":run.id,"campaign_id":run.campaign_id,"template_code":template.code,"requested_format":run.requested_format,"status":run.status,"report_date":run.report_date,"date_from":run.date_from,"date_to":run.date_to,"title":run.title,"error_code":run.error_code,"error_message":run.error_message,"artifact":a}
@router.get("/report-templates",response_model=list[ReportTemplateRead])
def templates(include_inactive:bool=False,db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):return [template_read(x) for x in ReportService(db).list_templates(user,include_inactive)]
@router.get("/report-templates/{template_id}",response_model=ReportTemplateRead)
def template(template_id:UUID,db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):return template_read(invoke(ReportService(db).template,template_id,user))
@router.post("/report-templates",response_model=ReportTemplateRead,status_code=201)
def create_template(data:ReportTemplateCreate,db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):return template_read(invoke(ReportService(db).create_template,data,user))
@router.patch("/report-templates/{template_id}",response_model=ReportTemplateRead)
def update_template(template_id:UUID,data:ReportTemplateUpdate,db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):return template_read(invoke(ReportService(db).update_template,template_id,data,user))
@router.post("/campaigns/{campaign_id}/reports/generate",response_model=ReportGenerationResponse,status_code=201)
def generate(campaign_id:UUID,data:ReportGenerationRequest,db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):
    service=ReportService(db);run=invoke(service.generate,campaign_id,data,user);SecurityAuditService(db).record("REPORT_GENERATED","SUCCESS","Informe generado",user_id=user.id,campaign_id=campaign_id,resource_type="REPORT_RUN",resource_id=run.id);db.commit();return run_read(service,run,user)
@router.get("/campaigns/{campaign_id}/reports",response_model=ReportListResponse)
def reports(campaign_id:UUID,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):
    service=ReportService(db);items,total=invoke(service.list_runs,campaign_id,user,page,page_size);return {"items":[run_read(service,x,user) for x in items],"page":page,"page_size":page_size,"total":total}
@router.get("/campaigns/{campaign_id}/reports/{run_id}",response_model=ReportRunRead)
def report(campaign_id:UUID,run_id:UUID,db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):
    service=ReportService(db);return run_read(service,invoke(service.get_run,campaign_id,run_id,user),user)
@router.get("/campaigns/{campaign_id}/reports/{run_id}/download")
def download(campaign_id:UUID,run_id:UUID,db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):
    path,artifact=invoke(ReportService(db).download,campaign_id,run_id,user,date.today());SecurityAuditService(db).record("REPORT_DOWNLOADED","SUCCESS","Informe descargado",user_id=user.id,campaign_id=campaign_id,resource_type="REPORT_RUN",resource_id=run_id);db.commit();return FileResponse(path,media_type=artifact.mime_type,filename=artifact.original_download_name,headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})
@router.delete("/campaigns/{campaign_id}/reports/{run_id}",status_code=204)
def delete(campaign_id:UUID,run_id:UUID,db:Session=Depends(get_db),user:User=Depends(get_current_active_user)):invoke(ReportService(db).deactivate,campaign_id,run_id,user);return Response(status_code=204)
