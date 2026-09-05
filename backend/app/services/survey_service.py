import hashlib,hmac,re
from datetime import date
from decimal import Decimal
from math import ceil
from statistics import median
from uuid import UUID
from sqlalchemy import func,or_,select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session,selectinload
from app.core.config import settings
from app.models.campaign import Campaign
from app.models.operational import TerritorialActivity
from app.models.survey import *
from app.models.territory import Parish,Community,Sector
from app.models.user import User
from app.schemas.survey import *
from app.services.campaign_access_service import CampaignAccessService
from app.services.campaign_permissions import CAMPAIGN_EXECUTIVE_ROLES
from app.services.exceptions import BusinessRuleError,ConflictError,NotFoundError
from app.services.operational_service import OperationalService

PERSONAL=re.compile(r'(?i)(?:[\w.+-]+@[\w.-]+\.[a-z]{2,}|(?:\+?593|0)?9\d{8}|\b\d{10}\b)')
def safe_text(value:str|None)->str|None:
    if value is None:return None
    value=' '.join(value.split())
    if PERSONAL.search(value):raise BusinessRuleError('Elimine datos personales del texto')
    return value
class SurveyService:
    MANAGERS=CAMPAIGN_EXECUTIVE_ROLES
    def __init__(self,db:Session,today_provider=date.today):self.db=db;self.access=CampaignAccessService(db);self.today=today_provider;self.ops=OperationalService(db,today_provider)
    def roles(self,u):return {r.code for r in u.roles}
    def campaign(self,cid,user,manage=False):
        if manage and not self.access.admin(user) and not self.roles(user).intersection(CAMPAIGN_EXECUTIVE_ROLES):
            raise PermissionError('Sin permisos de gestión')
        return self.access.require_access(cid,user)
    def survey(self,cid,sid,user,manage=False,active=True):
        self.campaign(cid,user,manage);obj=self.db.get(Survey,sid)
        if not obj or obj.campaign_id!=cid or (active and not obj.is_active):raise NotFoundError('Encuesta no encontrada')
        return obj
    def create(self,cid,data,user):
        campaign=self.campaign(cid,user,True)
        if campaign.status not in {'DRAFT','ACTIVE'}:raise BusinessRuleError('La campaña no permite encuestas')
        values=data.model_dump();values['anonymous_only']=True;obj=Survey(**values,campaign_id=cid,status='DRAFT',created_by_user_id=user.id);self.db.add(obj)
        try:self.db.commit();self.db.refresh(obj);return obj
        except IntegrityError:self.db.rollback();raise ConflictError('Slug duplicado')
    def list(self,cid,user,page=1,size=20,**f):
        self.campaign(cid,user);conds=[Survey.campaign_id==cid]
        if f.get('is_active') is not None:conds.append(Survey.is_active==f['is_active'])
        else:conds.append(Survey.is_active.is_(True))
        for k,col in {'status':Survey.status,'target_scope':Survey.target_scope}.items():
            if f.get(k):conds.append(col==f[k])
        if f.get('search'):conds.append(or_(func.lower(Survey.title).like(f"%{f['search'].lower()}%"),func.lower(Survey.description).like(f"%{f['search'].lower()}%")))
        if f.get('date_from'):conds.append(or_(Survey.start_date.is_(None),Survey.start_date>=f['date_from']))
        if f.get('date_to'):conds.append(or_(Survey.end_date.is_(None),Survey.end_date<=f['date_to']))
        rows=list(self.db.scalars(select(Survey).where(*conds).order_by(Survey.status,Survey.start_date.desc(),Survey.title)));total=len(rows);return SurveyListResponse(items=rows[(page-1)*size:page*size],page=page,page_size=size,total=total,total_pages=ceil(total/size) if total else 0)
    def detail(self,cid,sid,user):
        obj=self.survey(cid,sid,user);sections=[]
        for sec in sorted((x for x in obj.sections if x.is_active),key=lambda x:(x.display_order,x.title)):
            questions=[]
            for q in sorted((x for x in sec.questions if x.is_active),key=lambda x:(x.display_order,x.code)):
                questions.append({**SurveyQuestionRead.model_validate(q).model_dump(), 'options':[SurveyOptionRead.model_validate(o).model_dump() for o in q.options if o.is_active]})
            sections.append({**SurveySectionRead.model_validate(sec).model_dump(),'questions':questions})
        total=self.db.scalar(select(func.count()).select_from(SurveyResponse).where(SurveyResponse.survey_id==sid,SurveyResponse.is_valid.is_(True))) or 0
        return {**SurveyRead.model_validate(obj).model_dump(),'sections':sections,'total_valid_responses':total}
    def update(self,cid,sid,data,user):
        obj=self.survey(cid,sid,user,True)
        if obj.status!='DRAFT':raise BusinessRuleError('Solo se edita una encuesta en borrador')
        for k,v in data.model_dump(exclude_unset=True).items():setattr(obj,k,v)
        if obj.start_date and obj.end_date and obj.start_date>obj.end_date:raise BusinessRuleError('Rango de fechas inválido')
        try:self.db.commit();self.db.refresh(obj);return obj
        except IntegrityError:self.db.rollback();raise ConflictError('Slug duplicado')
    def deactivate(self,cid,sid,user):
        obj=self.survey(cid,sid,user,True)
        if obj.status=='ARCHIVED':raise BusinessRuleError('Encuesta archivada')
        obj.is_active=False;self.db.commit()
    def draft(self,cid,sid,user):
        obj=self.survey(cid,sid,user,True)
        if obj.status!='DRAFT':raise BusinessRuleError('La estructura solo se modifica en borrador')
        return obj
    def add_section(self,cid,sid,data,user):
        self.draft(cid,sid,user);obj=SurveySection(**data.model_dump(),survey_id=sid);self.db.add(obj);self.db.commit();self.db.refresh(obj);return obj
    def section(self,cid,sid,id,user):
        self.draft(cid,sid,user);obj=self.db.get(SurveySection,id)
        if not obj or obj.survey_id!=sid or not obj.is_active:raise NotFoundError('Sección no encontrada')
        return obj
    def update_section(self,cid,sid,id,data,user):
        obj=self.section(cid,sid,id,user)
        for k,v in data.model_dump(exclude_unset=True).items():setattr(obj,k,v)
        self.db.commit();self.db.refresh(obj);return obj
    def add_question(self,cid,sid,section_id,data,user):
        sec=self.section(cid,sid,section_id,user);values=data.model_dump()
        if values['question_type']=='SHORT_TEXT' and values['max_length'] is None:values['max_length']=250
        if values['question_type']=='LONG_TEXT' and values['max_length'] is None:values['max_length']=2000
        obj=SurveyQuestion(**values,survey_id=sid,section_id=sec.id);self.db.add(obj)
        try:self.db.commit();self.db.refresh(obj);return obj
        except IntegrityError:self.db.rollback();raise ConflictError('Código de pregunta duplicado')
    def question(self,cid,sid,id,user):
        self.draft(cid,sid,user);obj=self.db.get(SurveyQuestion,id)
        if not obj or obj.survey_id!=sid or not obj.is_active:raise NotFoundError('Pregunta no encontrada')
        return obj
    def update_question(self,cid,sid,id,data,user):
        obj=self.question(cid,sid,id,user)
        for k,v in data.model_dump(exclude_unset=True).items():setattr(obj,k,v)
        self.db.commit();self.db.refresh(obj);return obj
    def add_option(self,cid,sid,qid,data,user):
        q=self.question(cid,sid,qid,user)
        if q.question_type not in {'SINGLE_CHOICE','MULTIPLE_CHOICE'}:raise BusinessRuleError('Este tipo no acepta opciones')
        if data.is_other and not q.allow_other:raise BusinessRuleError('La pregunta no permite Otro')
        if data.is_other and self.db.scalar(select(SurveyOption).where(SurveyOption.question_id==qid,SurveyOption.is_other.is_(True),SurveyOption.is_active.is_(True))):raise ConflictError('Ya existe una opción Otro')
        obj=SurveyOption(**data.model_dump(),question_id=qid);self.db.add(obj)
        try:self.db.commit();self.db.refresh(obj);return obj
        except IntegrityError:self.db.rollback();raise ConflictError('Opción duplicada')
    def option(self,cid,sid,qid,id,user):
        self.question(cid,sid,qid,user);obj=self.db.get(SurveyOption,id)
        if not obj or obj.question_id!=qid or not obj.is_active:raise NotFoundError('Opción no encontrada')
        return obj
    def update_option(self,cid,sid,qid,id,data,user):
        obj=self.option(cid,sid,qid,id,user)
        for k,v in data.model_dump(exclude_unset=True).items():setattr(obj,k,v)
        if obj.is_other and not obj.question.allow_other:raise BusinessRuleError('La pregunta no permite Otro')
        self.db.commit();self.db.refresh(obj);return obj
    def publish(self,cid,sid,user):
        obj=self.draft(cid,sid,user);sections=list(self.db.scalars(select(SurveySection).where(SurveySection.survey_id==sid,SurveySection.is_active.is_(True))));questions=list(self.db.scalars(select(SurveyQuestion).where(SurveyQuestion.survey_id==sid,SurveyQuestion.is_active.is_(True)).options(selectinload(SurveyQuestion.options))))
        if not sections or not questions:raise BusinessRuleError('La encuesta requiere secciones y preguntas')
        for q in questions:
            options=list(self.db.scalars(select(SurveyOption).where(SurveyOption.question_id==q.id,SurveyOption.is_active.is_(True))))
            if q.question_type in {'SINGLE_CHOICE','MULTIPLE_CHOICE'} and len(options)<2:raise BusinessRuleError(f'La pregunta {q.code} requiere al menos dos opciones')
            if q.question_type=='MULTIPLE_CHOICE' and q.max_selections and q.max_selections>len(options):raise BusinessRuleError('Máximo de selecciones inválido')
        obj.status='PUBLISHED';obj.published_date=self.today();self.db.commit();self.db.refresh(obj);return obj
    def transition(self,cid,sid,user,target):
        obj=self.survey(cid,sid,user,True);allowed={'CLOSED':{'PUBLISHED'},'ARCHIVED':{'DRAFT','PUBLISHED','CLOSED'}}
        if obj.status not in allowed[target]:raise BusinessRuleError('Transición inválida')
        obj.status=target
        if target=='CLOSED':obj.closed_date=self.today()
        self.db.commit();self.db.refresh(obj);return obj
    def territory(self,campaign,s):
        self.ops.territory(campaign,s.parish_id,s.community_id,s.sector_id)
        if s.activity_id:
            a=self.db.get(TerritorialActivity,s.activity_id)
            if not a or a.campaign_id!=campaign.id or (a.parish_id,a.community_id,a.sector_id)!=(s.parish_id,s.community_id,s.sector_id):raise BusinessRuleError('Actividad o territorio inválido')
    def can_submit(self,user,cid,s):
        roles=self.roles(user)
        if self.access.admin(user) or roles.intersection(CAMPAIGN_EXECUTIVE_ROLES):return
        if 'TERRITORIAL_COORDINATOR' not in roles:raise PermissionError('Sin permiso para registrar respuestas')
        if not self.ops.territorial_access(user,cid,s.parish_id,s.community_id,s.sector_id):raise PermissionError('Sin acceso territorial')
    def digest(self,key):return hmac.new(settings.survey_submission_hmac_secret.encode(),key.encode(),hashlib.sha256).hexdigest()
    def validate_answer(self,q,raw):
        values=[raw.text_value,raw.integer_value,raw.decimal_value,raw.boolean_value,raw.rating_value];selected=list(dict.fromkeys(raw.selected_option_codes));provided=sum(x is not None for x in values)+bool(selected)
        if provided!=1:raise BusinessRuleError(f'Respuesta inválida para {q.code}')
        answer=SurveyAnswer(question_id=q.id)
        if q.question_type in {'SHORT_TEXT','LONG_TEXT'}:
            if raw.text_value is None:raise BusinessRuleError('Se esperaba texto')
            value=safe_text(raw.text_value);minimum=q.min_length or 0;maximum=q.max_length or (250 if q.question_type=='SHORT_TEXT' else 2000)
            if len(value)<minimum or len(value)>maximum:raise BusinessRuleError('Longitud de texto inválida')
            answer.text_value=value
        elif q.question_type=='INTEGER':
            if raw.integer_value is None or isinstance(raw.integer_value,bool):raise BusinessRuleError('Se esperaba entero')
            value=Decimal(raw.integer_value);answer.integer_value=raw.integer_value
            if q.min_value is not None and value<q.min_value or q.max_value is not None and value>q.max_value:raise BusinessRuleError('Valor fuera de rango')
        elif q.question_type=='DECIMAL':
            if raw.decimal_value is None:raise BusinessRuleError('Se esperaba decimal')
            value=raw.decimal_value;answer.decimal_value=value
            if q.min_value is not None and value<q.min_value or q.max_value is not None and value>q.max_value:raise BusinessRuleError('Valor fuera de rango')
        elif q.question_type=='YES_NO':
            if raw.boolean_value is None:raise BusinessRuleError('Se esperaba sí/no')
            answer.boolean_value=raw.boolean_value
        elif q.question_type=='RATING':
            if raw.rating_value is None or raw.rating_value<q.rating_min or raw.rating_value>q.rating_max:raise BusinessRuleError('Valoración fuera de rango')
            answer.rating_value=raw.rating_value
        else:
            options=list(self.db.scalars(select(SurveyOption).where(SurveyOption.question_id==q.id,SurveyOption.code.in_([x.upper() for x in selected]),SurveyOption.is_active.is_(True))))
            if len(options)!=len(selected):raise BusinessRuleError('Opción inválida')
            if q.question_type=='SINGLE_CHOICE' and len(options)!=1:raise BusinessRuleError('Seleccione una opción')
            if q.question_type=='MULTIPLE_CHOICE' and (len(options)<(q.min_selections or 0) or q.max_selections and len(options)>q.max_selections):raise BusinessRuleError('Cantidad de selecciones inválida')
            if raw.other_text:
                if not q.allow_other or not any(o.is_other for o in options):raise BusinessRuleError('Texto Otro no permitido')
                answer.other_text=safe_text(raw.other_text)
            answer.selected_options=options
        return answer
    def submit(self,cid,sid,data,user):
        campaign=self.campaign(cid,user);survey=self.survey(cid,sid,user)
        if survey.status!='PUBLISHED':raise BusinessRuleError('Encuesta no publicada')
        if survey.start_date and data.response_date<survey.start_date or survey.end_date and data.response_date>survey.end_date:raise BusinessRuleError('Fecha fuera del período')
        self.territory(campaign,data);self.can_submit(user,cid,data)
        questions=list(self.db.scalars(select(SurveyQuestion).join(SurveySection).where(SurveyQuestion.survey_id==sid,SurveyQuestion.is_active.is_(True),SurveySection.is_active.is_(True)).options(selectinload(SurveyQuestion.options))))
        raw={x.question_code.upper():x for x in data.answers}
        if len(raw)!=len(data.answers):raise ConflictError('Pregunta duplicada')
        missing=[q.code for q in questions if q.is_required and q.code not in raw]
        if missing:raise BusinessRuleError('Falta una respuesta obligatoria')
        if set(raw)-{q.code for q in questions}:raise BusinessRuleError('Pregunta inexistente')
        digest=self.digest(data.submission_key) if data.submission_key and not survey.allow_multiple_submissions else None
        if digest and self.db.scalar(select(SurveyResponse).where(SurveyResponse.survey_id==sid,SurveyResponse.submission_key_hash==digest)):raise ConflictError('Respuesta duplicada')
        obj=SurveyResponse(survey_id=sid,campaign_id=cid,response_date=data.response_date,parish_id=data.parish_id,community_id=data.community_id,sector_id=data.sector_id,activity_id=data.activity_id,source_channel=data.source_channel,age_range=data.age_range,submission_key_hash=digest,created_by_user_id=user.id);self.db.add(obj);self.db.flush()
        try:
            for q in questions:
                if q.code in raw:
                    answer=self.validate_answer(q,raw[q.code]);answer.response_id=obj.id;self.db.add(answer)
            self.db.commit();self.db.refresh(obj);return obj
        except Exception:self.db.rollback();raise
    def response_query(self,cid,sid,user,aggregated=False,**f):
        survey=self.survey(cid,sid,user);roles=self.roles(user)
        if 'CANDIDATE' in roles and not self.access.admin(user) and not aggregated:raise PermissionError('El candidato solo consulta agregados')
        conds=[SurveyResponse.survey_id==sid,SurveyResponse.campaign_id==cid]
        mapping={'parish_id':SurveyResponse.parish_id,'community_id':SurveyResponse.community_id,'sector_id':SurveyResponse.sector_id,'activity_id':SurveyResponse.activity_id,'source_channel':SurveyResponse.source_channel,'age_range':SurveyResponse.age_range,'is_valid':SurveyResponse.is_valid,'is_complete':SurveyResponse.is_complete}
        for k,col in mapping.items():
            if f.get(k) is not None:conds.append(col==f[k])
        if f.get('date_from'):conds.append(SurveyResponse.response_date>=f['date_from'])
        if f.get('date_to'):conds.append(SurveyResponse.response_date<=f['date_to'])
        rows=list(self.db.scalars(select(SurveyResponse).where(*conds).order_by(SurveyResponse.response_date.desc())))
        if not (self.access.admin(user) or roles.intersection({'CAMPAIGN_MANAGER','ANALYST','CANDIDATE'})):rows=[x for x in rows if self.ops.territorial_access(user,cid,x.parish_id,x.community_id,x.sector_id)]
        return rows
    def responses(self,cid,sid,user,page=1,size=20,**f):
        rows=self.response_query(cid,sid,user,**f);total=len(rows);return SurveyResponseListResponse(items=rows[(page-1)*size:page*size],page=page,page_size=size,total=total,total_pages=ceil(total/size) if total else 0)
    def response(self,cid,sid,rid,user):
        rows=self.response_query(cid,sid,user);obj=next((x for x in rows if x.id==rid),None)
        if not obj:raise NotFoundError('Respuesta no encontrada')
        answers=[]
        for a in obj.answers:
            q=self.db.get(SurveyQuestion,a.question_id);answers.append(SurveyAnswerRead(question_code=q.code,text_value=a.text_value,integer_value=a.integer_value,decimal_value=a.decimal_value,boolean_value=a.boolean_value,rating_value=a.rating_value,selected_option_codes=[o.code for o in a.selected_options],other_text=a.other_text))
        return {**SurveyResponseSummary.model_validate(obj).model_dump(),'answers':answers}
    def invalidate(self,cid,sid,rid,reason,user):
        self.campaign(cid,user,True);obj=self.response(cid,sid,rid,user);row=self.db.get(SurveyResponse,rid);row.is_valid=False;row.invalid_reason=safe_text(reason);self.db.commit();self.db.refresh(row);return row
    def results(self,cid,sid,user,**f):
        survey=self.survey(cid,sid,user);all_rows=self.response_query(cid,sid,user,aggregated=True,**f);valid=[r for r in all_rows if r.is_valid];questions=list(self.db.scalars(select(SurveyQuestion).where(SurveyQuestion.survey_id==sid,SurveyQuestion.is_active.is_(True)).options(selectinload(SurveyQuestion.options))))
        bypar=self.group(valid,'parish_id');bychan=self.group(valid,'source_channel');byage=self.group(valid,'age_range');qresults=[]
        for q in questions:
            answers=list(self.db.scalars(select(SurveyAnswer).join(SurveyResponse).where(SurveyAnswer.question_id==q.id,SurveyResponse.id.in_([r.id for r in valid])))) if valid else []
            result=SurveyQuestionResult(code=q.code,question_text=q.question_text,question_type=q.question_type,answered_count=len(answers))
            if q.question_type in {'SINGLE_CHOICE','MULTIPLE_CHOICE'}:
                for o in q.options:
                    count=sum(o in a.selected_options for a in answers);result.options.append(SurveyOptionResult(code=o.code,label=o.label,count=count,percentage=round(count*100/len(answers),2) if answers else None))
            elif q.question_type=='YES_NO':
                for val,label in [(True,'YES'),(False,'NO')]:
                    count=sum(a.boolean_value is val for a in answers);result.options.append(SurveyOptionResult(code=label,label='Sí' if val else 'No',count=count,percentage=round(count*100/len(answers),2) if answers else None))
            elif q.question_type in {'INTEGER','DECIMAL','RATING'}:
                vals=[Decimal(a.integer_value if q.question_type=='INTEGER' else a.decimal_value if q.question_type=='DECIMAL' else a.rating_value) for a in answers]
                result.numeric=SurveyNumericSummary(count=len(vals),average=sum(vals)/len(vals) if vals else None,minimum=min(vals) if vals else None,maximum=max(vals) if vals else None,median=Decimal(str(median(vals))) if vals else None,distribution={str(v):vals.count(v) for v in sorted(set(vals))} if q.question_type=='RATING' else None)
            else:result.text=SurveyTextSummary(count=len(answers),non_empty_count=sum(bool(a.text_value) for a in answers))
            qresults.append(result)
        return SurveyResultsRead(survey_id=sid,title=survey.title,date_from=f.get('date_from'),date_to=f.get('date_to'),total_responses=len(all_rows),valid_responses=len(valid),invalid_responses=len(all_rows)-len(valid),complete_responses=sum(r.is_complete for r in valid),responses_by_parish=bypar,responses_by_channel=bychan,responses_by_age_range=byage,question_results=qresults)
    @staticmethod
    def group(rows,field):
        values={getattr(x,field) for x in rows};return [{'value':str(v) if v is not None else 'NOT_PROVIDED','count':sum(getattr(x,field)==v for x in rows)} for v in values]
    def participation(self,cid,sid,user,**f):
        rows=self.response_query(cid,sid,user,aggregated=True,**f);valid=[x for x in rows if x.is_valid];survey=self.survey(cid,sid,user);campaign=self.db.get(Campaign,cid);parishes=list(self.db.scalars(select(Parish).where(Parish.canton_id==campaign.canton_id,Parish.is_active.is_(True))));roles=self.roles(user)
        if not (self.access.admin(user) or roles.intersection({'CANDIDATE','CAMPAIGN_MANAGER','ANALYST'})):parishes=[p for p in parishes if self.ops.territorial_access(user,cid,p.id)]
        counts={p.id:sum(x.parish_id==p.id and x.is_valid for x in rows) for p in parishes};threshold=settings.survey_min_aggregate_responses
        return SurveyParticipationSummary(total_responses=len(rows),valid_responses=len(valid),invalid_responses=len(rows)-len(valid),complete_responses=sum(x.is_complete for x in valid),responses_by_parish=self.group(valid,'parish_id'),responses_by_channel=self.group(valid,'source_channel'),responses_by_age_range=self.group(valid,'age_range'),responses_by_date=self.group(valid,'response_date'),territories_without_responses=[{'id':p.id,'name':p.name} for p in parishes if counts[p.id]==0],territories_below_threshold=[{'id':p.id,'name':p.name,'response_count':counts[p.id]} for p in parishes if 0<counts[p.id]<threshold])
    def comparison(self,cid,sid,user,level,question_code,**f):
        if level not in {'PARISH','COMMUNITY','SECTOR'}:raise BusinessRuleError('Nivel inválido')
        q=self.db.scalar(select(SurveyQuestion).where(SurveyQuestion.survey_id==sid,SurveyQuestion.code==question_code.upper(),SurveyQuestion.is_active.is_(True)))
        if not q:raise NotFoundError('Pregunta no encontrada')
        if q.question_type in {'SHORT_TEXT','LONG_TEXT'}:raise BusinessRuleError('Texto abierto no es comparable')
        rows=[x for x in self.response_query(cid,sid,user,aggregated=True,**f) if x.is_valid];field={'PARISH':'parish_id','COMMUNITY':'community_id','SECTOR':'sector_id'}[level];threshold=settings.survey_min_aggregate_responses;items=[]
        for value in {getattr(x,field) for x in rows if getattr(x,field) is not None}:
            grouped=[x for x in rows if getattr(x,field)==value];suppressed=len(grouped)<threshold
            model={'PARISH':Parish,'COMMUNITY':Community,'SECTOR':Sector}[level];territory=self.db.get(model,value);detail=None
            if not suppressed:
                scoped={**f,field:value};aggregate=self.results(cid,sid,user,**scoped);detail=next((x.model_dump(mode='json') for x in aggregate.question_results if x.code==q.code),None)
            items.append(SurveyTerritorialResult(territory_id=str(value),territory_name=territory.name if territory else str(value),response_count=len(grouped),suppressed=suppressed,result=detail))
        return SurveyComparisonRead(level=level,question_code=q.code,items=items)
    def export(self,cid,sid,user,**f):
        if not (self.access.admin(user) or self.roles(user).intersection(CAMPAIGN_EXECUTIVE_ROLES|{'ANALYST'})):raise PermissionError('Sin permiso de exportación')
        return {'survey':self.detail(cid,sid,user),'responses':[self.response(cid,sid,x.id,user) for x in self.response_query(cid,sid,user,**f)]}
