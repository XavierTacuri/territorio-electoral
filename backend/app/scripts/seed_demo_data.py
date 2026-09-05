"""Dataset DEMO idempotente para una campana existente de Gualaceo.

Este modulo no crea territorios, geometrias, usuarios ni datos CNE/INEC.
Cada registro propio se identifica por DEMO_PREFIX o por un codigo DEMO_*.
"""
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.assignments import CampaignUser
from app.models.campaign import Campaign
from app.models.operational import ActivityType, CitizenNeed, Commitment, NeedCategory, TerritorialActivity
from app.models.public_intelligence import PublicIntelligenceItem, PublicItemNeedLink, PublicItemTerritory, PublicSource
from app.models.survey_study import SurveyStudy, SurveyStudyOption, SurveyStudyResult, SurveyStudyTerritory
from app.models.territory import Canton, Parish
from app.models.user import User
from app.services.activity_catalog_service import seed as seed_catalogs

DEMO_PREFIX = "[DEMO]"
DEMO_SOURCE_CODE = "DEMO_TERRITORIAL"
DEMO_STUDY_CODES = ("DEMO_AGG_2026_08", "DEMO_TRACKING_2026_08")
DISCLAIMER = "DATOS SIMULADOS PARA DEMOSTRACIÓN."
PUBLIC_DISCLAIMER = "Contenido sintético creado exclusivamente para demostración de Territorio Electoral."
DEFAULT_CAMPAIGN_SLUGS = ("gualaceo2026", "gualaceo-e2e-2027", "operacion-gualaceo-2027")


@dataclass
class SeedSummary:
    campaign_slug: str
    activities: int = 0
    needs: int = 0
    commitments: int = 0
    studies: int = 0
    public_sources: int = 0
    public_items: int = 0
    territorial_associations: int = 0
    demo_users_created: int = 0


ACTIVITIES = (
    ("010353", "COMMUNITY_MEETING", "Reunion comunitaria en Jadan", -9, "COMPLETED", "APPROVED"),
    ("010357", "TOUR", "Recorrido territorial en San Juan", -6, "COMPLETED", "APPROVED"),
    ("010358", "COMMUNITY_MEETING", "Encuentro vecinal en Zhidmad", -3, "IN_PROGRESS", "APPROVED"),
    ("010350", "OTHER", "Reunion de coordinacion en Gualaceo", 1, "IN_PROGRESS", "PENDING_APPROVAL"),
    ("010354", "ORGANIZATION_VISIT", "Visita territorial en Mariano Moreno", 4, "PLANNED", "APPROVED"),
    ("010352", "PUBLIC_EVENT", "Jornada informativa en Daniel Cordova Toral", 7, "PLANNED", "PENDING_APPROVAL"),
    ("010356", "TOUR", "Recorrido comunitario en Remigio Crespo Toral", 10, "PLANNED", "DRAFT"),
    ("010359", "ASSEMBLY", "Asamblea territorial en Luis Cordero Vega", -12, "COMPLETED", "APPROVED"),
    ("010360", "TRAINING", "Taller informativo en Simon Bolivar", 13, "PLANNED", "PENDING_APPROVAL"),
    ("010353", "TOUR", "Seguimiento territorial en Jadan", 16, "PLANNED", "DRAFT"),
    ("010357", "COMMUNITY_MEETING", "Mesa comunitaria en San Juan", 19, "PLANNED", "PENDING_APPROVAL"),
)

NEEDS = (
    ("010353", "ROADS", "Mejoramiento vial", "HIGH", "VALIDATED", 8),
    ("010357", "OTHER", "Alumbrado publico", "MEDIUM", "UNDER_REVIEW", 5),
    ("010358", "PUBLIC_SPACES", "Mantenimiento de espacio comunitario", "MEDIUM", "IDENTIFIED", 4),
    ("010352", "DRINKING_WATER", "Acceso a agua", "HIGH", "REPORTED", 7),
    ("010354", "TRANSPORT", "Transporte comunitario", "MEDIUM", "REPORTED", 3),
    ("010359", "CONNECTIVITY", "Conectividad", "LOW", "VALIDATED", 6),
)

