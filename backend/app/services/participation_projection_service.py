from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.campaign import Campaign
from app.models.historical import (ElectoralContest, ElectoralProcess, ElectoralRollSnapshot,
    ElectoralRollSnapshotEntry, ElectoralGeography, ElectoralTurnout,
    ParticipationProjectionResult, ParticipationProjectionRun)
from app.services.exceptions import BusinessRuleError, NotFoundError


class ParticipationProjectionService:
    MODEL_CODE = 'TURNOUT_HISTORICAL_WEIGHTED_V1'
    MODEL_VERSION = '1.0'
    OLD_WEIGHT = Decimal('0.35')
    RECENT_WEIGHT = Decimal('0.65')
    BREAK_THRESHOLD = Decimal('0.10')

    def __init__(self, db: Session): self.db = db

    def _processes(self, campaign, process_ids=None):
        q = select(ElectoralProcess).join(ElectoralContest, ElectoralContest.electoral_process_id == ElectoralProcess.id).where(
            ElectoralProcess.process_type == 'SECTIONAL', ElectoralProcess.is_final.is_(True), ElectoralProcess.is_active.is_(True),
            ElectoralContest.office_type == campaign.office_type, ElectoralContest.canton_id == campaign.canton_id, ElectoralContest.is_active.is_(True))
        if process_ids: q = q.where(ElectoralProcess.id.in_(process_ids))
        return list(self.db.scalars(q.order_by(ElectoralProcess.year.desc())).unique())[:2]

    def project(self, campaign_id, snapshot_id, user_id, process_ids=None):
        campaign = self.db.get(Campaign, campaign_id)
        if not campaign: raise NotFoundError('Campaña inexistente')
        snapshot = self.db.get(ElectoralRollSnapshot, snapshot_id)
        if not snapshot: raise NotFoundError('Snapshot de registro inexistente')
        processes = self._processes(campaign, process_ids)
        if not processes: raise BusinessRuleError('INSUFFICIENT_DATA: no hay procesos históricos compatibles')
        parameters = {'historical_weight_old': str(self.OLD_WEIGHT), 'historical_weight_recent': str(self.RECENT_WEIGHT), 'registration_break_threshold': str(self.BREAK_THRESHOLD)}
        run = ParticipationProjectionRun(campaign_id=campaign.id, electoral_process_id=processes[0].id if processes else campaign.id, snapshot_id=snapshot.id, model_code=self.MODEL_CODE, model_version=self.MODEL_VERSION, historical_process_ids=[str(p.id) for p in processes], parameters=parameters, run_date=date.today(), created_by_user_id=user_id)
        self.db.add(run); self.db.flush()
        entries = list(self.db.scalars(select(ElectoralRollSnapshotEntry).where(ElectoralRollSnapshotEntry.snapshot_id == snapshot.id, ElectoralRollSnapshotEntry.geography_level == 'PARISH', ElectoralRollSnapshotEntry.canton_id == campaign.canton_id)))
        warnings = []
        if len(processes) < 2: warnings.append('LOW_HISTORICAL_COVERAGE')
        historical = {}
        for process in processes:
            contest = self.db.scalar(select(ElectoralContest).where(ElectoralContest.electoral_process_id == process.id, ElectoralContest.office_type == campaign.office_type, ElectoralContest.canton_id == campaign.canton_id, ElectoralContest.is_active.is_(True)))
            if not contest: continue
            rows = self.db.execute(select(ElectoralGeography.parish_id, ElectoralTurnout.registered_voters, ElectoralTurnout.ballots_cast).join(ElectoralTurnout, ElectoralTurnout.electoral_geography_id == ElectoralGeography.id).where(ElectoralGeography.electoral_process_id == process.id, ElectoralGeography.level == 'PARISH', ElectoralGeography.canton_id == campaign.canton_id, ElectoralGeography.is_mapped.is_(True), ElectoralTurnout.electoral_contest_id == contest.id, ElectoralTurnout.is_final.is_(True))).all()
            historical[process.year] = {parish_id: (Decimal(ballots) / Decimal(registered), registered) for parish_id, registered, ballots in rows if registered > 0}
        if len(processes) >= 2 and historical.get(processes[0].year) and historical.get(processes[1].year):
            old_total = sum(v[1] for v in historical[processes[1].year].values()); recent_total = sum(v[1] for v in historical[processes[0].year].values())
            if old_total and abs(Decimal(recent_total - old_total) / Decimal(old_total)) > self.BREAK_THRESHOLD: warnings.append('REGISTRATION_SERIES_BREAK')
        # The current roll is part of the registration series as well.  A large
        # change versus the most recent official turnout denominator is a data
        # quality warning, not a demographic conclusion.
        if processes and historical.get(processes[0].year):
            historical_current = sum(v[1] for v in historical[processes[0].year].values())
            snapshot_current = sum(e.registered_voters for e in entries)
            if historical_current and abs(Decimal(snapshot_current - historical_current) / Decimal(historical_current)) > self.BREAK_THRESHOLD:
                if 'REGISTRATION_SERIES_BREAK' not in warnings: warnings.append('REGISTRATION_SERIES_BREAK')
        for entry in entries:
            old = historical.get(processes[-1].year, {}).get(entry.parish_id) if processes else None
            recent = historical.get(processes[0].year, {}).get(entry.parish_id) if processes else None
            if not old or not recent:
                continue
            low, high = min(old[0], recent[0]), max(old[0], recent[0]); central = self.OLD_WEIGHT * old[0] + self.RECENT_WEIGHT * recent[0]
            def rounded(rate): return int((Decimal(entry.registered_voters) * rate).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            quality = 'HIGH' if len(processes) >= 2 and not warnings else ('MEDIUM' if len(processes) >= 2 else 'LOW')
            explanation = f'{self.OLD_WEIGHT} × {old[0]:.6%} + {self.RECENT_WEIGHT} × {recent[0]:.6%} = {central:.6%}; electores × tasa central'
            self.db.add(ParticipationProjectionResult(run_id=run.id, parish_id=entry.parish_id, registered_voters=entry.registered_voters, turnout_rate_low=low, turnout_rate_central=central, turnout_rate_high=high, expected_voters_low=min(entry.registered_voters, rounded(low)), expected_voters_central=min(entry.registered_voters, rounded(central)), expected_voters_high=min(entry.registered_voters, rounded(high)), data_quality_status=quality, explanation=explanation))
        self.db.commit(); self.db.refresh(run)
        return {'run': run, 'warnings': warnings, 'historical_processes': processes}

    def latest(self, campaign_id): return self.db.scalar(select(ParticipationProjectionRun).where(ParticipationProjectionRun.campaign_id == campaign_id).order_by(ParticipationProjectionRun.created_at.desc()))
    def results(self, run_id): return list(self.db.scalars(select(ParticipationProjectionResult).where(ParticipationProjectionResult.run_id == run_id)))
