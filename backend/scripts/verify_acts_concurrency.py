"""Fase 2 — verificación manual de concurrencia real contra PostgreSQL
(no forma parte de la suite pytest, que corre en SQLite y no puede probar
SELECT ... FOR UPDATE ni carreras de UNIQUE reales). Ejecutar dentro del
contenedor `api` del docker-compose.yml de desarrollo:

    docker compose run --rm api python -m scripts.verify_acts_concurrency

Este script NUNCA se ejecuta automáticamente (no es parte de ningún
entrypoint, CMD de Docker, migración ni pipeline de CI) y crea datos
sintéticos claramente identificables (campañas "Concurrencia %", usuarios
"cc_*"). Aun así rechaza correr contra APP_ENV=production como salvaguarda
explícita — igual que scripts/seed_e2e.py rechaza correr fuera de
APP_ENV=e2e — para que un DATABASE_URL mal apuntado nunca escriba estos
datos de prueba en una base productiva.

Escenarios:
  A) Dos hilos crean un borrador para la misma (operación, junta, contienda)
     al mismo tiempo -> exactamente uno gana, el otro recibe 409/Conflict.
  B) Un acta ya enviada: dos hilos intentan reclamarla (claim) al mismo
     tiempo -> exactamente uno la reclama, el otro recibe 409/Conflict.
  C) validated_revision_id no puede apuntar a la revisión de OTRA acta
     (FK compuesta, §8 auditoría).
  D) Fase 3 §30: mientras una validación real ocurre, lecturas concurrentes
     del Centro de Control nunca ven un estado parcial y ven el resultado
     validado exactamente una vez tras el commit (sin duplicar por reintentos).
"""
import threading
from datetime import date
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import hash_password
from app.models.assignments import CampaignUser
from app.models.campaign import Campaign
from app.models.organization import OrganizationMembership
from app.models.election_day import ElectionAct, ElectionActRevision, ElectionDayAssignment, ElectionDayOperation, ElectoralBoard, PollingPlace
from app.models.historical import DataSource, ElectoralCandidate, ElectoralContest, ElectoralProcess
from app.models.territory import Canton, Parish, Province
from app.models.user import User
from app.schemas.election_act import ElectionActDraftCreate, ElectionActResultInput, ElectionActValidateRequest
from app.schemas.election_day import ElectionDayAssignmentCreate, ElectionDayOperationCreate
from app.services.election_act_service import ElectionActService
from app.services.election_day_service import ElectionDayService
from app.services.evidence_storage_service import LocalEvidenceStorage
from app.services.exceptions import ConflictError
from app.services.role_service import RoleService

engine = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)


