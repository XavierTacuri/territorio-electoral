"""Fase 4B §7/§53: DB engine pool configuration — pool_pre_ping, recycle,
size/overflow/timeouts all come from Settings; SQLite (the whole test suite)
must keep working with none of the Postgres-only pool options applied."""

from app.core.config import Settings
from app.db.session import build_engine_options


def _settings(**overrides):
    values = dict(
        db_pool_size=7, db_max_overflow=13, db_pool_timeout_seconds=20,
        db_pool_recycle_seconds=900, db_connect_timeout_seconds=4,
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_sqlite_url_gets_no_postgres_only_pool_options():
    options = build_engine_options("sqlite://", _settings())
    assert options == {"pool_pre_ping": True}


def test_postgres_url_gets_full_pool_configuration():
    options = build_engine_options("postgresql+psycopg://user:pass@db:5432/territorio", _settings())
    assert options["pool_pre_ping"] is True
    assert options["pool_size"] == 7
    assert options["max_overflow"] == 13
    assert options["pool_timeout"] == 20
    assert options["pool_recycle"] == 900
    assert options["connect_args"] == {"connect_timeout": 4}


def test_pool_recycle_default_is_conservative_not_disabled():
    options = build_engine_options("postgresql+psycopg://user:pass@db:5432/territorio", _settings())
    assert 0 < options["pool_recycle"] <= 3600


def test_engine_options_never_leak_credentials():
    options = build_engine_options("postgresql+psycopg://user:realsecret@db:5432/territorio", _settings())
    assert "realsecret" not in str(options)
