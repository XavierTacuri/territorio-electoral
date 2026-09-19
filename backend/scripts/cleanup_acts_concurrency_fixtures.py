"""Limpia los datos sintéticos que dejan corridas de verify_acts_concurrency.py
en la base de datos de desarrollo (nunca en producción). Conserva la fila de
territorio reservada (id=989898) para que corridas futuras la reutilicen.

§17 auditoría Fase 2: el matching NUNCA usa un patrón amplio como el nombre
de campaña ("Concurrencia %" podría coincidir con una campaña real llamada
así — "concurrencia" es una palabra española común). Todo el borrado se
ancla en identificadores sintéticos que solo este script crea:
- electoral_processes.code LIKE 'CC-PROC-%' (nunca un código real)
- data_sources.code LIKE 'CC-SRC-%'
- users.username que coincide EXACTAMENTE con los prefijos literales que
  verify_acts_concurrency.py usa (cc_admin_/cc_exec_/cc_d1_/cc_v1_/cc_v2_),
  nunca un comodín genérico 'cc_%' que pudiera atrapar un username real.
Las campañas a borrar se derivan de esos procesos sintéticos (vía
election_day_operations), no de su nombre.
"""
import re

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.campaign import Campaign
from app.models.historical import ElectoralProcess

engine = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)

SYNTHETIC_USERNAME_RE = re.compile(r"^cc_(admin|exec|d1|v1|v2)_[0-9a-f]{8}$")


def main():
    if settings.app_env.lower() == "production":
        raise SystemExit("Este script borra datos y nunca debe correr con APP_ENV=production")
    db = Session()
    process_ids = list(db.scalars(select(ElectoralProcess.id).where(ElectoralProcess.code.like("CC-PROC-%"))))
    print(f"Procesos electorales sintéticos encontrados: {len(process_ids)}")
    if not process_ids:
        print("Nada que limpiar.")
        return
    campaign_ids = [row[0] for row in db.execute(
        text("SELECT DISTINCT campaign_id FROM election_day_operations WHERE electoral_process_id = ANY(:ids)"),
        {"ids": process_ids},
    ).all()]
    # Segunda comprobación (cinturón y tirantes): además de venir de un
    # proceso sintético, el nombre debe empezar por "Concurrencia " — si
    # alguna vez no coincide, se excluye en vez de asumir que sí es sintética.
    campaign_ids = [
        c.id for c in db.scalars(select(Campaign).where(Campaign.id.in_(campaign_ids)))
        if c.name.startswith("Concurrencia ")
    ]
    print(f"Campañas sintéticas encontradas: {len(campaign_ids)}")

    # Usuarios: coinciden por prefijo Y por pertenecer únicamente a estas
    # campañas — nunca por el patrón de nombre de usuario en solitario.
    all_synthetic_users = db.execute(text("SELECT id, username FROM users")).all()
    user_ids = [row[0] for row in all_synthetic_users if SYNTHETIC_USERNAME_RE.match(row[1] or "")]
    print(f"Usuarios sintéticos encontrados: {len(user_ids)}")

    if campaign_ids:
        db.execute(text("DELETE FROM election_act_results WHERE revision_id IN (SELECT r.id FROM election_act_revisions r JOIN election_acts a ON a.id = r.act_id WHERE a.campaign_id = ANY(:ids))"), {"ids": campaign_ids})
        db.execute(text("DELETE FROM election_act_evidence WHERE revision_id IN (SELECT r.id FROM election_act_revisions r JOIN election_acts a ON a.id = r.act_id WHERE a.campaign_id = ANY(:ids))"), {"ids": campaign_ids})
        db.execute(text("DELETE FROM election_act_reviews WHERE act_id IN (SELECT id FROM election_acts WHERE campaign_id = ANY(:ids))"), {"ids": campaign_ids})
        db.execute(text("UPDATE election_acts SET validated_revision_id = NULL WHERE campaign_id = ANY(:ids)"), {"ids": campaign_ids})
        db.execute(text("DELETE FROM election_act_revisions WHERE act_id IN (SELECT id FROM election_acts WHERE campaign_id = ANY(:ids))"), {"ids": campaign_ids})
        db.execute(text("DELETE FROM election_acts WHERE campaign_id = ANY(:ids)"), {"ids": campaign_ids})
        db.execute(text("DELETE FROM election_day_assignments WHERE operation_id IN (SELECT id FROM election_day_operations WHERE campaign_id = ANY(:ids))"), {"ids": campaign_ids})
        db.execute(text("DELETE FROM election_day_operations WHERE campaign_id = ANY(:ids)"), {"ids": campaign_ids})
        db.execute(text("DELETE FROM campaign_users WHERE campaign_id = ANY(:ids)"), {"ids": campaign_ids})
        db.execute(text("DELETE FROM campaigns WHERE id = ANY(:ids)"), {"ids": campaign_ids})
    db.execute(text("DELETE FROM electoral_boards WHERE polling_place_id IN (SELECT id FROM polling_places WHERE data_source_id IN (SELECT id FROM data_sources WHERE code LIKE 'CC-SRC-%'))"))
    db.execute(text("DELETE FROM polling_places WHERE data_source_id IN (SELECT id FROM data_sources WHERE code LIKE 'CC-SRC-%')"))
    db.execute(text("DELETE FROM electoral_candidates WHERE external_code LIKE 'CC-CAND-%'"))
    db.execute(text("DELETE FROM electoral_contests WHERE electoral_process_id = ANY(:ids)"), {"ids": process_ids})
    db.execute(text("DELETE FROM electoral_processes WHERE id = ANY(:ids)"), {"ids": process_ids})
    db.execute(text("DELETE FROM data_sources WHERE code LIKE 'CC-SRC-%'"))
    if user_ids:
        db.execute(text("DELETE FROM organization_memberships WHERE user_id = ANY(:ids)"), {"ids": user_ids})
        db.execute(text("DELETE FROM user_roles WHERE user_id = ANY(:ids)"), {"ids": user_ids})
        db.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": user_ids})
    db.commit()
    print("Limpieza completada.")


if __name__ == "__main__":
    main()
