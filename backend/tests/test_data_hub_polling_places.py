from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.election_day import ElectoralBoard, PollingPlace
from app.models.historical import DataImportError, DataImportJob, DataSource, ElectoralProcess
from app.models.territory import Canton, Parish, Province
from app.schemas.historical import DataSourceCreate
from app.services.data_import_service import DataImportService
from app.services.data_source_service import DataSourceService
from app.services.exceptions import ConflictError

PP_HEADER = "process_code,province_dpa,canton_dpa,parish_dpa,polling_place_code,polling_place_name,polling_place_address,polling_place_latitude,polling_place_longitude\n"
BOARD_HEADER = "process_code,polling_place_code,board_code,board_number,sex_category,registered_voters\n"


@pytest.fixture
def ctx(db, admin):
    province = Province(code="70", name="Provincia DH")
    db.add(province)
    db.flush()
    canton = Canton(province_id=province.id, code="01", dpa_code="7001", name="Cantón DH")
    db.add(canton)
    db.flush()
    parish_a = Parish(canton_id=canton.id, code="01", dpa_code="700101", name="Parroquia DH A", parish_type="URBAN")
    parish_b = Parish(canton_id=canton.id, code="02", dpa_code="700102", name="Parroquia DH B", parish_type="RURAL")
    db.add_all([parish_a, parish_b])
    db.flush()
    other_province = Province(code="71", name="Otra Provincia DH")
    db.add(other_province)
    db.flush()
    foreign_canton = Canton(province_id=other_province.id, code="01", dpa_code="7101", name="Cantón Ajeno DH")
    db.add(foreign_canton)
    db.flush()
    process = ElectoralProcess(code=f"DH-PP-{uuid4().hex[:6].upper()}", name="Proceso DH", process_type="SECTIONAL", election_date=date(2027, 2, 14), year=2027, status="VALIDATED", is_final=True, source_id=None, is_active=True)
    source = DataSourceService(db).create(DataSourceCreate(code=f"DH_POLLING_{uuid4().hex[:6].upper()}", institution="Consejo Nacional Electoral", dataset_name="Recintos sintéticos", dataset_type="CNE_POLLING_PLACES", reference_date=date(2026, 1, 1)), admin)
    process.source_id = source.id
    db.add(process)
    db.commit()
    return source, process, province, canton, parish_a, parish_b, foreign_canton


def test_polling_place_requires_existing_process(db, admin, ctx):
    source, process, province, canton, parish_a, parish_b, foreign_canton = ctx
    content = (PP_HEADER + f"GHOST,{province.code},{canton.dpa_code},{parish_a.dpa_code},R01,Escuela Central,,,\n").encode()
    job = DataImportService(db).run(source.id, "CNE_POLLING_PLACES", "r.csv", content, admin, True, "CANONICAL_POLLING_PLACE")
    assert job.status == "REJECTED"
    error = db.scalar(select(DataImportError).where(DataImportError.import_job_id == job.id))
    assert "proceso" in error.message.lower()


def test_polling_place_dpa_hierarchy_regression(db, admin, ctx):
    source, process, province, canton, parish_a, parish_b, foreign_canton = ctx
    svc = DataImportService(db)
    good = (PP_HEADER + f"{process.code},{province.code},{canton.dpa_code},{parish_a.dpa_code},R01,Escuela Central,Av. Principal,-2.9,-78.8\n").encode()
    assert svc.run(source.id, "CNE_POLLING_PLACES", "ok.csv", good, admin, True, "CANONICAL_POLLING_PLACE").status == "VALIDATED"
    wrong_canton = (PP_HEADER + f"{process.code},{province.code},{foreign_canton.dpa_code},{parish_a.dpa_code},R02,Escuela Norte,,,\n").encode()
    job = svc.run(source.id, "CNE_POLLING_PLACES", "wc.csv", wrong_canton, admin, True, "CANONICAL_POLLING_PLACE")
    assert job.status == "REJECTED"
    error = db.scalar(select(DataImportError).where(DataImportError.import_job_id == job.id))
    assert "provincia" in error.message.lower() or "cantón" in error.message.lower()


