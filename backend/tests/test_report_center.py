from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.security import hash_password
from app.models.assignments import CampaignUser, TerritorialAssignment
from app.models.campaign import Campaign
from app.models.historical import DataSource, ElectoralProcess, ElectoralRollSnapshot, ElectoralRollSnapshotEntry, ParticipationProjectionResult, ParticipationProjectionRun
from app.models.territory import Canton, Parish, Province
from app.models.user import User
from app.schemas.operational import CitizenNeedCreate, TerritorialActivityCreate
from app.schemas.reports import ReportGenerationRequest
from app.services.activity_catalog_service import seed as seed_catalogs
from app.services.exceptions import BusinessRuleError
from app.services.operational_service import OperationalService
from app.services.report_service import ReportService
from app.services.role_service import RoleService
from app.scripts.seed_reports_and_alerts import seed as seed_report_templates


def _report_dataset(db, admin, index, registered=1000, central=650):
    province = Province(id=900 + index, code=f"{90 + index:02}", name=f"Provincia RC {index}"); db.add(province); db.flush()
    canton = Canton(id=900 + index, province_id=province.id, code=f"{index:02}", dpa_code=f"{90 + index:02}{index:02}", name=f"Cantón RC {index}"); db.add(canton); db.flush()
    parish_a = Parish(id=9000 + index * 2, canton_id=canton.id, code="01", dpa_code=f"{canton.dpa_code}01", name=f"Parroquia A {index}", parish_type="RURAL")
    parish_b = Parish(id=9000 + index * 2 + 1, canton_id=canton.id, code="02", dpa_code=f"{canton.dpa_code}02", name=f"Parroquia B {index}", parish_type="RURAL")
    db.add(parish_a); db.add(parish_b); db.flush()
    campaign = Campaign(name=f"Campaña RC {index}", slug=f"rc-{index}-{uuid4().hex[:6]}", canton_id=canton.id, office_type="MAYOR", election_name=f"Elección RC {index}", election_date=date(2027, 2, 14), status="ACTIVE", created_by_user_id=admin.id)
    db.add(campaign); db.flush()
    source = DataSource(code=f"RC-{index}-{uuid4().hex[:4]}", institution="Fuente sintética", dataset_name=f"Dataset RC {index}", dataset_type="CNE_ELECTORAL_ROLL_SNAPSHOT", created_by_user_id=admin.id); db.add(source); db.flush()
    process = ElectoralProcess(code=f"RC-P-{index}-{uuid4().hex[:4]}", name=f"Proceso RC {index}", process_type="SECTIONAL", election_date=date(2027, 2, 14), year=2027, status="VALIDATED", is_final=True, source_id=source.id, is_active=True); db.add(process); db.flush()
    snapshot = ElectoralRollSnapshot(source_id=source.id, electoral_process_id=process.id, snapshot_date=date(2026, 6, 1), name=f"Snapshot RC {index}", status="VALIDATED", is_final=True, created_by_user_id=admin.id); db.add(snapshot); db.flush()
    for parish, reg in ((parish_a, registered), (parish_b, registered // 2)):
        db.add(ElectoralRollSnapshotEntry(snapshot_id=snapshot.id, geography_level="PARISH", province_id=province.id, canton_id=canton.id, parish_id=parish.id, province_dpa=province.code, canton_dpa=canton.dpa_code, parish_dpa=parish.dpa_code, registered_voters=reg, male_voters=reg // 2, female_voters=reg - reg // 2, electoral_zones=1, juntas=2))
    db.flush()
    run = ParticipationProjectionRun(campaign_id=campaign.id, electoral_process_id=process.id, snapshot_id=snapshot.id, model_code="TURNOUT_HISTORICAL_WEIGHTED_V1", model_version="1.0", historical_process_ids=[], parameters={}, run_date=date(2026, 6, 1), created_by_user_id=admin.id); db.add(run); db.flush()
    for parish, reg, cen in ((parish_a, registered, central), (parish_b, registered // 2, central // 2)):
        db.add(ParticipationProjectionResult(run_id=run.id, parish_id=parish.id, registered_voters=reg, turnout_rate_low=Decimal("0.60"), turnout_rate_central=Decimal(str(cen / reg)), turnout_rate_high=Decimal("0.80"), expected_voters_low=int(reg * .6), expected_voters_central=cen, expected_voters_high=int(reg * .8), data_quality_status="MEDIUM", explanation="Fixture Centro de Informes"))
    db.commit()
    return campaign, canton, parish_a, parish_b


@pytest.fixture
def rc(db, admin):
    seed_catalogs(db); seed_report_templates(db); db.commit()
    campaign, canton, parish_a, parish_b = _report_dataset(db, admin, 1)
    return campaign, canton, parish_a, parish_b


def _request(**overrides):
    base = dict(template_code="CAMPAIGN_EXECUTIVE_REPORT", format="PDF", title="Informe de prueba", report_date=date(2026, 8, 20))
    base.update(overrides)
    return ReportGenerationRequest(**base)


def test_report_types_lists_six_report_center_types():
    codes = {t.code for t in ReportService.list_types()}
    assert codes == {"CAMPAIGN_EXECUTIVE_REPORT", "PARISH_TERRITORIAL_PROFILE", "OPERATION_TERRITORIAL_REPORT", "CURRENT_ELECTION_EXECUTIVE", "THEMATIC_REPORT", "ELECTION_DAY_REPORT"}


def test_executive_report_preview_is_grounded_and_deterministic_without_provider(db, admin, rc):
    campaign, *_ = rc
    preview = ReportService(db).preview(campaign.id, _request(), admin)
    assert preview.narrative.provider == "deterministic-fallback"
    assert preview.narrative.resumen_ejecutivo
    assert preview.narrative.hallazgos_principales
    assert preview.sections
    assert preview.is_demo is False


def test_parish_profile_preview_includes_activities_needs_evidence_and_studies(db, admin, rc):
    campaign, canton, parish_a, _ = rc
    ops = OperationalService(db)
    activity = ops.create_activity(campaign.id, TerritorialActivityCreate(activity_type_code="ASSEMBLY", title="Asamblea territorial RC", description="Objetivo", activity_date=date(2026, 8, 10), status="PLANNED", parish_id=parish_a.id), admin)
    ops.create_need(campaign.id, activity.id, CitizenNeedCreate(need_category_code="ROADS", title="Necesidad vial RC", description="Bache en la vía principal", priority="HIGH", urgency="HIGH", source_type="CAMPAIGN_ACTIVITY", reported_date=date(2026, 8, 10), scope="PARISH"), admin)
    request = _request(template_code="PARISH_TERRITORIAL_PROFILE", parish_id=parish_a.id)
    preview = ReportService(db).preview(campaign.id, request, admin)
    assert any(c.source_type == "TERRITORIAL_ACTIVITY" and c.title == "Asamblea territorial RC" for c in preview.citations)
    assert any(c.source_type == "CITIZEN_NEED" and c.title == "Necesidad vial RC" for c in preview.citations)
    assert any(s.title == "Actividades en la parroquia" for s in preview.sections)
    assert any(s.title == "Necesidades registradas" for s in preview.sections)


def test_parish_profile_requires_parish_id():
    with pytest.raises(ValueError):
        _request(template_code="PARISH_TERRITORIAL_PROFILE")


def test_thematic_report_matches_only_the_requested_theme(db, admin, rc):
    campaign, canton, parish_a, _ = rc
    ops = OperationalService(db)
    activity = ops.create_activity(campaign.id, TerritorialActivityCreate(activity_type_code="ASSEMBLY", title="Recorrido vial RC", description="Revisión de vías", activity_date=date(2026, 8, 11), status="PLANNED", parish_id=parish_a.id), admin)
    ops.create_need(campaign.id, activity.id, CitizenNeedCreate(need_category_code="ROADS", title="Bache en calle principal", description="Vía en mal estado", priority="HIGH", urgency="HIGH", source_type="CAMPAIGN_ACTIVITY", reported_date=date(2026, 8, 11), scope="PARISH"), admin)
    ops.create_need(campaign.id, activity.id, CitizenNeedCreate(need_category_code="HEALTH", title="Falta de médico en el centro de salud", description="Atención médica insuficiente", priority="HIGH", urgency="HIGH", source_type="CAMPAIGN_ACTIVITY", reported_date=date(2026, 8, 11), scope="PARISH"), admin)
    request = _request(template_code="THEMATIC_REPORT", theme="vialidad")
    preview = ReportService(db).preview(campaign.id, request, admin)
    titles = {c.title for c in preview.citations if c.source_type == "CITIZEN_NEED"}
    assert "Bache en calle principal" in titles
    assert "Falta de médico en el centro de salud" not in titles


def test_thematic_report_requires_theme():
    with pytest.raises(ValueError):
        _request(template_code="THEMATIC_REPORT")


def test_operation_report_counts_completed_and_upcoming_activities(db, admin, rc):
    campaign, canton, parish_a, _ = rc
    ops = OperationalService(db, today_provider=lambda: date(2026, 8, 20))
    from app.schemas.operational import ActivityCloseRequest
    done = ops.create_activity(campaign.id, TerritorialActivityCreate(activity_type_code="ASSEMBLY", title="Actividad realizada RC", description="Objetivo", activity_date=date(2026, 8, 10), status="PLANNED", parish_id=parish_a.id), admin)
    ops.complete_activity(campaign.id, done.id, ActivityCloseRequest(summary="Actividad territorial realizada con éxito y buena asistencia."), admin)
    ops.create_activity(campaign.id, TerritorialActivityCreate(activity_type_code="ASSEMBLY", title="Actividad próxima RC", description="Objetivo", activity_date=date(2026, 9, 1), status="PLANNED", parish_id=parish_a.id), admin)
    request = _request(template_code="OPERATION_TERRITORIAL_REPORT")
    preview = ReportService(db).preview(campaign.id, request, admin)
    executive_section = next(s for s in preview.sections if s.title == "Resumen operativo")
    values = {row[0]: row[1] for row in executive_section.rows}
    assert values["Actividades realizadas"] == 1
    assert values["Actividades próximas"] == 1


def test_demo_items_excluded_when_include_demo_false(db, admin, rc):
    campaign, canton, parish_a, _ = rc
    ops = OperationalService(db)
    ops.create_activity(campaign.id, TerritorialActivityCreate(activity_type_code="ASSEMBLY", title="[DEMO] Actividad simulada RC", description="Objetivo", activity_date=date(2026, 8, 10), status="PLANNED", parish_id=parish_a.id), admin)
    request = _request(template_code="PARISH_TERRITORIAL_PROFILE", parish_id=parish_a.id, include_demo=True)
    preview = ReportService(db).preview(campaign.id, request, admin)
    assert preview.is_demo is True
    assert any(c.evidence_class == "DEMO" for c in preview.citations)
    request_excl = _request(template_code="PARISH_TERRITORIAL_PROFILE", parish_id=parish_a.id, include_demo=False)
    preview_excl = ReportService(db).preview(campaign.id, request_excl, admin)
    assert preview_excl.is_demo is False
    assert not any("simulada" in c.title.lower() for c in preview_excl.citations)


def test_coordinator_cannot_preview_parish_outside_assigned_scope(db, admin, rc):
    campaign, canton, parish_a, parish_b = rc
    role = RoleService(db).repository.get_by_code("TERRITORIAL_COORDINATOR")
    user = User(email="rc-coord@example.test", username="rc-coord", first_name="RC", last_name="Coord", hashed_password=hash_password("CoordPass123"), is_active=True, roles=[role])
    db.add(user); db.flush()
    db.add(CampaignUser(campaign_id=campaign.id, user_id=user.id, assigned_by_user_id=admin.id, is_active=True))
    db.add(TerritorialAssignment(campaign_id=campaign.id, user_id=user.id, parish_id=parish_a.id, assigned_by_user_id=admin.id, is_active=True))
    db.commit()
    ReportService(db).preview(campaign.id, _request(template_code="PARISH_TERRITORIAL_PROFILE", parish_id=parish_a.id), user)
    with pytest.raises(PermissionError):
        ReportService(db).preview(campaign.id, _request(template_code="PARISH_TERRITORIAL_PROFILE", parish_id=parish_b.id), user)


def test_coordinator_can_prepare_debate_brief_only_for_assigned_parish(db, admin, rc):
    campaign, canton, parish_a, parish_b = rc
    role = RoleService(db).repository.get_by_code("TERRITORIAL_COORDINATOR")
    user = User(email="rc-debate-coord@example.test", username="rc-debate-coord", first_name="RC", last_name="Coord", hashed_password=hash_password("CoordPass123"), is_active=True, roles=[role])
    db.add(user); db.flush()
    db.add(CampaignUser(campaign_id=campaign.id, user_id=user.id, assigned_by_user_id=admin.id, is_active=True))
    db.add(TerritorialAssignment(campaign_id=campaign.id, user_id=user.id, parish_id=parish_a.id, assigned_by_user_id=admin.id, is_active=True))
    db.commit()
    preview = ReportService(db).preview(campaign.id, _request(template_code="DEBATE_BRIEF_REPORT", theme="vialidad", parish_id=parish_a.id), user)
    assert preview.report_kind == "DEBATE_BRIEF_REPORT"
    with pytest.raises(PermissionError):
        ReportService(db).preview(campaign.id, _request(template_code="DEBATE_BRIEF_REPORT", theme="vialidad", parish_id=parish_b.id), user)


def test_citations_reference_only_real_objects_no_orphan_ids(db, admin, rc):
    campaign, canton, parish_a, _ = rc
    ops = OperationalService(db)
    activity = ops.create_activity(campaign.id, TerritorialActivityCreate(activity_type_code="ASSEMBLY", title="Actividad citada RC", description="Objetivo", activity_date=date(2026, 8, 10), status="PLANNED", parish_id=parish_a.id), admin)
    request = _request(template_code="PARISH_TERRITORIAL_PROFILE", parish_id=parish_a.id)
    preview = ReportService(db).preview(campaign.id, request, admin)
    activity_citation = next(c for c in preview.citations if c.source_type == "TERRITORIAL_ACTIVITY")
    assert activity_citation.id == str(activity.id)
    assert activity_citation.deep_link == f"/app/campaigns/{campaign.id}/activities/{activity.id}"


def test_generate_pdf_end_to_end_persists_run_and_artifact(db, admin, rc, tmp_path):
    from app.services.report_storage_service import LocalReportStorage
    campaign, *_ = rc
    service = ReportService(db, LocalReportStorage(str(tmp_path), 10))
    run = service.generate(campaign.id, _request(), admin)
    assert run.status == "COMPLETED"
    artifact = service.artifact(run)
    assert artifact is not None and artifact.is_available
    path, _ = service.download(campaign.id, run.id, admin, date(2026, 8, 20))
    assert path.exists()


def test_preview_rejects_unknown_template_code(db, admin, rc):
    campaign, *_ = rc
    from app.services.exceptions import NotFoundError
    with pytest.raises(NotFoundError):
        ReportService(db).preview(campaign.id, _request(template_code="DOES_NOT_EXIST"), admin)


def test_http_report_types_endpoint_lists_six_types(client, admin_headers):
    response = client.get("/api/v1/report-types", headers=admin_headers)
    assert response.status_code == 200
    codes = {item["code"] for item in response.json()}
    assert codes == {"CAMPAIGN_EXECUTIVE_REPORT", "PARISH_TERRITORIAL_PROFILE", "OPERATION_TERRITORIAL_REPORT", "CURRENT_ELECTION_EXECUTIVE", "THEMATIC_REPORT", "ELECTION_DAY_REPORT"}


def test_http_preview_endpoint_returns_grounded_report(client, admin_headers, db, admin, rc):
    campaign, *_ = rc
    payload = {"template_code": "CAMPAIGN_EXECUTIVE_REPORT", "format": "PDF", "title": "Informe HTTP", "report_date": "2026-08-20"}
    response = client.post(f"/api/v1/campaigns/{campaign.id}/reports/preview", headers=admin_headers, json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["narrative"]["provider"] == "deterministic-fallback"
    assert body["is_demo"] is False
    assert body["sections"]


def test_preview_run_regenerates_detail_from_stored_filters(db, admin, rc, tmp_path):
    from app.services.report_storage_service import LocalReportStorage
    campaign, canton, parish_a, _ = rc
    service = ReportService(db, LocalReportStorage(str(tmp_path), 10))
    run = service.generate(campaign.id, _request(template_code="PARISH_TERRITORIAL_PROFILE", parish_id=parish_a.id), admin)
    preview = service.preview_run(campaign.id, run.id, admin)
    assert preview.report_kind == "PARISH_TERRITORIAL_PROFILE"
    assert preview.subtitle and parish_a.name in preview.subtitle


def test_http_preview_thematic_requires_theme_returns_422(client, admin_headers, db, admin, rc):
    campaign, *_ = rc
    payload = {"template_code": "THEMATIC_REPORT", "format": "PDF", "title": "Informe temático", "report_date": "2026-08-20"}
    response = client.post(f"/api/v1/campaigns/{campaign.id}/reports/preview", headers=admin_headers, json=payload)
    assert response.status_code == 422


def test_debate_brief_requires_theme():
    with pytest.raises(ValueError):
        _request(template_code="DEBATE_BRIEF_REPORT")


def test_debate_brief_report_not_among_the_five_main_types():
    codes = {t.code for t in ReportService.list_types()}
    assert "DEBATE_BRIEF_REPORT" not in codes


def test_debate_brief_preview_has_structured_sections_and_no_prediction_language(db, admin, rc):
    campaign, canton, parish_a, _ = rc
    ops = OperationalService(db)
    activity = ops.create_activity(campaign.id, TerritorialActivityCreate(activity_type_code="ASSEMBLY", title="Recorrido vial de debate", description="Revisión de vías", activity_date=date(2026, 8, 11), status="PLANNED", parish_id=parish_a.id), admin)
    ops.create_need(campaign.id, activity.id, CitizenNeedCreate(need_category_code="ROADS", title="Bache vial para debate", description="Vía en mal estado", priority="HIGH", urgency="HIGH", source_type="CAMPAIGN_ACTIVITY", reported_date=date(2026, 8, 11), scope="PARISH"), admin)
    request = _request(template_code="DEBATE_BRIEF_REPORT", theme="vialidad")
    preview = ReportService(db).preview(campaign.id, request, admin)
    titles = {s.title for s in preview.sections}
    assert {"Datos oficiales", "Evidencia territorial", "Actividades relacionadas", "Necesidades registradas", "Preguntas que podrían surgir", "Puntos que necesitan verificación"} <= titles
    questions_section = next(s for s in preview.sections if s.title == "Preguntas que podrían surgir")
    assert questions_section.rows and all(len(row) == 4 for row in questions_section.rows)
    full_text = " ".join((s.text or "") + " ".join(str(v) for row in s.rows for v in row) for s in preview.sections)
    for banned in ("ganador", "persuadir", "microtargeting", "favorabilidad"):
        assert banned not in full_text.casefold()


def test_debate_brief_official_facts_include_electoral_roll_citation(db, admin, rc):
    campaign, *_ = rc
    request = _request(template_code="DEBATE_BRIEF_REPORT", theme="vialidad")
    preview = ReportService(db).preview(campaign.id, request, admin)
    official_section = next(s for s in preview.sections if s.title == "Datos oficiales")
    assert any(row[0] == "Padrón electoral actual" for row in official_section.rows)


def test_report_run_read_exposes_filters_for_client_side_regeneration(client, admin_headers, db, admin, rc, tmp_path):
    from app.services.report_storage_service import LocalReportStorage
    campaign, canton, parish_a, _ = rc
    service = ReportService(db, LocalReportStorage(str(tmp_path), 10))
    run = service.generate(campaign.id, _request(template_code="THEMATIC_REPORT", theme="vialidad", parish_id=parish_a.id, include_public_intelligence=False), admin)
    response = client.get(f"/api/v1/campaigns/{campaign.id}/reports/{run.id}", headers=admin_headers)
    assert response.status_code == 200
    filters = response.json()["filters"]
    assert filters["theme"] == "VIALIDAD"
    assert filters["parish_id"] == parish_a.id
    assert filters["include_public_intelligence"] is False


def test_regenerating_a_report_creates_new_version_and_leaves_original_intact(db, admin, rc, tmp_path):
    from app.services.report_storage_service import LocalReportStorage
    campaign, canton, parish_a, _ = rc
    service = ReportService(db, LocalReportStorage(str(tmp_path), 10))
    original_request = _request(template_code="THEMATIC_REPORT", theme="vialidad", parish_id=parish_a.id, report_date=date(2026, 8, 15))
    original = service.generate(campaign.id, original_request, admin)
    original_artifact = service.artifact(original)
    original_sections = service.preview_run(campaign.id, original.id, admin).sections

    updated_request = _request(template_code="THEMATIC_REPORT", theme="vialidad", parish_id=parish_a.id, report_date=date(2026, 9, 1))
    updated = service.generate(campaign.id, updated_request, admin)

    assert updated.id != original.id
    still_original = service.get_run(campaign.id, original.id, admin)
    assert still_original.status == "COMPLETED"
    assert still_original.report_date == date(2026, 8, 15)
    assert service.artifact(still_original).id == original_artifact.id
    assert service.preview_run(campaign.id, original.id, admin).sections == original_sections
    runs, total = service.list_runs(campaign.id, admin)
    assert total == 2 and {r.id for r in runs} == {original.id, updated.id}


def test_debate_brief_generates_pdf_and_persists_like_other_reports(db, admin, rc, tmp_path):
    from app.services.report_storage_service import LocalReportStorage
    campaign, *_ = rc
    service = ReportService(db, LocalReportStorage(str(tmp_path), 10))
    run = service.generate(campaign.id, _request(template_code="DEBATE_BRIEF_REPORT", theme="vialidad"), admin)
    assert run.status == "COMPLETED"
    artifact = service.artifact(run)
    assert artifact is not None and artifact.is_available and artifact.original_download_name.startswith("preparacion-debate-")
