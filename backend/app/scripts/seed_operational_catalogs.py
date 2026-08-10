from sqlalchemy.exc import SQLAlchemyError
from app.db.session import SessionLocal
from app.services.activity_catalog_service import seed

def seed_operational_catalogs():
    with SessionLocal() as db:
        try:seed(db);db.commit();print("Catálogos operativos inicializados: 11 tipos de actividad y 17 categorías de necesidad.")
        except SQLAlchemyError:db.rollback();print("No fue posible inicializar los catálogos operativos.");raise SystemExit(1)
if __name__=="__main__":seed_operational_catalogs()