# Seguimientos/Commitments es dominio legacy (retiro de producto): ya no forma
# parte del dataset DEMO productivo. Este spec solo lo consume
# seed_legacy_commitments_fixture(), invocado explícitamente por pruebas
# legacy, y clean(), para poder limpiar datos de corridas anteriores.
LEGACY_COMMITMENTS_SPEC = (
    ("010353", "Revisar informacion disponible sobre mejoramiento vial", "IN_PROGRESS", 14),
    ("010357", "Preparar informacion sobre alumbrado publico", "PENDING", 21),
    ("010358", "Contactar nuevamente al sector comunitario", "COMPLETED", -2),
    ("010352", "Revisar informacion disponible sobre acceso a agua", "IN_PROGRESS", 30),
    ("010354", "Coordinar una reunion sobre transporte", "PENDING", 45),
)

PUBLIC_ITEMS = (
    ("010353", "Boletin territorial de Jadan"),
    ("010357", "Informacion comunitaria de San Juan"),
    ("010358", "Reporte publico territorial de Zhidmad"),
    ("010354", "Actualizacion de infraestructura local"),
    (None, "Agenda comunitaria cantonal"),
    ("010352", "Boletin comunitario de Daniel Cordova Toral"),
    ("010359", "Resumen territorial de Luis Cordero Vega"),
    (None, "Compendio publico cantonal"),
)


def _campaign(db: Session, slug: str | None) -> Campaign:
    if slug:
        campaign = db.scalar(select(Campaign).where(Campaign.slug == slug))
        if not campaign:
            raise RuntimeError(f"No existe la campana con slug {slug!r}.")
    else:
        env_slug = os.getenv("DEMO_CAMPAIGN_SLUG")
        candidates = ([env_slug] if env_slug else []) + list(DEFAULT_CAMPAIGN_SLUGS)
        campaign = next((db.scalar(select(Campaign).where(Campaign.slug == value)) for value in candidates if value), None)
        if not campaign:
            rows = list(db.scalars(select(Campaign).join(Canton).where(Canton.dpa_code == "0103", Campaign.is_active.is_(True))))
            if len(rows) != 1:
                raise RuntimeError("No se pudo resolver una unica campana de Gualaceo; use --campaign-slug.")
            campaign = rows[0]
    canton_dpa = db.scalar(select(Canton.dpa_code).where(Canton.id == campaign.canton_id))
    if canton_dpa != "0103":
        raise RuntimeError("La campana seleccionada no pertenece al canton Gualaceo (DPA 0103).")
    return campaign


def _actor(db: Session, campaign: Campaign) -> User:
    actor = db.scalar(select(User).join(CampaignUser, CampaignUser.user_id == User.id).where(
        CampaignUser.campaign_id == campaign.id, CampaignUser.is_active.is_(True), User.is_active.is_(True)
    ).order_by(User.is_superuser.desc(), User.username))
    actor = actor or db.get(User, campaign.created_by_user_id)
    if not actor:
        raise RuntimeError("La campana no tiene un usuario existente utilizable para el seed.")
    return actor


def _parishes(db: Session, campaign: Campaign) -> dict[str, Parish]:
    rows = list(db.scalars(select(Parish).where(Parish.canton_id == campaign.canton_id, Parish.dpa_code.in_({x[0] for x in ACTIVITIES}))))
    found = {row.dpa_code: row for row in rows}
    missing = sorted({x[0] for x in ACTIVITIES} - found.keys())
    if missing:
        raise RuntimeError(f"Faltan parroquias oficiales DPA: {', '.join(missing)}")
    return found


