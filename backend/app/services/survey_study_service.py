from decimal import Decimal
from math import ceil
from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.campaign import Campaign
from app.models.survey_study import SurveyStudy,SurveyStudyTerritory,SurveyStudyOption,SurveyStudyResult
from app.models.territory import Parish
from app.schemas.survey_study import *
from app.services.campaign_access_service import CampaignAccessService
from app.services.exceptions import BusinessRuleError,ConflictError,NotFoundError
from app.services.security_audit_service import SecurityAuditService
from app.importers.csv_utils import parse_csv

class SurveyStudyService:
    def __init__(self,db:Session): self.db=db; self.access=CampaignAccessService(db)
    def campaign(self,cid,user,manage=False): return self.access.require_management(cid,user) if manage else self.access.require_access(cid,user)
    def get(self,sid,user,manage=False):
        obj=self.db.get(SurveyStudy,sid)
        if not obj: raise NotFoundError("Estudio no encontrado")
        self.campaign(obj.campaign_id,user,manage)
        return obj
    def completeness(self,s):
        fields=[s.sample_size_total,s.fieldwork_start_date and s.fieldwork_end_date,s.sampling_method and s.collection_method,s.universe_description,s.margin_of_error,s.pollster_name]
        count=sum(bool(x) for x in fields)
        return "COMPLETE" if count==6 else "PARTIAL" if count>=4 else "LIMITED"
    def read(self,s,detail=False):
        base={c.name:getattr(s,c.name) for c in s.__table__.columns}; base["methodology_completeness"]=self.completeness(s)
        if not detail:return StudyRead.model_validate(base)
        territories=[]
        for t in s.territories:
            p=self.db.get(Parish,t.parish_id) if t.parish_id else None
            territories.append(TerritoryRead.model_validate({**{c.name:getattr(t,c.name) for c in t.__table__.columns},"parish_name":p.name if p else None,"parish_dpa":p.dpa_code if p else None}))
        options=[OptionRead.model_validate(o) for o in sorted(s.options,key=lambda x:x.display_order)]
        omap={o.id:o for o in s.options}; results=[]
        for t in s.territories:
            for r in t.results:
                o=omap[r.option_id]; results.append(ResultRead.model_validate({**{c.name:getattr(r,c.name) for c in r.__table__.columns},"option_code":o.code,"option_label":o.label,"option_type":o.option_type}))
        warning="Resultado de estudio de salida de urna. No corresponde al escrutinio oficial del Consejo Nacional Electoral." if s.study_type=="EXIT_POLL" else None
        return StudyDetail.model_validate({**base,"territories":territories,"options":options,"results":results,"exit_poll_warning":warning})
    def audit(self,event,s,user): SecurityAuditService(self.db).record(event,"SUCCESS",f"Estudio {s.code}: {event.lower()}",user_id=user.id,campaign_id=s.campaign_id,resource_type="SURVEY_STUDY",resource_id=s.id)
    def create(self,cid,data,user):
        self.campaign(cid,user,True); values=data.model_dump(); values["source_url"]=str(values["source_url"]) if values.get("source_url") else None
        s=SurveyStudy(**values,campaign_id=cid,created_by_user_id=user.id); self.db.add(s); self.audit("SURVEY_STUDY_CREATED",s,user)
        try:self.db.commit();self.db.refresh(s);return self.read(s)
        except IntegrityError:self.db.rollback();raise ConflictError("Código de estudio duplicado")
    def list(self,cid,user,page,size,status=None,study_type=None,parish_id=None):
        self.campaign(cid,user); q=select(SurveyStudy).where(SurveyStudy.campaign_id==cid)
        if status:q=q.where(SurveyStudy.status==status)
        if study_type:q=q.where(SurveyStudy.study_type==study_type)
        if parish_id:q=q.join(SurveyStudyTerritory).where(SurveyStudyTerritory.parish_id==parish_id)
        rows=list(self.db.scalars(q.order_by(SurveyStudy.fieldwork_end_date.desc()))); total=len(rows)
        return StudyList(items=[self.read(x) for x in rows[(page-1)*size:page*size]],page=page,page_size=size,total=total,total_pages=ceil(total/size) if total else 0)
    def update(self,sid,data,user):
        s=self.get(sid,user,True)
        if s.status not in {"DRAFT","VALIDATED"}:raise BusinessRuleError("Solo se editan estudios borrador o validados")
        for k,v in data.model_dump(exclude_unset=True).items():setattr(s,k,str(v) if k=="source_url" and v else v)
        if s.fieldwork_start_date>s.fieldwork_end_date:raise BusinessRuleError("Las fechas de campo son inválidas")
        s.status="DRAFT";self.audit("SURVEY_STUDY_UPDATED",s,user);self.db.commit();return self.read(s)
    def add_territory(self,sid,data,user):
        s=self.get(sid,user,True)
        if s.status!="DRAFT":raise BusinessRuleError("Solo se modifica un borrador")
        if data.parish_id is None and any(t.parish_id is None for t in s.territories):raise ConflictError("Territorio cantonal duplicado")
        campaign=self.db.get(Campaign,s.campaign_id)
        if s.geography_level=="PARISH":
            p=self.db.get(Parish,data.parish_id)
            if not p or p.canton_id!=campaign.canton_id:raise BusinessRuleError("La parroquia no pertenece al cantón de la campaña")
        elif data.parish_id is not None:raise BusinessRuleError("Un estudio cantonal no usa parroquia")
        t=SurveyStudyTerritory(**data.model_dump(),study_id=s.id);self.db.add(t)
        try:self.db.commit();self.db.refresh(t);return self.read(s,True).territories[-1]
        except IntegrityError:self.db.rollback();raise ConflictError("Territorio duplicado")
    def add_option(self,sid,data,user):
        s=self.get(sid,user,True)
        if s.status!="DRAFT":raise BusinessRuleError("Solo se modifica un borrador")
        values=data.model_dump();values["code"]="_".join(values["code"].upper().split());o=SurveyStudyOption(**values,study_id=s.id);self.db.add(o)
        try:self.db.commit();self.db.refresh(o);return OptionRead.model_validate(o)
        except IntegrityError:self.db.rollback();raise ConflictError("Opción duplicada")
    def replace_results(self,sid,rows,user):
        s=self.get(sid,user,True)
        if s.status!="DRAFT":raise BusinessRuleError("Solo se modifica un borrador")
        tids={t.id:t for t in s.territories};oids={o.id:o for o in s.options};seen=set()
        for row in rows:
            if row.study_territory_id not in tids or row.option_id not in oids:raise BusinessRuleError("Territorio u opción no pertenece al estudio")
            key=(row.study_territory_id,row.option_id)
            if key in seen:raise ConflictError("Resultado duplicado")
            seen.add(key)
        self.db.query(SurveyStudyResult).filter(SurveyStudyResult.study_id==sid).delete()
        self.db.add_all([SurveyStudyResult(**r.model_dump(),study_id=sid) for r in rows]);self.db.commit();return self.read(s,True).results
    def issues(self,s):
        issues=[];tol=Decimal(str(settings.survey_result_percentage_tolerance))
        if not s.territories:issues.append(ValidationIssue(code="NO_TERRITORIES",message="Debe registrar cobertura territorial"))
        if len(s.options)<2:issues.append(ValidationIssue(code="NO_OPTIONS",message="Debe registrar al menos dos opciones"))
        for t in s.territories:
            total=sum((r.percentage for r in t.results),Decimal(0)); counts=sum(r.response_count for r in t.results if r.response_count is not None)
            if not t.results:issues.append(ValidationIssue(code="NO_RESULTS",message="El territorio no tiene resultados",territory_id=t.id))
            elif abs(total-Decimal(1))>tol:issues.append(ValidationIssue(code="PERCENTAGE_SUM",message=f"La suma de porcentajes es {total}; debe aproximarse a 1",territory_id=t.id))
            if counts>t.sample_size:issues.append(ValidationIssue(code="COUNT_EXCEEDS_SAMPLE",message="Los conteos superan la muestra territorial",territory_id=t.id))
        if sum(t.sample_size for t in s.territories)>s.sample_size_total:issues.append(ValidationIssue(code="TERRITORY_SAMPLE_EXCEEDS_TOTAL",message="Las muestras territoriales superan la muestra total"))
        return issues
    def validate(self,sid,user):
        s=self.get(sid,user,True);issues=self.issues(s)
        if not issues:s.status="VALIDATED";self.audit("SURVEY_STUDY_VALIDATED",s,user);self.db.commit()
        return ValidationResponse(valid=not issues,status=s.status,issues=issues,methodology_completeness=self.completeness(s))
    def publish(self,sid,user):
        s=self.get(sid,user,True)
        if s.status!="VALIDATED":raise BusinessRuleError("El estudio debe validarse antes de publicar")
        if self.issues(s):raise BusinessRuleError("El estudio contiene errores de validación")
        s.status="PUBLISHED";self.audit("SURVEY_STUDY_PUBLISHED",s,user);self.db.commit();return self.read(s,True)
    def delete(self,sid,user):
        s=self.get(sid,user,True)
        if s.status!="DRAFT":raise BusinessRuleError("Solo se elimina un borrador")
        self.db.delete(s);self.db.commit()
    def compare(self,ids,user):
        if not 1<len(ids)<=3:raise BusinessRuleError("Seleccione entre 2 y 3 estudios")
        studies=[self.get(i,user) for i in ids]; first=studies[0]
        compatible=all(x.campaign_id==first.campaign_id and x.question_code==first.question_code and x.geography_level==first.geography_level and x.universe_description.strip().lower()==first.universe_description.strip().lower() and x.sampling_method.strip().lower()==first.sampling_method.strip().lower() for x in studies)
        return ComparisonResponse(comparable=compatible,message=None if compatible else "Estudios no directamente comparables.",studies=[self.read(x,True) for x in studies])
    def parse_import(self,cid,content,user):
        campaign=self.campaign(cid,user,True)
        rows,_,_=parse_csv(content,"CANONICAL_SURVEY_AGGREGATE_RESULT")
        errors=[];parsed=[];study_codes=set();territory_keys=set();option_defs={};result_keys=set();sums={}
        allowed_types={"CANDIDATE","UNDECIDED","BLANK","NULL_VOTE","OTHER","NO_RESPONSE"}
        for number,row in rows:
            try:
                study_code=row["study_code"].strip().upper();level=row["territory_level"].strip().upper();dpa=row["parish_dpa"].strip();option_code=row["option_code"].strip().upper()
                study=self.db.scalar(select(SurveyStudy).where(SurveyStudy.campaign_id==cid,SurveyStudy.code==study_code))
                if not study:raise BusinessRuleError("study_code inexistente")
                if study.status not in {"DRAFT"}:raise BusinessRuleError("El estudio no es editable")
                if level not in {"CANTON","PARISH"} or level!=study.geography_level:raise BusinessRuleError("territory_level incompatible")
                parish=None
                if level=="PARISH":
                    if not dpa:raise BusinessRuleError("parish_dpa requerido")
                    parish=self.db.scalar(select(Parish).where(Parish.dpa_code==dpa))
                    if not parish:raise BusinessRuleError("DPA parroquial inválido")
                    if parish.canton_id!=campaign.canton_id:raise BusinessRuleError("La parroquia no pertenece al cantón")
                elif dpa:raise BusinessRuleError("parish_dpa debe estar vacío para CANTON")
                option_type=row["option_type"].strip().upper()
                if not option_code or option_type not in allowed_types:raise BusinessRuleError("Opción o tipo inválido")
                definition=(row["option_label"].strip(),option_type)
                if option_code in option_defs and option_defs[option_code]!=definition:raise BusinessRuleError("option_code duplicado con definición distinta")
                option_defs[option_code]=definition
                try:pct=Decimal(row["percentage"])
                except Exception:raise BusinessRuleError("percentage inválido")
                if pct<0 or pct>1:raise BusinessRuleError("percentage debe estar entre 0 y 1")
                count=None
                if row["response_count"]:
                    try:count=int(row["response_count"])
                    except ValueError:raise BusinessRuleError("response_count inválido")
                    if count<0:raise BusinessRuleError("response_count no puede ser negativo")
                territory_key=(study.id,parish.id if parish else None);key=(territory_key,option_code)
                if key in result_keys:raise BusinessRuleError("Resultado duplicado para territorio y opción")
                result_keys.add(key);territory_keys.add(territory_key);study_codes.add(study_code);sums[territory_key]=sums.get(territory_key,Decimal(0))+pct
                parsed.append(dict(number=number,study=study,parish=parish,territory_key=territory_key,option_code=option_code,option_label=definition[0],option_type=option_type,response_count=count,percentage=pct))
            except BusinessRuleError as exc:errors.append(SurveyImportIssue(row_number=number,code="INVALID_ROW",message=str(exc)))
        tolerance=Decimal(str(settings.survey_result_percentage_tolerance))
        for key,total in sums.items():
            if abs(total-Decimal(1))>tolerance:errors.append(SurveyImportIssue(code="PERCENTAGE_SUM",message=f"La suma territorial {total} no se aproxima a 1"))
        return rows,parsed,errors,study_codes,territory_keys,option_defs
    def validate_import(self,cid,content,user):
        rows,parsed,errors,studies,territories,options=self.parse_import(cid,content,user)
        return SurveyImportSummary(status="VALIDATED" if not errors else "REJECTED",rows_read=len(rows),rows_valid=len(parsed) if not errors else max(0,len(rows)-len({e.row_number for e in errors if e.row_number})),rows_rejected=len({e.row_number for e in errors if e.row_number})+sum(e.row_number is None for e in errors),studies=sorted(studies),territories=len(territories),options=len(options),errors=errors)
    def execute_import(self,cid,content,user):
        rows,parsed,errors,studies,territory_keys,option_defs=self.parse_import(cid,content,user)
        if errors:raise BusinessRuleError("El CSV contiene errores; valide antes de ejecutar")
        touched={item["study"] for item in parsed}
        for study in touched:
            study_rows=[x for x in parsed if x["study"].id==study.id]
            territory_map={}
            for item in study_rows:
                parish_id=item["parish"].id if item["parish"] else None
                territory=self.db.scalar(select(SurveyStudyTerritory).where(SurveyStudyTerritory.study_id==study.id,SurveyStudyTerritory.parish_id==parish_id))
                if not territory:
                    count=sum(x["response_count"] or 0 for x in study_rows if x["territory_key"]==item["territory_key"])
                    territory=SurveyStudyTerritory(study_id=study.id,parish_id=parish_id,sample_size=count or study.sample_size_total);self.db.add(territory);self.db.flush()
                territory_map[item["territory_key"]]=territory
            option_map={}
            for code,(label,kind) in option_defs.items():
                option=self.db.scalar(select(SurveyStudyOption).where(SurveyStudyOption.study_id==study.id,SurveyStudyOption.code==code))
                if not option:option=SurveyStudyOption(study_id=study.id,code=code,label=label,option_type=kind,display_order=len(option_map));self.db.add(option);self.db.flush()
                elif (option.label,option.option_type)!=(label,kind):raise BusinessRuleError("La opción existente no coincide con el CSV")
                option_map[code]=option
            for territory in territory_map.values():self.db.query(SurveyStudyResult).filter(SurveyStudyResult.study_id==study.id,SurveyStudyResult.study_territory_id==territory.id).delete()
            self.db.add_all([SurveyStudyResult(study_id=x["study"].id,study_territory_id=territory_map[x["territory_key"]].id,option_id=option_map[x["option_code"]].id,response_count=x["response_count"],percentage=x["percentage"]) for x in study_rows])
            self.audit("SURVEY_STUDY_IMPORTED",study,user)
        self.db.commit()
        return SurveyImportSummary(status="COMPLETED",rows_read=len(rows),rows_valid=len(rows),rows_rejected=0,studies=sorted(studies),territories=len(territory_keys),options=len(option_defs),errors=[])
