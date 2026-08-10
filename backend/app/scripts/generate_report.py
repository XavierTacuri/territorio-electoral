import argparse
from datetime import date
from uuid import UUID
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.user import User
from app.schemas.reports import ReportGenerationRequest
from app.services.report_service import ReportService

def main():
    p=argparse.ArgumentParser();p.add_argument("--campaign-id",required=True);p.add_argument("--template-code",required=True);p.add_argument("--format",choices=["PDF","XLSX"],required=True);p.add_argument("--report-date",type=date.fromisoformat,required=True);p.add_argument("--date-from",type=date.fromisoformat);p.add_argument("--date-to",type=date.fromisoformat);args=p.parse_args()
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.is_superuser.is_(True),User.is_active.is_(True)))
        if not user:raise SystemExit("No existe un administrador activo para la ejecución controlada.")
        data=ReportGenerationRequest(template_code=args.template_code,format=args.format,title=args.template_code.replace("_"," ").title(),report_date=args.report_date,date_from=args.date_from,date_to=args.date_to)
        run=ReportService(db).generate(UUID(args.campaign_id),data,user);print(f"Informe generado: id={run.id}, estado={run.status}, formato={run.requested_format}")
if __name__=="__main__":main()
