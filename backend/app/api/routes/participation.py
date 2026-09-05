from datetime import date
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_active_user, require_admin
from app.db.session import get_db
from app.models.historical import ElectoralRollSnapshot, ElectoralRollSnapshotEntry, ParticipationProjectionRun, ParticipationProjectionResult, ElectoralProcess, ElectoralContest, ElectoralGeography, ElectoralTurnout, DemographicIndicator, DemographicObservation, DataSource
from app.models.campaign import Campaign
from app.models.territory import Canton, Parish
from app.services.campaign_access_service import CampaignAccessService
from app.models.user import User
from app.schemas.historical import ElectoralRollSnapshotRead, ElectoralRollSnapshotEntryRead, ParticipationProjectionRunRead, ParticipationProjectionResultRead
from app.services.participation_projection_service import ParticipationProjectionService
from app.services.exceptions import BusinessRuleError, NotFoundError

router = APIRouter(tags=['participation'])

@router.get('/campaigns/{campaign_id}/current-election/analysis')
def current_election_analysis(campaign_id: UUID, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    campaign = db.get(Campaign, campaign_id)
    if not campaign: raise HTTPException(404, 'Campaña inexistente')
    try: CampaignAccessService(db).require_access(campaign_id, user)
    except PermissionError as exc: raise HTTPException(403, str(exc)) from exc
    run = db.scalar(select(ParticipationProjectionRun).where(ParticipationProjectionRun.campaign_id == campaign_id).order_by(ParticipationProjectionRun.created_at.desc()))
    snapshot = db.get(ElectoralRollSnapshot, run.snapshot_id) if run else None
    if not snapshot or not run: raise HTTPException(404, 'Datos de elección actual incompletos')
    entries = list(db.scalars(select(ElectoralRollSnapshotEntry).where(ElectoralRollSnapshotEntry.snapshot_id == snapshot.id, ElectoralRollSnapshotEntry.geography_level == 'PARISH', ElectoralRollSnapshotEntry.canton_id == campaign.canton_id)))
    parish_ids = [e.parish_id for e in entries if e.parish_id is not None]
    access = CampaignAccessService(db)
    roles = {r.code for r in user.roles}
    broad = access.admin(user) or bool(roles.intersection({'CANDIDATE', 'CAMPAIGN_MANAGER', 'ANALYST'}))
    if not broad:
        assignments = access.territorial_ids(campaign_id, user)
        if assignments is not None:
            allowed_parish_ids = {a.parish_id for a in assignments}
            parish_ids = [pid for pid in parish_ids if pid in allowed_parish_ids]
    entries = [e for e in entries if e.parish_id in parish_ids]
    parishes = {p.id: p for p in db.scalars(select(Parish).where(Parish.id.in_(parish_ids)))}
    results = {r.parish_id: r for r in db.scalars(select(ParticipationProjectionResult).where(ParticipationProjectionResult.run_id == run.id))}
    processes = list(db.scalars(select(ElectoralProcess).where(ElectoralProcess.id.in_([str(x) for x in run.historical_process_ids]))))
    historical = {}
    for process in processes:
        contest = db.scalar(select(ElectoralContest).where(ElectoralContest.electoral_process_id == process.id, ElectoralContest.office_type == campaign.office_type, ElectoralContest.canton_id == campaign.canton_id, ElectoralContest.is_active.is_(True)))
        if not contest: continue
        rows = db.execute(select(ElectoralGeography.parish_id, ElectoralTurnout.registered_voters, ElectoralTurnout.ballots_cast).join(ElectoralTurnout, ElectoralTurnout.electoral_geography_id == ElectoralGeography.id).where(ElectoralGeography.electoral_process_id == process.id, ElectoralGeography.level == 'PARISH', ElectoralGeography.parish_id.in_(parish_ids), ElectoralTurnout.electoral_contest_id == contest.id, ElectoralTurnout.is_final.is_(True))).all()
        historical[process.year] = {pid: {'registered_voters': registered, 'ballots_cast': ballots, 'turnout_rate': float(ballots / registered) if registered else None} for pid, registered, ballots in rows}
    indicators = {i.id: i for i in db.scalars(select(DemographicIndicator).where(DemographicIndicator.is_active.is_(True)))}
    observations = db.execute(select(DemographicObservation, DemographicIndicator).join(DemographicIndicator, DemographicIndicator.id == DemographicObservation.demographic_indicator_id).where(DemographicObservation.parish_id.in_(parish_ids), DemographicObservation.reference_year.in_([2010, 2022]), DemographicObservation.is_active.is_(True), DemographicObservation.is_official.is_(True))).all()
    demographic_by_year = {2010: {pid: {} for pid in parish_ids}, 2022: {pid: {} for pid in parish_ids}}
    for obs, indicator in observations: demographic_by_year.setdefault(obs.reference_year, {}).setdefault(obs.parish_id, {})[indicator.code] = float(obs.value)
    demographic = demographic_by_year[2022]
    age_groups = {'AGE_0_14': ('POP_AGE_0_4','POP_AGE_5_9','POP_AGE_10_14'), 'AGE_15_29': ('POP_AGE_15_19','POP_AGE_20_24','POP_AGE_25_29'), 'AGE_30_44': ('POP_AGE_30_34','POP_AGE_35_39','POP_AGE_40_44'), 'AGE_45_64': ('POP_AGE_45_49','POP_AGE_50_54','POP_AGE_55_59','POP_AGE_60_64'), 'AGE_65_PLUS': ('POP_AGE_65_69','POP_AGE_70_74','POP_AGE_75_79','POP_AGE_80_84','POP_AGE_85_PLUS')}
    for values in demographic.values():
        for name, codes in age_groups.items(): values[name] = sum(values.get(code, 0) for code in codes)
    entry_by_parish = {e.parish_id: e for e in entries}
    parish_rows = []
    for pid in parish_ids:
        entry, result = entry_by_parish[pid], results.get(pid); values = demographic.get(pid, {})
        old_values=demographic_by_year.get(2010, {}).get(pid, {});population_2010=old_values.get('POP_TOTAL');population_2022=values.get('POP_TOTAL');growth=((population_2022-population_2010)/population_2010) if population_2010 and population_2022 is not None else None
        parish_rows.append({'parish_id': pid, 'name': parishes.get(pid).name if parishes.get(pid) else entry.parish_dpa, 'dpa_code': entry.parish_dpa, 'registered_voters_current': entry.registered_voters, 'male_voters': entry.male_voters, 'female_voters': entry.female_voters, 'juntas': entry.juntas, 'historical_2019': historical.get(2019, {}).get(pid), 'historical_2023': historical.get(2023, {}).get(pid), 'projection': {'low': float(result.turnout_rate_low), 'central': float(result.turnout_rate_central), 'high': float(result.turnout_rate_high), 'expected_voters_low': result.expected_voters_low, 'expected_voters_central': result.expected_voters_central, 'expected_voters_high': result.expected_voters_high} if result else None, 'data_quality_status': result.data_quality_status if result else 'INSUFFICIENT_DATA', 'demographics': values, 'demographics_2010': old_values, 'population_growth_2010_2022': growth, 'availability': {'cne_2019': pid in historical.get(2019, {}), 'cne_2023': pid in historical.get(2023, {}), 'current_registration': True, 'inec_2022': bool(values), 'geometry': bool(parishes.get(pid) and parishes[pid].geometry is not None)}})
    totals = lambda rows, key: sum((row.get(key) or 0) for row in rows)
    current_total = {'registered_voters': totals(parish_rows, 'registered_voters_current'), 'male_voters': totals(parish_rows, 'male_voters'), 'female_voters': totals(parish_rows, 'female_voters'), 'juntas': totals(parish_rows, 'juntas')}
    historical_totals = {str(year): {'registered_voters': sum(v['registered_voters'] for v in rows.values()), 'ballots_cast': sum(v['ballots_cast'] for v in rows.values()), 'turnout_rate': (sum(v['ballots_cast'] for v in rows.values()) / sum(v['registered_voters'] for v in rows.values())) if rows else None} for year, rows in historical.items()}
    projection_totals = {key: sum((row['projection'] or {}).get(key, 0) for row in parish_rows) for key in ('expected_voters_low','expected_voters_central','expected_voters_high')}
    warnings = []
    latest_historical = historical_totals.get('2023')
    if latest_historical and latest_historical['registered_voters'] and abs(current_total['registered_voters'] - latest_historical['registered_voters']) / latest_historical['registered_voters'] > 0.10: warnings.append({'code': 'REGISTRATION_SERIES_BREAK', 'message': 'Se detectó una variación elevada del registro electoral entre procesos. Esta diferencia puede responder a cambios administrativos, metodológicos, territoriales o del registro electoral y no debe interpretarse automáticamente como una tendencia demográfica.'})
    older_historical = historical_totals.get('2019')
    if older_historical and latest_historical and older_historical['registered_voters'] and abs(latest_historical['registered_voters'] - older_historical['registered_voters']) / older_historical['registered_voters'] > 0.10 and not warnings: warnings.append({'code': 'REGISTRATION_SERIES_BREAK', 'message': 'Se detectó una variación elevada del registro electoral entre procesos. Esta diferencia puede responder a cambios administrativos, metodológicos, territoriales o del registro electoral y no debe interpretarse automáticamente como una tendencia demográfica.'})
    canton = db.get(Canton, campaign.canton_id)
    current_process = db.get(ElectoralProcess, snapshot.electoral_process_id) if snapshot.electoral_process_id else None
    source_ids={snapshot.source_id};source_ids.update(p.source_id for p in processes);source_ids.update(obs.source_id for obs,_ in observations);sources=list(db.scalars(select(DataSource).where(DataSource.id.in_(source_ids))))
    return {'context': {'campaign_name': campaign.name, 'canton_name': canton.name if canton else str(campaign.canton_id), 'election_name': current_process.name if current_process else campaign.election_name}, 'snapshot': {'id': str(snapshot.id), 'snapshot_date': snapshot.snapshot_date, 'name': snapshot.name, **current_total}, 'historical': historical_totals, 'projection': {'model_code': run.model_code, 'model_version': run.model_version, 'parameters': run.parameters, **projection_totals}, 'warnings': warnings, 'demographics': {'year': 2022, 'parishes': parish_rows}, 'sources': [{'code':s.code,'institution':s.institution,'dataset_name':s.dataset_name,'dataset_type':s.dataset_type,'official_url':s.official_url,'reference_year':s.reference_year,'reference_date':s.reference_date,'publication_date':s.publication_date} for s in sources], 'parishes': parish_rows}

@router.get('/electoral-roll-snapshots', response_model=list[ElectoralRollSnapshotRead])
def snapshots(source_id: UUID | None = None, process_id: UUID | None = None, snapshot_date: date | None = None, _: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    q = select(ElectoralRollSnapshot).where(ElectoralRollSnapshot.is_final.is_(True))
    if source_id: q = q.where(ElectoralRollSnapshot.source_id == source_id)
    if process_id: q = q.where(ElectoralRollSnapshot.electoral_process_id == process_id)
    if snapshot_date: q = q.where(ElectoralRollSnapshot.snapshot_date == snapshot_date)
    return list(db.scalars(q.order_by(ElectoralRollSnapshot.snapshot_date.desc())))

@router.get('/electoral-roll-snapshots/latest', response_model=ElectoralRollSnapshotRead)
def latest_snapshot(_: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    obj = db.scalar(select(ElectoralRollSnapshot).where(ElectoralRollSnapshot.is_final.is_(True)).order_by(ElectoralRollSnapshot.snapshot_date.desc()))
    if not obj: raise HTTPException(404, 'Snapshot de registro inexistente')
    return obj

@router.get('/electoral-roll-snapshots/{snapshot_id}', response_model=ElectoralRollSnapshotRead)
def snapshot(snapshot_id: UUID, _: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    obj = db.get(ElectoralRollSnapshot, snapshot_id)
    if not obj: raise HTTPException(404, 'Snapshot de registro inexistente')
    return obj

@router.get('/electoral-roll-snapshots/{snapshot_id}/entries', response_model=list[ElectoralRollSnapshotEntryRead])
def snapshot_entries(snapshot_id: UUID, canton_id: int | None = None, _: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if not db.get(ElectoralRollSnapshot, snapshot_id): raise HTTPException(404, 'Snapshot de registro inexistente')
    q = select(ElectoralRollSnapshotEntry).where(ElectoralRollSnapshotEntry.snapshot_id == snapshot_id)
    if canton_id: q = q.where(ElectoralRollSnapshotEntry.canton_id == canton_id)
    return list(db.scalars(q))

@router.post('/participation-projections', status_code=201)
def create_projection(campaign_id: UUID, snapshot_id: UUID, process_ids: list[UUID] | None = Query(None), user: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        result = ParticipationProjectionService(db).project(campaign_id, snapshot_id, user.id, process_ids)
        return {'run': ParticipationProjectionRunRead.model_validate(result['run']).model_dump(mode='json'), 'warnings': result['warnings'], 'historical_processes': [str(x.id) for x in result['historical_processes']]}
    except (BusinessRuleError, NotFoundError) as exc: raise HTTPException(400 if isinstance(exc, BusinessRuleError) else 404, str(exc))

@router.get('/campaigns/{campaign_id}/participation-projections/latest')
def latest_projection(campaign_id: UUID, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    try: CampaignAccessService(db).require_access(campaign_id, user)
    except PermissionError as exc: raise HTTPException(403, str(exc)) from exc
    run = ParticipationProjectionService(db).latest(campaign_id)
    if not run: raise HTTPException(404, 'Proyección inexistente')
    return {'run': ParticipationProjectionRunRead.model_validate(run), 'results': [ParticipationProjectionResultRead.model_validate(x) for x in ParticipationProjectionService(db).results(run.id)]}

@router.get('/participation-projections/{run_id}', response_model=ParticipationProjectionRunRead)
def projection(run_id: UUID, _: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    from app.models.historical import ParticipationProjectionRun
    obj = db.get(ParticipationProjectionRun, run_id)
    if not obj: raise HTTPException(404, 'Proyección inexistente')
    return obj

@router.get('/participation-projections/{run_id}/results', response_model=list[ParticipationProjectionResultRead])
def projection_results(run_id: UUID, _: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    return ParticipationProjectionService(db).results(run_id)

@router.get('/participation-projections/{run_id}/explanation')
def projection_explanation(run_id: UUID, _: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    from app.models.historical import ParticipationProjectionRun
    obj = db.get(ParticipationProjectionRun, run_id)
    if not obj: raise HTTPException(404, 'Proyección inexistente')
    return {'model_code': obj.model_code, 'model_version': obj.model_version, 'parameters': obj.parameters, 'results': [ParticipationProjectionResultRead.model_validate(x) for x in ParticipationProjectionService(db).results(run_id)]}
