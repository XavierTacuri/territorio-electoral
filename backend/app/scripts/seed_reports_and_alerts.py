from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.alerts import AlertRule
from app.models.reports import ReportTemplate

TEMPLATE_NAMES={"CAMPAIGN_EXECUTIVE_SUMMARY":"Resumen ejecutivo de campaña","OPERATIONAL_ACTIVITY":"Actividad operativa","TERRITORIAL_COVERAGE":"Cobertura territorial","NEEDS":"Necesidades","COMMITMENTS":"Compromisos","SURVEY_RESULTS":"Resultados de encuestas","ELECTORAL_HISTORY":"Historial electoral","DEMOGRAPHIC_PROFILE":"Perfil demográfico","DATA_QUALITY":"Calidad de datos"}
DEFAULT_SECTIONS=["COVER","EXECUTIVE_METRICS","TERRITORIAL_COVERAGE","ACTIVITY_SUMMARY","TOP_NEEDS","COMMITMENTS","SURVEYS","ELECTORAL_HISTORY","DEMOGRAPHICS","DATA_QUALITY","SOURCES"]
TEMPLATE_NAMES["COMMITMENTS"]="Seguimientos de campaña"
TEMPLATE_NAMES["CURRENT_ELECTION_EXECUTIVE"]="Informe ejecutivo - Eleccion actual"
TEMPLATE_NAMES["PARISH_TERRITORIAL_PROFILE"]="Ficha territorial parroquial"
TEMPLATE_NAMES["SURVEY_STUDY_REPORT"]="Informe de encuesta o estudio territorial"
TEMPLATE_NAMES["OPERATION_TERRITORIAL_REPORT"]="Informe de operación territorial"
TEMPLATE_NAMES["PUBLIC_INTELLIGENCE_REPORT"]="Informe de inteligencia pública"
# Centro de Informes V1.
TEMPLATE_NAMES["CAMPAIGN_EXECUTIVE_REPORT"]="Informe ejecutivo de campaña"
TEMPLATE_NAMES["THEMATIC_REPORT"]="Informe temático"
# Asistente de Debate: briefing factual persistible, generado con la misma
# infraestructura de informes (preview, PDF/XLSX, versión, RBAC).
TEMPLATE_NAMES["DEBATE_BRIEF_REPORT"]="Preparación para debate"
# Modo Jornada Electoral: informe operativo, nunca de resultados (§56/§60/§88).
TEMPLATE_NAMES["ELECTION_DAY_REPORT"]="Informe de jornada electoral"
# Seguimientos/Commitments es dominio legacy (retiro de producto): la plantilla
# y las reglas de alerta se conservan por compatibilidad con lectura histórica,
# pero se marcan inactivas para que no aparezcan en flujos nuevos (informes,
# evaluación de alertas) sin necesidad de una migración destructiva.
DEPRECATED_ALERT_RULES={"COMMITMENT_DUE_SOON","OVERDUE_COMMITMENT","COMMITMENT_WITHOUT_RESPONSIBLE","COMMITMENT_WITHOUT_DUE_DATE"}
RULES=[
("SOURCE_FETCH_FAILED","PUBLIC_INTELLIGENCE","WARNING",{}),("NEW_OFFICIAL_PUBLICATION","PUBLIC_INTELLIGENCE","INFO",{}),("PUBLIC_DOCUMENT_UPDATED","PUBLIC_INTELLIGENCE","INFO",{}),("SOURCE_STALE","PUBLIC_INTELLIGENCE","WARNING",{"maximum_age_hours":48}),
("ACTIVITY_PENDING_APPROVAL","OPERATIONS","INFO",{}),("ACTIVITY_APPROVED","OPERATIONS","INFO",{}),("ACTIVITY_REJECTED","OPERATIONS","WARNING",{}),("ACTIVITY_UPCOMING","OPERATIONS","INFO",{"days_ahead":7}),("COMMITMENT_DUE_SOON","COMMITMENTS","INFO",{"days_ahead":7}),("CRITICAL_NEED_UNASSIGNED","OPERATIONS","CRITICAL",{}),("NEED_REVIEW_STALE","OPERATIONS","WARNING",{"days_in_review":7}),
("OVERDUE_COMMITMENT","COMMITMENTS","WARNING",{"days_overdue":0}),("COMMITMENT_WITHOUT_RESPONSIBLE","COMMITMENTS","WARNING",{}),("COMMITMENT_WITHOUT_DUE_DATE","COMMITMENTS","INFO",{}),("PAST_PLANNED_ACTIVITY","OPERATIONS","WARNING",{}),("ACTIVITY_WITHOUT_RESPONSIBLE","OPERATIONS","WARNING",{}),("ACTIVITY_WITHOUT_LOCATION","OPERATIONS","INFO",{}),("ACTIVITY_WITHOUT_PARTICIPANT_SUMMARY","OPERATIONS","INFO",{}),("TERRITORY_WITHOUT_COMPLETED_ACTIVITY","OPERATIONS","WARNING",{"inactivity_days":14,"territory_level":"PARISH"}),("SURVEY_WITHOUT_RESPONSES","SURVEYS","WARNING",{}),("SURVEY_LOW_SAMPLE","SURVEYS","INFO",{"minimum_valid_responses":5}),("SURVEY_PRIVACY_SUPPRESSED","SURVEYS","INFO",{"minimum_valid_responses":5}),("FAILED_DATA_IMPORT","DATA_IMPORTS","CRITICAL",{}),("UNMAPPED_ELECTORAL_GEOGRAPHY","ELECTORAL_DATA","WARNING",{}),("CONTEST_WITHOUT_RESULTS","ELECTORAL_DATA","WARNING",{}),("CONTEST_WITHOUT_TURNOUT","ELECTORAL_DATA","WARNING",{}),("MISSING_CANTON_GEOMETRY","GEOMETRY","WARNING",{}),("MISSING_PARISH_GEOMETRY","GEOMETRY","WARNING",{}),("INVALID_GEOMETRY","GEOMETRY","CRITICAL",{}),("INACTIVE_DATA_SOURCE","DATA_QUALITY","INFO",{}),("STALE_DEMOGRAPHIC_DATA","DEMOGRAPHICS","WARNING",{"maximum_age_days":365}),("MISSING_DEMOGRAPHIC_INDICATOR","DEMOGRAPHICS","INFO",{}),
("ACTIVITY_SUSPENDED","OPERATIONS","WARNING",{}),("UPCOMING_OFFICIAL_MILESTONE","ELECTORAL_DATA","INFO",{"days_ahead":7}),("DATASET_UPDATE","DATA_IMPORTS","INFO",{"lookback_days":7}),("CAMPAIGN_WITHOUT_ACTIVE_ROLL","DATA_QUALITY","WARNING",{}),("SURVEY_WITHOUT_METHODOLOGY","SURVEYS","INFO",{}),("DATA_SOURCE_WITHOUT_REFERENCE_DATE","DATA_QUALITY","INFO",{}),
# Alertas inteligentes — Centro de Informes (§25/§26/§27/§30 de Fase Final).
("ACTIVITY_COMPLETED_WITHOUT_EVIDENCE","EVIDENCE","INFO",{}),("NEEDS_TOPIC_RECURRENCE","OPERATIONS","INFO",{"lookback_days":7,"minimum_count":3}),("REPORT_DATA_UPDATED_SINCE_GENERATION","REPORTS","INFO",{}),("SURVEY_COMPARISON_CHANGE","SURVEYS","INFO",{}),
# Modo Jornada Electoral — alertas de jornada (§42-44 de Fase Modo Jornada).
("ELECTION_PLACE_UNCOVERED","OPERATIONS","WARNING",{}),("BOARD_UNCOVERED","OPERATIONS","WARNING",{}),("ASSIGNED_PERSON_NOT_CHECKED_IN","OPERATIONS","WARNING",{"grace_minutes":60}),("OPEN_ELECTION_INCIDENT","OPERATIONS","WARNING",{}),("BOARD_DOCUMENT_MISSING","OPERATIONS","INFO",{}),("OFFLINE_SYNC_FAILURE","OPERATIONS","INFO",{"delay_threshold_minutes":120})]

