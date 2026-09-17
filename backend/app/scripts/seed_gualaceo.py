from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.territory import Canton,Parish,Province

PARISHES=(("010350","Gualaceo","URBAN"),("010352","Daniel Córdova Toral","RURAL"),("010353","Jadán","RURAL"),("010354","Mariano Moreno","RURAL"),("010356","Remigio Crespo Toral","RURAL"),("010357","San Juan","RURAL"),("010358","Zhidmad","RURAL"),("010359","Luis Cordero Vega","RURAL"),("010360","Simón Bolívar","RURAL"))

def seed(db:Session)->tuple[Province,Canton,list[Parish]]:
    province=db.scalar(select(Province).where(Province.code=="01"))
    if not province:province=Province(code="01",name="Azuay");db.add(province);db.flush()
    else:province.name="Azuay";province.is_active=True
    canton=db.scalar(select(Canton).where(Canton.dpa_code=="0103"))
    if not canton:canton=Canton(province_id=province.id,code="03",dpa_code="0103",name="Gualaceo");db.add(canton);db.flush()
    else:canton.province_id=province.id;canton.code="03";canton.name="Gualaceo";canton.is_active=True
    records=[]
    for dpa,name,kind in PARISHES:
        parish=db.scalar(select(Parish).where(Parish.dpa_code==dpa))
        if not parish:parish=Parish(canton_id=canton.id,code=dpa[-2:],dpa_code=dpa,name=name,parish_type=kind);db.add(parish)
        else:parish.canton_id=canton.id;parish.code=dpa[-2:];parish.name=name;parish.parish_type=kind;parish.is_active=True
        records.append(parish)
    db.flush()
    # The E2E fixture needs deterministic, non-authoritative geometries so
    # territorial map flows can render from a clean database. They are only
    # synthetic polygons (small squares near [0,0], NOT real Gualaceo boundaries)
    # tagged geometry_source=SYNTHETIC_PLACEHOLDER so the map API and frontend
    # never present them as official territory. Electoral values remain
    # separate from geometry. A parish already carrying an official import
    # (geometry_source=OFFICIAL_IMPORT) is left untouched: re-running this
    # seed must never clobber real imported geometry with a placeholder. This
    # guard is dialect-independent on purpose (it is a business rule, not a
    # spatial operation) so it also runs, and is testable, without PostGIS.
    for index, parish in enumerate(records):
        if parish.geometry_source == "OFFICIAL_IMPORT":
            continue
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            x = index % 3
            y = index // 3
            polygon = f"MULTIPOLYGON((({x} {y},{x + 0.8} {y},{x + 0.8} {y + 0.8},{x} {y + 0.8},{x} {y})))"
            db.execute(update(Parish).where(Parish.id == parish.id).values(geometry=func.ST_GeomFromText(polygon, 4326), geometry_source="SYNTHETIC_PLACEHOLDER", geometry_quality="PLACEHOLDER"))
    db.flush();return province,canton,records

def seed_gualaceo()->None:
    with SessionLocal() as db:
        try:
            province,canton,parishes=seed(db);db.commit();print(f"Territorio inicializado: {province.name}, {canton.name}, {len(parishes)} parroquias.")
        except SQLAlchemyError:
            db.rollback();print("No fue posible inicializar el territorio de Gualaceo.");raise SystemExit(1)
if __name__=="__main__":seed_gualaceo()