def test_polling_place_rejects_coordinates_out_of_range(db, admin, ctx):
    source, process, province, canton, parish_a, parish_b, foreign_canton = ctx
    content = (PP_HEADER + f"{process.code},{province.code},{canton.dpa_code},{parish_a.dpa_code},R01,Escuela Central,,999,-78.8\n").encode()
    job = DataImportService(db).run(source.id, "CNE_POLLING_PLACES", "bad.csv", content, admin, True, "CANONICAL_POLLING_PLACE")
    assert job.status == "REJECTED"


def test_polling_place_coordinates_are_optional(db, admin, ctx):
    source, process, province, canton, parish_a, parish_b, foreign_canton = ctx
    content = (PP_HEADER + f"{process.code},{province.code},{canton.dpa_code},{parish_a.dpa_code},R01,Escuela Central,,,\n").encode()
    job = DataImportService(db).run(source.id, "CNE_POLLING_PLACES", "no-coords.csv", content, admin, False, "CANONICAL_POLLING_PLACE")
    assert job.status == "COMPLETED"
    place = db.scalar(select(PollingPlace).where(PollingPlace.official_code == "R01"))
    assert place.latitude is None and place.longitude is None


def test_polling_place_rejects_duplicate_code_within_file(db, admin, ctx):
    source, process, province, canton, parish_a, parish_b, foreign_canton = ctx
    content = (PP_HEADER + f"{process.code},{province.code},{canton.dpa_code},{parish_a.dpa_code},R01,Escuela Central,,,\n" + f"{process.code},{province.code},{canton.dpa_code},{parish_a.dpa_code},R01,Escuela Duplicada,,,\n").encode()
    job = DataImportService(db).run(source.id, "CNE_POLLING_PLACES", "dup.csv", content, admin, True, "CANONICAL_POLLING_PLACE")
    assert job.status == "REJECTED"
    error = db.scalar(select(DataImportError).where(DataImportError.import_job_id == job.id))
    assert "duplicado" in error.message.lower()


def test_polling_place_import_is_idempotent_and_upserts_by_code(db, admin, ctx):
    source, process, province, canton, parish_a, parish_b, foreign_canton = ctx
    svc = DataImportService(db)
    content = (PP_HEADER + f"{process.code},{province.code},{canton.dpa_code},{parish_a.dpa_code},R01,Escuela Central,,,\n").encode()
    first = svc.run(source.id, "CNE_POLLING_PLACES", "same.csv", content, admin, False, "CANONICAL_POLLING_PLACE")
    assert first.status == "COMPLETED" and first.rows_inserted == 1
    with pytest.raises(ConflictError):
        svc.run(source.id, "CNE_POLLING_PLACES", "same.csv", content, admin, False, "CANONICAL_POLLING_PLACE")
    # Same official code, different capitalization/name: upsert in place, never a second row.
    renamed = (PP_HEADER + f"{process.code},{province.code},{canton.dpa_code},{parish_a.dpa_code},r01,ESCUELA CENTRAL RENOMBRADA,,,\n").encode()
    second = svc.run(source.id, "CNE_POLLING_PLACES", "renamed.csv", renamed, admin, False, "CANONICAL_POLLING_PLACE", force=True)
    assert second.status == "COMPLETED" and second.rows_updated == 1
    places = list(db.scalars(select(PollingPlace).where(PollingPlace.electoral_process_id == process.id)))
    assert len(places) == 1
    assert places[0].name == "ESCUELA CENTRAL RENOMBRADA"


def test_polling_place_provenance_recorded(db, admin, ctx):
    source, process, province, canton, parish_a, parish_b, foreign_canton = ctx
    content = (PP_HEADER + f"{process.code},{province.code},{canton.dpa_code},{parish_a.dpa_code},R01,Escuela Central,,,\n").encode()
    job = DataImportService(db).run(source.id, "CNE_POLLING_PLACES", "prov.csv", content, admin, False, "CANONICAL_POLLING_PLACE")
    place = db.scalar(select(PollingPlace).where(PollingPlace.official_code == "R01"))
    assert place.data_source_id == source.id
    assert place.import_job_id == job.id