def seed(db):
    for code,name in TEMPLATE_NAMES.items():
        item=db.scalar(select(ReportTemplate).where(ReportTemplate.code==code))
        report_type="ELECTORAL_HISTORY" if code in {"CURRENT_ELECTION_EXECUTIVE","PARISH_TERRITORIAL_PROFILE"} else "SURVEY_STUDY" if code=="SURVEY_STUDY_REPORT" else "OPERATIONAL_ACTIVITY" if code=="OPERATION_TERRITORIAL_REPORT" else "PUBLIC_INTELLIGENCE" if code=="PUBLIC_INTELLIGENCE_REPORT" else "CAMPAIGN_EXECUTIVE_SUMMARY" if code=="CAMPAIGN_EXECUTIVE_REPORT" else "THEMATIC" if code=="THEMATIC_REPORT" else "DEBATE_BRIEF" if code=="DEBATE_BRIEF_REPORT" else "ELECTION_DAY" if code=="ELECTION_DAY_REPORT" else code
        description=f"Plantilla legacy (Seguimientos/Commitments retirado del producto): {name}. No disponible para nuevos informes." if code=="COMMITMENTS" else f"Plantilla del sistema: {name}."
        values={"name":name,"description":description,"report_type":report_type,"allowed_formats":["PDF","XLSX"],"definition":{"sections":DEFAULT_SECTIONS,"include_comparisons":True,"include_methodology":True,"include_sources":True,"max_items_per_section":50},"is_system":True,"is_active":code!="COMMITMENTS"}
        if item:
            for key,value in values.items():setattr(item,key,value)
        else:db.add(ReportTemplate(code=code,**values))
    for code,module,severity,configuration in RULES:
        item=db.scalar(select(AlertRule).where(AlertRule.code==code));values={"name":code.replace("_"," ").title(),"description":f"Regla técnica determinista: {code}.","module":module,"condition_type":code,"default_severity":severity,"configuration":configuration,"is_system":True,"is_active":code not in DEPRECATED_ALERT_RULES}
        if item:
            for key,value in values.items():setattr(item,key,value)
        else:db.add(AlertRule(code=code,**values))
    db.flush();return len(TEMPLATE_NAMES),len(RULES)

def main():
    with SessionLocal() as db:
        try:templates,rules=seed(db);db.commit()
        except Exception:db.rollback();raise
    print(f"Plantillas y reglas inicializadas: {templates} plantillas y {rules} reglas.")
if __name__=="__main__":main()