def seed(db: Session, campaign_slug: str | None = None, *, today: date = date(2026, 8, 18)) -> SeedSummary:
    campaign = _campaign(db, campaign_slug)
    actor = _actor(db, campaign)
    parishes = _parishes(db, campaign)
    seed_catalogs(db)
    activity_types = {x.code: x for x in db.scalars(select(ActivityType))}
    need_categories = {x.code: x for x in db.scalars(select(NeedCategory))}

    activities = {}
    for dpa, type_code, label, offset, status, approval in ACTIVITIES:
        title = f"{DEMO_PREFIX} {label}"
        obj = db.scalar(select(TerritorialActivity).where(TerritorialActivity.campaign_id == campaign.id, TerritorialActivity.title == title))
        approval_time = datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc)
        values = dict(activity_type_id=activity_types[type_code].id, description=f"{DISCLAIMER} Actividad territorial agregada sin datos personales.", activity_date=date.fromordinal(today.toordinal() + offset), status=status, approval_status=approval, parish_id=parishes[dpa].id, location_name=f"{DEMO_PREFIX} {parishes[dpa].name}", created_by_user_id=actor.id, responsible_user_id=actor.id, submitted_for_approval_at=approval_time if approval != "DRAFT" else None, submitted_by_user_id=actor.id if approval != "DRAFT" else None, approved_at=approval_time if approval == "APPROVED" else None, approved_by_user_id=actor.id if approval == "APPROVED" else None, is_active=True)
        if not obj:
            obj = TerritorialActivity(campaign_id=campaign.id, title=title, **values); db.add(obj); db.flush()
        else:
            for key, value in values.items(): setattr(obj, key, value)
        activities[dpa] = obj

    needs = {}
    for dpa, category, label, priority, status, mentions in NEEDS:
        title = f"{DEMO_PREFIX} {label}"
        obj = db.scalar(select(CitizenNeed).where(CitizenNeed.campaign_id == campaign.id, CitizenNeed.title == title))
        values = dict(activity_id=activities[dpa].id, need_category_id=need_categories[category].id, description=f"{DISCLAIMER} Necesidad comunitaria sintetica y agregada.", mentions_count=mentions, priority=priority, status=status, parish_id=parishes[dpa].id, created_by_user_id=actor.id, source_type="CAMPAIGN_ACTIVITY", reported_date=today, urgency=priority, scope="PARISH", source_reference="DEMO_DATASET_V1", evidence_notes=f"{DISCLAIMER} demo=true", is_active=True)
        if not obj:
            obj = CitizenNeed(campaign_id=campaign.id, title=title, **values); db.add(obj); db.flush()
        else:
            for key, value in values.items(): setattr(obj, key, value)
        needs[dpa] = obj

    # Seguimientos/Commitments ya no se crea para demostración productiva
    # (retiro de producto). Ver seed_legacy_commitments_fixture() para el
    # fixture aislado que usan las pruebas legacy del dominio.
    _seed_studies(db, campaign, actor, parishes)
    source = _seed_public(db, campaign, actor, parishes, needs)
    db.flush()
    return SeedSummary(campaign.slug, len(ACTIVITIES), len(NEEDS), 0, len(DEMO_STUDY_CODES), 1, len(PUBLIC_ITEMS), 38, 0)


def seed_legacy_commitments_fixture(db: Session, campaign_slug: str | None = None) -> int:
    """Fixture aislado únicamente para pruebas legacy de Seguimientos/Commitments.

    Seguimientos es dominio legacy retirado de la experiencia productiva:
    seed() ya no lo invoca ni lo incluye en el dataset DEMO principal. Solo
    debe llamarse explícitamente desde pruebas que verifiquen ese dominio
    histórico, nunca desde flujos productivos o de demostración.
    """
    campaign = _campaign(db, campaign_slug)
    actor = _actor(db, campaign)
    parishes = _parishes(db, campaign)
    activity_title_by_dpa = {dpa: f"{DEMO_PREFIX} {label}" for dpa, _type_code, label, *_ in ACTIVITIES}
    need_by_dpa = {row[0]: db.scalar(select(CitizenNeed).where(CitizenNeed.campaign_id == campaign.id, CitizenNeed.title == f"{DEMO_PREFIX} {row[2]}")) for row in NEEDS}
    activity_by_dpa = {dpa: db.scalar(select(TerritorialActivity).where(TerritorialActivity.campaign_id == campaign.id, TerritorialActivity.title == title)) for dpa, title in activity_title_by_dpa.items()}
    today = date(2026, 8, 18)
    created = 0
    for dpa, label, status, offset in LEGACY_COMMITMENTS_SPEC:
        title = f"{DEMO_PREFIX} {label}"
        obj = db.scalar(select(Commitment).where(Commitment.campaign_id == campaign.id, Commitment.title == title))
        due = date.fromordinal(today.toordinal() + offset)
        need = need_by_dpa.get(dpa); activity = activity_by_dpa.get(dpa)
        values = dict(activity_id=activity.id if activity else None, need_id=need.id if need else None, description=f"{DISCLAIMER} Seguimiento operativo no dirigido a grupos de votantes.", priority=need.priority if need else "MEDIUM", status=status, due_date=due, completed_date=due if status == "COMPLETED" else None, responsible_user_id=actor.id, parish_id=parishes[dpa].id, created_by_user_id=actor.id, is_active=True)
        if not obj:
            obj = Commitment(campaign_id=campaign.id, title=title, **values); db.add(obj); created += 1
        else:
            for key, value in values.items(): setattr(obj, key, value)
    db.flush()
    return created


