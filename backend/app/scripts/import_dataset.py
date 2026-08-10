import argparse,json,sys
from pathlib import Path
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.user import User
from app.services.data_import_service import DataImportService
def main():
 p=argparse.ArgumentParser(description='Importación trazable de CSV oficial agregado');p.add_argument('--dataset-type',required=True);p.add_argument('--source-code',required=True);p.add_argument('--file',required=True);p.add_argument('--mapping-profile');p.add_argument('--validate-only',action='store_true');p.add_argument('--encoding');p.add_argument('--delimiter');p.add_argument('--mapping-json');p.add_argument('--force',action='store_true');a=p.parse_args()
 path=Path(a.file)
 if not path.is_file():print('Archivo no encontrado');return 2
 with SessionLocal() as db:
  from app.models.historical import DataSource
  source=db.scalar(select(DataSource).where(DataSource.code==a.source_code.upper(),DataSource.is_active.is_(True)));user=db.scalar(select(User).where(User.is_superuser.is_(True),User.is_active.is_(True)))
  if not source or not user:print('Fuente o administrador no configurado');return 2
  try:
   mapping=json.loads(a.mapping_json) if a.mapping_json else None;job=DataImportService(db).run(source.id,a.dataset_type,path.name,path.read_bytes(),user,a.validate_only,a.mapping_profile,a.encoding,a.delimiter,mapping,a.force);print(f'Estado: {job.status}. Leídas: {job.rows_read}. Válidas: {job.rows_valid}. Insertadas: {job.rows_inserted}. Actualizadas: {job.rows_updated}. Fallidas: {job.rows_failed}.');return 0 if job.status in {'VALIDATED','COMPLETED'} else 1
  except Exception as e:print(f'Importación rechazada: {e}');return 1
if __name__=='__main__':sys.exit(main())
