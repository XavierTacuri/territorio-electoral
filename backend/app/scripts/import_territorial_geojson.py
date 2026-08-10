import argparse
from pathlib import Path
from sqlalchemy import select
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.historical import DataSource
from app.models.user import User
from app.services.geometry_import_service import GeometryImportService
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--source-code',required=True);parser.add_argument('--file',required=True);parser.add_argument('--territory-level',required=True);parser.add_argument('--dpa-code-property',default='dpa_code');parser.add_argument('--name-property',default='name');parser.add_argument('--validate-only',action='store_true');parser.add_argument('--force',action='store_true');parser.add_argument('--allow-make-valid',action='store_true');args=parser.parse_args()
 with SessionLocal() as db:
  source=db.scalar(select(DataSource).where(DataSource.code==args.source_code));user=db.scalar(select(User).where(User.is_superuser.is_(True),User.is_active.is_(True)))
  if not source or not user:raise SystemExit('Fuente o administrador no disponible')
  job=GeometryImportService(db).run(source.id,Path(args.file).name,Path(args.file).read_bytes(),user,args.territory_level,args.dpa_code_property,args.name_property,args.validate_only,args.force,args.allow_make_valid);print(f'Importación geográfica {job.status}: {job.rows_read} leídas, {job.rows_valid} válidas, {job.rows_updated} actualizadas, {job.rows_failed} rechazadas.')
if __name__=='__main__':main()
