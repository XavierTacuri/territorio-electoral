"""Fase 4C.6 — exporta a JSON los identificadores reales del fixture E2E
(app.scripts.seed_e2e) que loadtests/k6 necesita: campaña, recinto/junta con
un delegado asignado y en jornada ACTIVA (para el escenario de escritura de
incidencias), y conteos del dataset para documentar su volumen real.

Nunca inventa IDs: los consulta contra la base real ya sembrada. Requiere
que app.scripts.seed_e2e ya se haya ejecutado. Solo lectura — no modifica
ninguna fila.

Uso (dentro del contenedor api del stack docker-compose.e2e.yml):
    python -m scripts.export_loadtest_fixture > /tmp/loadtest_fixture.json
"""

import json

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.campaign import Campaign
from app.models.election_day import ElectionDayAssignment, ElectionDayOperation, ElectoralBoard, PollingPlace
from app.models.user import User


def main() -> None:
    with SessionLocal() as db:
        campaign = db.scalar(select(Campaign).where(Campaign.slug == "gualaceo-e2e-2027"))
        if not campaign:
            raise SystemExit("Fixture 'gualaceo-e2e-2027' no encontrado — ejecuta app.scripts.seed_e2e primero")
        operation = db.scalar(select(ElectionDayOperation).where(ElectionDayOperation.campaign_id == campaign.id))
        delegate = db.scalar(select(User).where(User.username == "delegate_e2e_a"))
        assignment = db.scalar(
            select(ElectionDayAssignment).where(
                ElectionDayAssignment.operation_id == operation.id,
                ElectionDayAssignment.user_id == delegate.id,
            )
        )
        board = db.scalar(select(ElectoralBoard).where(ElectoralBoard.polling_place_id == assignment.polling_place_id))

        polling_place_count = db.scalar(select(func.count()).select_from(PollingPlace))
        board_count = db.scalar(select(func.count()).select_from(ElectoralBoard))
        user_count = db.scalar(select(func.count()).select_from(User))

        fixture = {
            "campaign_id": str(campaign.id),
            "campaign_slug": campaign.slug,
            "operation_id": str(operation.id),
            "operation_status": operation.status,
            "polling_place_id": str(assignment.polling_place_id),
            "board_id": str(board.id) if board else None,
            "delegate_username": delegate.username,
            "dataset_counts": {
                "polling_places_total": polling_place_count,
                "electoral_boards_total": board_count,
                "users_total": user_count,
            },
        }
        print(json.dumps(fixture, indent=2))


if __name__ == "__main__":
    main()