def _seed_studies(db, campaign, actor, parishes):
    specs = ((DEMO_STUDY_CODES[0], "Encuesta general Gualaceo - Agosto 2026", (31.2, 24.5, 18.7, 15.1, 10.5)), (DEMO_STUDY_CODES[1], "Encuesta general Gualaceo - Segunda medición", (29.0, 26.0, 19.0, 16.0, 10.0)))
    selected = [parishes[x] for x in ("010350", "010353", "010357", "010358")]
    for code, label, percentages in specs:
        study = db.scalar(select(SurveyStudy).where(SurveyStudy.campaign_id == campaign.id, SurveyStudy.code == code))
        if not study:
            study = SurveyStudy(campaign_id=campaign.id, code=code, name=f"{DEMO_PREFIX} {label}", description=f"{DISCLAIMER} Resultados exclusivamente agregados.", study_type="GENERAL_SURVEY", status="PUBLISHED", fieldwork_start_date=date(2026, 8, 1), fieldwork_end_date=date(2026, 8, 12), publication_date=date(2026, 8, 15), geography_level="PARISH", sample_size_total=800, universe_description=f"{DISCLAIMER} Universo cantonal sintético.", sampling_method="Estudio agregado sintético para demostración.", collection_method="Resultados agregados sintéticos; sin respuestas individuales.", confidence_level=Decimal("0.95"), margin_of_error=Decimal("0.035"), pollster_name=f"{DEMO_PREFIX} Laboratorio sintético", sponsor_name=f"{DEMO_PREFIX} Territorio Electoral", source_type="SYNTHETIC_DEMO", notes=f"{DISCLAIMER} Datos simulados para demostración.", is_official=False, question_code="AGGREGATED_QUESTIONS", result_count_notes=f"{DISCLAIMER} Conteos agregados simulados.", created_by_user_id=actor.id, imported_by_user_id=actor.id); db.add(study); db.flush()
        else:
            study.name=f"{DEMO_PREFIX} {label}";study.study_type="GENERAL_SURVEY";study.sample_size_total=800;study.sampling_method="Estudio agregado sintético para demostración.";study.notes=f"{DISCLAIMER} Datos simulados para demostración."
        if not study.options:
            option_specs=(("Q1","¿Cuál considera que es el principal problema del cantón?","SINGLE_CHOICE",(("ROADS","Vialidad",percentages[0]),("SECURITY","Seguridad",percentages[1]),("WATER","Agua y saneamiento",percentages[2]),("EMPLOYMENT","Empleo",percentages[3]),("OTHER","Otros",percentages[4]))),("Q2","¿Cómo valora los servicios públicos del cantón?","RATING",(("GOOD","Buena",42),("REGULAR","Regular",37),("BAD","Mala",21))))
            options=[];option_values={}
            for qcode,qtext,qtype,rows in option_specs:
                for i,(ocode,label_,pct) in enumerate(rows):
                    option=SurveyStudyOption(study_id=study.id,question_code=qcode,question_text=qtext,question_type=qtype,code=ocode,label=label_,option_type="OTHER",display_order=i);options.append(option);option_values[option]=pct
            db.add_all(options);db.flush()
            for parish in selected:
                territory = SurveyStudyTerritory(study_id=study.id, parish_id=parish.id, sample_size=200, margin_of_error=Decimal("0.07"), coverage_notes=f"{DISCLAIMER} Agregado parroquial simulado."); db.add(territory); db.flush()
                db.add_all([SurveyStudyResult(study_id=study.id,study_territory_id=territory.id,option_id=option.id,response_count=200,percentage=Decimal(str(option_values[option]))/100) for option in options])


