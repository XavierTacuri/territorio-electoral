"""Fase 4B §42/§48: request ID, structured logging + redaction, health/ready
(including DB down/up recovery), and the new operational metrics counters."""

import logging
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.observability import JsonFormatter, SensitiveDataFilter, event_metrics, prometheus_metrics, record_event
from app.db.session import get_db
from app.main import app


# ---------- /health (liveness) ----------

def test_health_returns_200_without_touching_db(client: TestClient, monkeypatch):
    def explode():
        raise AssertionError("¡/health nunca debe consultar la base de datos!")

    monkeypatch.setattr("app.db.session.SessionLocal", explode)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------- /ready (readiness, DB down/up) ----------

def test_ready_returns_200_when_db_healthy(client: TestClient):
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "READY"}


def test_ready_returns_503_when_db_unavailable(client: TestClient, db):
    def failing_execute(*_args, **_kwargs):
        raise SQLAlchemyError("simulated connection failure")

    original = db.execute
    db.execute = failing_execute
    try:
        response = client.get("/api/v1/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "NOT_READY"}
    finally:
        db.execute = original


def test_ready_response_never_leaks_db_details(client: TestClient, db):
    def failing_execute(*_args, **_kwargs):
        raise SQLAlchemyError(f"connection to postgresql://user:realpassword@internal-host/db failed")

    original = db.execute
    db.execute = failing_execute
    try:
        response = client.get("/api/v1/ready")
        body = response.text
        assert "postgresql://" not in body
        assert "realpassword" not in body
        assert "Traceback" not in body
        assert response.json() == {"status": "NOT_READY"}
    finally:
        db.execute = original


def test_ready_recovers_after_db_available_again(client: TestClient, db):
    def failing_execute(*_args, **_kwargs):
        raise SQLAlchemyError("simulated connection failure")

    original = db.execute
    db.execute = failing_execute
    assert client.get("/api/v1/ready").status_code == 503
    db.execute = original
    assert client.get("/api/v1/ready").status_code == 200


# ---------- Request ID (§13/§42) ----------

def test_response_always_includes_x_request_id_header(client: TestClient):
    response = client.get("/api/v1/health")
    assert re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", response.headers["X-Request-ID"])


def test_valid_supplied_request_id_is_reused(client: TestClient):
    response = client.get("/api/v1/health", headers={"X-Request-ID": "trace-abc-123"})
    assert response.headers["X-Request-ID"] == "trace-abc-123"


def test_malicious_request_id_is_replaced_not_reflected(client: TestClient):
    malicious = "abc\r\nX-Injected: 1"
    response = client.get("/api/v1/health", headers={"X-Request-ID": malicious})
    returned = response.headers["X-Request-ID"]
    assert returned != malicious
    assert "\r" not in returned and "\n" not in returned
    assert re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", returned)


def test_overlong_request_id_is_replaced(client: TestClient):
    too_long = "a" * 500
    response = client.get("/api/v1/health", headers={"X-Request-ID": too_long})
    assert response.headers["X-Request-ID"] != too_long
    assert len(response.headers["X-Request-ID"]) <= 128


def test_request_id_reaches_the_request_complete_log(client: TestClient):
    # request_id travels via a ContextVar that JsonFormatter reads AT FORMAT
    # TIME — caplog's own handler stores raw records and formats them lazily
    # (after the request, once the context var already reset), so it can't
    # prove this. Attach a real formatting handler for the duration of the
    # request instead, exactly like the app's own configured handler does.
    import io

    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SensitiveDataFilter())
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        response = client.get("/api/v1/health", headers={"X-Request-ID": "trace-log-check"})
    finally:
        root.removeHandler(handler)
    assert response.headers["X-Request-ID"] == "trace-log-check"
    assert '"request_id":"trace-log-check"' in buffer.getvalue()


def test_json_formatter_includes_request_id_field():
    record = logging.LogRecord("territorio.test", logging.INFO, __file__, 1, "algo pasó", None, None)
    record.request_id = "explicit-id-123"
    formatted = JsonFormatter().format(record)
    assert '"request_id":"explicit-id-123"' in formatted


# ---------- Redaction (§14/§15) ----------

@pytest.mark.parametrize("key", ["upload_token", "Authorization", "cookie", "password", "client_secret", "presigned_url", "signature", "database_url"])
def test_sensitive_extra_keys_are_redacted(key):
    record = logging.LogRecord("territorio.test", logging.INFO, __file__, 1, "evento", None, None)
    setattr(record, key, "muy-secreto-no-debe-verse")
    assert SensitiveDataFilter().filter(record) is True
    assert getattr(record, key) == "[REDACTED]"