def setup():
    db = Session()
    RoleService(db).initialize_roles()
    suffix = uuid4().hex[:8]
    # Identificador de territorio fijo y reservado (nunca un DPA real):
    # get-or-create, no un insert ciego — Province.code/name son UNIQUE en
    # todo el sistema con solo 100 valores posibles, así que un id aleatorio
    # nuevo en cada corrida eventualmente choca contra el mismo puñado de
    # filas sintéticas que corridas manuales anteriores de este script (que,
    # al fallar a mitad de camino después de que CampaignService ya hizo su
    # propio commit interno, dejan esas filas de territorio persistidas).
    rand_id = 989898
    province = db.get(Province, rand_id)
    if not province:
        province = Province(id=rand_id, code="98", name="Provincia Verificación Concurrencia")
        db.add(province)
        db.flush()
    canton = db.get(Canton, rand_id)
    if not canton:
        canton = Canton(id=rand_id, province_id=rand_id, code="01", dpa_code="9801", name="Cantón Verificación Concurrencia")
        db.add(canton)
        db.flush()
    parish = db.get(Parish, rand_id)
    if not parish:
        parish = Parish(id=rand_id, canton_id=rand_id, code="01", dpa_code="980101", name="Parroquia Verificación Concurrencia", parish_type="URBAN")
        db.add(parish)
        db.flush()

    admin_role = RoleService(db).repository.get_by_code("ADMIN")
    executive_role = RoleService(db).repository.get_by_code("CANDIDATE")
    delegate_role = RoleService(db).repository.get_by_code("TERRITORIAL_COORDINATOR")
    validator_role = RoleService(db).repository.get_by_code("ANALYST")
    admin = User(email=f"cc-admin-{suffix}@example.test", username=f"cc_admin_{suffix}", first_name="CC", last_name="Admin", hashed_password=hash_password("Pass12345"), is_active=True, is_superuser=True, roles=[admin_role])
    executive = User(email=f"cc-exec-{suffix}@example.test", username=f"cc_exec_{suffix}", first_name="CC", last_name="Exec", hashed_password=hash_password("Pass12345"), is_active=True, roles=[executive_role])
    delegate1 = User(email=f"cc-d1-{suffix}@example.test", username=f"cc_d1_{suffix}", first_name="CC", last_name="D1", hashed_password=hash_password("Pass12345"), is_active=True, roles=[delegate_role])
    validator1 = User(email=f"cc-v1-{suffix}@example.test", username=f"cc_v1_{suffix}", first_name="CC", last_name="V1", hashed_password=hash_password("Pass12345"), is_active=True, roles=[validator_role])
    validator2 = User(email=f"cc-v2-{suffix}@example.test", username=f"cc_v2_{suffix}", first_name="CC", last_name="V2", hashed_password=hash_password("Pass12345"), is_active=True, roles=[validator_role])
    db.add_all([admin, executive, delegate1, validator1, validator2])
    db.flush()

    from app.schemas.campaign import CampaignCreate
    from app.services.campaign_service import CampaignService
    campaign = CampaignService(db).create(CampaignCreate(name=f"Concurrencia {suffix}", slug=f"concurrencia-{suffix}", canton_id=canton.id, office_type="MAYOR", election_name="Elección concurrencia", election_date=date(2027, 2, 14), status="ACTIVE"), admin)
    db.add(OrganizationMembership(organization_id=campaign.organization_id, user_id=executive.id, organization_role="MEMBER", status="ACTIVE"))
    for member in (executive, delegate1, validator1, validator2):
        db.add(CampaignUser(campaign_id=campaign.id, user_id=member.id, assigned_by_user_id=admin.id, is_active=True))
    db.flush()

    source = DataSource(code=f"CC-SRC-{suffix}", institution="Institución sintética", dataset_name="Concurrencia", dataset_type="CNE_POLLING_PLACES", created_by_user_id=admin.id)
    db.add(source)
    db.flush()
    process = ElectoralProcess(code=f"CC-PROC-{suffix}", name="Proceso concurrencia", process_type="SECTIONAL", election_date=date(2027, 2, 14), year=2027, status="VALIDATED", is_final=True, source_id=source.id, is_active=True)
    db.add(process)
    db.flush()
    contest = ElectoralContest(electoral_process_id=process.id, office_type="MAYOR", name="Alcaldía concurrencia", vote_method="SINGLE_CHOICE", seats=1, canton_id=canton.id, is_active=True)
    db.add(contest)
    db.flush()
    candidate = ElectoralCandidate(electoral_contest_id=contest.id, external_code=f"CC-CAND-{suffix}", full_name="Candidata Concurrencia", source_id=source.id, is_active=True)
    db.add(candidate)
    place = PollingPlace(electoral_process_id=process.id, province_id=province.id, canton_id=canton.id, parish_id=parish.id, official_code=f"CC-{suffix}", name="Recinto Concurrencia", is_active=True, data_source_id=source.id)
    db.add(place)
    db.flush()
    board = ElectoralBoard(polling_place_id=place.id, official_code=f"CC-{suffix}-J01", board_number=1, registered_voters=300, is_active=True)
    db.add(board)
    board2 = ElectoralBoard(polling_place_id=place.id, official_code=f"CC-{suffix}-J02", board_number=2, registered_voters=300, is_active=True)
    db.add(board2)
    board3 = ElectoralBoard(polling_place_id=place.id, official_code=f"CC-{suffix}-J03", board_number=3, registered_voters=300, is_active=True)
    db.add(board3)
    board4 = ElectoralBoard(polling_place_id=place.id, official_code=f"CC-{suffix}-J04", board_number=4, registered_voters=300, is_active=True)
    db.add(board4)
    db.flush()

    svc = ElectionDayService(db)
    op = svc.create_operation(campaign.id, ElectionDayOperationCreate(electoral_process_id=process.id, election_date=date(2027, 2, 14)), executive)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=delegate1.id, assignment_role="POLLING_PLACE_DELEGATE", polling_place_id=place.id), executive)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=validator1.id, assignment_role="ACT_VALIDATOR"), executive)
    svc.create_assignment(campaign.id, ElectionDayAssignmentCreate(user_id=validator2.id, assignment_role="ACT_VALIDATOR"), executive)
    op = svc.open_operation(campaign.id, executive)
    op = svc.start_scrutiny(campaign.id, executive)
    db.commit()
    ids = dict(campaign_id=campaign.id, place_id=place.id, board_id=board.id, board2_id=board2.id, board3_id=board3.id, board4_id=board4.id, contest_id=contest.id, candidate_id=candidate.id, executive_id=executive.id, delegate1_id=delegate1.id, validator1_id=validator1.id, validator2_id=validator2.id)
    db.close()
    return ids


