from collections.abc import Generator
from unittest.mock import Mock

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_db
from app.main import app


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


def test_health_endpoint_reports_connected_database() -> None:
    app.dependency_overrides[get_db] = healthy_db
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "application": "Territorio Electoral API",
        "database": "connected",
    }


def test_health_endpoint_handles_unavailable_database() -> None:
    app.dependency_overrides[get_db] = unavailable_db
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "application": "Territorio Electoral API",
        "database": "unavailable",
    }

