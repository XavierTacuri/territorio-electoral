from decimal import Decimal
from math import ceil
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.config import settings
from app.importers.csv_utils import parse_csv
from app.models.campaign import Campaign
from app.models.survey_study import SurveyStudy,SurveyStudyTerritory,SurveyStudyOption,SurveyStudyResult
from app.models.territory import Parish
from app.schemas.survey_study import *
from app.services.campaign_access_service import CampaignAccessService
from app.services.exceptions import BusinessRuleError,ConflictError,NotFoundError
from app.services.security_audit_service import SecurityAuditService


def _study_question_signature(study):
    return {(o.question_code, o.question_text.strip().lower()) for o in study.options}


def studies_are_comparable(first, second):
    """Predicado compartido de comparabilidad (§3): mismo criterio usado por el
    comparador manual de estudios y por la alerta de nueva medición comparable
    — una sola fuente de verdad evita que ambas superficies decidan distinto."""
    return (
        first.campaign_id == second.campaign_id
        and first.geography_level == second.geography_level
        and first.universe_description.strip().lower() == second.universe_description.strip().lower()
        and first.sampling_method.strip().lower() == second.sampling_method.strip().lower()
        and first.collection_method.strip().lower() == second.collection_method.strip().lower()
        and _study_question_signature(first) == _study_question_signature(second)
    )


