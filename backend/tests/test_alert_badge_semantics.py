"""Semántica del badge de notificaciones (campana del header).

Investigación: no existe una entidad Notification separada de OperationalAlert
en este sistema — el badge (`useAlertBadgeCount` en el frontend) llama
directamente a `GET /campaigns/{id}/alerts/summary`, que suma `by_severity`
excluyendo INFO. La causa real de un badge en 31 mientras el Centro de
Alertas mostraba 3 resultados: `AlertService.summary()` nunca aplicaba la
misma restricción de familias (Candidate/Manager) ni el alcance territorial
que `AlertService.list()` sí aplica — contaba TODAS las alertas activas de la
campaña sin importar si el usuario tenía autorización para verlas. Corregido
para que summary() espeje exactamente el alcance de list().

No existe un flag "leído/no leído" por usuario: el ciclo de vida real es el
`status` (OPEN -> ACKNOWLEDGED -> RESOLVED/DISMISSED). El badge cuenta
OPEN+ACKNOWLEDGED ("activas"), nunca RESOLVED/DISMISSED ("histórico").
"""
from datetime import date

import pytest

from app.schemas.alerts import AlertActionRequest, AlertEvaluationRequest
from app.schemas.campaign import CampaignCreate, CampaignUserAssign
from app.schemas.historical import DataSourceCreate
from app.scripts.seed_gualaceo import seed as seed_territory
from app.scripts.seed_reports_and_alerts import seed as seed_alert_rules
from app.services.activity_catalog_service import seed as seed_catalogs
from app.services.alert_service import AlertService
from app.services.campaign_service import CampaignService
from app.services.data_import_service import DataImportService
from app.services.data_source_service import DataSourceService
from app.services.dataset_version_service import DatasetVersionService
from app.services.role_service import RoleService
from app.services.territorial_assignment_service import TerritorialAssignmentService
from app.core.security import hash_password
from app.models.user import User


def _badge(summary):
    return sum(row["count"] for row in summary["by_severity"] if row["severity"] != "INFO")


@pytest.fixture
def ctx(db, admin):
    _, canton, parishes = seed_territory(db)
    seed_catalogs(db)
    seed_alert_rules(db)
    db.commit()
    campaign_a = CampaignService(db).create(
        CampaignCreate(name="Badge A", slug="badge-a", canton_id=canton.id, office_type="MAYOR",
                       election_name="Elección A", election_date=date(2027, 2, 14), status="ACTIVE"),
        admin,
    )
    campaign_b = CampaignService(db).create(
        CampaignCreate(name="Badge B", slug="badge-b", canton_id=canton.id, office_type="MAYOR",
                       election_name="Elección B", election_date=date(2027, 2, 14), status="ACTIVE"),
        admin,
    )
    roles = RoleService(db)
    candidate = User(email="badge-candidate@example.test", username="badge_candidate", first_name="B",
                      last_name="Candidata", hashed_password=hash_password("Testing123"),
                      roles=[roles.repository.get_by_code("CANDIDATE")])
    db.add(candidate)
    db.commit()
    assignments = TerritorialAssignmentService(db)
    assignments.assign_user(campaign_a.id, CampaignUserAssign(user_id=candidate.id), admin)
    return campaign_a, campaign_b, parishes, candidate


def test_7_badge_excludes_resolved_alerts_from_the_count(db, admin, ctx):
    campaign_a, _, parishes, _ = ctx
    svc = AlertService(db)
    request = AlertEvaluationRequest(rule_codes=["CAMPAIGN_WITHOUT_ACTIVE_ROLL"], as_of_date=date.today())
    svc.evaluate(campaign_a.id, admin, request)
    before = _badge(svc.summary(campaign_a.id, admin))
    assert before == 1

    # La condición desaparece: se activa una versión real del padrón (mismo
    # camino que usa el producto), y la alerta se autorresuelve.
    source = DataSourceService(db).create(DataSourceCreate(code="BADGE_ROLL", institution="Consejo Nacional Electoral", dataset_name="Padrón sintético", dataset_type="CNE_ELECTORAL_ROLL_SNAPSHOT"), admin)
    content = (
        b"snapshot_date,process_code,geography_level,province_dpa,canton_dpa,parish_dpa,registered_voters,male_voters,female_voters,electoral_zones,juntas\n"
        b"2027-01-01,,PARISH,01,0103," + parishes[0].dpa_code.encode() + b",100,50,50,,\n"
    )
    job = DataImportService(db).run(source.id, "CNE_ELECTORAL_ROLL_SNAPSHOT", "r.csv", content, admin, False, "CANONICAL_ELECTORAL_ROLL_SNAPSHOT")
    version = DatasetVersionService(db).create_from_job(job, source)
    DatasetVersionService(db).activate(version.id, admin)

    svc.evaluate(campaign_a.id, admin, request)
    after = _badge(svc.summary(campaign_a.id, admin))
    assert after == 0