def scenario_a_duplicate_draft(ids):
    print("\n=== Escenario A: dos hilos crean un borrador para la misma junta+contienda ===")
    results = {}

    def attempt(name):
        db = Session()
        try:
            delegate = db.get(User, ids["delegate1_id"])
            service = ElectionActService(db)
            data = ElectionActDraftCreate(
                polling_place_id=ids["place_id"], electoral_board_id=ids["board_id"], electoral_contest_id=ids["contest_id"],
                blank_ballots=1, null_ballots=1, valid_ballots=10, ballots_counted=12,
                results=[ElectionActResultInput(electoral_candidate_id=ids["candidate_id"], votes=10)],
            )
            act, revision = service.create_draft(ids["campaign_id"], data, delegate)
            results[name] = ("OK", act.id)
        except ConflictError as exc:
            results[name] = ("CONFLICT", str(exc))
        except Exception as exc:  # noqa: BLE001
            results[name] = ("ERROR", repr(exc))
        finally:
            db.close()

    barrier = threading.Barrier(2)

    def attempt_synced(name):
        barrier.wait()
        attempt(name)

    t1 = threading.Thread(target=attempt_synced, args=("t1",))
    t2 = threading.Thread(target=attempt_synced, args=("t2",))
    t1.start(); t2.start(); t1.join(); t2.join()
    print("resultados:", results)
    outcomes = [r[0] for r in results.values()]
    assert outcomes.count("OK") == 1, f"Se esperaba exactamente 1 OK, hubo: {outcomes}"
    assert outcomes.count("CONFLICT") == 1, f"Se esperaba exactamente 1 CONFLICT, hubo: {outcomes}"
    assert outcomes.count("ERROR") == 0, f"Nunca debe haber un 500 sin manejar, hubo: {results}"
    print("OK: exactamente un hilo creó el acta, el otro recibió 409/Conflict (nunca 500).")

    # §11 auditoría: la carrera perdedora no debe dejar revisiones/resultados
    # huérfanos — el rollback de la fila `act` ocurre ANTES de que exista
    # cualquier revisión, así que solo debe existir UNA acta con UNA
    # revisión (y sus resultados), nada más.
    from app.models.election_day import ElectionActResult
    db = Session()
    try:
        acts_for_board = list(db.scalars(select(ElectionAct).where(
            ElectionAct.operation_id.in_(select(ElectionDayOperation.id).where(ElectionDayOperation.campaign_id == ids["campaign_id"])),
            ElectionAct.electoral_board_id == ids["board_id"],
        )))
        assert len(acts_for_board) == 1, f"Se esperaba exactamente 1 ElectionAct para la junta, hubo {len(acts_for_board)}"
        revisions = list(db.scalars(select(ElectionActRevision).where(ElectionActRevision.act_id == acts_for_board[0].id)))
        assert len(revisions) == 1, f"Se esperaba exactamente 1 revisión, hubo {len(revisions)} (huérfanas?)"
        results_rows = list(db.scalars(select(ElectionActResult).where(ElectionActResult.revision_id == revisions[0].id)))
        assert len(results_rows) == 1, f"Se esperaba exactamente 1 resultado, hubo {len(results_rows)} (huérfanos?)"
        print("OK: sin revisiones ni resultados huérfanos tras la carrera.")
    finally:
        db.close()


