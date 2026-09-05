from datetime import date

from sqlalchemy import func, select

from app.models.campaign import Campaign
from app.models.operational import CitizenNeed, Commitment, TerritorialActivity
from app.models.public_intelligence import PublicIntelligenceItem, PublicItemTerritory, PublicSource
from app.models.survey_study import SurveyStudy, SurveyStudyResult
from app.scripts.seed_demo_data import DEMO_PREFIX, DEMO_SOURCE_CODE, clean, seed, seed_legacy_commitments_fixture
from app.scripts.seed_gualaceo import seed as seed_gualaceo


def _campaign(db, admin):
    _, canton, _ = seed_gualaceo(db)
    campaign = Campaign(name="Gualaceo DEMO host", slug="gualaceo-demo-host", canton_id=canton.id, office_type="MAYOR", election_name="Proceso sintetico", election_date=date(2027, 2, 14), status="ACTIVE", created_by_user_id=admin.id)
    db.add(campaign); db.commit()
    return campaign


def _counts(db, campaign):
    return (
        db.scalar(select(func.count()).select_from(TerritorialActivity).where(TerritorialActivity.campaign_id == campaign.id, TerritorialActivity.title.startswith(DEMO_PREFIX))),
        db.scalar(select(func.count()).select_from(CitizenNeed).where(CitizenNeed.campaign_id == campaign.id, CitizenNeed.title.startswith(DEMO_PREFIX))),
        db.scalar(select(func.count()).select_from(Commitment).where(Commitment.campaign_id == campaign.id, Commitment.title.startswith(DEMO_PREFIX))),
        db.scalar(select(func.count()).select_from(SurveyStudy).where(SurveyStudy.campaign_id == campaign.id, SurveyStudy.code.startswith("DEMO_"))),
    )


def test_demo_seed_is_idempotent_and_aggregated(db, admin):
    campaign = _campaign(db, admin)
    first = seed(db, campaign.slug); db.commit()
    seed(db, campaign.slug); db.commit()
    # Seguimientos/Commitments es dominio legacy retirado de la experiencia
    # productiva: el dataset DEMO principal ya no crea seguimientos nuevos.
    assert _counts(db, campaign) == (11, 6, 0, 2)
    assert (first.activities, first.needs, first.commitments, first.studies, first.public_items) == (11, 6, 0, 2, 8)
    source = db.scalar(select(PublicSource).where(PublicSource.campaign_id == campaign.id, PublicSource.code == DEMO_SOURCE_CODE))
    assert source and not source.official and source.source_type == "OTHER" and source.adapter_config["demo"] is True
    items = list(db.scalars(select(PublicIntelligenceItem).where(PublicIntelligenceItem.source_id == source.id)))
    assert len(items) == 8 and all("exclusivamente para demostración" in item.summary for item in items)
    assert db.scalar(select(func.count()).select_from(PublicItemTerritory).where(PublicItemTerritory.item_id.in_([x.id for x in items]))) == 8
    assert db.scalar(select(func.count()).select_from(SurveyStudyResult)) == 64


def test_legacy_commitments_fixture_is_isolated_and_idempotent(db, admin):
    # El fixture legacy solo se crea cuando una prueba lo invoca explícitamente;
    # no contamina el dataset principal ni se ejecuta desde seed().
    campaign = _campaign(db, admin)
    seed(db, campaign.slug); db.commit()
    assert _counts(db, campaign)[2] == 0
    first_created = seed_legacy_commitments_fixture(db, campaign.slug); db.commit()
    second_created = seed_legacy_commitments_fixture(db, campaign.slug); db.commit()
    assert first_created == 5 and second_created == 0
    assert _counts(db, campaign)[2] == 5


def test_demo_clean_is_selective_and_repeatable(db, admin):
    campaign = _campaign(db, admin)
    real = TerritorialActivity(campaign_id=campaign.id, activity_type_id=1, title="Actividad real preservada", activity_date=date(2026, 8, 18), status="PLANNED", approval_status="DRAFT", parish_id=1, created_by_user_id=admin.id)
    db.add(real); seed(db, campaign.slug); db.commit()
    clean(db, campaign.slug); db.commit()
    clean(db, campaign.slug); db.commit()
    assert _counts(db, campaign) == (0, 0, 0, 0)
    assert db.get(TerritorialActivity, real.id) is not None
    assert db.scalar(select(PublicSource).where(PublicSource.campaign_id == campaign.id, PublicSource.code == DEMO_SOURCE_CODE)) is None