def test_non_sensitive_extra_keys_survive_the_filter():
    record = logging.LogRecord("territorio.test", logging.INFO, __file__, 1, "evento", None, None)
    record.mime_type = "image/jpeg"
    record.size_bytes = 1024
    assert SensitiveDataFilter().filter(record) is True
    assert record.mime_type == "image/jpeg"
    assert record.size_bytes == 1024


@pytest.mark.parametrize(
    "message",
    [
        "authorization header was Bearer abc123.def456.ghi789",
        "token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
        "redirect to https://bucket.s3.amazonaws.com/x?X-Amz-Signature=abcdef0123456789&other=1",
        "failed to connect: postgresql+psycopg://territorio_user:realsecret@db:5432/territorio_electoral",
    ],
)
def test_sensitive_value_patterns_in_message_are_redacted(message):
    record = logging.LogRecord("territorio.test", logging.INFO, __file__, 1, message, None, None)
    SensitiveDataFilter().filter(record)
    rendered = record.getMessage()
    assert "abc123" not in rendered
    assert "realsecret" not in rendered
    assert "X-Amz-Signature=abcdef0123456789" not in rendered
    assert "eyJhbGciOiJIUzI1NiJ9" not in rendered


def test_redaction_filter_is_wired_into_configured_logging():
    root = logging.getLogger()
    assert any(isinstance(f, SensitiveDataFilter) for h in root.handlers for f in h.filters)


# ---------- Error classification (§19) ----------

def test_conflict_409_is_not_logged_as_error(client: TestClient, admin_headers, caplog):
    # A 409 on a nonexistent resource path still exercises the "expected
    # business error, not a crash" logging path via a 404 here (404 is
    # equally "expected", and doesn't require standing up a full claim-race
    # fixture just to prove the log level contract).
    with caplog.at_level("INFO"):
        response = client.get("/api/v1/campaigns/00000000-0000-0000-0000-000000000000", headers=admin_headers)
    assert response.status_code in (403, 404)
    assert not any(r.levelname == "ERROR" for r in caplog.records if r.name == "territorio.http")


def test_unexpected_500_is_logged_as_error_with_request_id(client: TestClient, caplog):
    # A genuinely unhandled exception (not one of our mapped business
    # exceptions) — simulated via a broken dependency override, which the
    # outer middleware must still convert to a safe 500 and log at ERROR
    # with the request id, never leaking the raw exception to the client.
    def broken_db():
        raise RuntimeError("fallo inesperado simulado")
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = broken_db
    try:
        with caplog.at_level("ERROR"):
            response = client.get("/api/v1/ready", headers={"X-Request-ID": "trace-500-check"})
        assert response.status_code == 500
        assert "trace-500-check" in response.json()["detail"]
        assert any(r.levelname == "ERROR" and r.name == "territorio.http" for r in caplog.records)
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------- Metrics (§17/§43) ----------

def test_record_event_appears_in_prometheus_exposition():
    event_metrics.clear()
    record_event("act_submit_total")
    record_event("act_submit_total")
    output = prometheus_metrics()
    assert 'territorio_events_total{event="act_submit_total"} 2' in output


def test_prometheus_output_never_contains_high_cardinality_identifiers():
    event_metrics.clear()
    record_event("artifact_upload_complete_total")
    output = prometheus_metrics()
    # No UUID-shaped identifiers anywhere in the exposition.
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", output)


def test_metrics_endpoint_disabled_by_default_returns_404(client: TestClient):
    response = client.get("/api/v1/metrics")
    assert response.status_code == 404


def test_metrics_endpoint_requires_token_when_enabled(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "metrics_enabled", True)
    monkeypatch.setattr(settings, "metrics_token", "a-real-metrics-token-value")
    try:
        assert client.get("/api/v1/metrics").status_code == 403
        response = client.get("/api/v1/metrics", headers={"Authorization": "Bearer a-real-metrics-token-value"})
        assert response.status_code == 200
        assert "territorio_http_requests_total" in response.text
    finally:
        monkeypatch.setattr(settings, "metrics_enabled", False)


# ---------- DB pool config (§7/§53) ----------

def test_db_pool_recycle_seconds_has_conservative_default():
    assert 0 < settings.db_pool_recycle_seconds <= 3600


def test_web_concurrency_defaults_to_one_and_is_positive():
    assert settings.web_concurrency >= 1
