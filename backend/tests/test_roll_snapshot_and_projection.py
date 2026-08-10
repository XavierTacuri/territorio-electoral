from datetime import date
from sqlalchemy import select

from app.models.historical import ElectoralRollSnapshot, ElectoralRollSnapshotEntry
from app.schemas.historical import DataSourceCreate
from app.scripts.seed_gualaceo import seed as seed_gualaceo
from app.services.data_import_service import DataImportService
from app.services.data_source_service import DataSourceService
from app.services.participation_projection_service import ParticipationProjectionService


def test_roll_snapshot_import_preserves_dpa_and_is_not_turnout(db, admin):
    province, canton, _ = seed_gualaceo(db)
    db.commit()
    source = DataSourceService(db).create(
        DataSourceCreate(
            code='TEST_ROLL_SOURCE',
            institution='Consejo Nacional Electoral',
            dataset_name='Registro sintético',
            dataset_type='CNE_ELECTORAL_ROLL_SNAPSHOT',
            publication_date=date(2026, 6, 1),
        ),
        admin,
    )
    content = (
        b'snapshot_date,process_code,geography_level,province_dpa,canton_dpa,parish_dpa,'
        b'registered_voters,male_voters,female_voters,electoral_zones,juntas\n'
        b'2026-06-01,,PARISH,01,0103,010350,100,40,60,1,2\n'
    )
    job = DataImportService(db).run(
        source.id,
        'CNE_ELECTORAL_ROLL_SNAPSHOT',
        'synthetic-roll.csv',
        content,
        admin,
        False,
    )
    assert job.status == 'COMPLETED' and job.rows_inserted == 1
    entry = db.scalar(select(ElectoralRollSnapshotEntry))
    assert entry.province_dpa == '01' and entry.canton_dpa == '0103' and entry.parish_dpa == '010350'
    assert db.scalar(select(ElectoralRollSnapshot)) is not None


def test_projection_model_is_versioned_and_exposes_weights():
    assert ParticipationProjectionService.MODEL_CODE == 'TURNOUT_HISTORICAL_WEIGHTED_V1'
    assert ParticipationProjectionService.MODEL_VERSION == '1.0'
    assert ParticipationProjectionService.OLD_WEIGHT + ParticipationProjectionService.RECENT_WEIGHT == 1
