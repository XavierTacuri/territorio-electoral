"""Fase 3 §33 — verificación manual de rendimiento del Centro de Control
contra PostgreSQL real: confirma que `control_center_summary` ejecuta un
número de consultas SQL aproximadamente CONSTANTE (agregaciones), nunca
proporcional a la cantidad de actas (lo que delataría un N+1 real).
Ejecutar dentro del contenedor `api` del docker-compose.yml de desarrollo:

    docker compose run --rm api python -m scripts.verify_control_center_performance

Crea datos sintéticos con los mismos identificadores reservados que
verify_acts_concurrency.py (CC-PROC-%, CC-SRC-%, cc_*) para que
cleanup_acts_concurrency_fixtures.py los limpie sin cambios. Nunca corre
con APP_ENV=production, igual que los demás scripts de esta carpeta.
"""
from datetime import date
from uuid import uuid4

from sqlalchemy import create_engine, event

from app.core.config import settings
from app.services.election_act_service import ElectionActService
from scripts.verify_acts_concurrency import Session, setup

N_EXTRA_BOARDS = 200


def _add_bulk_validated_acts(ids, n):
    """Crea y valida N actas adicionales en juntas nuevas del mismo recinto,
    para que el conteo de consultas se mida bajo un volumen realista de
    escrutinio (cientos de JRV), no solo el puñado de juntas de setup()."""
    from app.models.election_day import ElectoralBoard
    from app.schemas.election_act import ElectionActDraftCreate, ElectionActResultInput, ElectionActValidateRequest

    for i in range(n):
        db = Session()
        try:
            from app.models.user import User
            delegate = db.get(User, ids["delegate1_id"])
            validator = db.get(User, ids["validator1_id"])
            service = ElectionActService(db)
            board = ElectoralBoard(
                polling_place_id=ids["place_id"], official_code=f"CC-PERF-J{i:04d}",
                board_number=100 + i, registered_voters=300, is_active=True,
            )
            db.add(board)
            db.flush()
            data = ElectionActDraftCreate(
                polling_place_id=ids["place_id"], electoral_board_id=board.id, electoral_contest_id=ids["contest_id"],
                blank_ballots=1, null_ballots=1, valid_ballots=10, ballots_counted=12,
                results=[ElectionActResultInput(electoral_candidate_id=ids["candidate_id"], votes=10)],
            )
            act, revision = service.create_draft(ids["campaign_id"], data, delegate)
            jpeg = b"\xff\xd8\xff" + b"\x00" * 32
            service.upload_evidence(ids["campaign_id"], act.id, revision.id, delegate, file_bytes=jpeg, original_filename=f"perf-{i}.jpg", client_generated_id=None)
            service.submit_revision(ids["campaign_id"], act.id, revision.id, delegate)
            service.claim(ids["campaign_id"], act.id, validator)
            service.validate_act(ids["campaign_id"], act.id, ElectionActValidateRequest(revision_id=revision.id), validator)
        finally:
            db.close()


def main():
    if settings.app_env.lower() == "production":
        raise SystemExit("Este script crea datos sintéticos y nunca debe correr con APP_ENV=production")

    print(f"Creando fixtures base y {N_EXTRA_BOARDS} actas validadas adicionales…")
    ids = setup()
    _add_bulk_validated_acts(ids, N_EXTRA_BOARDS)

    engine = create_engine(settings.database_url)
    queries = []

    def on_execute(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(engine, "before_cursor_execute", on_execute)
    db = engine.connect()
    try:
        from sqlalchemy.orm import Session as OrmSession
        session = OrmSession(bind=db)
        from app.models.user import User
        executive = session.get(User, ids["executive_id"])
        queries.clear()
        ElectionActService(session).control_center_summary(ids["campaign_id"], executive)
        n = len(queries)
        session.close()
    finally:
        event.remove(engine, "before_cursor_execute", on_execute)
        db.close()
        engine.dispose()

    print(f"\nconsultas SQL ejecutadas por control_center_summary con {N_EXTRA_BOARDS + 2} JRV validadas: {n}")
    for q in queries:
        print(" -", " ".join(q.split())[:140])
    # Un N+1 real haría este número crecer con N_EXTRA_BOARDS (cientos de
    # consultas); las agregaciones SQL de control_center_summary emiten un
    # puñado fijo de SELECT sin importar cuántas actas existan.
    assert n < 18, f"Se esperaban menos de 18 consultas (agregaciones), hubo {n} — posible N+1."
    print("OK: el número de consultas es constante, no proporcional a la cantidad de actas (sin N+1).")


if __name__ == "__main__":
    main()