def test_8_badge_respects_current_campaign_isolation(db, admin, ctx):
    campaign_a, campaign_b, _, _ = ctx
    svc = AlertService(db)
    svc.evaluate(campaign_a.id, admin, AlertEvaluationRequest(rule_codes=["CAMPAIGN_WITHOUT_ACTIVE_ROLL"], as_of_date=date.today()))
    assert _badge(svc.summary(campaign_a.id, admin)) == 1
    # La campaña B nunca fue evaluada: su badge no hereda nada de A.
    assert _badge(svc.summary(campaign_b.id, admin)) == 0


def test_9_badge_respects_role_family_restriction_root_cause_of_31_vs_3(db, admin, ctx):
    """Reproduce exactamente el bug reportado: Centro de Alertas (list, con
    restricción) mostraba 3; la campana (summary, sin restricción) mostraba
    31. Ambos deben reflejar el mismo alcance para el mismo usuario."""
    campaign_a, _, parishes, candidate = ctx
    svc = AlertService(db)
    # Condición ajena a las 2 familias autorizadas para Candidate/Manager,
    # severidad WARNING (para que sí sumaría al badge si no se restringiera).
    svc.evaluate(campaign_a.id, admin, AlertEvaluationRequest(rule_codes=["CAMPAIGN_WITHOUT_ACTIVE_ROLL"], as_of_date=date.today()))
    admin_badge = _badge(svc.summary(campaign_a.id, admin))
    assert admin_badge == 1  # admin ve todo: sin restricción de familia.

    candidate_badge = _badge(svc.summary(campaign_a.id, candidate))
    _, candidate_total = svc.list(campaign_a.id, candidate, statuses=("OPEN", "ACKNOWLEDGED"))
    assert candidate_total == 0  # la única alerta activa no es de su familia.
    assert candidate_badge == 0  # el badge debe coincidir, no mostrar el 1 de admin.


def test_10_acknowledging_keeps_it_active_only_resolving_or_dismissing_clears_the_badge(db, admin, ctx):
    """No existe un flag leído/no leído: el ciclo real es OPEN -> ACKNOWLEDGED
    (sigue activa/pendiente de seguimiento) -> RESOLVED/DISMISSED (histórico,
    sale del badge)."""
    campaign_a, _, _, _ = ctx
    svc = AlertService(db)
    svc.evaluate(campaign_a.id, admin, AlertEvaluationRequest(rule_codes=["CAMPAIGN_WITHOUT_ACTIVE_ROLL"], as_of_date=date.today()))
    items, _ = svc.list(campaign_a.id, admin, statuses=("OPEN", "ACKNOWLEDGED"))
    alert = items[0]
    assert _badge(svc.summary(campaign_a.id, admin)) == 1

    svc.action(campaign_a.id, alert.id, "ACKNOWLEDGE", AlertActionRequest(action_date=date.today()), admin)
    assert _badge(svc.summary(campaign_a.id, admin)) == 1  # revisada, sigue activa.

    svc.action(campaign_a.id, alert.id, "RESOLVE", AlertActionRequest(action_date=date.today()), admin)
    assert _badge(svc.summary(campaign_a.id, admin)) == 0  # resuelta, sale del badge.


def test_11_a_resolved_alert_does_not_keep_re_triggering_the_badge(db, admin, ctx):
    campaign_a, _, _, _ = ctx
    svc = AlertService(db)
    request = AlertEvaluationRequest(rule_codes=["CAMPAIGN_WITHOUT_ACTIVE_ROLL"], as_of_date=date.today())
    svc.evaluate(campaign_a.id, admin, request)
    items, _ = svc.list(campaign_a.id, admin, statuses=("OPEN", "ACKNOWLEDGED"))
    svc.action(campaign_a.id, items[0].id, "RESOLVE", AlertActionRequest(action_date=date.today()), admin)
    assert _badge(svc.summary(campaign_a.id, admin)) == 0
    # La condición real (sin padrón) sigue existiendo: reevaluar la reabre —
    # es la MISMA fila, no una nueva; el badge vuelve a 1, no a 2.
    svc.evaluate(campaign_a.id, admin, request)
    assert _badge(svc.summary(campaign_a.id, admin)) == 1
    resolved, resolved_total = svc.list(campaign_a.id, admin, statuses=("RESOLVED", "DISMISSED"))
    assert resolved_total == 0  # se reabrió la misma fila, no quedó un duplicado resuelto.


def test_12_repeated_evaluations_never_inflate_the_badge(db, admin, ctx):
    campaign_a, _, _, _ = ctx
    svc = AlertService(db)
    request = AlertEvaluationRequest(rule_codes=["CAMPAIGN_WITHOUT_ACTIVE_ROLL"], as_of_date=date.today())
    for _ in range(10):
        svc.evaluate(campaign_a.id, admin, request)
    assert _badge(svc.summary(campaign_a.id, admin)) == 1
