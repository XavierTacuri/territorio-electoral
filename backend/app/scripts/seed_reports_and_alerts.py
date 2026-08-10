from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.alerts import AlertRule
from app.models.reports import ReportTemplate

TEMPLATE_NAMES={"CAMPAIGN_EXECUTIVE_SUMMARY":"Resumen ejecutivo de campaña","OPERATIONAL_ACTIVITY":"Actividad operativa","TERRITORIAL_COVERAGE":"Cobertura territorial","NEEDS":"Necesidades","COMMITMENTS":"Compromisos","SURVEY_RESULTS":"Resultados de encuestas","ELECTORAL_HISTORY":"Historial electoral","DEMOGRAPHIC_PROFILE":"Perfil demográfico","DATA_QUALITY":"Calidad de datos"}
DEFAULT_SECTIONS=["COVER","EXECUTIVE_METRICS","TERRITORIAL_COVERAGE","ACTIVITY_SUMMARY","TOP_NEEDS","COMMITMENTS","SURVEYS","ELECTORAL_HISTORY","DEMOGRAPHICS","DATA_QUALITY","SOURCES"]
TEMPLATE_NAMES["CURRENT_ELECTION_EXECUTIVE"]="Informe ejecutivo - Eleccion actual"
RULES=[
("OVERDUE_COMMITMENT","COMMITMENTS","WARNING",{"days_overdue":0}),("COMMITMENT_WITHOUT_RESPONSIBLE","COMMITMENTS","WARNING",{}),("COMMITMENT_WITHOUT_DUE_DATE","COMMITMENTS","INFO",{}),("PAST_PLANNED_ACTIVITY","OPERATIONS","WARNING",{}),("ACTIVITY_WITHOUT_RESPONSIBLE","OPERATIONS","WARNING",{}),("ACTIVITY_WITHOUT_LOCATION","OPERATIONS","INFO",{}),("ACTIVITY_WITHOUT_PARTICIPANT_SUMMARY","OPERATIONS","INFO",{}),("TERRITORY_WITHOUT_COMPLETED_ACTIVITY","OPERATIONS","WARNING",{"inactivity_days":14,"territory_level":"PARISH"}),("SURVEY_WITHOUT_RESPONSES","SURVEYS","WARNING",{}),("SURVEY_LOW_SAMPLE","SURVEYS","INFO",{"minimum_valid_responses":5}),("SURVEY_PRIVACY_SUPPRESSED","SURVEYS","INFO",{"minimum_valid_responses":5}),("FAILED_DATA_IMPORT","DATA_IMPORTS","CRITICAL",{}),("UNMAPPED_ELECTORAL_GEOGRAPHY","ELECTORAL_DATA","WARNING",{}),("CONTEST_WITHOUT_RESULTS","ELECTORAL_DATA","WARNING",{}),("CONTEST_WITHOUT_TURNOUT","ELECTORAL_DATA","WARNING",{}),("MISSING_CANTON_GEOMETRY","GEOMETRY","WARNING",{}),("MISSING_PARISH_GEOMETRY","GEOMETRY","WARNING",{}),("INVALID_GEOMETRY","GEOMETRY","CRITICAL",{}),("INACTIVE_DATA_SOURCE","DATA_QUALITY","INFO",{}),("STALE_DEMOGRAPHIC_DATA","DEMOGRAPHICS","WARNING",{"maximum_age_days":365}),("MISSING_DEMOGRAPHIC_INDICATOR","DEMOGRAPHICS","INFO",{})]

def seed(db):
    for code,name in TEMPLATE_NAMES.items():
        item=db.scalar(select(ReportTemplate).where(ReportTemplate.code==code))
        report_type="ELECTORAL_HISTORY" if code=="CURRENT_ELECTION_EXECUTIVE" else code
        values={"name":name,"description":f"Plantilla del sistema: {name}.","report_type":report_type,"allowed_formats":["PDF","XLSX"],"definition":{"sections":DEFAULT_SECTIONS,"include_comparisons":True,"include_methodology":True,"include_sources":True,"max_items_per_section":50},"is_system":True,"is_active":True}
        if item:
            for key,value in values.items():setattr(item,key,value)
        else:db.add(ReportTemplate(code=code,**values))
    for code,module,severity,configuration in RULES:
        item=db.scalar(select(AlertRule).where(AlertRule.code==code));values={"name":code.replace("_"," ").title(),"description":f"Regla técnica determinista: {code}.","module":module,"condition_type":code,"default_severity":severity,"configuration":configuration,"is_system":True,"is_active":True}
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
