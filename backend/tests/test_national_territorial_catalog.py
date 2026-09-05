from datetime import date

import pytest
from sqlalchemy import func, select

from app.models.campaign import Campaign
from app.models.territory import Canton, Parish, Province
from app.schemas.campaign import CampaignCreate
from app.services.campaign_service import CampaignService
from app.services.exceptions import BusinessRuleError
from app.services.territorial_catalog_service import TerritorialCatalogService


def load_catalog(db):
    first = TerritorialCatalogService(db).import_inec_2026()
    second = TerritorialCatalogService(db).import_inec_2026()
    assert first == second
    return first


def test_inec_2026_catalog_is_national_and_idempotent(db):
    result = load_catalog(db)
    assert result.provinces == 24
    assert result.cantons == 222
    assert result.parishes == 1317
    assert db.scalar(select(func.count()).select_from(Province)) == 24
    assert db.scalar(select(func.count()).select_from(Canton)) == 222
    assert db.scalar(select(func.count()).select_from(Parish)) == 1317
    assert db.scalar(select(Province).where(Province.code == "90")) is None


@pytest.mark.parametrize(
    ("province_dpa", "expected_canton"),
    [
        ("01", "Cuenca"),
        ("17", "Distrito Metropolitano de Quito"),
        ("09", "Guayaquil"),
        ("13", "Manta"),
        ("11", "Loja"),
        ("20", "San Cristóbal"),
    ],
)
def test_cantons_belong_to_official_province(db, province_dpa, expected_canton):
    load_catalog(db)
    province = db.scalar(select(Province).where(Province.code == province_dpa))
    names = set(db.scalars(select(Canton.name).where(Canton.province_id == province.id)))
    assert expected_canton in names


def test_parishes_are_scoped_to_canton_and_gualaceo_is_reused(db):
    load_catalog(db)
    gualaceo = db.scalar(select(Canton).where(Canton.dpa_code == "0103"))
    assert gualaceo.name == "Gualaceo"
    assert db.scalar(select(func.count()).select_from(Canton).where(Canton.dpa_code == "0103")) == 1
    parish_dpas = set(db.scalars(select(Parish.dpa_code).where(Parish.canton_id == gualaceo.id)))
    assert {"010350", "010353", "010360"}.issubset(parish_dpas)
    assert "170150" not in parish_dpas


def test_gualaceo_exposes_exactly_nine_current_dpa_territories(client, admin_headers, db):
    load_catalog(db)
    gualaceo = db.scalar(select(Canton).where(Canton.dpa_code == "0103"))
    for dpa, name in (("010351", "Chordeleg"), ("010355", "Principal"), ("010398", "Centro")):
        if db.scalar(select(Parish).where(Parish.dpa_code == dpa)) is None:
            db.add(Parish(
                canton_id=gualaceo.id,
                code=dpa[-2:],
                dpa_code=dpa,
                name=name,
                parish_type="RURAL" if dpa != "010398" else "URBAN",
                is_active=True,
            ))
    db.commit()

    load_catalog(db)
    expected = {
        "010350", "010352", "010353", "010354", "010356",
        "010357", "010358", "010359", "010360",
    }
    active = set(db.scalars(select(Parish.dpa_code).where(
        Parish.canton_id == gualaceo.id,
        Parish.is_active.is_(True),
    )))
    assert active == expected
    assert set(db.scalars(select(Parish.dpa_code).where(
        Parish.dpa_code.in_(("010351", "010355", "010398")),
        Parish.is_active.is_(False),
    ))) == {"010351", "010355", "010398"}

    response = client.get(f"/api/v1/parishes?canton_id={gualaceo.id}", headers=admin_headers)
    assert response.status_code == 200
    assert {item["dpa_code"] for item in response.json()} == expected
    assert len(response.json()) == 9


def test_campaign_rejects_canton_from_another_province(db, admin):
    load_catalog(db)
    azuay = db.scalar(select(Province).where(Province.code == "01"))
    guayaquil = db.scalar(select(Canton).where(Canton.dpa_code == "0901"))
    with pytest.raises(BusinessRuleError, match="no pertenece a la provincia"):
        CampaignService(db).create(
            CampaignCreate(
                name="Cruce inválido",
                slug="cruce-invalido",
                province_id=azuay.id,
                canton_id=guayaquil.id,
                office_type="MAYOR",
                election_name="Elecciones Seccionales 2027",
                election_date=date(2027, 2, 14),
            ),
            admin,
        )


def test_cuenca_and_quito_campaigns_can_be_created_and_cleaned_up(db, admin):
    load_catalog(db)
    gualaceo_id = db.scalar(select(Canton.id).where(Canton.dpa_code == "0103"))
    created = []
    for slug, province_dpa, canton_dpa in (
        ("demo-cuenca-territorial", "01", "0101"),
        ("demo-quito-territorial", "17", "1701"),
    ):
        province = db.scalar(select(Province).where(Province.code == province_dpa))
        canton = db.scalar(select(Canton).where(Canton.dpa_code == canton_dpa))
        created.append(CampaignService(db).create(CampaignCreate(
            name=f"[DEMO] {canton.name} territorial",
            slug=slug,
            province_id=province.id,
            canton_id=canton.id,
            office_type="MAYOR",
            election_name="Elecciones Seccionales 2027",
            election_date=date(2027, 2, 14),
        ), admin))
    assert [campaign.canton_id for campaign in created] == [
        db.scalar(select(Canton.id).where(Canton.dpa_code == "0101")),
        db.scalar(select(Canton.id).where(Canton.dpa_code == "1701")),
    ]
    for campaign in created: db.delete(campaign)
    db.commit()
    assert db.scalar(select(func.count()).select_from(Campaign).where(Campaign.slug.like("demo-%-territorial"))) == 0
    assert db.scalar(select(Canton.id).where(Canton.dpa_code == "0103")) == gualaceo_id


def test_catalog_endpoints_return_lightweight_scoped_payloads(client, admin_headers, db):
    load_catalog(db)
    provinces = client.get("/api/v1/provinces", headers=admin_headers)
    assert provinces.status_code == 200 and len(provinces.json()) == 24
    azuay = next(item for item in provinces.json() if item["dpa_code"] == "01")
    cantons = client.get(f"/api/v1/cantons?province_id={azuay['id']}", headers=admin_headers)
    assert cantons.status_code == 200
    assert {item["name"] for item in cantons.json()} >= {"Cuenca", "Gualaceo", "Paute"}
    assert all(item["province_id"] == azuay["id"] and "geometry" not in item for item in cantons.json())