class SurveyStudyService:
    def __init__(self,db:Session):self.db=db;self.access=CampaignAccessService(db)
    def roles(self,user):return {r.code for r in user.roles}
    def can_manage(self,user,kind):return self.access.admin(user) or (kind=="GENERAL_SURVEY" and "ANALYST" in self.roles(user))
    def campaign(self,cid,user,manage=False,kind="GENERAL_SURVEY"):
        campaign=self.access.require_access(cid,user)
        if manage and not self.can_manage(user,kind):raise PermissionError("Sin permisos para gestionar este tipo de estudio")
        return campaign
    def get(self,sid,user,manage=False):
        study=self.db.get(SurveyStudy,sid)
        if not study:raise NotFoundError("Estudio no encontrado")
        self.campaign(study.campaign_id,user,manage,study.study_type)
        if not manage and study.status!="PUBLISHED" and not self.can_manage(user,study.study_type):raise PermissionError("El estudio todavía no está publicado")
        return study
    def completeness(self,s):
        n=sum(bool(x) for x in [s.sample_size_total,s.fieldwork_start_date and s.fieldwork_end_date,s.sampling_method and s.collection_method,s.universe_description,s.margin_of_error,s.pollster_name])
        return "COMPLETE" if n==6 else "PARTIAL" if n>=4 else "LIMITED"
    def read(self,s,detail=False):
        base={c.name:getattr(s,c.name) for c in s.__table__.columns};base["methodology_completeness"]=self.completeness(s)
        if not detail:return StudyRead.model_validate(base)
        territories=[]
        for t in s.territories:
            p=self.db.get(Parish,t.parish_id) if t.parish_id else None
            territories.append(TerritoryRead.model_validate({**{c.name:getattr(t,c.name) for c in t.__table__.columns},"parish_name":p.name if p else None,"parish_dpa":p.dpa_code if p else None}))
        options=[OptionRead.model_validate(o) for o in sorted(s.options,key=lambda o:(o.question_code,o.display_order))];omap={o.id:o for o in s.options};results=[]
        for t in s.territories:
            for r in t.results:
                o=omap[r.option_id];results.append(ResultRead.model_validate({**{c.name:getattr(r,c.name) for c in r.__table__.columns},"option_code":o.code,"option_label":o.label,"option_type":o.option_type}))
        warning="Este estudio no sustituye los resultados oficiales del proceso electoral." if s.study_type in {"CNE_EXIT_POLL","EXIT_POLL"} else None
        return StudyDetail.model_validate({**base,"territories":territories,"options":options,"results":results,"exit_poll_warning":warning})
    def audit(self,event,s,user):SecurityAuditService(self.db).record(event,"SUCCESS",f"Estudio {s.code}: {event.lower()}",user_id=user.id,campaign_id=s.campaign_id,resource_type="SURVEY_STUDY",resource_id=s.id)
    def create(self,cid,data,user):
        self.campaign(cid,user,True,data.study_type)
        if data.study_type not in {StudyType.GENERAL_SURVEY,StudyType.CNE_EXIT_POLL}:raise BusinessRuleError("Las nuevas creaciones solo admiten GENERAL_SURVEY o CNE_EXIT_POLL")
        if data.study_type==StudyType.CNE_EXIT_POLL and data.is_official:raise BusinessRuleError("El escrutinio oficial CNE corresponde al módulo electoral")
        values=data.model_dump();values["source_url"]=str(values["source_url"]) if values.get("source_url") else None
        s=SurveyStudy(**values,campaign_id=cid,created_by_user_id=user.id,imported_by_user_id=user.id);self.db.add(s);self.audit("SURVEY_STUDY_CREATED",s,user)
        try:self.db.commit();self.db.refresh(s);return self.read(s)
        except IntegrityError:self.db.rollback();raise ConflictError("Código de estudio duplicado")
    def list(self,cid,user,page,size,status=None,study_type=None,parish_id=None):
        self.campaign(cid,user);q=select(SurveyStudy).where(SurveyStudy.campaign_id==cid)
        if not (self.access.admin(user) or "ANALYST" in self.roles(user)):q=q.where(SurveyStudy.status=="PUBLISHED")
        if status:q=q.where(SurveyStudy.status==status)
        if study_type:q=q.where(SurveyStudy.study_type==study_type)
        if parish_id:q=q.join(SurveyStudyTerritory).where(SurveyStudyTerritory.parish_id==parish_id)
        rows=list(self.db.scalars(q.order_by(SurveyStudy.fieldwork_end_date.desc())));total=len(rows)
        return StudyList(items=[self.read(x) for x in rows[(page-1)*size:page*size]],page=page,page_size=size,total=total,total_pages=ceil(total/size) if total else 0)
    def update(self,sid,data,user):
        s=self.get(sid,user,True)
        if s.status not in {"DRAFT","VALIDATED"}:raise BusinessRuleError("Solo se editan estudios en preparación")
        for k,v in data.model_dump(exclude_unset=True).items():setattr(s,k,str(v) if k=="source_url" and v else v)
        if s.fieldwork_start_date>s.fieldwork_end_date:raise BusinessRuleError("Fechas de campo inválidas")
        s.status="DRAFT";self.audit("SURVEY_STUDY_UPDATED",s,user);self.db.commit();return self.read(s)
    def add_territory(self,sid,data,user):
        s=self.get(sid,user,True)
        if s.status!="DRAFT":raise BusinessRuleError("Solo se modifica un borrador")
        campaign=self.db.get(Campaign,s.campaign_id)
        if s.geography_level=="PARISH":
            p=self.db.get(Parish,data.parish_id)
            if not p or p.canton_id!=campaign.canton_id:raise BusinessRuleError("La parroquia no pertenece al cantón de la campaña")
        elif data.parish_id is not None:raise BusinessRuleError("Un estudio cantonal no usa parroquia")
        t=SurveyStudyTerritory(**data.model_dump(),study_id=s.id);self.db.add(t)
        try:self.db.commit();self.db.refresh(t);return next(x for x in self.read(s,True).territories if x.id==t.id)
        except IntegrityError:self.db.rollback();raise ConflictError("Territorio duplicado")
    def add_option(self,sid,data,user):
        s=self.get(sid,user,True)
        if s.status!="DRAFT":raise BusinessRuleError("Solo se modifica un borrador")
        v=data.model_dump();v["code"]="_".join(v["code"].upper().split());v["question_code"]="_".join(v["question_code"].upper().split());o=SurveyStudyOption(**v,study_id=s.id);self.db.add(o)
        try:self.db.commit();self.db.refresh(o);return OptionRead.model_validate(o)
        except IntegrityError:self.db.rollback();raise ConflictError("Opción duplicada en la pregunta")
    def replace_results(self,sid,rows,user):
        s=self.get(sid,user,True)
        if s.status!="DRAFT":raise BusinessRuleError("Solo se modifica un borrador")
        tids={t.id for t in s.territories};oids={o.id for o in s.options};seen=set()
        for r in rows:
            key=(r.study_territory_id,r.option_id)
            if r.study_territory_id not in tids or r.option_id not in oids:raise BusinessRuleError("Territorio u opción no pertenece al estudio")
            if key in seen:raise ConflictError("Resultado duplicado")
            seen.add(key)
        self.db.query(SurveyStudyResult).filter(SurveyStudyResult.study_id==sid).delete();self.db.add_all([SurveyStudyResult(**r.model_dump(),study_id=sid) for r in rows]);self.db.commit();return self.read(s,True).results
    def issues(self,s):
        issues=[];tol=Decimal(str(settings.survey_result_percentage_tolerance));omap={o.id:o for o in s.options}
        if not s.territories:issues.append(ValidationIssue(code="NO_TERRITORIES",message="Debe registrar cobertura territorial"))
        if len(s.options)<2:issues.append(ValidationIssue(code="NO_OPTIONS",message="Debe registrar al menos dos opciones"))
        for t in s.territories:
            if not t.results:issues.append(ValidationIssue(code="NO_RESULTS",message="El territorio no tiene resultados",territory_id=t.id));continue
            groups={}
            for r in t.results:groups.setdefault(omap[r.option_id].question_code,[]).append((omap[r.option_id],r))
            for q,items in groups.items():
                total=sum((r.percentage for _,r in items),Decimal(0))
                if items[0][0].question_type!="MULTIPLE_CHOICE" and total>Decimal(1)+tol:issues.append(ValidationIssue(code="PERCENTAGE_SUM",message=f"La suma de {q} supera 100 % y la tolerancia",territory_id=t.id))
        if sum(t.sample_size for t in s.territories)>s.sample_size_total:issues.append(ValidationIssue(code="TERRITORY_SAMPLE_EXCEEDS_TOTAL",message="Las muestras territoriales superan la muestra total"))
        return issues
    def validate(self,sid,user):
        s=self.get(sid,user,True);issues=self.issues(s)
        if not issues:s.status="VALIDATED";self.audit("SURVEY_STUDY_VALIDATED",s,user);self.db.commit()
        return ValidationResponse(valid=not issues,status=s.status,issues=issues,methodology_completeness=self.completeness(s))
    def publish(self,sid,user):
        s=self.get(sid,user,True)
        if s.status=="DRAFT":
            if not self.validate(sid,user).valid:raise BusinessRuleError("El estudio contiene errores de validación")
            s=self.get(sid,user,True)
        if s.status!="VALIDATED":raise BusinessRuleError("El estudio no está listo para publicar")
        s.status="PUBLISHED";self.audit("SURVEY_STUDY_PUBLISHED",s,user);self.db.commit();return self.read(s,True)
    def delete(self,sid,user):
        s=self.get(sid,user,True)
        if s.status!="DRAFT":raise BusinessRuleError("Solo se elimina un borrador")
        self.db.delete(s);self.db.commit()
    def archive(self,sid,user):
        s=self.get(sid,user,True)
        if s.status!="PUBLISHED":raise BusinessRuleError("Solo se archiva un estudio publicado")
        s.status="ARCHIVED";self.audit("SURVEY_STUDY_ARCHIVED",s,user);self.db.commit();return self.read(s,True)
    def compare(self,ids,user):
        if not 1<len(ids)<=3:raise BusinessRuleError("Seleccione entre 2 y 3 estudios")
        studies=[self.get(i,user) for i in ids];first=studies[0]
        ok=all(studies_are_comparable(first,s) for s in studies)
        message="Comparación descriptiva entre periodos de campo; no se infiere tendencia predictiva." if ok else "Preguntas, metodología, cobertura o universo incompatibles; los valores solo pueden describirse por separado y no se infiere tendencia."
        return ComparisonResponse(comparable=ok,message=message,studies=[self.read(s,True) for s in studies])
    def parse_import(self,cid,content,user):
        campaign=self.access.require_access(cid,user);rows,_,_=parse_csv(content,"CANONICAL_SURVEY_AGGREGATE_RESULT");errors=[];parsed=[];studies=set();territories=set();definitions={};keys=set();sums={}
        for number,row in rows:
            try:
                study=self.db.scalar(select(SurveyStudy).where(SurveyStudy.campaign_id==cid,SurveyStudy.code==row["study_code"].upper()))
                if not study:raise BusinessRuleError("study_code inexistente")
                if not self.can_manage(user,study.study_type):raise PermissionError("Sin permisos para importar este tipo de estudio")
                if study.status!="DRAFT":raise BusinessRuleError("El estudio no es editable")
                parish=None;dpa=row["parish_dpa"]
                if dpa:
                    if study.geography_level!="PARISH":raise BusinessRuleError("parish_dpa requiere cobertura PARISH")
                    parish=self.db.scalar(select(Parish).where(Parish.dpa_code==dpa))
                    if not parish or parish.canton_id!=campaign.canton_id:raise BusinessRuleError("La parroquia indicada no pertenece al cantón de la campaña.")
                elif study.geography_level!="CANTON":raise BusinessRuleError("Cobertura PARISH requiere parish_dpa")
                qc=row["question_code"].upper();qt=row["question_text"];kind=row["question_type"].upper();oc=row["option_code"].upper()
                if not qt:raise BusinessRuleError("Falta el texto de la pregunta.")
                if kind not in {"SINGLE_CHOICE","MULTIPLE_CHOICE","SCALE","RATING","VOTE_INTENTION"} or not all((qc,oc,row["option_label"])):raise BusinessRuleError("La pregunta o la opción no es válida.")
                try:pct=Decimal(row["percentage"])
                except Exception:raise BusinessRuleError("El porcentaje debe ser numérico.")
                pct=pct/100 if pct>1 else pct
                if not 0<=pct<=1:raise BusinessRuleError("percentage fuera de rango")
                try:base=int(row["base_n"]) if row["base_n"] else None
                except ValueError:raise BusinessRuleError("Base N debe ser un número entero.")
                tk=(study.id,parish.id if parish else None);ok=(qc,oc);rk=(tk,ok);definition=(row["option_label"],qt,kind)
                if ok in definitions and definitions[ok]!=definition:raise BusinessRuleError("Código reutilizado con definición distinta")
                if rk in keys:raise BusinessRuleError("Resultado duplicado")
                definitions[ok]=definition;keys.add(rk);studies.add(study.code);territories.add(tk);sums[(tk,qc,kind)]=sums.get((tk,qc,kind),Decimal(0))+pct
                parsed.append(dict(study=study,parish=parish,territory_key=tk,option_key=ok,question_code=qc,question_text=qt,question_type=kind,option_code=oc,option_label=row["option_label"],base_n=base,percentage=pct))
            except (ValueError,BusinessRuleError,PermissionError) as e:errors.append(SurveyImportIssue(row_number=number,code="INVALID_ROW",message=str(e)))
        tol=Decimal(str(settings.survey_result_percentage_tolerance))
        for (_,q,kind),total in sums.items():
            if kind!="MULTIPLE_CHOICE" and total>1+tol:errors.append(SurveyImportIssue(code="PERCENTAGE_SUM",message=f"La suma de {q} supera 100 % y la tolerancia"))
        return rows,parsed,errors,studies,territories,definitions
    def validate_import(self,cid,content,user):
        rows,parsed,errors,studies,territories,options=self.parse_import(cid,content,user);rejected=len({e.row_number for e in errors if e.row_number})+sum(e.row_number is None for e in errors)
        return SurveyImportSummary(status="VALIDATED" if not errors else "REJECTED",rows_read=len(rows),rows_valid=len(parsed) if not errors else max(0,len(rows)-rejected),rows_rejected=rejected,studies=sorted(studies),territories=len(territories),options=len(options),questions=len({x["question_code"] for x in parsed}),parishes=sorted({x["parish"].dpa_code for x in parsed if x["parish"]}),errors=errors)
    def execute_import(self,cid,content,user):
        rows,parsed,errors,studies,territory_keys,definitions=self.parse_import(cid,content,user)
        if errors:raise BusinessRuleError("El CSV contiene errores; valide antes de ejecutar")
        for study in {x["study"] for x in parsed}:
            items=[x for x in parsed if x["study"].id==study.id];tm={};om={}
            for x in items:
                pid=x["parish"].id if x["parish"] else None;t=self.db.scalar(select(SurveyStudyTerritory).where(SurveyStudyTerritory.study_id==study.id,SurveyStudyTerritory.parish_id==pid))
                if not t:t=SurveyStudyTerritory(study_id=study.id,parish_id=pid,sample_size=study.sample_size_total);self.db.add(t);self.db.flush()
                tm[x["territory_key"]]=t;o=self.db.scalar(select(SurveyStudyOption).where(SurveyStudyOption.study_id==study.id,SurveyStudyOption.question_code==x["question_code"],SurveyStudyOption.code==x["option_code"]))
                if not o:o=SurveyStudyOption(study_id=study.id,question_code=x["question_code"],question_text=x["question_text"],question_type=x["question_type"],code=x["option_code"],label=x["option_label"],option_type="OTHER",display_order=len(om));self.db.add(o);self.db.flush()
                om[x["option_key"]]=o
            for t in tm.values():self.db.query(SurveyStudyResult).filter(SurveyStudyResult.study_id==study.id,SurveyStudyResult.study_territory_id==t.id).delete()
            self.db.add_all([SurveyStudyResult(study_id=study.id,study_territory_id=tm[x["territory_key"]].id,option_id=om[x["option_key"]].id,response_count=x["base_n"],percentage=x["percentage"]) for x in items]);study.imported_by_user_id=user.id;self.audit("SURVEY_STUDY_IMPORTED",study,user)
        self.db.commit();return SurveyImportSummary(status="COMPLETED",rows_read=len(rows),rows_valid=len(rows),rows_rejected=0,studies=sorted(studies),territories=len(territory_keys),options=len(definitions),questions=len({x["question_code"] for x in parsed}),parishes=sorted({x["parish"].dpa_code for x in parsed if x["parish"]}),errors=[])