def test_polling_place_rejects_microdata_headers(db, admin, ctx):
    from app.services.exceptions import BusinessRuleError
    source, process, province, canton, parish_a, parish_b, foreign_canton = ctx
    header = PP_HEADER.strip() + ",cedula\n"
    content = (header + f"{process.code},{province.code},{canton.dpa_code},{parish_a.dpa_code},R01,Escuela Central,,,,12345678\n").encode()
    with pytest.raises(BusinessRuleError, match="microdatos"):
        DataImportService(db).run(source.id, "CNE_POLLING_PLACES", "microdata.csv", content, admin, True, "CANONICAL_POLLING_PLACE")
    job = db.scalar(select(DataImportJob).where(DataImportJob.original_filename == "microdata.csv"))
    assert job.status == "FAILED"


def test_multi_process_polling_places_never_mix(db, admin, ctx):
    source, process, province, canton, parish_a, parish_b, foreign_canton = ctx
    other_process = ElectoralProcess(code=f"DH-PP-OTHER-{uuid4().hex[:6].upper()}", name="Otro proceso DH", process_type="SECTIONAL", election_date=date(2023, 2, 5), year=2023, status="VALIDATED", is_final=True, source_id=source.id, is_active=True)
    db.add(other_process)
    db.commit()
    svc = DataImportService(db)
    svc.run(source.id, "CNE_POLLING_PLACES", "p1.csv", (PP_HEADER + f"{process.code},{province.code},{canton.dpa_code},{parish_a.dpa_code},R01,Escuela Proceso 1,,,\n").encode(), admin, False, "CANONICAL_POLLING_PLACE")
    svc.run(source.id, "CNE_POLLING_PLACES", "p2.csv", (PP_HEADER + f"{other_process.code},{province.code},{canton.dpa_code},{parish_a.dpa_code},R01,Escuela Proceso 2,,,\n").encode(), admin, False, "CANONICAL_POLLING_PLACE")
    places = list(db.scalars(select(PollingPlace).where(PollingPlace.official_code == "R01")))
    assert len(places) == 2
    assert {p.electoral_process_id for p in places} == {process.id, other_process.id}


def test_board_requires_existing_polling_place(db, admin, ctx):
    source, process, province, canton, parish_a, parish_b, foreign_canton = ctx
    board_source = DataSourceService(db).create(DataSourceCreate(code=f"DH_BOARDS_{uuid4().hex[:6].upper()}", institution="Consejo Nacional Electoral", dataset_name="Juntas sintéticas", dataset_type="CNE_ELECTORAL_BOARDS", reference_date=date(2026, 1, 1)), admin)
    content = (BOARD_HEADER + f"{process.code},GHOST,J01,1,,\n").encode()
    job = DataImportService(db).run(board_source.id, "CNE_ELECTORAL_BOARDS", "b.csv", content, admin, True, "CANONICAL_ELECTORAL_BOARD")
    assert job.status == "REJECTED"
    error = db.scalar(select(DataImportError).where(DataImportError.import_job_id == job.id))
    assert "recinto" in error.message.lower()


