"""Fase 4C.6 (segunda pasada) — genera recintos/juntas SINTETICOS adicionales
sobre el MISMO electoral_process del fixture E2E (`E2E_ELECTION_DAY_2027`),
para medir sensibilidad de las lecturas agregadas (dashboard/overview,
election-day/coverage, control-center) al tamano del dataset. Respeta
relaciones reales: cada PollingPlace nuevo usa una parish/canton/province
YA existentes en el fixture (cicla entre las 3 parroquias sembradas por
seed_e2e.py), mismo electoral_process_id, mismo data_source_id — nunca
inventa una parroquia/canton nueva ni rompe una FK.

NO usa multiplicadores de "estimacion de produccion real" — son
multiplicadores TECNICOS puros (S=1x ya sembrado, M=~10x, L=~30-50x) para
observar si el cuello de botella cambia con el volumen, no para predecir
cuantos recintos tendra una eleccion real.

Uso (dentro del contenedor api):
    python -m scripts.scale_loadtest_dataset --target-places 60   # ~M (10x sobre 6)
    python -m scripts.scale_loadtest_dataset --target-places 250  # ~L (~40x)

Idempotente: usa official_code determinista (LOADTEST-{n:05d}) y hace
upsert-like skip si ya existe. --reset elimina unicamente los recintos con
prefijo LOADTEST- (y sus juntas, boards con ON DELETE dependiente) antes de
generar — nunca toca datos de seed_e2e.py.
"""

import argparse

from sqlalchemy import delete, func, select

from app.db.session import SessionLocal
from app.models.campaign import Campaign
from app.models.election_day import ElectionDayOperation, ElectoralBoard, PollingPlace
from app.models.historical import DataSource, ElectoralProcess

LOADTEST_PREFIX = "LOADTEST-"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--target-places", type=int, required=True, help="Numero TOTAL deseado de polling_places sinteticos LOADTEST- (no cuenta los del fixture base).")
    p.add_argument("--boards-per-place", type=int, default=3)
    p.add_argument("--reset", action="store_true", help="Elimina los recintos LOADTEST- existentes antes de generar.")
    args = p.parse_args()

    with SessionLocal() as db:
        campaign = db.scalar(select(Campaign).where(Campaign.slug == "gualaceo-e2e-2027"))
        if not campaign:
            raise SystemExit("Fixture 'gualaceo-e2e-2027' no encontrado — ejecuta app.scripts.seed_e2e primero")
        process = db.scalar(select(ElectoralProcess).where(ElectoralProcess.code == "E2E_ELECTION_DAY_2027"))
        source = db.scalar(select(DataSource).where(DataSource.code == "E2E_ELECTION_DAY"))
        operation = db.scalar(select(ElectionDayOperation).where(ElectionDayOperation.campaign_id == campaign.id))
        # (parish_id, canton_id, province_id) tomados de los PollingPlace YA
        # sembrados por seed_e2e.py — evita depender de relaciones ORM
        # Parish->Canton no necesariamente configuradas, y garantiza que la
        # combinacion parish/canton/province sea exactamente una ya valida.
        base_locations = list(db.execute(
            select(PollingPlace.parish_id, PollingPlace.canton_id, PollingPlace.province_id)
            .where(PollingPlace.electoral_process_id == process.id, ~PollingPlace.official_code.like(f"{LOADTEST_PREFIX}%"))
            .distinct()
        ).all())
        if not base_locations:
            raise SystemExit("Sin recintos base — ejecuta ensure_election_day_fixture (via seed_e2e) primero")

        if args.reset:
            existing_ids = list(db.scalars(select(PollingPlace.id).where(PollingPlace.electoral_process_id == process.id, PollingPlace.official_code.like(f"{LOADTEST_PREFIX}%"))))
            if existing_ids:
                db.execute(delete(ElectoralBoard).where(ElectoralBoard.polling_place_id.in_(existing_ids)))
                db.execute(delete(PollingPlace).where(PollingPlace.id.in_(existing_ids)))
                db.commit()
            print(f"reset: {len(existing_ids)} recintos LOADTEST- eliminados")

        existing_count = db.scalar(select(func.count()).select_from(PollingPlace).where(PollingPlace.electoral_process_id == process.id, PollingPlace.official_code.like(f"{LOADTEST_PREFIX}%"))) or 0
        to_create = max(0, args.target_places - existing_count)
        created_places = 0
        created_boards = 0
        for i in range(existing_count, existing_count + to_create):
            code = f"{LOADTEST_PREFIX}{i:05d}"
            parish_id, canton_id, province_id = base_locations[i % len(base_locations)]
            place = PollingPlace(
                electoral_process_id=process.id,
                province_id=province_id,
                canton_id=canton_id,
                parish_id=parish_id,
                official_code=code,
                name=f"Recinto sintetico de carga {i:05d}",
                address=f"Direccion sintetica {i:05d}",
                latitude=-2.88 + (i % 100) * 0.0005,
                longitude=-78.77 + (i % 100) * 0.0005,
                is_active=True,
                data_source_id=source.id,
            )
            db.add(place)
            db.flush()
            created_places += 1
            for b in range(1, args.boards_per_place + 1):
                db.add(ElectoralBoard(
                    polling_place_id=place.id,
                    official_code=f"{code}-J{b:02d}",
                    board_number=b,
                    registered_voters=250 + b * 5,
                    is_active=True,
                    data_source_id=source.id,
                ))
                created_boards += 1
            if created_places % 25 == 0:
                db.commit()
        db.commit()

        total_places = db.scalar(select(func.count()).select_from(PollingPlace).where(PollingPlace.electoral_process_id == process.id)) or 0
        total_boards = db.scalar(select(func.count()).select_from(ElectoralBoard).join(PollingPlace).where(PollingPlace.electoral_process_id == process.id)) or 0
        print(f"creados: {created_places} recintos, {created_boards} juntas (prefijo {LOADTEST_PREFIX})")
        print(f"total en electoral_process {process.code}: {total_places} recintos, {total_boards} juntas")


if __name__ == "__main__":
    main()
