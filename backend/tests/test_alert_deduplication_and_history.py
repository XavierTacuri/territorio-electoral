"""Regresión: el Centro de Alertas no debe acumular duplicados de la misma
condición, y el histórico resuelto no debe mezclarse con lo activo (§Parte 2
del ticket de reparación de mapa/alertas).

El mecanismo real ya vive en AlertService/AlertEvaluationService: cada
condición produce un `fingerprint` determinístico (regla + tipo de entidad +
entidad_id), y `operational_alerts` tiene un índice único real en
(campaign_id, fingerprint) — así que una misma condición nunca puede tener
más de una fila en la base, activa o resuelta. Estas pruebas documentan y
protegen ese contrato explícitamente, en vez de asumirlo.
"""
from datetime import date

import pytest

from app.schemas.alerts import AlertEvaluationRequest
from app.schemas.campaign import CampaignCreate
from app.schemas.operational import TerritorialActivityCreate
from app.scripts.seed_gualaceo import seed as seed_territory
from app.scripts.seed_reports_and_alerts import seed as seed_alert_rules
from app.services.activity_catalog_service import seed as seed_catalogs
from app.services.alert_service import AlertService
from app.services.campaign_service import CampaignService
from app.services.operational_service import OperationalService


@pytest.fixture
def ctx(db, admin):
    _, canton, parishes = seed_territory(db)
    seed_catalogs(db)
    seed_alert_rules(db)
    db.commit()
    campaign = CampaignService(db).create(
        CampaignCreate(
            name="Dedupe Alertas",
            slug="dedupe-alertas",
            canton_id=canton.id,
            office_type="MAYOR",
            election_name="Elección sintética",
            election_date=date(2027, 2, 14),
            status="ACTIVE",
        ),
        admin,
    )
    db.commit()
    return campaign, parishes


def _pending_activity(db, admin, campaign, parish, title="Actividad pendiente"):
    ops = OperationalService(db)
    activity = ops.create_activity(
        campaign.id,
        TerritorialActivityCreate(
            activity_type_code="ASSEMBLY",
            title=title,
            description="Objetivo",
            activity_date=date(2027, 1, 10),
            parish_id=parish.id,
            status="PLANNED",
        ),
        admin,
    )
    # admin auto-aprueba al crear (can_approve): se fuerza de vuelta a
    # PENDING_APPROVAL para reproducir la misma condición que dejaría una
    # actividad creada por un coordinador sin autoaprobación.
    activity.approval_status = "PENDING_APPROVAL"
    db.commit()
    db.refresh(activity)
    return activity


def test_1_una_actividad_pendiente_genera_exactamente_una_alerta_activa(db, admin, ctx):
    campaign, parishes = ctx
    _pending_activity(db, admin, campaign, parishes[0])
    svc = AlertService(db)
    result = svc.evaluate(campaign.id, admin, AlertEvaluationRequest(rule_codes=["ACTIVITY_PENDING_APPROVAL"], as_of_date=date(2027, 1, 1)))
    assert result["created"] == 1
    items, total = svc.list(campaign.id, admin, statuses=("OPEN", "ACKNOWLEDGED"))
    assert total == 1


def test_2_reejecutar_el_evaluador_no_crea_una_segunda_alerta(db, admin, ctx):
    campaign, parishes = ctx
    _pending_activity(db, admin, campaign, parishes[0])
    svc = AlertService(db)
    request = AlertEvaluationRequest(rule_codes=["ACTIVITY_PENDING_APPROVAL"], as_of_date=date(2027, 1, 1))
    svc.evaluate(campaign.id, admin, request)
    second = svc.evaluate(campaign.id, admin, request)
    assert second["created"] == 0 and second["unchanged"] == 1
    items, total = svc.list(campaign.id, admin, statuses=("OPEN", "ACKNOWLEDGED"))
    assert total == 1


