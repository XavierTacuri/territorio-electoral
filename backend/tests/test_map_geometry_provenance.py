from datetime import date
import pytest
from sqlalchemy.orm import Session
from app.models.territory import Canton, Parish, Province
from app.schemas.campaign import CampaignCreate
from app.schemas.maps import MapFilters
from app.scripts.seed_gualaceo import seed as seed_gualaceo
from app.services.campaign_service import CampaignService
from app.services.map_service import MapService


@pytest.fixture
def map_context(db: Session, admin):
    _, canton, parishes = seed_gualaceo(db)
    db.commit()
    campaign = CampaignService(db).create(
        CampaignCreate(
            name="Mapa Gualaceo",
            slug="mapa-gualaceo-provenance",
            canton_id=canton.id,
            office_type="MAYOR",
            election_name="Seccionales 2027",
            election_date=date(2027, 2, 14),
            status="DRAFT",
        ),
        admin,
    )
    return campaign, canton, parishes


def test_parish_and_canton_default_geometry_provenance_is_unknown(db: Session):
    province = Province(code="55", name="Provincia Test")
    db.add(province)
    db.flush()
    canton = Canton(province_id=province.id, code="01", dpa_code="5501", name="Cantón Test")
    db.add(canton)
    db.flush()
    parish = Parish(canton_id=canton.id, code="01", dpa_code="550101", name="Parroquia Test", parish_type="URBAN")
    db.add(parish)
    db.commit()
    assert canton.geometry_source == "UNKNOWN" and canton.geometry_quality == "UNKNOWN"
    assert parish.geometry_source == "UNKNOWN" and parish.geometry_quality == "UNKNOWN"


def test_seed_gualaceo_never_overwrites_an_official_import(db: Session):
    _, _, parishes = seed_gualaceo(db)
    db.commit()
    official = parishes[0]
    official.geometry = "OFFICIAL-GEOMETRY-SENTINEL"
    official.geometry_source = "OFFICIAL_IMPORT"
    official.geometry_quality = "VALID"
    db.commit()

    # Re-running the seed (e.g. a fresh dev bootstrap after a real import
    # already happened) must not clobber the official geometry with a
    # placeholder square.
    seed_gualaceo(db)
    db.commit()
    db.refresh(official)

    assert official.geometry_source == "OFFICIAL_IMPORT"
    assert official.geometry_quality == "VALID"
    assert official.geometry == "OFFICIAL-GEOMETRY-SENTINEL"


def test_boundaries_endpoint_returns_real_geometry_source_never_hardcoded(db: Session, admin, map_context):
    campaign, _, parishes = map_context
    placeholder, official = parishes[0], parishes[1]
    placeholder.geometry = "PLACEHOLDER-WKT"
    placeholder.geometry_source = "SYNTHETIC_PLACEHOLDER"
    placeholder.geometry_quality = "PLACEHOLDER"
    official.geometry = "OFFICIAL-WKT"
    official.geometry_source = "OFFICIAL_IMPORT"
    official.geometry_quality = "VALID"
    db.commit()

    result = MapService(db).boundaries(campaign.id, admin, MapFilters())
    by_id = {f["properties"]["resource_id"]: f["properties"] for f in result["features"]}

    assert by_id[str(placeholder.id)]["geometry_source"] == "SYNTHETIC_PLACEHOLDER"
    assert by_id[str(placeholder.id)]["geometry_quality"] == "PLACEHOLDER"
    assert by_id[str(official.id)]["geometry_source"] == "OFFICIAL_IMPORT"
    assert by_id[str(official.id)]["geometry_quality"] == "VALID"


def test_thematic_layer_reports_real_geometry_source_per_parish(db: Session, admin, map_context):
    campaign, _, parishes = map_context
    placeholder = parishes[0]
    placeholder.geometry = "PLACEHOLDER-WKT"
    placeholder.geometry_source = "SYNTHETIC_PLACEHOLDER"
    placeholder.geometry_quality = "PLACEHOLDER"
    db.commit()

    result = MapService(db).thematic(campaign.id, admin, MapFilters(), "OPERATIONAL_COVERAGE", "COMPLETED_ACTIVITIES")
    feature = next(f for f in result["features"] if f["properties"]["resource_id"] == str(placeholder.id))

    assert feature["properties"]["geometry_source"] == "SYNTHETIC_PLACEHOLDER"


def test_boundaries_http_endpoint_reflects_real_geometry_source(client, admin_headers, map_context, db: Session):
    campaign, _, parishes = map_context
    official = parishes[0]
    official.geometry = "OFFICIAL-WKT"
    official.geometry_source = "OFFICIAL_IMPORT"
    official.geometry_quality = "VALID"
    db.commit()

    response = client.get(f"/api/v1/campaigns/{campaign.id}/map/boundaries?level=PARISH", headers=admin_headers)
    assert response.status_code == 200
    feature = next(f for f in response.json()["features"] if f["properties"]["resource_id"] == str(official.id))
    assert feature["properties"]["geometry_source"] == "OFFICIAL_IMPORT"
