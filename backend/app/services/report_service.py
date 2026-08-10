import tempfile
from datetime import datetime,timedelta
from pathlib import Path
from uuid import UUID
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.campaign import Campaign
from app.models.reports import ReportArtifact,ReportRun,ReportTemplate
from app.models.user import User
from app.reports.common import flatten_metrics
from app.repositories.report_artifact_repository import ReportArtifactRepository
from app.repositories.report_run_repository import ReportRunRepository
from app.repositories.report_template_repository import ReportTemplateRepository
from app.schemas.reports import ReportGenerationRequest,ReportTemplateCreate,ReportTemplateUpdate
from app.services.campaign_access_service import CampaignAccessService
from app.services.exceptions import BusinessRuleError,ConflictError,NotFoundError
from app.services.report_data_service import ReportDataService
from app.services.report_excel_service import ReportExcelService
from app.services.report_pdf_service import ReportPDFService
from app.services.report_security_service import safe_download_name
from app.services.report_storage_service import LocalReportStorage

class ReportService:
    def __init__(self,db:Session,storage=None):
        self.db=db;self.templates=ReportTemplateRepository(db);self.runs=ReportRunRepository(db);self.artifacts=ReportArtifactRepository(db);self.access=CampaignAccessService(db);self.storage=storage or LocalReportStorage(settings.report_output_dir,settings.report_max_file_mb)
    @staticmethod
    def admin(user):return CampaignAccessService.admin(user)
    def list_templates(self,user,include_inactive=False):return self.templates.list(include_inactive and self.admin(user))
    def template(self,template_id,user):
        item=self.templates.by_id(template_id)
        if not item or (not item.is_active and not self.admin(user)):raise NotFoundError("Plantilla no encontrada")
        return item
    def create_template(self,data:ReportTemplateCreate,user):
        if not self.admin(user):raise PermissionError("Permisos insuficientes")
        if self.templates.by_code(data.code):raise ConflictError("Código de plantilla duplicado")
        item=ReportTemplate(**data.model_dump(mode="json"),is_system=False,created_by_user_id=user.id);self.templates.add(item);self.db.commit();return item
    def update_template(self,template_id,data:ReportTemplateUpdate,user):
        if not self.admin(user):raise PermissionError("Permisos insuficientes")
        item=self.template(template_id,user)
        for key,value in data.model_dump(exclude_unset=True,mode="json").items():setattr(item,key,value)
        self.db.commit();return item
    def _scope(self,campaign_id,user,request):
        campaign=self.access.require_access(campaign_id,user);assignments=self.access.territorial_ids(campaign_id,user)
        parish_ids=[] if assignments is None else sorted({a.parish_id for a in assignments if a.parish_id is not None})
        if assignments is not None and request.parish_id and request.parish_id not in parish_ids:raise PermissionError("Territorio fuera del alcance")
        return campaign,{"type":"CAMPAIGN" if assignments is None else "TERRITORIAL","user_id":str(user.id) if assignments is not None else None,"parish_ids":parish_ids,"community_ids":[],"sector_ids":[]}
    def _sections(self,data):
        if "current_election" in data:return self._current_election_sections(data["current_election"])
        sections=[];overview=data["overview"]
        sections.append({"title":"Resumen","text":overview.get("summary_text","Resumen agregado de campaña."),"headers":["Indicador","Valor","Unidad"],"rows":flatten_metrics(overview)})
        detail=data.get("detail")
        if isinstance(detail,dict):
            rows=[]
            for key,value in detail.items():
                if isinstance(value,(str,int,float)) or value is None:rows.append([key,value])
                elif isinstance(value,list):
                    for item in value[:settings.report_max_rows]:
                        if isinstance(item,dict):rows.append([key,str({k:v for k,v in item.items() if "timestamp" not in k and "hash" not in k})])
            sections.append({"title":"Detalle","headers":["Elemento","Valor"],"rows":rows})
        for key in ("needs","commitments","surveys","quality"):
            value=data.get(key)
            if value:sections.append({"title":key.title(),"headers":["Elemento","Valor"],"rows":[[k,v] for k,v in value.items() if not isinstance(v,list)]})
        sections.append({"title":"Metodología","text":"Información agregada obtenida de los módulos autorizados. No se aplican predicciones, perfilamiento ni recomendaciones políticas.","headers":[],"rows":[]})
        return sections
    def _current_election_sections(self,data):
        from app.reports.current_election import build_current_election_sections
        return build_current_election_sections(data)
    def generate(self,campaign_id:UUID,request:ReportGenerationRequest,user:User):
        campaign,scope=self._scope(campaign_id,user,request);template=self.templates.by_code(request.template_code)
        if not template or not template.is_active:raise NotFoundError("Plantilla no encontrada")
        if request.format.value not in template.allowed_formats:raise BusinessRuleError("Formato no permitido por la plantilla")
        active=self.db.scalar(select(func.count()).select_from(ReportArtifact).join(ReportRun).where(ReportRun.campaign_id==campaign_id,ReportArtifact.is_available.is_(True))) or 0
        if active>=settings.report_max_active_artifacts_per_campaign:raise BusinessRuleError("Se alcanzó el máximo de artefactos activos")
        filters=request.model_dump(mode="json",exclude={"title","template_code","format","report_date"})
        run=ReportRun(campaign_id=campaign_id,report_template_id=template.id,requested_format=request.format.value,status="GENERATING",report_date=request.report_date,date_from=request.date_from,date_to=request.date_to,filters=filters,resolved_scope=scope,title=request.title,requested_by_user_id=user.id)
        self.runs.add(run);self.db.commit();tmp_path=None;stored_key=None
        try:
            data=ReportDataService(self.db).collect(campaign_id,user,template.report_type,request,template.code);sections=self._sections(data)
            suffix=".pdf" if request.format.value=="PDF" else ".xlsx"
            with tempfile.NamedTemporaryFile(suffix=suffix,delete=False) as handle:tmp_path=Path(handle.name)
            if request.format.value=="PDF":ReportPDFService(settings.report_pdf_max_table_rows).render(tmp_path,request.title,campaign.name,request.report_date,(request.date_from,request.date_to),sections)
            else:ReportExcelService().render(tmp_path,request.title,campaign.name,request.report_date,(request.date_from,request.date_to),sections)
            stored_key,size,digest=self.storage.store(tmp_path,suffix[1:]);tmp_path=None
            artifact=ReportArtifact(report_run_id=run.id,format=request.format.value,original_download_name=f"informe-ejecutivo-eleccion-actual-{request.report_date.strftime('%d-%m-%Y')}{suffix}",storage_key=stored_key,mime_type="application/pdf" if suffix==".pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",size_bytes=size,sha256=digest,expires_on=request.report_date+timedelta(days=settings.report_artifact_retention_days),is_available=True,is_active=True)
            self.artifacts.add(artifact);run.status="COMPLETED";run.finished_at=datetime.now().astimezone();self.db.commit();return run
        except Exception as exc:
            if tmp_path and tmp_path.exists():tmp_path.unlink()
            if stored_key:
                try:self.storage.delete(stored_key)
                except Exception:pass
            self.db.rollback();run=self.runs.by_id(run.id)
            if run:run.status="FAILED";run.error_code="REPORT_GENERATION_FAILED";run.error_message="No fue posible generar el informe";run.finished_at=datetime.now().astimezone();self.db.commit()
            if isinstance(exc,(PermissionError,NotFoundError,BusinessRuleError)):raise
            raise BusinessRuleError("No fue posible generar el informe") from exc
    def get_run(self,campaign_id,run_id,user):
        self.access.require_access(campaign_id,user);run=self.runs.by_id(run_id)
        if not run or run.campaign_id!=campaign_id:raise NotFoundError("Informe no encontrado")
        if "TERRITORIAL_COORDINATOR" in {r.code for r in user.roles} and not self.admin(user) and run.requested_by_user_id!=user.id:raise PermissionError("Informe fuera del alcance territorial")
        return run
    def list_runs(self,campaign_id,user,page=1,page_size=20):
        self.access.require_access(campaign_id,user)
        items,total=self.runs.list(campaign_id,page,page_size)
        if "TERRITORIAL_COORDINATOR" in {r.code for r in user.roles} and not self.admin(user):
            items=[item for item in items if item.requested_by_user_id==user.id];total=len(items)
        return items,total
    def artifact(self,run):return self.artifacts.by_run(run.id)
    def download(self,campaign_id,run_id,user,today):
        run=self.get_run(campaign_id,run_id,user);artifact=self.artifact(run)
        if not artifact:raise NotFoundError("Artefacto no encontrado")
        if not artifact.is_available or not artifact.is_active or artifact.expires_on<today:raise BusinessRuleError("ARTEFACT_EXPIRED")
        path=self.storage.resolve(artifact.storage_key)
        if not path.exists():raise BusinessRuleError("ARTEFACT_EXPIRED")
        return path,artifact
    def deactivate(self,campaign_id,run_id,user):
        self.access.require_management(campaign_id,user);run=self.get_run(campaign_id,run_id,user);artifact=self.artifact(run)
        if artifact and artifact.is_available:self.storage.delete(artifact.storage_key);artifact.is_available=False;artifact.is_active=False
        self.db.commit()