def scenario_b_double_claim(ids):
    print("\n=== Escenario B: dos validadores reclaman la misma acta al mismo tiempo ===")
    db = Session()
    act = db.scalar(select(ElectionAct).where(ElectionAct.operation_id.in_(
        select(ElectionDayOperation.id).where(ElectionDayOperation.campaign_id == ids["campaign_id"])
    )))
    assert act is not None, "El escenario A debe haber creado un acta antes de este escenario"
    act_id = act.id
    delegate = db.get(User, ids["delegate1_id"])
    service = ElectionActService(db)
    _, revision = service.upload_evidence, None
    # Sube evidencia y envía la revisión para que el acta entre a la cola de validación.
    from app.services.election_act_service import ElectionActRevision
    rev = db.scalar(select(ElectionActRevision).where(ElectionActRevision.act_id == act_id))
    import tempfile
    from pathlib import Path
    jpeg = b"\xff\xd8\xff" + b"\x00" * 32
    service.upload_evidence(ids["campaign_id"], act_id, rev.id, delegate, file_bytes=jpeg, original_filename="acta.jpg", client_generated_id=None)
    service.submit_revision(ids["campaign_id"], act_id, rev.id, delegate)
    db.close()

    results = {}

    def attempt(name, user_id):
        db = Session()
        try:
            user = db.get(User, user_id)
            service = ElectionActService(db)
            act = service.claim(ids["campaign_id"], act_id, user)
            results[name] = ("OK", act.review_claimed_by_user_id)
        except ConflictError as exc:
            results[name] = ("CONFLICT", str(exc))
        except Exception as exc:  # noqa: BLE001
            results[name] = ("ERROR", repr(exc))
        finally:
            db.close()

    barrier = threading.Barrier(2)

    def attempt_synced(name, user_id):
        barrier.wait()
        attempt(name, user_id)

    t1 = threading.Thread(target=attempt_synced, args=("v1", ids["validator1_id"]))
    t2 = threading.Thread(target=attempt_synced, args=("v2", ids["validator2_id"]))
    t1.start(); t2.start(); t1.join(); t2.join()
    print("resultados:", results)
    outcomes = [r[0] for r in results.values()]
    assert outcomes.count("OK") == 1, f"Se esperaba exactamente 1 OK, hubo: {outcomes}"
    assert outcomes.count("CONFLICT") == 1, f"Se esperaba exactamente 1 CONFLICT, hubo: {outcomes}"
    print("OK: exactamente un validador reclamó el acta, el otro recibió 409/Conflict.")


def scenario_c_cross_act_validated_revision_id(ids):
    """§8 auditoría: la FK compuesta (id, validated_revision_id) ->
    revisions(act_id, id) debe rechazar, a nivel de PostgreSQL, que
    validated_revision_id de un acta apunte a la revisión de OTRA acta."""
    print("\n=== Escenario C: validated_revision_id no puede apuntar a la revisión de otra acta ===")
    db = Session()
    try:
        delegate = db.get(User, ids["delegate1_id"])
        service = ElectionActService(db)
        jpeg = b"\xff\xd8\xff" + b"\x00" * 32
        data1 = ElectionActDraftCreate(
            polling_place_id=ids["place_id"], electoral_board_id=ids["board2_id"], electoral_contest_id=ids["contest_id"],
            blank_ballots=1, null_ballots=1, valid_ballots=10, ballots_counted=12,
            results=[ElectionActResultInput(electoral_candidate_id=ids["candidate_id"], votes=10)],
        )
        act1, rev1 = service.create_draft(ids["campaign_id"], data1, delegate)
        service.upload_evidence(ids["campaign_id"], act1.id, rev1.id, delegate, file_bytes=jpeg, original_filename="a.jpg", client_generated_id=None)
        service.submit_revision(ids["campaign_id"], act1.id, rev1.id, delegate)

        data2 = ElectionActDraftCreate(
            polling_place_id=ids["place_id"], electoral_board_id=ids["board3_id"], electoral_contest_id=ids["contest_id"],
            blank_ballots=1, null_ballots=1, valid_ballots=10, ballots_counted=12,
            results=[ElectionActResultInput(electoral_candidate_id=ids["candidate_id"], votes=10)],
        )
        act2, rev2 = service.create_draft(ids["campaign_id"], data2, delegate)
        service.upload_evidence(ids["campaign_id"], act2.id, rev2.id, delegate, file_bytes=jpeg, original_filename="b.jpg", client_generated_id=None)
        service.submit_revision(ids["campaign_id"], act2.id, rev2.id, delegate)

        from sqlalchemy import text
        try:
            db.execute(text("UPDATE election_acts SET validated_revision_id = :rev WHERE id = :act"), {"rev": str(rev2.id), "act": str(act1.id)})
            db.commit()
            raise AssertionError("La FK compuesta debió rechazar validated_revision_id de otra acta, pero lo aceptó.")
        except IntegrityError:
            db.rollback()
            print("OK: PostgreSQL rechazó validated_revision_id apuntando a la revisión de otra acta (FK compuesta).")
    finally:
        db.close()