def _seed_public(db, campaign, actor, parishes, needs):
    source = db.scalar(select(PublicSource).where(PublicSource.campaign_id == campaign.id, PublicSource.code == DEMO_SOURCE_CODE))
    if not source:
        source = PublicSource(campaign_id=campaign.id, code=DEMO_SOURCE_CODE, name=f"{DEMO_PREFIX} Fuente de demostracion territorial", publisher=f"{DEMO_PREFIX} Territorio Electoral", source_type="OTHER", base_url="https://example.invalid/demo-territorial", jurisdiction="Gualaceo", province="Azuay", canton="Gualaceo", official=False, active=True, retrieval_method="MANUAL", terms_notes=DISCLAIMER, license_notes="Contenido sintetico no reutilizable como fuente oficial.", adapter_config={"demo": True, "disclaimer": DISCLAIMER}); db.add(source); db.flush()
    for index, (dpa, label) in enumerate(PUBLIC_ITEMS, 1):
        canonical = f"https://example.invalid/demo-territorial/items/{index}"
        item = db.scalar(select(PublicIntelligenceItem).where(PublicIntelligenceItem.source_id == source.id, PublicIntelligenceItem.canonical_url == canonical))
        text = f"{PUBLIC_DISCLAIMER} {DISCLAIMER} Informacion publica agregada y ficticia."
        if not item:
            item = PublicIntelligenceItem(source_id=source.id, external_id=f"DEMO-TERRITORIAL-{index:02d}", title=f"{DEMO_PREFIX} {label}", summary=text, item_type="PUBLIC_DOCUMENT", url=canonical, canonical_url=canonical, published_at=datetime(2026, 8, index, tzinfo=timezone.utc), fetched_at=datetime(2026, 8, 18, tzinfo=timezone.utc), content_excerpt=text, normalized_text=text, content_hash=sha256(f"demo-territorial-{index}".encode()).hexdigest(), status="ACTIVE", original_metadata={"demo": True, "official": False, "disclaimer": DISCLAIMER}); db.add(item); db.flush()
        territory = db.scalar(select(PublicItemTerritory).where(PublicItemTerritory.item_id == item.id))
        if not territory:
            db.add(PublicItemTerritory(item_id=item.id, territory_level="PARISH" if dpa else "CANTON", parish_id=parishes[dpa].id if dpa else None, association_method="MANUAL", confidence=1.0))
        if dpa in needs and not db.scalar(select(PublicItemNeedLink).where(PublicItemNeedLink.item_id == item.id, PublicItemNeedLink.need_id == needs[dpa].id)):
            db.add(PublicItemNeedLink(item_id=item.id, need_id=needs[dpa].id, linked_by_user_id=actor.id))
    return source


def clean(db: Session, campaign_slug: str | None = None) -> SeedSummary:
    campaign = _campaign(db, campaign_slug)
    source = db.scalar(select(PublicSource).where(PublicSource.campaign_id == campaign.id, PublicSource.code == DEMO_SOURCE_CODE))
    item_ids = list(db.scalars(select(PublicIntelligenceItem.id).where(PublicIntelligenceItem.source_id == source.id))) if source else []
    if item_ids:
        db.execute(delete(PublicItemNeedLink).where(PublicItemNeedLink.item_id.in_(item_ids)))
        db.execute(delete(PublicItemTerritory).where(PublicItemTerritory.item_id.in_(item_ids)))
        db.execute(delete(PublicIntelligenceItem).where(PublicIntelligenceItem.id.in_(item_ids)))
    if source: db.delete(source)
    studies = list(db.scalars(select(SurveyStudy).where(SurveyStudy.campaign_id == campaign.id, SurveyStudy.code.in_(DEMO_STUDY_CODES))))
    for study in studies: db.delete(study)
    commitment_titles = [f"{DEMO_PREFIX} {label}" for _, label, _, _ in LEGACY_COMMITMENTS_SPEC]
    need_titles = [f"{DEMO_PREFIX} {row[2]}" for row in NEEDS]
    activity_titles = [f"{DEMO_PREFIX} {row[2]}" for row in ACTIVITIES]
    commitment_count = db.execute(delete(Commitment).where(Commitment.campaign_id == campaign.id, Commitment.title.in_(commitment_titles))).rowcount
    need_count = db.execute(delete(CitizenNeed).where(CitizenNeed.campaign_id == campaign.id, CitizenNeed.title.in_(need_titles))).rowcount
    activity_count = db.execute(delete(TerritorialActivity).where(TerritorialActivity.campaign_id == campaign.id, TerritorialActivity.title.in_(activity_titles))).rowcount
    return SeedSummary(campaign.slug, activity_count, need_count, commitment_count, len(studies), int(source is not None), len(item_ids), 0, 0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga o limpia datos DEMO de Gualaceo")
    parser.add_argument("--clean", action="store_true", help="Elimina solamente este dataset DEMO")
    parser.add_argument("--campaign-slug", help="Slug de la campana existente de Gualaceo")
    args = parser.parse_args()
    with SessionLocal() as db:
        try:
            summary = clean(db, args.campaign_slug) if args.clean else seed(db, args.campaign_slug)
            db.commit()
        except Exception:
            db.rollback(); raise
    action = "Limpieza" if args.clean else "Carga"
    print(f"{action} DEMO completada: {asdict(summary)}")


if __name__ == "__main__":
    main()
