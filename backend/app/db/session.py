from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, settings


def build_engine_options(database_url: str, app_settings: Settings) -> dict:
    """Pure function so Fase 4B's pool config (§7) is testable without
    depending on the module-level `engine` singleton below, which is bound
    once at import time to whatever `settings.database_url` happened to be
    (sqlite in every test that doesn't override it)."""
    options: dict = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        return options
    options.update(
        pool_size=app_settings.db_pool_size,
        max_overflow=app_settings.db_max_overflow,
        pool_timeout=app_settings.db_pool_timeout_seconds,
        # Recycles a connection before RDS/PgBouncer/RDS Proxy (Fase 4C
        # target) would otherwise drop it silently from under us — pairs
        # with pool_pre_ping (catches an already-dead connection) rather
        # than replacing it: recycle bounds how OLD a connection can get,
        # pre_ping catches one that died for any other reason.
        pool_recycle=app_settings.db_pool_recycle_seconds,
        connect_args={"connect_timeout": app_settings.db_connect_timeout_seconds},
    )
    return options


engine_options = build_engine_options(settings.database_url, settings)
engine = create_engine(settings.database_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, class_=Session, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
