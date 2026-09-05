import hashlib
from datetime import date,datetime,timedelta,timezone
from sqlalchemy import func,select
from app.core.config import settings
from app.models.alerts import AlertRule,OperationalAlert
from app.models.election_day import ElectionDayAssignment,ElectionDayDocument,ElectionDayIncident,ElectionDayOperation,ElectoralBoard,PollingPlace
from app.models.historical import DataImportJob,DataSource,DatasetVersion,DemographicObservation,ElectoralCandidateResult,ElectoralContest,ElectoralGeography,ElectoralMilestone,ElectoralTurnout
from app.models.operational import ActivityEvidence,ActivityParticipantSummary,CitizenNeed,TerritorialActivity
from app.models.reports import ReportRun
from app.models.survey import Survey,SurveyResponse
from app.models.survey_study import SurveyStudy
from app.models.territory import Canton,Parish
from app.reports.theme_catalog import THEME_KEYWORDS,THEME_LABELS,theme_match
from app.services.survey_study_service import studies_are_comparable

class AlertEvaluationService:
    TITLES={
      "ACTIVITY_UPCOMING":("Actividad próxima","Existe una actividad aprobada próxima."),"CRITICAL_NEED_UNASSIGNED":("Necesidad crítica sin responsable","Existe una necesidad crítica abierta sin responsable."),"NEED_REVIEW_STALE":("Necesidad demasiado tiempo en revisión","Existe una necesidad que requiere actualización de revisión."),
      "PAST_PLANNED_ACTIVITY":("Actividad planificada con fecha pasada","Existe una actividad planificada cuya fecha ya pasó."),"ACTIVITY_WITHOUT_RESPONSIBLE":("Actividad sin responsable","Existe una actividad activa sin responsable asignado."),"ACTIVITY_WITHOUT_LOCATION":("Actividad sin ubicación","Existe una actividad activa sin ubicación geográfica."),"ACTIVITY_WITHOUT_PARTICIPANT_SUMMARY":("Actividad sin resumen de participantes","Existe una actividad completada sin resumen agregado de participantes."),"TERRITORY_WITHOUT_COMPLETED_ACTIVITY":("Territorio sin actividad completada","Un territorio autorizado no registra actividades completadas en el período configurado."),"SURVEY_WITHOUT_RESPONSES":("Encuesta sin respuestas","Existe una encuesta publicada sin respuestas válidas."),"SURVEY_LOW_SAMPLE":("Encuesta con muestra baja","Una encuesta tiene menos respuestas válidas que el mínimo configurado."),"SURVEY_PRIVACY_SUPPRESSED":("Resultado suprimido por privacidad","Existen segmentos de encuesta bajo el umbral mínimo de privacidad."),"FAILED_DATA_IMPORT":("Importación fallida","Existe una importación de datos que terminó con error."),"UNMAPPED_ELECTORAL_GEOGRAPHY":("Geografía electoral sin mapear","Existe una geografía electoral sin correspondencia territorial."),"CONTEST_WITHOUT_RESULTS":("Contienda sin resultados","Existe una contienda electoral sin resultados importados."),"CONTEST_WITHOUT_TURNOUT":("Contienda sin participación","Existe una contienda electoral sin participación importada."),"MISSING_CANTON_GEOMETRY":("Geometría cantonal faltante","El cantón de la campaña no dispone de geometría."),"MISSING_PARISH_GEOMETRY":("Geometría parroquial faltante","Existe una parroquia activa sin geometría."),"INVALID_GEOMETRY":("Geometría inválida","Existen geometrías que requieren revisión técnica."),"INACTIVE_DATA_SOURCE":("Fuente de datos inactiva","Existe una fuente oficial inactiva."),"STALE_DEMOGRAPHIC_DATA":("Datos demográficos antiguos","Las observaciones demográficas disponibles superan la antigüedad configurada."),"MISSING_DEMOGRAPHIC_INDICATOR":("Indicador demográfico faltante","No existen observaciones demográficas agregadas para el ámbito de la campaña.")}
    TITLES.update({
      "ACTIVITY_PENDING_APPROVAL":("Actividad pendiente de aprobación","Existe una actividad esperando aprobación."),
      "ACTIVITY_SUSPENDED":("Actividad suspendida","Existe una actividad aprobada que fue suspendida."),
      "UPCOMING_OFFICIAL_MILESTONE":("Hito electoral próximo","Se aproxima un hito oficial del proceso electoral."),
      "DATASET_UPDATE":("Nueva versión de datos disponible","Se activó una nueva versión de un conjunto de datos oficial."),
      "CAMPAIGN_WITHOUT_ACTIVE_ROLL":("Campaña sin padrón vigente","No existe una versión activa del registro electoral."),
      "SURVEY_WITHOUT_METHODOLOGY":("Estudio sin metodología","Existe un estudio publicado sin metodología de muestreo registrada."),
      "DATA_SOURCE_WITHOUT_REFERENCE_DATE":("Fuente sin fecha de referencia","Existe una fuente oficial activa sin fecha de referencia."),
      "ACTIVITY_COMPLETED_WITHOUT_EVIDENCE":("Actividad realizada sin evidencia","Existe una actividad completada sin evidencia adjunta."),
      "NEEDS_TOPIC_RECURRENCE":("Tema recurrente en registros territoriales","Un tema aparece de forma recurrente en necesidades registradas recientemente."),
      "REPORT_DATA_UPDATED_SINCE_GENERATION":("Información más reciente disponible","Existe información oficial o de encuestas más reciente que la utilizada en un informe generado."),
      "SURVEY_COMPARISON_CHANGE":("Nueva medición comparable disponible","Existe una nueva medición comparable disponible para esta pregunta."),
      "ELECTION_PLACE_UNCOVERED":("Recinto sin cobertura","Existe un recinto electoral sin personal asignado en la jornada activa."),
      "BOARD_UNCOVERED":("Junta sin cobertura","Existe una junta receptora del voto sin delegado asignado en la jornada activa."),
      "ASSIGNED_PERSON_NOT_CHECKED_IN":("Personal asignado sin confirmar presencia","Existe personal asignado que aún no confirma su presencia transcurrido el umbral operativo de la jornada."),
      "OPEN_ELECTION_INCIDENT":("Incidencia de jornada abierta","Existe una incidencia de jornada sin resolver."),
      "BOARD_DOCUMENT_MISSING":("Documentación de junta pendiente","Existe una junta sin copia de acta recibida."),
      "OFFLINE_SYNC_FAILURE":("Registro sincronizado con retraso","Un registro offline de jornada se sincronizó con un retraso significativo respecto a su creación en el dispositivo."),
    })
    def __init__(self,db):self.db=db
    @staticmethod
    def _study_canton_territory(study):
        return next((t for t in study.territories if t.parish_id is None),None) or (study.territories[0] if study.territories else None)
    def _survey_comparison_summary(self,older,newer):
        # Comparación estrictamente aritmética (§5): no se afirma significancia
        # estadística; solo se describe la diferencia observada entre dos
        # mediciones ya determinadas comparables por studies_are_comparable.
        question_code=newer.question_code
        older_territory=self._study_canton_territory(older);newer_territory=self._study_canton_territory(newer)
        if not older_territory or not newer_territory:return {"question_code":question_code,"comparable_result":False}
        older_options={o.code:o for o in older.options if o.question_code==question_code}
        newer_options={o.code:o for o in newer.options if o.question_code==question_code}
        shared=set(older_options)&set(newer_options)
        if not shared:return {"question_code":question_code,"comparable_result":False}
        older_by_option={r.option_id:r for r in older_territory.results};newer_by_option={r.option_id:r for r in newer_territory.results}
        best=None
        for code in shared:
            o_result=older_by_option.get(older_options[code].id);n_result=newer_by_option.get(newer_options[code].id)
            if not o_result or not n_result:continue
            previous=float(o_result.percentage);current=float(n_result.percentage)
            candidate={"option_code":code,"option_label":newer_options[code].label,"previous_percentage":previous,"new_percentage":current,"difference_points":round((current-previous)*100,2)}
            if best is None or candidate["new_percentage"]>best["new_percentage"]:best=candidate
        if best is None:return {"question_code":question_code,"comparable_result":False}
        return {"question_code":question_code,"comparable_result":True,**best}
    def _item(self,rule,resource_type,resource_id,parish_id,evidence):
        title,message=self.TITLES[rule.condition_type];raw=f"{rule.code}|{resource_type}|{resource_id or parish_id or 'campaign'}";return {"fingerprint":hashlib.sha256(raw.encode()).hexdigest(),"title":title,"message":message,"resource_type":resource_type,"resource_id":resource_id,"parish_id":parish_id,"evidence":evidence}
    def evaluate_rule(self,rule,campaign,as_of):
        c=rule.condition_type;items=[]
        if c=="ACTIVITY_UPCOMING":
            days=int(rule.configuration.get("days_ahead",7));q=select(TerritorialActivity).where(TerritorialActivity.campaign_id==campaign.id,TerritorialActivity.approval_status=="APPROVED",TerritorialActivity.status=="PLANNED",TerritorialActivity.activity_date.between(as_of,as_of+timedelta(days=days)),TerritorialActivity.is_active.is_(True))
            for x in self.db.scalars(q):items.append(self._item(rule,"ACTIVITY",x.id,x.parish_id,{"activity_date":x.activity_date.isoformat(),"days_until":(x.activity_date-as_of).days}))
        elif c in {"CRITICAL_NEED_UNASSIGNED","NEED_REVIEW_STALE"}:
            q=select(CitizenNeed).where(CitizenNeed.campaign_id==campaign.id,CitizenNeed.is_active.is_(True))
            if c=="CRITICAL_NEED_UNASSIGNED":q=q.where(CitizenNeed.urgency=="CRITICAL",CitizenNeed.assigned_to_user_id.is_(None),CitizenNeed.status.in_(["REPORTED","UNDER_REVIEW","VALIDATED"]))
            else:q=q.where(CitizenNeed.status=="UNDER_REVIEW",CitizenNeed.updated_at<as_of-timedelta(days=int(rule.configuration.get("days_in_review",7))))
            for x in self.db.scalars(q):items.append(self._item(rule,"NEED",x.id,x.parish_id,{"status":x.status,"urgency":x.urgency}))
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
        elif c=="ACTIVITY_PENDING_APPROVAL":
            q=select(TerritorialActivity).where(TerritorialActivity.campaign_id==campaign.id,TerritorialActivity.approval_status=="PENDING_APPROVAL",TerritorialActivity.is_active.is_(True))
            for x in self.db.scalars(q):items.append(self._item(rule,"ACTIVITY",x.id,x.parish_id,{"activity_date":x.activity_date.isoformat()}))
        elif c=="ACTIVITY_SUSPENDED":
            q=select(TerritorialActivity).where(TerritorialActivity.campaign_id==campaign.id,TerritorialActivity.status=="SUSPENDED",TerritorialActivity.is_active.is_(True))
            for x in self.db.scalars(q):items.append(self._item(rule,"ACTIVITY",x.id,x.parish_id,{"reason":x.suspension_reason}))
        elif c=="UPCOMING_OFFICIAL_MILESTONE":
            days=int(rule.configuration.get("days_ahead",7));processes=select(ElectoralContest.electoral_process_id).where(ElectoralContest.canton_id==campaign.canton_id,ElectoralContest.office_type==campaign.office_type)
            q=select(ElectoralMilestone).where(ElectoralMilestone.electoral_process_id.in_(processes),ElectoralMilestone.status=="ACTIVE",func.date(ElectoralMilestone.starts_at).between(as_of,as_of+timedelta(days=days)))
            for x in self.db.scalars(q):items.append(self._item(rule,"ELECTORAL_MILESTONE",x.id,None,{"title":x.title,"starts_at":x.starts_at.isoformat(),"days_until":(x.starts_at.date()-as_of).days}))
        elif c=="DATASET_UPDATE":
            days=int(rule.configuration.get("lookback_days",7));q=select(DatasetVersion).where(DatasetVersion.dataset_type=="CNE_ELECTORAL_ROLL_SNAPSHOT",DatasetVersion.status=="ACTIVE",DatasetVersion.activated_at.isnot(None),func.date(DatasetVersion.activated_at)>=as_of-timedelta(days=days))
            for x in self.db.scalars(q):items.append(self._item(rule,"DATASET_VERSION",x.id,None,{"version_label":x.version_label,"activated_at":x.activated_at.isoformat()}))
        elif c=="CAMPAIGN_WITHOUT_ACTIVE_ROLL":
            has_active=self.db.scalar(select(func.count()).select_from(DatasetVersion).where(DatasetVersion.dataset_type=="CNE_ELECTORAL_ROLL_SNAPSHOT",DatasetVersion.status=="ACTIVE")) or 0
            if not has_active:items.append(self._item(rule,"CAMPAIGN",None,None,{}))
        elif c=="SURVEY_WITHOUT_METHODOLOGY":
            q=select(SurveyStudy).where(SurveyStudy.campaign_id==campaign.id,SurveyStudy.status=="PUBLISHED",(SurveyStudy.sampling_method.is_(None))|(SurveyStudy.sampling_method==""))
            for x in self.db.scalars(q):items.append(self._item(rule,"SURVEY_STUDY",x.id,None,{"name":x.name}))
        elif c=="DATA_SOURCE_WITHOUT_REFERENCE_DATE":
            count=self.db.scalar(select(func.count()).select_from(DataSource).where(DataSource.is_active.is_(True),DataSource.is_official.is_(True),DataSource.reference_date.is_(None))) or 0
            if count:items.append(self._item(rule,"DATA_SOURCE",None,None,{"sources_without_reference_date":count}))
        elif c=="ACTIVITY_COMPLETED_WITHOUT_EVIDENCE":
            q=select(TerritorialActivity).where(TerritorialActivity.campaign_id==campaign.id,TerritorialActivity.status=="COMPLETED",TerritorialActivity.is_active.is_(True),~select(ActivityEvidence.id).where(ActivityEvidence.activity_id==TerritorialActivity.id,ActivityEvidence.is_active.is_(True)).exists())
            for x in self.db.scalars(q):items.append(self._item(rule,"ACTIVITY",x.id,x.parish_id,{"activity_date":x.activity_date.isoformat()}))
        elif c=="NEEDS_TOPIC_RECURRENCE":
            days=int(rule.configuration.get("lookback_days",7));minimum=int(rule.configuration.get("minimum_count",3));cutoff=as_of-timedelta(days=days)
            q=select(CitizenNeed).where(CitizenNeed.campaign_id==campaign.id,CitizenNeed.is_active.is_(True),CitizenNeed.reported_date>=cutoff,CitizenNeed.reported_date<=as_of)
            rows=list(self.db.scalars(q))
            for theme in THEME_KEYWORDS:
                if theme=="OTROS":continue
                matches=[n for n in rows if theme_match(theme,n.title,getattr(n,"description",None))]
                if len(matches)>=minimum:
                    # El tema, no un recurso individual, distingue el fingerprint: se
                    # codifica en resource_type porque resource_id es un UUID y no
                    # admite el código de tema como valor.
                    items.append(self._item(rule,f"NEEDS_THEME_{theme}",None,None,{"theme":theme,"theme_label":THEME_LABELS.get(theme,theme),"count":len(matches),"lookback_days":days}))
        elif c=="REPORT_DATA_UPDATED_SINCE_GENERATION":
            runs=list(self.db.scalars(select(ReportRun).where(ReportRun.campaign_id==campaign.id,ReportRun.status=="COMPLETED")))
            if runs:
                latest_roll=self.db.scalar(select(func.max(DatasetVersion.activated_at)).where(DatasetVersion.dataset_type=="CNE_ELECTORAL_ROLL_SNAPSHOT",DatasetVersion.status=="ACTIVE"))
                latest_survey=self.db.scalar(select(func.max(SurveyStudy.publication_date)).where(SurveyStudy.campaign_id==campaign.id,SurveyStudy.status=="PUBLISHED"))
                for run in runs:
                    if run.finished_at is None:continue
                    finished_date=run.finished_at.date()
                    reasons=[]
                    if latest_roll and latest_roll.date()>finished_date:reasons.append(f"nuevo corte de padrón ({latest_roll.date().isoformat()})")
                    if latest_survey and latest_survey>finished_date:reasons.append(f"nueva encuesta publicada ({latest_survey.isoformat()})")
                    if reasons:items.append(self._item(rule,"REPORT_RUN",run.id,None,{"reasons":reasons,"generated_at":finished_date.isoformat()}))
        elif c=="SURVEY_COMPARISON_CHANGE":
            studies=list(self.db.scalars(select(SurveyStudy).where(SurveyStudy.campaign_id==campaign.id,SurveyStudy.status=="PUBLISHED").order_by(SurveyStudy.fieldwork_end_date.asc())))
            for index,newer in enumerate(studies):
                # §7: compara contra la medición inmediatamente anterior compatible,
                # no necesariamente la primera de la serie (V1).
                candidates=[s for s in studies[:index] if studies_are_comparable(newer,s)]
                if not candidates:continue
                older=max(candidates,key=lambda s:s.fieldwork_end_date)
                summary=self._survey_comparison_summary(older,newer)
                items.append(self._item(rule,"SURVEY_STUDY",newer.id,None,{"previous_study_id":str(older.id),"previous_study_name":older.name,"previous_fieldwork_end_date":older.fieldwork_end_date.isoformat(),"new_study_id":str(newer.id),"new_study_name":newer.name,"new_fieldwork_end_date":newer.fieldwork_end_date.isoformat(),**summary}))
        elif c in {"ELECTION_PLACE_UNCOVERED","BOARD_UNCOVERED","ASSIGNED_PERSON_NOT_CHECKED_IN","OPEN_ELECTION_INCIDENT","BOARD_DOCUMENT_MISSING","OFFLINE_SYNC_FAILURE"}:
            op=self.db.scalar(select(ElectionDayOperation).where(ElectionDayOperation.campaign_id==campaign.id,ElectionDayOperation.status=="ACTIVE"))
            if not op:return items
            places=list(self.db.scalars(select(PollingPlace).where(PollingPlace.electoral_process_id==op.electoral_process_id,PollingPlace.canton_id==campaign.canton_id,PollingPlace.is_active.is_(True))))
            place_ids=[p.id for p in places];place_by_id={p.id:p for p in places}
            boards=list(self.db.scalars(select(ElectoralBoard).where(ElectoralBoard.polling_place_id.in_(place_ids),ElectoralBoard.is_active.is_(True)))) if place_ids else []
            assignments=list(self.db.scalars(select(ElectionDayAssignment).where(ElectionDayAssignment.operation_id==op.id,ElectionDayAssignment.status!="REPLACED")))
            if c=="ELECTION_PLACE_UNCOVERED":
                covered={a.polling_place_id for a in assignments}
                for p in places:
                    if p.id not in covered:items.append(self._item(rule,"POLLING_PLACE",p.id,p.parish_id,{"polling_place_name":p.name}))
            elif c=="BOARD_UNCOVERED":
                covered={a.board_id for a in assignments if a.board_id}
                for b in boards:
                    if b.id not in covered:items.append(self._item(rule,"ELECTORAL_BOARD",b.id,place_by_id[b.polling_place_id].parish_id,{"board_code":b.official_code,"polling_place_name":place_by_id[b.polling_place_id].name}))
            elif c=="ASSIGNED_PERSON_NOT_CHECKED_IN":
                if op.opened_at:
                    grace=int(rule.configuration.get("grace_minutes",60));threshold=op.opened_at+timedelta(minutes=grace)
                    if datetime.now(timezone.utc)>=threshold:
                        for a in assignments:
                            if a.status in {"ASSIGNED","CONFIRMED"}:
                                place=place_by_id.get(a.polling_place_id)
                                items.append(self._item(rule,"ELECTION_DAY_ASSIGNMENT",a.id,place.parish_id if place else None,{"assignment_role":a.assignment_role,"grace_minutes":grace}))
            elif c=="OPEN_ELECTION_INCIDENT":
                for i in self.db.scalars(select(ElectionDayIncident).where(ElectionDayIncident.operation_id==op.id,ElectionDayIncident.status!="RESOLVED",ElectionDayIncident.is_active.is_(True))):
                    place=place_by_id.get(i.polling_place_id)
                    items.append(self._item(rule,"ELECTION_DAY_INCIDENT",i.id,place.parish_id if place else None,{"category":i.category,"status":i.status}))
            elif c=="BOARD_DOCUMENT_MISSING":
                documented={d.board_id for d in self.db.scalars(select(ElectionDayDocument).where(ElectionDayDocument.operation_id==op.id,ElectionDayDocument.is_active.is_(True),ElectionDayDocument.document_type=="ACTA_COPY")) if d.board_id}
                for b in boards:
                    if b.id not in documented:items.append(self._item(rule,"ELECTORAL_BOARD",b.id,place_by_id[b.polling_place_id].parish_id,{"board_code":b.official_code,"polling_place_name":place_by_id[b.polling_place_id].name}))
            elif c=="OFFLINE_SYNC_FAILURE":
                threshold_minutes=int(rule.configuration.get("delay_threshold_minutes",120))
                for a in assignments:
                    if a.checkin_offline_created_at and a.checked_in_at and (a.checked_in_at-a.checkin_offline_created_at).total_seconds()>=threshold_minutes*60:
                        place=place_by_id.get(a.polling_place_id)
                        items.append(self._item(rule,"ELECTION_DAY_ASSIGNMENT",a.id,place.parish_id if place else None,{"record_type":"CHECK_IN","delay_minutes":round((a.checked_in_at-a.checkin_offline_created_at).total_seconds()/60)}))
                for i in self.db.scalars(select(ElectionDayIncident).where(ElectionDayIncident.operation_id==op.id,ElectionDayIncident.is_active.is_(True),ElectionDayIncident.offline_created_at.isnot(None))):
                    if (i.reported_at-i.offline_created_at).total_seconds()>=threshold_minutes*60:
                        place=place_by_id.get(i.polling_place_id)
                        items.append(self._item(rule,"ELECTION_DAY_INCIDENT",i.id,place.parish_id if place else None,{"record_type":"INCIDENT","delay_minutes":round((i.reported_at-i.offline_created_at).total_seconds()/60)}))
        return items
