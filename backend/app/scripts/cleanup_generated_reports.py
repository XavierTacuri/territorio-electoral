import argparse
from datetime import date
from sqlalchemy import select
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.reports import ReportArtifact
from app.services.report_storage_service import LocalReportStorage
def main():
    p=argparse.ArgumentParser();p.add_argument("--dry-run",action="store_true");args=p.parse_args();removed=skipped=0;storage=LocalReportStorage(settings.report_output_dir,settings.report_max_file_mb)
    with SessionLocal() as db:
        for artifact in db.scalars(select(ReportArtifact).where(ReportArtifact.expires_on<date.today(),ReportArtifact.is_available.is_(True))):
            try:
                if not args.dry_run:storage.delete(artifact.storage_key);artifact.is_available=False
                removed+=1
            except ValueError:skipped+=1
        if args.dry_run:db.rollback()
        else:db.commit()
    print(f"Artefactos expirados: {removed}; omitidos por seguridad: {skipped}; dry_run={args.dry_run}")
if __name__=="__main__":main()
