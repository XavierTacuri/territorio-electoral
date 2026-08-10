import argparse
from datetime import datetime, timezone
from sqlalchemy import delete, select
from app.db.session import SessionLocal
from app.models.security import AuthSession


def main() -> None:
    parser = argparse.ArgumentParser(description="Limpia sesiones de navegador expiradas")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        count = len(db.scalars(select(AuthSession.id).where(AuthSession.expires_at <= now)).all())
        if not args.dry_run:
            db.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
            db.commit()
        print(f"Sesiones expiradas: {count}; modo: {'simulación' if args.dry_run else 'eliminación'}")


if __name__ == "__main__":
    main()