def test_board_import_upserts_by_code_and_records_provenance(db, admin, ctx):
    source, process, province, canton, parish_a, parish_b, foreign_canton = ctx
    DataImportService(db).run(source.id, "CNE_POLLING_PLACES", "place.csv", (PP_HEADER + f"{process.code},{province.code},{canton.dpa_code},{parish_a.dpa_code},R01,Escuela Central,,,\n").encode(), admin, False, "CANONICAL_POLLING_PLACE")
    board_source = DataSourceService(db).create(DataSourceCreate(code=f"DH_BOARDS_{uuid4().hex[:6].upper()}", institution="Consejo Nacional Electoral", dataset_name="Juntas sintéticas", dataset_type="CNE_ELECTORAL_BOARDS", reference_date=date(2026, 1, 1)), admin)
    svc = DataImportService(db)
    content = (BOARD_HEADER + f"{process.code},R01,J01,1,MIXED,300\n").encode()
    job = svc.run(board_source.id, "CNE_ELECTORAL_BOARDS", "boards.csv", content, admin, False, "CANONICAL_ELECTORAL_BOARD")
    assert job.status == "COMPLETED" and job.rows_inserted == 1
    board = db.scalar(select(ElectoralBoard).where(ElectoralBoard.official_code == "J01"))
    assert board.registered_voters == 300 and board.data_source_id == board_source.id and board.import_job_id == job.id
    updated = svc.run(board_source.id, "CNE_ELECTORAL_BOARDS", "boards2.csv", (BOARD_HEADER + f"{process.code},R01,J01,1,MIXED,320\n").encode(), admin, False, "CANONICAL_ELECTORAL_BOARD", force=True)
    assert updated.status == "COMPLETED" and updated.rows_updated == 1
    boards = list(db.scalars(select(ElectoralBoard).where(ElectoralBoard.polling_place_id == board.polling_place_id)))
    assert len(boards) == 1 and boards[0].registered_voters == 320


def test_board_registered_voters_and_sex_category_are_optional(db, admin, ctx):
    source, process, province, canton, parish_a, parish_b, foreign_canton = ctx
    DataImportService(db).run(source.id, "CNE_POLLING_PLACES", "place.csv", (PP_HEADER + f"{process.code},{province.code},{canton.dpa_code},{parish_a.dpa_code},R01,Escuela Central,,,\n").encode(), admin, False, "CANONICAL_POLLING_PLACE")
    board_source = DataSourceService(db).create(DataSourceCreate(code=f"DH_BOARDS_{uuid4().hex[:6].upper()}", institution="Consejo Nacional Electoral", dataset_name="Juntas sintéticas", dataset_type="CNE_ELECTORAL_BOARDS", reference_date=date(2026, 1, 1)), admin)
    job = DataImportService(db).run(board_source.id, "CNE_ELECTORAL_BOARDS", "boards.csv", (BOARD_HEADER + f"{process.code},R01,J01,1,,\n").encode(), admin, False, "CANONICAL_ELECTORAL_BOARD")
    assert job.status == "COMPLETED"
    board = db.scalar(select(ElectoralBoard).where(ElectoralBoard.official_code == "J01"))
    assert board.sex_category is None and board.registered_voters is None


def test_polling_places_dataset_appears_in_data_hub_catalog(client, db, admin, admin_headers, ctx):
    source, process, province, canton, parish_a, parish_b, foreign_canton = ctx
    DataImportService(db).run(source.id, "CNE_POLLING_PLACES", "place.csv", (PP_HEADER + f"{process.code},{province.code},{canton.dpa_code},{parish_a.dpa_code},R01,Escuela Central,,,\n").encode(), admin, False, "CANONICAL_POLLING_PLACE")
    response = client.get("/api/v1/data-hub/catalog", headers=admin_headers)
    assert response.status_code == 200
    entry = next(e for e in response.json()["entries"] if e["dataset_type"] == "CNE_POLLING_PLACES")
    assert entry["dataset_label"] == "CNE · Recintos electorales"
    assert entry["version_kind"] == "UPSERT_GOVERNED"


def test_polling_place_import_template_lists_expected_headers(client, admin_headers):
    response = client.get("/api/v1/data-import-profiles/CNE_POLLING_PLACES/template", headers=admin_headers)
    assert response.status_code == 200
    header = response.text.strip().split("\n")[0]
    assert header == "process_code,province_dpa,canton_dpa,parish_dpa,polling_place_code,polling_place_name,polling_place_address,polling_place_latitude,polling_place_longitude"


def test_board_import_template_lists_expected_headers(client, admin_headers):
    response = client.get("/api/v1/data-import-profiles/CNE_ELECTORAL_BOARDS/template", headers=admin_headers)
    assert response.status_code == 200
    header = response.text.strip().split("\n")[0]
    assert header == "process_code,polling_place_code,board_code,board_number,sex_category,registered_voters"
