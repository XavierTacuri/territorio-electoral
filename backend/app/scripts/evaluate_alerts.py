import argparse
from datetime import date
from uuid import UUID
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.user import User
from app.schemas.alerts import AlertEvaluationRequest
from app.services.alert_service import AlertService
def main():
    p=argparse.ArgumentParser();p.add_argument("--campaign-id",required=True);p.add_argument("--as-of-date",type=date.fromisoformat,required=True);args=p.parse_args()
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.is_superuser.is_(True),User.is_active.is_(True)))
        if not user:raise SystemExit("No existe un administrador activo.")
        result=AlertService(db).evaluate(UUID(args.campaign_id),user,AlertEvaluationRequest(as_of_date=args.as_of_date));print("Alertas evaluadas: "+", ".join(f"{k}={v}" for k,v in result.items()))
if __name__=="__main__":main()
