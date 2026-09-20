"""§8 audit Fase 4A: concurrent `complete()` for the same upload intent must
resolve to exactly ONE `ElectionActEvidence` row, using the DB's own unique
constraint — never an in-memory lock (which wouldn't help across multiple
API instances anyway).

Every other test in this suite runs against an in-memory SQLite database
(see conftest.py's `db` fixture) — sufficient for almost everything, but
SQLite's single-writer locking doesn't exercise genuine concurrent-transaction
behavior the way Postgres's MVCC does, and the task explicitly asked for this
one scenario to be proven against real PostgreSQL. This module is the only
place in the suite that does that: it opens two independent connections
against the actual `db` service from docker-compose.yml (the same one the
dev API container uses), in a throwaway schema it creates and drops itself
so it never touches real data, and never runs unless that database is
reachable (skipped otherwise — e.g. outside the dev Docker Compose stack)."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from hashlib import sha256

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.models.campaign import Campaign
from app.models.election_day import ElectionAct, ElectionActEvidence, ElectionActRevision, ElectionDayAssignment, ElectionDayOperation, ElectoralBoard, PollingPlace
from app.models.historical import DataSource, ElectoralContest, ElectoralProcess
from app.models.organization import Organization, OrganizationSubscription
from app.models.territory import Canton, Parish, Province
from app.models.user import User
from app.services.artifact_storage import HeadResult, LocalArtifactStorage, S3ArtifactStorage
from app.services.artifact_upload_token import create_artifact_upload_token
from app.services.election_act_service import ElectionActService
from app.services.role_service import RoleService

# The app's own configured database — postgresql+psycopg://...@db:5432/...
# in the dev docker-compose stack, and CI's real `postgres` service
# (localhost:5432) in GitHub Actions. NOT the ephemeral SQLite the `db`
# pytest fixture uses for everything else (see module docstring above) —
# this is the one test in the suite that deliberately bypasses that fixture.
_DATABASE_URL = settings.database_url
_SCHEMA = f"test_race_4a_{uuid.uuid4().hex[:10]}"


def _postgres_reachable() -> bool:
    if _DATABASE_URL.startswith("sqlite"):
        return False
    try:
        engine = create_engine(_DATABASE_URL, connect_args={"connect_timeout": 2})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(
    not _postgres_reachable(),
    reason="requiere la Postgres real configurada en settings.database_url (docker-compose 'db' o el servicio postgres de CI); no disponible aquí",
)


@pytest.fixture
def pg_engine():
    bootstrap = create_engine(_DATABASE_URL, isolation_level="AUTOCOMMIT")
    with bootstrap.connect() as conn:
        conn.execute(text(f'CREATE SCHEMA "{_SCHEMA}"'))
    bootstrap.dispose()
    # public stays on the search_path (after our schema) so PostGIS's
    # `geometry` type — installed once per database, in public — stays
    # resolvable; tables still get created in our schema since it's first.
    engine = create_engine(_DATABASE_URL, connect_args={"options": f"-c search_path={_SCHEMA},public"})
    # checkfirst=False is required here: with checkfirst=True (the default),
    # SQLAlchemy's existence probe sees the app's real tables already
    # present in `public` (via search_path) and concludes ours "already
    # exist", silently skipping creation in our schema — leaving it empty,
    # so every unqualified INSERT/SELECT would then silently resolve
    # against `public` instead (a well-known create_all()+custom-schema
    # pitfall). Force unconditional creation instead.
    Base.metadata.create_all(engine, checkfirst=False)
    try:
        yield engine
    finally:
        engine.dispose()
        cleanup = create_engine(_DATABASE_URL, isolation_level="AUTOCOMMIT")
        with cleanup.connect() as conn:
            conn.execute(text(f'DROP SCHEMA "{_SCHEMA}" CASCADE'))
        cleanup.dispose()


@pytest.fixture
def pg_session_factory(pg_engine):
    return sessionmaker(bind=pg_engine, expire_on_commit=False)


@pytest.fixture
def pg_fixture(pg_session_factory, tmp_path):
    """Minimal real graph — one campaign/operation/recinto/junta/acta en
    SCRUTINY con una revisión DRAFT, un delegado asignado — built directly
    against the real Postgres schema above."""
    with pg_session_factory() as db:
        RoleService(db).initialize_roles()
        admin_role = RoleService(db).repository.get_by_code("ADMIN")
        delegate_role = RoleService(db).repository.get_by_code("TERRITORIAL_COORDINATOR")
        admin = User(email="admin-race@example.test", username="admin_race", first_name="Admin", last_name="Race", hashed_password=hash_password("AdminPass123"), is_active=True, is_superuser=True, roles=[admin_role])
        db.add(admin); db.commit(); db.refresh(admin)

        # Campaign.organization_id column-defaults to this fixed UUID when
        # not passed explicitly (see app/models/campaign.py) — the SQLite
        # test suite never notices because SQLAlchemy's sqlite3 driver
        # doesn't enforce FKs by default; real Postgres does, so the row
        # this default points at must actually exist here.
        default_org_id = uuid.UUID("00000000-0000-0000-0000-000000002801")
        org = Organization(id=default_org_id, name="Organización Race", slug=f"org-race-{uuid.uuid4().hex[:8]}", status="ACTIVE")
        db.add(org); db.flush()
        db.add(OrganizationSubscription(organization_id=org.id, plan_code="STANDARD", status="ACTIVE"))
        db.commit()

        province = Province(code="97", name="Provincia Race"); db.add(province); db.flush()
        canton = Canton(province_id=province.id, code="01", dpa_code="9701", name="Cantón Race"); db.add(canton); db.flush()
        parish = Parish(canton_id=canton.id, code="01", dpa_code="970101", name="Parroquia Race", parish_type="URBAN"); db.add(parish); db.flush()
        campaign = Campaign(name="Campaña Race", slug=f"race-{uuid.uuid4().hex[:8]}", canton_id=canton.id, office_type="MAYOR", election_name="Elección Race", election_date=date(2027, 2, 14), status="ACTIVE", created_by_user_id=admin.id, organization_id=org.id)
        db.add(campaign); db.flush()
        source = DataSource(code=f"RACE-{uuid.uuid4().hex[:6]}", institution="Fuente sintética", dataset_name="Race", dataset_type="CNE_POLLING_PLACES", created_by_user_id=admin.id)
        db.add(source); db.flush()
        process = ElectoralProcess(code=f"RACE-P-{uuid.uuid4().hex[:6]}", name="Proceso Race", process_type="SECTIONAL", election_date=date(2027, 2, 14), year=2027, status="VALIDATED", is_final=True, source_id=source.id, is_active=True)
        db.add(process); db.flush()
        contest = ElectoralContest(electoral_process_id=process.id, office_type="MAYOR", name="Alcaldía Race", vote_method="SINGLE_CHOICE", canton_id=canton.id, seats=1, is_active=True)
        db.add(contest); db.flush()
        place = PollingPlace(electoral_process_id=process.id, province_id=province.id, canton_id=canton.id, parish_id=parish.id, official_code="R01", name="Recinto Race", is_active=True, data_source_id=source.id)
        db.add(place); db.flush()
        board = ElectoralBoard(polling_place_id=place.id, official_code="J01", board_number=1, registered_voters=300, is_active=True)
        db.add(board); db.flush()
        delegate = User(email="delegate-race@example.test", username="delegate_race", first_name="Delegate", last_name="Race", hashed_password=hash_password("DelegatePass123"), is_active=True, roles=[delegate_role])
        db.add(delegate); db.flush()
        op = ElectionDayOperation(organization_id=org.id, campaign_id=campaign.id, electoral_process_id=process.id, election_date=campaign.election_date, status="SCRUTINY")
        db.add(op); db.flush()
        assignment = ElectionDayAssignment(operation_id=op.id, user_id=delegate.id, assignment_role="POLLING_PLACE_DELEGATE", polling_place_id=place.id, status="CONFIRMED", assigned_by_user_id=admin.id)
        db.add(assignment); db.flush()
        act = ElectionAct(organization_id=campaign.organization_id, campaign_id=campaign.id, operation_id=op.id, polling_place_id=place.id, electoral_board_id=board.id, electoral_contest_id=contest.id, status="RECEIVED", latest_revision_number=1)
        db.add(act); db.flush()
        revision = ElectionActRevision(act_id=act.id, revision_number=1, revision_type="INITIAL", status="DRAFT", submitted_by_user_id=delegate.id, blank_ballots=0, null_ballots=0, valid_ballots=0, ballots_counted=0)
        db.add(revision); db.flush()
        db.commit()
        return {
            "campaign_id": campaign.id, "operation_id": op.id, "act_id": act.id, "revision_id": revision.id,
            "delegate_id": delegate.id, "storage_root": str(tmp_path),
        }


def test_concurrent_complete_against_real_postgres_yields_exactly_one_evidence(pg_session_factory, pg_fixture):
    jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 64
    digest = sha256(jpeg_bytes).hexdigest()
    client_generated_id = uuid.uuid4()

    with pg_session_factory() as intent_db:
        storage = LocalArtifactStorage(pg_fixture["storage_root"], 15)
        service = ElectionActService(intent_db, storage=storage)
        delegate = intent_db.get(User, pg_fixture["delegate_id"])
        intent = service.create_upload_intent(
            pg_fixture["campaign_id"], pg_fixture["act_id"], pg_fixture["revision_id"], delegate,
            client_generated_id=client_generated_id, original_filename="acta.jpg", mime_type="image/jpeg",
            size_bytes=len(jpeg_bytes), sha256=digest,
        )
        assert intent.mode == "API_PROXY"  # LocalArtifactStorage: no presigned S3 in this scenario
        # Simulate the pending upload directly (this test targets the DB race
        # in complete(), not the S3 wire protocol — that's covered elsewhere).
        upload_token = create_artifact_upload_token(
            campaign_id=pg_fixture["campaign_id"], operation_id=pg_fixture["operation_id"], act_id=pg_fixture["act_id"],
            revision_id=pg_fixture["revision_id"], user_id=pg_fixture["delegate_id"], client_generated_id=client_generated_id,
            pending_key="unused", size_bytes=len(jpeg_bytes), mime_type="image/jpeg", sha256=digest,
            original_filename="acta.jpg", expires_in_seconds=300,
        )

    results: list = []
    errors: list = []

    def attempt_complete():
        with pg_session_factory() as thread_db:
            try:
                delegate = thread_db.get(User, pg_fixture["delegate_id"])
                # Both threads race to promote/insert for the SAME pending
                # upload — route through the actual S3-mode complete_upload
                # branch (isinstance(storage, S3ArtifactStorage)) via a fake
                # that IS an S3ArtifactStorage subclass, same pattern as
                # FakeS3EvidenceStorage in test_election_act_evidence_upload_intent.py.
                fake_s3 = _FakeConcurrentS3(pg_fixture["storage_root"], jpeg_bytes, "image/jpeg", digest)
                service = ElectionActService(thread_db, storage=fake_s3)
                evidence = service.complete_upload(
                    pg_fixture["campaign_id"], pg_fixture["act_id"], pg_fixture["revision_id"], delegate,
                    upload_token=upload_token,
                )
                results.append(evidence.id)
            except Exception as exc:  # noqa: BLE001 - captured for assertion below
                errors.append(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt_complete) for _ in range(2)]
        for f in futures:
            f.result()

    assert not errors, f"complete_upload no debe propagar errores en la carrera: {errors}"
    assert len(results) == 2
    assert results[0] == results[1], "ambos hilos deben resolver a la MISMA evidencia"

    with pg_session_factory() as check_db:
        rows = list(check_db.scalars(
            select(ElectionActEvidence).where(
                ElectionActEvidence.revision_id == pg_fixture["revision_id"],
                ElectionActEvidence.client_generated_id == client_generated_id,
            )
        ))
        assert len(rows) == 1, "la restricción UNIQUE de Postgres debe garantizar una sola fila, nunca dos"


class _FakeConcurrentS3(S3ArtifactStorage):
    """A real S3ArtifactStorage subclass (so `isinstance(storage,
    S3ArtifactStorage)` in complete_upload takes the S3 branch), backed by a
    LocalArtifactStorage instead of a real boto3 client — the point of this
    test is the Postgres-level race in complete(), not S3 wire semantics
    (already covered against a Stubber in test_artifact_storage_s3.py)."""

    def __init__(self, root, data, content_type, sha256_hex):
        super().__init__(client=None, bucket="race-bucket", prefix="evidence", max_file_mb=15)
        self._local = LocalArtifactStorage(root, 15)
        self._content_type = content_type
        self._sha256_hex = sha256_hex
        import tempfile
        from pathlib import Path

        handle, name = tempfile.mkstemp(suffix=".jpg")
        path = Path(name)
        path.write_bytes(data)
        try:
            self._key, self._size, _ = self._local.store(path, "jpg")
        finally:
            path.unlink(missing_ok=True)

    def head_metadata(self, key):
        if not self._local.exists(self._key):
            return None
        return HeadResult(size_bytes=self._size, content_type=self._content_type, checksum_sha256_hex=self._sha256_hex)

    def promote_pending(self, pending_key):
        # Idempotent from the losing racer's perspective: if the winner
        # already deleted the object, treat promotion as already done.
        return self._key

    def delete(self, key):
        return self._local.delete(key)

    def exists(self, key):
        return self._local.exists(key)