def scenario_d_control_center_never_sees_partial_validation(ids):
    """Fase 3 §30: mientras una validación real ocurre (claim + validate,
    cada uno su propia transacción con commit), muchos lectores del Centro
    de Control corren en paralelo. Por MVCC de PostgreSQL (READ COMMITTED),
    cada lectura debe ver o bien el estado ANTERIOR (0 votos, acta no
    validada) o bien el estado POSTERIOR COMPLETO (15 votos, acta validada)
    — nunca un estado intermedio, nunca duplicado."""
    print("\n=== Escenario D: el Centro de Control nunca ve una validación a medias ===")
    db = Session()
    try:
        delegate = db.get(User, ids["delegate1_id"])
        service = ElectionActService(db)
        data = ElectionActDraftCreate(
            polling_place_id=ids["place_id"], electoral_board_id=ids["board4_id"], electoral_contest_id=ids["contest_id"],
            blank_ballots=1, null_ballots=1, valid_ballots=15, ballots_counted=17,
            results=[ElectionActResultInput(electoral_candidate_id=ids["candidate_id"], votes=15)],
        )
        act, revision = service.create_draft(ids["campaign_id"], data, delegate)
        jpeg = b"\xff\xd8\xff" + b"\x00" * 32
        service.upload_evidence(ids["campaign_id"], act.id, revision.id, delegate, file_bytes=jpeg, original_filename="d.jpg", client_generated_id=None)
        service.submit_revision(ids["campaign_id"], act.id, revision.id, delegate)
        act_id, revision_id = act.id, revision.id
    finally:
        db.close()

    observed_votes = set()
    stop = threading.Event()
    read_count = [0]

    def reader():
        db = Session()
        try:
            executive = db.get(User, ids["executive_id"])
            while not stop.is_set():
                summary = ElectionActService(db).control_center_summary(ids["campaign_id"], executive)
                contest = next(c for c in summary["contests"] if str(c["contest_id"]) == str(ids["contest_id"]))
                votes = next((c["votes"] for c in contest["candidates"] if str(c["candidate_id"]) == str(ids["candidate_id"])), 0)
                observed_votes.add(votes)
                read_count[0] += 1
        finally:
            db.close()

    def validator_flow():
        db = Session()
        try:
            validator = db.get(User, ids["validator1_id"])
            svc = ElectionActService(db)
            svc.claim(ids["campaign_id"], act_id, validator)
            svc.validate_act(ids["campaign_id"], act_id, ElectionActValidateRequest(revision_id=revision_id), validator)
        finally:
            db.close()

    readers = [threading.Thread(target=reader) for _ in range(4)]
    for t in readers:
        t.start()
    validator_thread = threading.Thread(target=validator_flow)
    validator_thread.start()
    validator_thread.join()
    stop.set()
    for t in readers:
        t.join()

    print(f"lecturas totales: {read_count[0]}, valores de votos observados: {sorted(observed_votes)}")
    assert observed_votes <= {0, 15}, f"Se observó un estado intermedio/incorrecto: {observed_votes}"
    assert 15 in observed_votes, "Ningún lector vio el estado ya validado — ¿el validador falló?"

    db = Session()
    try:
        final = ElectionActService(db).control_center_summary(ids["campaign_id"], db.get(User, ids["executive_id"]))
        contest = next(c for c in final["contests"] if str(c["contest_id"]) == str(ids["contest_id"]))
        votes = next(c["votes"] for c in contest["candidates"] if str(c["candidate_id"]) == str(ids["candidate_id"]))
        assert votes == 15, f"Se esperaban 15 votos finales exactos (nunca duplicados por reintento), hubo {votes}"
    finally:
        db.close()
    print("OK: ninguna lectura vio un estado parcial; el voto validado aparece exactamente una vez.")


def main():
    if settings.app_env.lower() == "production":
        raise SystemExit("Este script crea datos sintéticos y nunca debe correr con APP_ENV=production")
    ids = setup()
    scenario_a_duplicate_draft(ids)
    scenario_b_double_claim(ids)
    scenario_c_cross_act_validated_revision_id(ids)
    scenario_d_control_center_never_sees_partial_validation(ids)
    print("\nTodos los escenarios de concurrencia real contra PostgreSQL pasaron.")


if __name__ == "__main__":
    main()
