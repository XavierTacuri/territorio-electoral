import csv
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.territory import Canton, Parish, Province


CATALOG_PATH = Path(__file__).parents[1] / "data" / "inec_dpa_2026.csv"
SOURCE_NAME = "Clasificador Geográfico Estadístico INEC 2026"
SOURCE_UPDATED_AT = "2025-12-31"
SOURCE_URL = "https://aplicaciones2.ecuadorencifras.gob.ec/SIN/descargas/cge2026.xls"


@dataclass(frozen=True)
class CatalogImportResult:
    provinces: int
    cantons: int
    parishes: int


class TerritorialCatalogService:
    """Importa datos maestros DPA sin eliminar territorios ya referenciados."""

    def __init__(self, db: Session):
        self.db = db

    def import_inec_2026(self, path: Path = CATALOG_PATH) -> CatalogImportResult:
        with path.open(encoding="utf-8", newline="") as catalog:
            rows = list(csv.DictReader(catalog))

        province_by_dpa: dict[str, Province] = {}
        for row in (item for item in rows if item["level"] == "PROVINCE"):
            province = self.db.scalar(select(Province).where(Province.code == row["dpa_code"]))
            if province is None:
                province = Province(code=row["dpa_code"], name=row["name"], is_active=True)
                self.db.add(province)
            else:
                province.name, province.is_active = row["name"], True
            province_by_dpa[row["dpa_code"]] = province
        self.db.flush()

        canton_by_dpa: dict[str, Canton] = {}
        for row in (item for item in rows if item["level"] == "CANTON"):
            canton = self.db.scalar(select(Canton).where(Canton.dpa_code == row["dpa_code"]))
            values = dict(
                province_id=province_by_dpa[row["parent_dpa_code"]].id,
                code=row["dpa_code"][2:],
                name=row["name"],
                is_active=True,
            )
            if canton is None:
                canton = Canton(dpa_code=row["dpa_code"], **values)
                self.db.add(canton)
            else:
                for key, value in values.items(): setattr(canton, key, value)
            canton_by_dpa[row["dpa_code"]] = canton
        self.db.flush()

        parish_count = 0
        current_parish_dpas: set[str] = set()
        for row in (item for item in rows if item["level"] == "PARISH"):
            current_parish_dpas.add(row["dpa_code"])
            parish = self.db.scalar(select(Parish).where(Parish.dpa_code == row["dpa_code"]))
            values = dict(
                canton_id=canton_by_dpa[row["parent_dpa_code"]].id,
                code=row["dpa_code"][4:],
                name=row["name"],
                parish_type=row["parish_type"],
                is_active=True,
            )
            if parish is None:
                self.db.add(Parish(dpa_code=row["dpa_code"], **values))
            else:
                for key, value in values.items(): setattr(parish, key, value)
            parish_count += 1

        # Preserve referenced historical/legacy rows, but keep only DPA entries present in
        # the current official catalog selectable inside official Ecuadorian cantons.
        official_canton_ids = [canton.id for canton in canton_by_dpa.values()]
        self.db.query(Parish).filter(
            Parish.canton_id.in_(official_canton_ids),
            Parish.dpa_code.not_in(current_parish_dpas),
        ).update({Parish.is_active: False}, synchronize_session=False)

        self.db.commit()
        return CatalogImportResult(len(province_by_dpa), len(canton_by_dpa), parish_count)
