#!/usr/bin/env python3
"""Fase 4B — prueba multiinstancia REAL (no simulada).

Ejercita dos procesos FastAPI independientes (api-a, api-b) que solo
comparten PostgreSQL (y, únicamente en esta topología de prueba, un volumen
de almacenamiento local — ver docker-compose.multi-instance.yml) para probar
que ninguna de las dos instancias guarda estado privado que la otra no vea:
sesión, reclamos de revisión, sesiones de soporte admin, invitaciones e
idempotencia por client_generated_id deben ser coherentes sin importar por
cuál instancia entre cada petición.

Requiere que backend/app/scripts/seed_e2e.py ya haya corrido contra la base
compartida (crea la campaña fixture "actas-e2e-2027" reutilizada aquí).

Uso:
    python backend/scripts/verify_multi_instance.py \
        --api-a http://localhost:18101/api/v1 \
        --api-b http://localhost:18102/api/v1

Sale con código 0 si todos los escenarios A-H pasan; código 1 en cualquier
otro caso (con el primer fallo impreso a stderr).
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid

import httpx

FIXTURE_CAMPAIGN_SLUG = "actas-e2e-2027"
FIXTURE_POLLING_PLACE_CODE = "E2E-ACT-REC-01"
USERNAMES = {
    "admin": "admin_e2e",
    "manager": "manager_e2e",
    "delegate_a": "delegate_e2e_a",
    "delegate_b": "delegate_e2e_b",
    "validator": "analyst_e2e",
}
DELEGATE_B_EMAIL = "delegate-b-e2e@example.com"

# Firma PNG mínima (§ sniff_evidence_mime en evidence_security_service.py
# sólo valida los primeros bytes, nunca decodifica la imagen) — suficiente
# para pasar la validación de evidencia sin depender de un archivo real.
FAKE_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class Failure(Exception):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)
    print(f"  OK: {message}")


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class ApiClient:
    def __init__(self, label: str, base_url: str):
        self.label = label
        self.base_url = base_url.rstrip("/")
        self.http = httpx.Client(timeout=20)

    def login(self, username: str, password: str) -> str:
        r = self.http.post(f"{self.base_url}/auth/login", data={"username": username, "password": password})
        check(r.status_code == 200, f"login de '{username}' contra {self.label} ({self.base_url}) -> 200")
        return r.json()["access_token"]

    def get(self, path: str, token: str, **kw) -> httpx.Response:
        return self.http.get(f"{self.base_url}{path}", headers=_auth(token), **kw)

    def post(self, path: str, token: str, json=None, **kw) -> httpx.Response:
        return self.http.post(f"{self.base_url}{path}", headers=_auth(token), json=json, **kw)

    def post_file(self, path: str, token: str, *, filename: str, content: bytes, mime: str, form: dict) -> httpx.Response:
        files = {"file": (filename, content, mime)}
        return self.http.post(f"{self.base_url}{path}", headers=_auth(token), files=files, data=form)


def find_campaign_id(client: ApiClient, token: str) -> str:
    r = client.get("/campaigns?page=1&page_size=100", token)
    check(r.status_code == 200, f"listado de campañas vía {client.label}")
    for item in r.json()["items"]:
        if item["slug"] == FIXTURE_CAMPAIGN_SLUG:
            return item["id"]
    raise Failure(
        f"No se encontró la campaña fixture '{FIXTURE_CAMPAIGN_SLUG}' vía {client.label} — "
        "¿corriste `python -m app.scripts.seed_e2e` contra esta base?"
    )


def find_board_id(client: ApiClient, token: str, campaign_id: str, board_code: str) -> tuple[str, str]:
    r = client.get(f"/campaigns/{campaign_id}/election-day/polling-places", token)
    check(r.status_code == 200, f"listado de recintos vía {client.label}")
    for place in r.json()["items"]:
        if place["official_code"] == FIXTURE_POLLING_PLACE_CODE:
            r2 = client.get(f"/campaigns/{campaign_id}/election-day/polling-places/{place['id']}/boards", token)
            check(r2.status_code == 200, f"listado de juntas del recinto fixture vía {client.label}")
            for board in r2.json():
                if board["official_code"] == board_code:
                    return place["id"], board["id"]
    raise Failure(f"No se encontró la junta '{board_code}' del recinto fixture vía {client.label}")


def find_contest_id(client: ApiClient, delegate_token: str, campaign_id: str) -> str:
    # list_contests exige require_delegate_assignment (§ acts service) — a
    # diferencia de polling-places/boards, no acepta un token ejecutivo.
    r = client.get(f"/campaigns/{campaign_id}/election-day/acts/contests", delegate_token)
    check(r.status_code == 200, f"listado de contiendas elegibles vía {client.label}")
    contests = r.json()
    check(len(contests) > 0, "existe al menos una contienda elegible en la campaña fixture")
    return contests[0]["id"]


def scenario_a_login(a: ApiClient, b: ApiClient, password: str) -> tuple[dict, dict, str]:
    print("\n[A] Login contra ambas instancias + validación cruzada de token")
    tokens_a = {key: a.login(username, password) for key, username in USERNAMES.items()}
    tokens_b = {key: b.login(username, password) for key, username in USERNAMES.items()}
    campaign_id = find_campaign_id(a, tokens_a["manager"])
    # Un token emitido por A debe ser aceptado por B sin volver a autenticar:
    # prueba que SECRET_KEY es compartido y que no existe estado de sesión
    # local en ninguna de las dos instancias (el usuario se resuelve desde
    # PostgreSQL en cada petición).
    r = b.get(f"/campaigns/{campaign_id}", tokens_a["manager"])
    check(
        r.status_code == 200,
        "un token emitido por API A es aceptado por API B sin reautenticar (SECRET_KEY compartido, sin sesión local)",
    )
    return tokens_a, tokens_b, campaign_id


def scenario_b_campaign_state(a: ApiClient, b: ApiClient, tokens_a: dict, tokens_b: dict, campaign_id: str) -> None:
    print("\n[B] Estado de la Jornada visible idéntico desde A y B")
    ra = a.get(f"/campaigns/{campaign_id}/election-day/operation", tokens_a["manager"])
    rb = b.get(f"/campaigns/{campaign_id}/election-day/operation", tokens_b["manager"])
    check(ra.status_code == 200 and rb.status_code == 200, "la operación de jornada es legible vía A y vía B")
    check(ra.json()["id"] == rb.json()["id"], "es la misma operación (mismo id) en A y B")
    check(
        ra.json()["status"] == rb.json()["status"] == "SCRUTINY",
        f"el estado de la jornada (SCRUTINY) es idéntico en A y B (A={ra.json()['status']!r}, B={rb.json()['status']!r})",
    )


def scenario_c_admin_support(a: ApiClient, b: ApiClient, tokens_a: dict, tokens_b: dict, campaign_id: str) -> str:
    print("\n[C] Sesión de soporte admin iniciada vía A, reconocida vía B")
    r = a.post(
        f"/campaigns/{campaign_id}/election-day/admin-support/start",
        tokens_a["admin"],
        json={"reason": "Fase 4B — verify_multi_instance.py"},
    )
    check(r.status_code == 201, "sesión de soporte admin iniciada vía API A")
    session_id = r.json()["id"]
    rb = b.get(f"/campaigns/{campaign_id}/election-day/admin-support/current", tokens_b["admin"])
    check(rb.status_code == 200 and rb.json() is not None, "API B reconoce una sesión de soporte admin activa")
    check(rb.json()["id"] == session_id, "es la MISMA sesión (mismo id), no una duplicada creada por B")
    return session_id


def scenario_d_act_draft(a: ApiClient, b: ApiClient, tokens_a: dict, tokens_b: dict, campaign_id: str, board_code: str) -> dict:
    print(f"\n[D] Delegado crea borrador de acta ({board_code}) vía A, API B lo lee")
    place_id, board_id = find_board_id(a, tokens_a["manager"], campaign_id, board_code)
    contest_id = find_contest_id(a, tokens_a["delegate_a"], campaign_id)
    payload = {
        "polling_place_id": place_id,
        "electoral_board_id": board_id,
        "electoral_contest_id": contest_id,
        "blank_ballots": 0,
        "null_ballots": 0,
        "valid_ballots": 0,
        "ballots_counted": 0,
        "results": [],
    }
    r = a.post(f"/campaigns/{campaign_id}/election-day/acts/drafts", tokens_a["delegate_a"], json=payload)
    check(r.status_code == 201, "borrador de acta creado vía API A")
    act_id = r.json()["act"]["id"]
    revision_id = r.json()["revision"]["id"]
    rb = b.get(f"/campaigns/{campaign_id}/election-day/acts/{act_id}", tokens_b["delegate_a"])
    check(rb.status_code == 200, "API B puede leer el acta creada vía API A")
    check(rb.json()["act"]["id"] == act_id, "es la misma acta (mismo id) vista desde B")
    return {"place_id": place_id, "board_id": board_id, "contest_id": contest_id, "act_id": act_id, "revision_id": revision_id}


def _upload_evidence_and_submit(client: ApiClient, token: str, campaign_id: str, act_id: str, revision_id: str, *, client_generated_id: str | None = None) -> dict:
    form = {}
    if client_generated_id:
        form["client_generated_id"] = client_generated_id
    r = client.post_file(
        f"/campaigns/{campaign_id}/election-day/acts/{act_id}/revisions/{revision_id}/evidence",
        token, filename="acta.png", content=FAKE_PNG_BYTES, mime="image/png", form=form,
    )
    check(r.status_code == 201, f"evidencia subida vía {client.label}")
    evidence = r.json()
    rs = client.post(f"/campaigns/{campaign_id}/election-day/acts/{act_id}/revisions/{revision_id}/submit", token)
    check(rs.status_code == 200, f"acta enviada a revisión vía {client.label}")
    return evidence


def scenario_e_claim_conflict(a: ApiClient, b: ApiClient, tokens_a: dict, tokens_b: dict, campaign_id: str, draft: dict) -> None:
    print("\n[E] Un validador reclama el acta vía B; otro validador vía A recibe 409 coherente")
    _upload_evidence_and_submit(a, tokens_a["delegate_a"], campaign_id, draft["act_id"], draft["revision_id"])
    r_claim = b.post(f"/campaigns/{campaign_id}/election-day/acts/{draft['act_id']}/claim", tokens_b["validator"])
    check(r_claim.status_code == 200, "analyst_e2e reclama el acta vía API B")
    check(r_claim.json()["review_claimed_by_user_id"] is not None, "el acta queda con un reclamo activo")
    # admin_e2e con soporte activo (escenario C) cuenta como revisor distinto
    # a analyst_e2e — intenta reclamar la MISMA acta vía la OTRA instancia.
    r_conflict = a.post(f"/campaigns/{campaign_id}/election-day/acts/{draft['act_id']}/claim", tokens_a["admin"])
    check(r_conflict.status_code == 409, f"un segundo revisor vía API A recibe 409 (obtuvo {r_conflict.status_code})")


def scenario_f_validate_control_center(a: ApiClient, b: ApiClient, tokens_a: dict, tokens_b: dict, campaign_id: str, draft: dict) -> None:
    print("\n[F] API A valida el acta reclamada vía B; Control Center en B la muestra exactamente una vez")
    r = a.post(
        f"/campaigns/{campaign_id}/election-day/acts/{draft['act_id']}/validate",
        tokens_a["validator"], json={"revision_id": draft["revision_id"]},
    )
    check(r.status_code == 200, "el acta se valida vía API A pese a que el reclamo se tomó vía API B")
    check(r.json()["status"] == "VALIDATED", "el acta queda en estado VALIDATED")
    rb_1 = b.get(f"/campaigns/{campaign_id}/election-day/control-center", tokens_b["manager"])
    rb_2 = b.get(f"/campaigns/{campaign_id}/election-day/control-center", tokens_b["manager"])
    check(rb_1.status_code == 200 and rb_2.status_code == 200, "Control Center responde 200 vía API B")
    cov_1 = rb_1.json()["coverage"]
    cov_2 = rb_2.json()["coverage"]
    check(cov_1 == cov_2, "dos lecturas consecutivas del Control Center vía B son idénticas (conteo exactamente una vez, no incrementa por lectura)")


def scenario_g_idempotency(a: ApiClient, b: ApiClient, tokens_a: dict, tokens_b: dict, campaign_id: str) -> None:
    print("\n[G] client_generated_id enviado primero a A y reintentado contra B no duplica acta/evidencia")
    place_id, board_id = find_board_id(a, tokens_a["manager"], campaign_id, "E2E-ACT-REC-01-J02")
    contest_id = find_contest_id(a, tokens_a["delegate_a"], campaign_id)
    client_generated_id = str(uuid.uuid4())
    payload = {
        "polling_place_id": place_id, "electoral_board_id": board_id, "electoral_contest_id": contest_id,
        "blank_ballots": 0, "null_ballots": 0, "valid_ballots": 0, "ballots_counted": 0, "results": [],
        "client_generated_id": client_generated_id,
    }
    r1 = a.post(f"/campaigns/{campaign_id}/election-day/acts/drafts", tokens_a["delegate_a"], json=payload)
    check(r1.status_code == 201, "primer envío del borrador (client_generated_id nuevo) vía API A -> 201")
    act_id_1 = r1.json()["act"]["id"]
    revision_id_1 = r1.json()["revision"]["id"]
    # Simula un cliente que no vio la respuesta de A (offline/timeout) y
    # reintenta la MISMA petición, esta vez contra B.
    r2 = b.post(f"/campaigns/{campaign_id}/election-day/acts/drafts", tokens_b["delegate_a"], json=payload)
    check(r2.status_code == 201, "reintento del mismo client_generated_id vía API B también responde 201 (idempotente, no error)")
    check(r2.json()["act"]["id"] == act_id_1, "el reintento vía B devuelve la MISMA acta, no una acta duplicada")
    check(r2.json()["revision"]["id"] == revision_id_1, "el reintento vía B devuelve la MISMA revisión")

    r_count = b.get(f"/campaigns/{campaign_id}/election-day/acts?polling_place_id={place_id}", tokens_b["manager"])
    check(r_count.status_code == 200, "listado de actas del recinto vía API B")
    matches = [item for item in r_count.json()["items"] if item["electoral_board_id"] == board_id]
    check(len(matches) == 1, f"solo existe UNA acta para esa junta tras el reintento cruzado (encontradas: {len(matches)})")

    evidence_client_id = str(uuid.uuid4())
    ev1 = a.post_file(
        f"/campaigns/{campaign_id}/election-day/acts/{act_id_1}/revisions/{revision_id_1}/evidence",
        tokens_a["delegate_a"], filename="acta.png", content=FAKE_PNG_BYTES, mime="image/png",
        form={"client_generated_id": evidence_client_id},
    )
    check(ev1.status_code == 201, "primera subida de evidencia (client_generated_id nuevo) vía API A -> 201")
    ev2 = b.post_file(
        f"/campaigns/{campaign_id}/election-day/acts/{act_id_1}/revisions/{revision_id_1}/evidence",
        tokens_b["delegate_a"], filename="acta.png", content=FAKE_PNG_BYTES, mime="image/png",
        form={"client_generated_id": evidence_client_id},
    )
    check(ev2.status_code == 201, "reintento de la misma evidencia vía API B también responde 201 (idempotente)")
    check(ev1.json()["id"] == ev2.json()["id"], "el reintento vía B devuelve la MISMA evidencia, no una copia")

    detail = b.get(f"/campaigns/{campaign_id}/election-day/acts/{act_id_1}", tokens_b["manager"])
    check(detail.status_code == 200, "detalle del acta vía API B")
    evidence_ids = {e["id"] for rev in detail.json()["revisions"] for e in rev.get("evidence", [])}
    check(len(evidence_ids) == 1, f"solo existe UNA evidencia activa tras el reintento cruzado (encontradas: {len(evidence_ids)})")


def scenario_h_invitation(a: ApiClient, b: ApiClient, tokens_a: dict, tokens_b: dict, campaign_id: str, password: str) -> None:
    print("\n[H] Invitación aceptada vía A es reconocida inmediatamente vía B")
    r_create = a.post(
        f"/campaigns/{campaign_id}/election-day/staff/invitations",
        tokens_a["manager"],
        json={
            "first_name": "Delegado", "last_name": "Sintético B",
            "email": DELEGATE_B_EMAIL, "staff_type": "ACT_VALIDATOR", "polling_place_ids": [],
        },
    )
    check(r_create.status_code == 201, "invitación de personal creada vía API A")
    invite_token = r_create.json()["invite_token"]

    delegate_b_token = a.login(USERNAMES["delegate_b"], password)
    r_accept = a.post("/election-day/invitations/accept", delegate_b_token, json={"token": invite_token})
    check(r_accept.status_code == 200, "delegate_e2e_b acepta la invitación vía API A")

    r_assignments = b.get(f"/campaigns/{campaign_id}/election-day/assignments", tokens_b["manager"])
    check(r_assignments.status_code == 200, "listado de asignaciones de jornada vía API B")
    matches = [
        item for item in r_assignments.json()["items"]
        if item["assignment_role"] == "ACT_VALIDATOR"
    ]
    check(len(matches) >= 1, "API B ve al menos una asignación ACT_VALIDATOR (la recién aceptada) sin esperar ni resincronizar")


def _cleanup(b: ApiClient, tokens_b: dict, campaign_id: str, session_id: str | None) -> None:
    if session_id:
        try:
            r = b.get(f"/campaigns/{campaign_id}/election-day/admin-support/current", tokens_b["admin"])
            if r.status_code == 200 and r.json() is not None:
                b.post(f"/campaigns/{campaign_id}/election-day/admin-support/end", tokens_b["admin"])
        except httpx.HTTPError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-a", required=True, help="Base URL de la instancia A, p.ej. http://localhost:18101/api/v1")
    parser.add_argument("--api-b", required=True, help="Base URL de la instancia B, p.ej. http://localhost:18102/api/v1")
    parser.add_argument("--password", default=None, help="Contraseña compartida de los usuarios E2E (por defecto: $E2E_USER_PASSWORD)")
    parser.add_argument(
        "--force", action="store_true",
        help="Omite el guardia de seguridad que exige localhost/127.0.0.1 en --api-a/--api-b",
    )
    args = parser.parse_args()

    # Guardia de seguridad: este script escribe datos sintéticos y termina
    # sesiones de soporte admin — jamás debe poder apuntarse por error a un
    # entorno real.
    if os.environ.get("APP_ENV") == "production":
        print("FALLO: APP_ENV=production en el entorno que ejecuta este script. Abortando.", file=sys.stderr)
        return 1
    if not args.force and not any(host in args.api_a for host in ("localhost", "127.0.0.1")):
        print(
            "FALLO: --api-a no apunta a localhost/127.0.0.1. Este script solo debe correr contra la "
            "topología de prueba de docker-compose.multi-instance.yml. Usa --force si estás seguro.",
            file=sys.stderr,
        )
        return 1

    password = args.password or os.environ.get("E2E_USER_PASSWORD")
    if not password:
        print("FALLO: falta --password o la variable de entorno E2E_USER_PASSWORD.", file=sys.stderr)
        return 1

    a = ApiClient("API A", args.api_a)
    b = ApiClient("API B", args.api_b)

    session_id = None
    tokens_b: dict = {}
    campaign_id = ""
    try:
        tokens_a, tokens_b, campaign_id = scenario_a_login(a, b, password)
        scenario_b_campaign_state(a, b, tokens_a, tokens_b, campaign_id)
        session_id = scenario_c_admin_support(a, b, tokens_a, tokens_b, campaign_id)
        draft = scenario_d_act_draft(a, b, tokens_a, tokens_b, campaign_id, "E2E-ACT-REC-01-J01")
        scenario_e_claim_conflict(a, b, tokens_a, tokens_b, campaign_id, draft)
        scenario_f_validate_control_center(a, b, tokens_a, tokens_b, campaign_id, draft)
        scenario_g_idempotency(a, b, tokens_a, tokens_b, campaign_id)
        scenario_h_invitation(a, b, tokens_a, tokens_b, campaign_id, password)
    except Failure as exc:
        print(f"\nFALLO: {exc}", file=sys.stderr)
        return 1
    except httpx.HTTPError as exc:
        print(f"\nFALLO: error de red/HTTP inesperado: {exc}", file=sys.stderr)
        return 1
    finally:
        _cleanup(b, tokens_b, campaign_id, session_id)

    print("\nTodos los escenarios A-H pasaron: api-a y api-b sirven estado coherente vía PostgreSQL compartido.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