def test_3_evaluar_muchas_veces_no_incrementa_el_numero_de_alertas_activas(db, admin, ctx):
    campaign, parishes = ctx
    _pending_activity(db, admin, campaign, parishes[0])
    svc = AlertService(db)
    request = AlertEvaluationRequest(rule_codes=["ACTIVITY_PENDING_APPROVAL"], as_of_date=date(2027, 1, 1))
    for _ in range(10):
        svc.evaluate(campaign.id, admin, request)
    items, total = svc.list(campaign.id, admin, statuses=("OPEN", "ACKNOWLEDGED"))
    assert total == 1


def test_4_aprobar_la_actividad_resuelve_la_misma_alerta_en_vez_de_crear_otra(db, admin, ctx):
    campaign, parishes = ctx
    activity = _pending_activity(db, admin, campaign, parishes[0])
    svc = AlertService(db)
    request = AlertEvaluationRequest(rule_codes=["ACTIVITY_PENDING_APPROVAL"], as_of_date=date(2027, 1, 1))
    svc.evaluate(campaign.id, admin, request)
    active_before, _ = svc.list(campaign.id, admin, statuses=("OPEN", "ACKNOWLEDGED"))
    alert_id = active_before[0].id

    OperationalService(db).approve_activity(campaign.id, activity.id, admin)
    result = svc.evaluate(campaign.id, admin, request)
    assert result["resolved"] == 1 and result["created"] == 0

    active_after, active_total = svc.list(campaign.id, admin, statuses=("OPEN", "ACKNOWLEDGED"))
    assert active_total == 0
    # Dos resueltas son legítimas y distintas: la propia alerta de "pendiente
    # de aprobación" (autorresuelta al desaparecer la condición) y el aviso
    # puntual "Actividad aprobada" (creado directamente como histórico) —
    # ninguna de las dos se duplica a sí misma.
    resolved, resolved_total = svc.list(campaign.id, admin, statuses=("RESOLVED", "DISMISSED"))
    assert resolved_total == 2
    pending_alert = next(a for a in resolved if a.id == alert_id)
    assert pending_alert.status == "RESOLVED"


