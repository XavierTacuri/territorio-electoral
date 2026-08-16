from collections.abc import Generator
from unittest.mock import Mock

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_db
from app.main import app


@app.get("/_test/unexpected-v29", include_in_schema=False)
def unexpected_v29():
    raise RuntimeError("internal detail must not leak")


def healthy_db() -> Generator[Mock, None, None]:
    session = Mock()
    session.execute.return_value = Mock()
    yield session


def unavailable_db() -> Generator[Mock, None, None]:
    session = Mock()
    session.execute.side_effect = OperationalError("SELECT 1", {}, Exception("offline"))
    yield session


def test_root_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "name": "Territorio Electoral API",
        "status": "running",
    }


def test_health_endpoint_is_liveness_only() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
    }


def test_ready_endpoint_handles_unavailable_database() -> None:
    app.dependency_overrides[get_db] = unavailable_db
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "status": "NOT_READY",
    }


def test_ready_endpoint_reports_available_database() -> None:
    app.dependency_overrides[get_db] = healthy_db
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/ready")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() == {"status": "READY"}


def test_request_id_and_security_headers() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health", headers={"X-Request-ID": "trace-valid-123"})
    assert response.headers["X-Request-ID"] == "trace-valid-123"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_invalid_request_id_is_replaced() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health", headers={"X-Request-ID": "invalid id with spaces"})
    assert response.headers["X-Request-ID"] != "invalid id with spaces"


def test_unexpected_error_is_safe_and_correlated() -> None:
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/_test/unexpected-v29", headers={"X-Request-ID": "failure-ref-29"})
    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "failure-ref-29"
    assert response.json() == {"detail": "Ha ocurrido un error inesperado. Código de referencia: failure-ref-29"}
    assert "internal detail" not in response.text
