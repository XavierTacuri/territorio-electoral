"""Tests de `_HealthCheckHostExemptMiddleware` (app/main.py): confirman que
SOLO `GET /api/v1/health` evita la validacion de Host, que ningun otro path
o metodo similar logra el mismo bypass, y que el resto de la aplicacion
conserva el comportamiento original de TrustedHostMiddleware. Host por
defecto de TestClient/Settings: "testserver" (confiable); se usa una IP
privada para simular el Host que envia un health check real de ALB
(target_type=ip)."""

from fastapi.testclient import TestClient

from app.main import app

UNTRUSTED_ALB_TARGET_IP = "10.20.3.15"
UNTRUSTED_ATTACKER_HOST = "evil.attacker.example"


def test_trusted_host_allows_normal_request() -> None:
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200


def test_untrusted_host_rejects_normal_request() -> None:
    with TestClient(app) as client:
        response = client.get("/", headers={"Host": UNTRUSTED_ALB_TARGET_IP})
    assert response.status_code == 400
    assert response.text == "Invalid host header"


def test_untrusted_host_is_exempt_only_on_health_path() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health", headers={"Host": UNTRUSTED_ALB_TARGET_IP})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_untrusted_host_still_rejected_on_ready_path() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/ready", headers={"Host": UNTRUSTED_ALB_TARGET_IP})
    assert response.status_code == 400


def test_untrusted_host_with_trailing_slash_is_not_exempt() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health/", headers={"Host": UNTRUSTED_ALB_TARGET_IP})
    assert response.status_code == 400


def test_untrusted_host_with_query_string_keeps_exemption() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health?x=1", headers={"Host": UNTRUSTED_ALB_TARGET_IP})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_arbitrary_attacker_host_rejected_on_normal_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/", headers={"Host": UNTRUSTED_ATTACKER_HOST})
    assert response.status_code == 400


def test_untrusted_host_with_unexpected_method_is_not_exempt() -> None:
    with TestClient(app) as client:
        post_response = client.post("/api/v1/health", headers={"Host": UNTRUSTED_ALB_TARGET_IP})
        delete_response = client.delete("/api/v1/health", headers={"Host": UNTRUSTED_ALB_TARGET_IP})
        head_response = client.head("/api/v1/health", headers={"Host": UNTRUSTED_ALB_TARGET_IP})
    assert post_response.status_code == 400
    assert delete_response.status_code == 400
    assert head_response.status_code == 400


def test_untrusted_host_with_similar_path_is_not_exempt() -> None:
    with TestClient(app) as client:
        suffix_response = client.get("/api/v1/healthx", headers={"Host": UNTRUSTED_ALB_TARGET_IP})
        double_slash_response = client.get("/api/v1//health", headers={"Host": UNTRUSTED_ALB_TARGET_IP})
    assert suffix_response.status_code == 400
    assert double_slash_response.status_code == 400


def test_health_exemption_still_executes_the_real_endpoint() -> None:
    """El bypass delega en la aplicacion real (router + vista), no en un
    atajo que devuelva 200 sin ejecutar nada — el cuerpo debe coincidir
    exactamente con `HealthResponse` de `app/api/routes/health.py`."""
    with TestClient(app) as client:
        response = client.get("/api/v1/health", headers={"Host": UNTRUSTED_ALB_TARGET_IP})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["content-type"].startswith("application/json")
