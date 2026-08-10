from sqlalchemy import select
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
    db.flush();return province,canton,records

def seed_gualaceo()->None:
    with SessionLocal() as db:
        try:
            province,canton,parishes=seed(db);db.commit();print(f"Territorio inicializado: {province.name}, {canton.name}, {len(parishes)} parroquias.")
        except SQLAlchemyError:
            db.rollback();print("No fue posible inicializar el territorio de Gualaceo.");raise SystemExit(1)
if __name__=="__main__":seed_gualaceo()
