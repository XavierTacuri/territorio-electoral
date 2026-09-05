from app.db.session import SessionLocal
from app.services.territorial_catalog_service import TerritorialCatalogService


def main() -> None:
    with SessionLocal() as db:
        result = TerritorialCatalogService(db).import_inec_2026()
    print(
        f"Catálogo INEC 2026 importado: {result.provinces} provincias, "
        f"{result.cantons} cantones, {result.parishes} parroquias."
    )


if __name__ == "__main__":
    main()
