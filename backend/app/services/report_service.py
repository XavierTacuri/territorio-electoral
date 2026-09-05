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
from app.reports.report_center import citations_section,debate_brief_sections,election_day_sections,electoral_descriptive_sections,executive_sections,limitations_section,narrative_sections,operation_sections,parish_profile_sections,thematic_sections
from app.services.report_narrative_service import ReportNarrativeService
from app.repositories.report_artifact_repository import ReportArtifactRepository
from app.repositories.report_run_repository import ReportRunRepository
from app.repositories.report_template_repository import ReportTemplateRepository
from app.schemas.reports import ReportCitationRead,ReportGenerationRequest,ReportNarrativeRead,ReportPreviewResponse,ReportSectionPreview,ReportTemplateCreate,ReportTemplateUpdate,ReportTypeRead
from app.services.campaign_access_service import CampaignAccessService
from app.services.campaign_permissions import CAMPAIGN_EXECUTIVE_ROLES
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
    def _narrative(self,data):
        overview=data.get("overview") or {}
        summary_text=overview.get("summary_text") or (data.get("fallback_bullets") or [None])[0]
        return ReportNarrativeService().synthesize(data["report_kind_label"],data.get("narrative_documents",[]),summary_text,data.get("fallback_bullets",[]),data.get("is_demo",False))
    def _report_center_content_sections(self,data):
        if data.get("_election_day_report"):return election_day_sections(data)
        if "chronology" in data:return operation_sections(data)
        if data.get("_debate_brief"):return debate_brief_sections(data)
        if "theme" in data:return thematic_sections(data)
        if "campaign_context" in data:return executive_sections(data)
        if "current_election" in data:
            base=self._current_election_sections(data["current_election"])
            return base+(parish_profile_sections(data) if "activities" in data else electoral_descriptive_sections(data))
        return []
    def _report_center_sections(self,data,include_citations=True):
        narrative=self._narrative(data)
        sections=narrative_sections(narrative.model_dump())+self._report_center_content_sections(data)
        if include_citations and data.get("citations"):sections.append(citations_section(data["citations"]))
        sections.append(limitations_section(narrative.limitations,data.get("is_demo",False)))
        return sections,narrative
    def _sections(self,data,include_citations=True):
        if data.get("_report_center"):sections,_narr=self._report_center_sections(data,include_citations);return sections
        if "survey_study" in data:return self._survey_study_sections(data["survey_study"])
        if "current_election" in data:return self._current_election_sections(data["current_election"])
        if "public_intelligence" in data:return self._public_intelligence_sections(data["public_intelligence"])
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
    def _public_intelligence_sections(self,data):
        summary=data["summary"]
        publications=data["publications"]
        return [
            {"title":"Resumen","headers":["Indicador","Valor"],"rows":[
                ["Fuentes activas",summary["active_sources"]],
                ["Fuentes oficiales",summary["official_sources"]],
                ["Publicaciones últimas 24 h",summary["items_last_24h"]],
                ["Publicaciones últimos 7 días",summary["items_last_7_days"]],
                ["Fuentes con error",summary["sources_with_error"]],
                ["Última actualización",summary.get("last_update")],
            ]},
            {"title":"Fuentes","headers":["Fuente","Publicador","Tipo","Oficial","URL","Último éxito"],"rows":[
                [source["name"],source["publisher"],source["source_type"],"Sí" if source["official"] else "No",source["base_url"],source.get("last_success_at")]
                for source in data["sources"]
            ]},
            {"title":"Publicaciones","headers":["Título","Publicador","Fuente","Publicado","Tipo","URL","Resumen"],"rows":[
                [item["title"],item["publisher"],item["source_name"],item.get("published_at"),item["item_type"],item["url"],item.get("summary")]
                for item in publications
            ]},
            {"title":"Temas","headers":["Publicación","Tema"],"rows":[
                [item["title"],topic["name"]] for item in publications for topic in item["topics"]
            ]},
            {"title":"Territorios","headers":["Publicación","Parroquia","Método","Confianza geográfica"],"rows":[
                [item["title"],territory["name"],territory["association_method"],territory.get("confidence")]
                for item in publications for territory in item["territories"]
            ]},
            {"title":"Actualizaciones","headers":["Publicación","Consultado","Cambio detectado"],"rows":[
                [item["title"],revision["fetched_at"],"Sí" if revision["change_detected"] else "No"]
                for item in publications for revision in item["revisions"]
            ]},
            {"title":"Metodología","text":data["methodology"],"headers":[],"rows":[]},
        ]
    def _survey_study_sections(self,s):
        warning="Los resultados representan respuestas agregadas de una muestra y no constituyen resultados electorales oficiales ni garantía de comportamiento electoral futuro."
        options={str(o["id"]):o for o in s["options"]};territories={str(t["id"]):t for t in s["territories"]}
        results=[[options[str(r["option_id"])]["label"],r["percentage"],r["response_count"]] for r in s["results"]]
        territorial=[[territories[str(r["study_territory_id"])].get("parish_name") or "Cantón",territories[str(r["study_territory_id"])]["sample_size"],options[str(r["option_id"])]["label"],r["percentage"],r["response_count"]] for r in s["results"]]
        context={"report_kind":"ENCUESTA Y ESTUDIO TERRITORIAL","study_name":s["name"],"study_type":s["study_type"],"fieldwork_start_date":s["fieldwork_start_date"],"fieldwork_end_date":s["fieldwork_end_date"],"publication_date":s.get("publication_date")}
        warnings=[[warning]]
        if s["study_type"]=="EXIT_POLL":warnings.append(["Resultado de estudio de salida de urna. No corresponde al escrutinio oficial del Consejo Nacional Electoral."])
        return [{"title":"Resumen","context":context,"text":warning,"headers":["Campo","Valor"],"rows":[["Nombre",s["name"]],["Tipo",s["study_type"]],["Fecha inicio",s["fieldwork_start_date"]],["Fecha fin",s["fieldwork_end_date"]],["Fecha publicación",s.get("publication_date")]]},{"title":"Metodología","headers":["Campo","Valor"],"rows":[["Universo",s["universe_description"]],["Muestra",s["sample_size_total"]],["Método de muestreo",s["sampling_method"]],["Método de recolección",s["collection_method"]],["Margen de error declarado",s.get("margin_of_error")],["Nivel de confianza",s.get("confidence_level")],["Encuestadora",s.get("pollster_name")],["Patrocinador",s.get("sponsor_name")]]},{"title":"Resultados","headers":["Opción","Porcentaje","Conteo"],"rows":results,"formats":[None,"percent","integer"]},{"title":"Resultados territoriales","headers":["Parroquia","Muestra","Opción","Porcentaje","Conteo"],"rows":territorial,"formats":[None,"integer",None,"percent","integer"]},{"title":"Comparación","text":"La comparación o tendencia solo se presenta cuando los estudios son metodológicamente comparables.","headers":[],"rows":[]},{"title":"Advertencias","headers":["Advertencia"],"rows":warnings},{"title":"Fuentes","headers":["Campo","Valor"],"rows":[["Quién realizó",s.get("pollster_name")],["Quién encargó",s.get("sponsor_name")],["Tipo de fuente",s["source_type"]],["URL",str(s["source_url"]) if s.get("source_url") else None]]}]
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
            data=ReportDataService(self.db).collect(campaign_id,user,template.report_type,request,template.code);sections=self._sections(data,request.include_citations)
            suffix=".pdf" if request.format.value=="PDF" else ".xlsx"
            with tempfile.NamedTemporaryFile(suffix=suffix,delete=False) as handle:tmp_path=Path(handle.name)
            if request.format.value=="PDF":ReportPDFService(settings.report_pdf_max_table_rows).render(tmp_path,request.title,campaign.name,request.report_date,(request.date_from,request.date_to),sections)
            else:ReportExcelService().render(tmp_path,request.title,campaign.name,request.report_date,(request.date_from,request.date_to),sections)
            stored_key,size,digest=self.storage.store(tmp_path,suffix[1:]);tmp_path=None
            prefix={"SURVEY_STUDY_REPORT":"estudio-territorial","PARISH_TERRITORIAL_PROFILE":"ficha-territorial","PUBLIC_INTELLIGENCE_REPORT":"inteligencia-publica","CAMPAIGN_EXECUTIVE_REPORT":"informe-ejecutivo-campana","OPERATION_TERRITORIAL_REPORT":"informe-operacion-territorial","THEMATIC_REPORT":"informe-tematico","DEBATE_BRIEF_REPORT":"preparacion-debate","ELECTION_DAY_REPORT":"informe-jornada-electoral"}.get(request.template_code,"informe-ejecutivo-eleccion-actual")
            artifact=ReportArtifact(report_run_id=run.id,format=request.format.value,original_download_name=f"{prefix}-{request.report_date.strftime('%d-%m-%Y')}{suffix}",storage_key=stored_key,mime_type="application/pdf" if suffix==".pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",size_bytes=size,sha256=digest,expires_on=request.report_date+timedelta(days=settings.report_artifact_retention_days),is_available=True,is_active=True)
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
    @staticmethod
    def list_types():
        return [
            ReportTypeRead(code="CAMPAIGN_EXECUTIVE_REPORT",name="Informe ejecutivo de campaña",description="Resumen general de la campaña: cobertura operativa, necesidades, encuestas e información pública.",allowed_formats=["PDF","XLSX"]),
            ReportTypeRead(code="PARISH_TERRITORIAL_PROFILE",name="Informe territorial por parroquia",description="Ficha narrativa de una parroquia basada en el expediente territorial.",requires_parish=True,allowed_formats=["PDF","XLSX"]),
            ReportTypeRead(code="OPERATION_TERRITORIAL_REPORT",name="Informe de operación territorial",description="Actividades realizadas y próximas, cobertura, necesidades detectadas y evidencia.",allowed_formats=["PDF","XLSX"]),
            ReportTypeRead(code="CURRENT_ELECTION_EXECUTIVE",name="Informe electoral descriptivo",description="Padrón, antecedentes, participación histórica y modelo V1, demografía y encuestas publicadas. Descriptivo, sin predicción.",allowed_formats=["PDF","XLSX"]),
            ReportTypeRead(code="THEMATIC_REPORT",name="Informe temático",description="Cruce de necesidades, actividades, encuestas, información pública y evidencia sobre un tema (vialidad, agua, seguridad, etc.).",requires_theme=True,allowed_formats=["PDF","XLSX"]),
            ReportTypeRead(code="ELECTION_DAY_REPORT",name="Informe de jornada electoral",description="Cobertura de recintos y juntas, presencia de personal, incidencias y documentación recibida durante la jornada. Información estrictamente operativa: no es un informe de resultados.",allowed_formats=["PDF","XLSX"]),
        ]
    def preview(self,campaign_id:UUID,request:ReportGenerationRequest,user:User):
        self._scope(campaign_id,user,request);template=self.templates.by_code(request.template_code)
        if not template or not template.is_active:raise NotFoundError("Plantilla no encontrada")
        data=ReportDataService(self.db).collect(campaign_id,user,template.report_type,request,template.code)
        if not data.get("_report_center"):raise BusinessRuleError("Esta plantilla no admite previsualización")
        narrative=self._narrative(data);content=self._report_center_content_sections(data)
        citations=[ReportCitationRead.model_validate(c) for c in (data.get("citations") or [])] if request.include_citations else []
        return ReportPreviewResponse(
            report_kind=template.code,title=request.title,subtitle=data.get("report_kind_label"),generated_at=request.report_date,
            generated_by=user.username,is_demo=data.get("is_demo",False),narrative=ReportNarrativeRead.model_validate(narrative.model_dump()),
            sections=[ReportSectionPreview(title=s["title"],subtitle=s.get("subtitle"),text=s.get("text"),headers=s.get("headers",[]),rows=s.get("rows",[])) for s in content],
            citations=citations,limitations=narrative.limitations,
        )
    def preview_run(self,campaign_id:UUID,run_id:UUID,user:User):
        run=self.get_run(campaign_id,run_id,user);template=self.templates.by_id(run.report_template_id)
        request=ReportGenerationRequest(template_code=template.code,format=run.requested_format,title=run.title,report_date=run.report_date,**{k:v for k,v in run.filters.items() if k not in {"template_code","format","title","report_date"}})
        return self.preview(campaign_id,request,user)
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
        self.access.require_access(campaign_id,user)
        if not self.admin(user) and not CAMPAIGN_EXECUTIVE_ROLES.intersection(r.code for r in user.roles):raise PermissionError("Sin permisos")
        run=self.get_run(campaign_id,run_id,user);artifact=self.artifact(run)
        if artifact and artifact.is_available:self.storage.delete(artifact.storage_key);artifact.is_available=False;artifact.is_active=False
        self.db.commit()