def test_5_centro_de_alertas_con_filtro_activas_no_devuelve_resueltas(client, admin_headers, db, admin, ctx):
    campaign, parishes = ctx
    activity = _pending_activity(db, admin, campaign, parishes[0])
    svc = AlertService(db)
    request = AlertEvaluationRequest(rule_codes=["ACTIVITY_PENDING_APPROVAL"], as_of_date=date(2027, 1, 1))
    svc.evaluate(campaign.id, admin, request)
    OperationalService(db).approve_activity(campaign.id, activity.id, admin)
    svc.evaluate(campaign.id, admin, request)

    response = client.get(f"/api/v1/campaigns/{campaign.id}/alerts?state=ACTIVE", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert all(item["status"] in {"OPEN", "ACKNOWLEDGED"} for item in body["items"])


def test_6_centro_de_alertas_con_filtro_resueltas_devuelve_el_historico(client, admin_headers, db, admin, ctx):
    campaign, parishes = ctx
    activity = _pending_activity(db, admin, campaign, parishes[0])
    svc = AlertService(db)
    request = AlertEvaluationRequest(rule_codes=["ACTIVITY_PENDING_APPROVAL"], as_of_date=date(2027, 1, 1))
    svc.evaluate(campaign.id, admin, request)
    OperationalService(db).approve_activity(campaign.id, activity.id, admin)
    svc.evaluate(campaign.id, admin, request)

    response = client.get(f"/api/v1/campaigns/{campaign.id}/alerts?state=RESOLVED", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    # La propia "pendiente de aprobación" autorresuelta y el aviso puntual
    # "Actividad aprobada" (creado ya como histórico) — ambas legítimas.
    assert body["total"] == 2
    assert all(item["status"] == "RESOLVED" for item in body["items"])


def test_7_el_contador_del_dashboard_solo_cuenta_alertas_activas(db, admin, ctx):
    campaign, parishes = ctx
    # Dos actividades: una queda pendiente (activa), la otra se aprueba
    # (resuelta) — el contador debe reflejar solo la primera.
    pending = _pending_activity(db, admin, campaign, parishes[0], title="Pendiente activa")
    resolved_soon = _pending_activity(db, admin, campaign, parishes[0], title="Pendiente que se resolverá")
    svc = AlertService(db)
    request = AlertEvaluationRequest(rule_codes=["ACTIVITY_PENDING_APPROVAL"], as_of_date=date(2027, 1, 1))
    svc.evaluate(campaign.id, admin, request)
    OperationalService(db).approve_activity(campaign.id, resolved_soon.id, admin)
    svc.evaluate(campaign.id, admin, request)

    summary = svc.summary(campaign.id, admin)
    total_active_by_severity = sum(row["count"] for row in summary["by_severity"])
    assert total_active_by_severity == 1
    # RESOLVED = la "pendiente de aprobación" de resolved_soon (autorresuelta)
    # + el aviso puntual "Actividad aprobada" creado ya como histórico.
    assert summary["statuses"]["RESOLVED"] == 2
    assert summary["statuses"]["OPEN"] == 1


def test_workflow_alert_approve_reject_never_accumulates_duplicate_rows(db, admin, ctx):
    """Root cause found while writing these tests: `workflow_alert()` (used by
    approve_activity/reject_activity) salted its fingerprint with the current
    timestamp, so it created a brand-new, permanently-OPEN row on every single
    call — never deduplicated, never auto-resolved by the evaluator (which
    doesn't manage ACTIVITY_APPROVED/ACTIVITY_REJECTED at all). Re-triggering
    the same workflow event on the same activity must update one row, not
    insert another."""
    from app.models.alerts import OperationalAlert

    campaign, parishes = ctx
    activity = _pending_activity(db, admin, campaign, parishes[0])
    ops = OperationalService(db)
    ops.workflow_alert("ACTIVITY_APPROVED", activity, "Actividad aprobada", activity.title)
    ops.workflow_alert("ACTIVITY_APPROVED", activity, "Actividad aprobada", activity.title)
    ops.workflow_alert("ACTIVITY_APPROVED", activity, "Actividad aprobada", activity.title)
    db.commit()
    rows = db.query(OperationalAlert).filter(OperationalAlert.resource_id == activity.id, OperationalAlert.title == "Actividad aprobada").all()
    assert len(rows) == 1
    assert rows[0].status == "RESOLVED"


def test_evaluator_is_idempotent_across_many_runs_with_evidence_of_the_old_bug_class(db, admin, ctx):
    """Reproduce la forma exacta del histórico contaminado encontrado en el
    entorno de desarrollo: si por cualquier motivo llegara a existir una
    fila OPEN con un fingerprint que ya no corresponde al esquema actual
    (arrastrada de una versión anterior del evaluador), una reevaluación con
    el código actual debe autorresolverla — nunca acumularla junto a la
    alerta correcta."""
    from app.models.alerts import AlertRule, OperationalAlert

    campaign, parishes = ctx
    activity = _pending_activity(db, admin, campaign, parishes[0])
    rule = db.query(AlertRule).filter(AlertRule.condition_type == "ACTIVITY_PENDING_APPROVAL").one()
    legacy_alert = OperationalAlert(
        alert_rule_id=rule.id,
        campaign_id=campaign.id,
        severity="INFO",
        status="OPEN",
        title="Actividad pendiente de aprobación",
        message="Existe una actividad esperando aprobación.",
        detected_date=date(2027, 1, 1),
        last_seen_date=date(2027, 1, 1),
        resource_type="ACTIVITY",
        resource_id=activity.id,
        parish_id=activity.parish_id,
        fingerprint="legacy-non-deterministic-fingerprint-0001",
        evidence={},
        is_active=True,
    )
    db.add(legacy_alert)
    db.commit()

    svc = AlertService(db)
    svc.evaluate(campaign.id, admin, AlertEvaluationRequest(rule_codes=["ACTIVITY_PENDING_APPROVAL"], as_of_date=date(2027, 1, 1)))

    active, active_total = svc.list(campaign.id, admin, statuses=("OPEN", "ACKNOWLEDGED"))
    assert active_total == 1
    assert active[0].fingerprint != "legacy-non-deterministic-fingerprint-0001"
    db.refresh(legacy_alert)
    assert legacy_alert.status == "RESOLVED"
