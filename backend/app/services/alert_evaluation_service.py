import hashlib
from datetime import date
from sqlalchemy import func,select
from app.core.config import settings
from app.models.alerts import AlertRule,OperationalAlert
from app.models.historical import DataImportJob,DataSource,DemographicObservation,ElectoralCandidateResult,ElectoralContest,ElectoralGeography,ElectoralTurnout
from app.models.operational import ActivityEvidence,ActivityParticipantSummary,Commitment,TerritorialActivity
from app.models.survey import Survey,SurveyResponse
from app.models.territory import Canton,Parish

class AlertEvaluationService:
    TITLES={
      "OVERDUE_COMMITMENT":("Compromiso vencido","Existe un compromiso pendiente cuya fecha límite fue superada."),"COMMITMENT_WITHOUT_RESPONSIBLE":("Compromiso sin responsable","Existe un compromiso activo sin responsable asignado."),"COMMITMENT_WITHOUT_DUE_DATE":("Compromiso sin fecha límite","Existe un compromiso activo sin fecha límite."),"PAST_PLANNED_ACTIVITY":("Actividad planificada con fecha pasada","Existe una actividad planificada cuya fecha ya pasó."),"ACTIVITY_WITHOUT_RESPONSIBLE":("Actividad sin responsable","Existe una actividad activa sin responsable asignado."),"ACTIVITY_WITHOUT_LOCATION":("Actividad sin ubicación","Existe una actividad activa sin ubicación geográfica."),"ACTIVITY_WITHOUT_PARTICIPANT_SUMMARY":("Actividad sin resumen de participantes","Existe una actividad completada sin resumen agregado de participantes."),"TERRITORY_WITHOUT_COMPLETED_ACTIVITY":("Territorio sin actividad completada","Un territorio autorizado no registra actividades completadas en el período configurado."),"SURVEY_WITHOUT_RESPONSES":("Encuesta sin respuestas","Existe una encuesta publicada sin respuestas válidas."),"SURVEY_LOW_SAMPLE":("Encuesta con muestra baja","Una encuesta tiene menos respuestas válidas que el mínimo configurado."),"SURVEY_PRIVACY_SUPPRESSED":("Resultado suprimido por privacidad","Existen segmentos de encuesta bajo el umbral mínimo de privacidad."),"FAILED_DATA_IMPORT":("Importación fallida","Existe una importación de datos que terminó con error."),"UNMAPPED_ELECTORAL_GEOGRAPHY":("Geografía electoral sin mapear","Existe una geografía electoral sin correspondencia territorial."),"CONTEST_WITHOUT_RESULTS":("Contienda sin resultados","Existe una contienda electoral sin resultados importados."),"CONTEST_WITHOUT_TURNOUT":("Contienda sin participación","Existe una contienda electoral sin participación importada."),"MISSING_CANTON_GEOMETRY":("Geometría cantonal faltante","El cantón de la campaña no dispone de geometría."),"MISSING_PARISH_GEOMETRY":("Geometría parroquial faltante","Existe una parroquia activa sin geometría."),"INVALID_GEOMETRY":("Geometría inválida","Existen geometrías que requieren revisión técnica."),"INACTIVE_DATA_SOURCE":("Fuente de datos inactiva","Existe una fuente oficial inactiva."),"STALE_DEMOGRAPHIC_DATA":("Datos demográficos antiguos","Las observaciones demográficas disponibles superan la antigüedad configurada."),"MISSING_DEMOGRAPHIC_INDICATOR":("Indicador demográfico faltante","No existen observaciones demográficas agregadas para el ámbito de la campaña.")}
    def __init__(self,db):self.db=db
    def _item(self,rule,resource_type,resource_id,parish_id,evidence):
        title,message=self.TITLES[rule.condition_type];raw=f"{rule.code}|{resource_type}|{resource_id or parish_id or 'campaign'}";return {"fingerprint":hashlib.sha256(raw.encode()).hexdigest(),"title":title,"message":message,"resource_type":resource_type,"resource_id":resource_id,"parish_id":parish_id,"evidence":evidence}
    def evaluate_rule(self,rule,campaign,as_of):
        c=rule.condition_type;items=[]
        if c in {"OVERDUE_COMMITMENT","COMMITMENT_WITHOUT_RESPONSIBLE","COMMITMENT_WITHOUT_DUE_DATE"}:
            q=select(Commitment).where(Commitment.campaign_id==campaign.id,Commitment.is_active.is_(True))
            if c=="OVERDUE_COMMITMENT":q=q.where(Commitment.due_date<as_of,Commitment.status.in_(["PENDING","IN_PROGRESS"]))
            elif c=="COMMITMENT_WITHOUT_RESPONSIBLE":q=q.where(Commitment.responsible_user_id.is_(None),Commitment.status.in_(["PENDING","IN_PROGRESS"]))
            else:q=q.where(Commitment.due_date.is_(None),Commitment.status.in_(["PENDING","IN_PROGRESS"]))
            for x in self.db.scalars(q):items.append(self._item(rule,"COMMITMENT",x.id,x.parish_id,{"due_date":x.due_date.isoformat() if x.due_date else None,"status":x.status,"days_overdue":(as_of-x.due_date).days if x.due_date and x.due_date<as_of else 0}))
        elif c in {"PAST_PLANNED_ACTIVITY","ACTIVITY_WITHOUT_RESPONSIBLE","ACTIVITY_WITHOUT_LOCATION","ACTIVITY_WITHOUT_PARTICIPANT_SUMMARY"}:
            q=select(TerritorialActivity).where(TerritorialActivity.campaign_id==campaign.id,TerritorialActivity.is_active.is_(True))
            if c=="PAST_PLANNED_ACTIVITY":q=q.where(TerritorialActivity.status=="PLANNED",TerritorialActivity.activity_date<as_of)
            elif c=="ACTIVITY_WITHOUT_RESPONSIBLE":q=q.where(TerritorialActivity.responsible_user_id.is_(None))
            elif c=="ACTIVITY_WITHOUT_LOCATION":q=q.where(TerritorialActivity.location.is_(None))
            else:q=q.outerjoin(ActivityParticipantSummary,ActivityParticipantSummary.activity_id==TerritorialActivity.id).where(TerritorialActivity.status=="COMPLETED",ActivityParticipantSummary.id.is_(None))
            for x in self.db.scalars(q):items.append(self._item(rule,"ACTIVITY",x.id,x.parish_id,{"activity_date":x.activity_date.isoformat(),"status":x.status}))
        elif c=="TERRITORY_WITHOUT_COMPLETED_ACTIVITY":
            days=int(rule.configuration.get("inactivity_days",settings.alert_default_inactivity_days));cutoff=as_of-__import__('datetime').timedelta(days=days)
            q=select(Parish).where(Parish.canton_id==campaign.canton_id,Parish.is_active.is_(True),~select(TerritorialActivity.id).where(TerritorialActivity.campaign_id==campaign.id,TerritorialActivity.parish_id==Parish.id,TerritorialActivity.status=="COMPLETED",TerritorialActivity.is_active.is_(True),TerritorialActivity.activity_date>=cutoff).exists())
            for p in self.db.scalars(q):items.append(self._item(rule,"PARISH",None,p.id,{"inactivity_days":days,"cutoff_date":cutoff.isoformat()}))
        elif c in {"SURVEY_WITHOUT_RESPONSES","SURVEY_LOW_SAMPLE","SURVEY_PRIVACY_SUPPRESSED"}:
            threshold=int(rule.configuration.get("minimum_valid_responses",settings.survey_min_aggregate_responses));q=select(Survey).where(Survey.campaign_id==campaign.id,Survey.status.in_(["PUBLISHED","CLOSED"]),Survey.is_active.is_(True))
            for survey in self.db.scalars(q):
                count=self.db.scalar(select(func.count()).select_from(SurveyResponse).where(SurveyResponse.survey_id==survey.id,SurveyResponse.is_valid.is_(True))) or 0
                match=count==0 if c=="SURVEY_WITHOUT_RESPONSES" else 0<count<threshold
                if match:items.append(self._item(rule,"SURVEY",survey.id,None,{"valid_responses":count,"minimum":threshold,"suppressed":c=="SURVEY_PRIVACY_SUPPRESSED"}))
        elif c=="FAILED_DATA_IMPORT":
            count=self.db.scalar(select(func.count()).select_from(DataImportJob).where(DataImportJob.status.in_(["FAILED","REJECTED"]))) or 0
            if count:items.append(self._item(rule,"DATA_IMPORT",None,None,{"failed_imports":count}))
        elif c=="UNMAPPED_ELECTORAL_GEOGRAPHY":
            count=self.db.scalar(select(func.count()).select_from(ElectoralGeography).where(ElectoralGeography.canton_id==campaign.canton_id,ElectoralGeography.is_mapped.is_(False))) or 0
            if count:items.append(self._item(rule,"ELECTORAL_GEOGRAPHY",None,None,{"unmapped_geographies":count}))
        elif c in {"CONTEST_WITHOUT_RESULTS","CONTEST_WITHOUT_TURNOUT"}:
            model=ElectoralCandidateResult if c=="CONTEST_WITHOUT_RESULTS" else ElectoralTurnout
            q=select(ElectoralContest).where(ElectoralContest.canton_id==campaign.canton_id,ElectoralContest.office_type==campaign.office_type,ElectoralContest.is_active.is_(True),~select(model.id).where(model.electoral_contest_id==ElectoralContest.id).exists())
            for x in self.db.scalars(q):items.append(self._item(rule,"ELECTORAL_CONTEST",x.id,x.parish_id,{"office_type":x.office_type}))
        elif c=="MISSING_CANTON_GEOMETRY":
            canton=self.db.get(Canton,campaign.canton_id)
            if canton and canton.geometry is None:items.append(self._item(rule,"CANTON",None,None,{"canton_id":campaign.canton_id}))
        elif c in {"MISSING_PARISH_GEOMETRY","INVALID_GEOMETRY"}:
            q=select(Parish).where(Parish.canton_id==campaign.canton_id,Parish.is_active.is_(True),Parish.geometry.is_(None))
            for p in self.db.scalars(q):items.append(self._item(rule,"PARISH",None,p.id,{"geometry_status":"MISSING" if c=="MISSING_PARISH_GEOMETRY" else "UNAVAILABLE"}))
        elif c=="INACTIVE_DATA_SOURCE":
            count=self.db.scalar(select(func.count()).select_from(DataSource).where(DataSource.is_active.is_(False))) or 0
            if count:items.append(self._item(rule,"DATA_SOURCE",None,None,{"inactive_sources":count}))
        elif c in {"STALE_DEMOGRAPHIC_DATA","MISSING_DEMOGRAPHIC_INDICATOR"}:
            max_year=self.db.scalar(select(func.max(DemographicObservation.reference_year)).where(DemographicObservation.canton_id==campaign.canton_id,DemographicObservation.is_active.is_(True)))
            maximum=int(rule.configuration.get("maximum_age_days",settings.alert_default_data_stale_days));stale=max_year is not None and (as_of.year-max_year)*365>maximum
            if (c=="MISSING_DEMOGRAPHIC_INDICATOR" and max_year is None) or (c=="STALE_DEMOGRAPHIC_DATA" and stale):items.append(self._item(rule,"DEMOGRAPHICS",None,None,{"latest_reference_year":max_year,"maximum_age_days":maximum}))
        return items
