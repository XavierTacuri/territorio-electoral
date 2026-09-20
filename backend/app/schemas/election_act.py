from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ElectionActResultInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    electoral_candidate_id: UUID
    votes: int = Field(ge=0)


def _unique_candidates(value: list[ElectionActResultInput]) -> list[ElectionActResultInput]:
    ids = [r.electoral_candidate_id for r in value]
    if len(ids) != len(set(ids)):
        raise ValueError("No se permiten candidatos repetidos")
    return value


class ElectionActDraftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    polling_place_id: UUID
    electoral_board_id: UUID
    electoral_contest_id: UUID
    blank_ballots: int = Field(ge=0)
    null_ballots: int = Field(ge=0)
    valid_ballots: int | None = Field(None, ge=0)
    ballots_counted: int | None = Field(None, ge=0)
    results: list[ElectionActResultInput] = Field(default_factory=list)
    client_generated_id: UUID | None = None
    offline_created_at: datetime | None = None

    @field_validator("results")
    @classmethod
    def results_valid(cls, value: list[ElectionActResultInput]) -> list[ElectionActResultInput]:
        return _unique_candidates(value)


class ElectionActCorrectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blank_ballots: int = Field(ge=0)
    null_ballots: int = Field(ge=0)
    valid_ballots: int | None = Field(None, ge=0)
    ballots_counted: int | None = Field(None, ge=0)
    results: list[ElectionActResultInput] = Field(default_factory=list)
    correction_reason: str = Field(min_length=1, max_length=2000)
    client_generated_id: UUID | None = None
    offline_created_at: datetime | None = None

    @field_validator("results")
    @classmethod
    def results_valid(cls, value: list[ElectionActResultInput]) -> list[ElectionActResultInput]:
        return _unique_candidates(value)


class ElectionActObserveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision_id: UUID
    reason: str = Field(min_length=1, max_length=2000)


class ElectionActValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision_id: UUID


class ElectionActResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    electoral_candidate_id: UUID
    votes: int


class ElectionActEvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    revision_id: UUID
    mime_type: str
    size_bytes: int
    original_filename: str | None
    uploaded_by_user_id: UUID
    created_at: datetime


class ElectionActRevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    act_id: UUID
    revision_number: int
    revision_type: str
    status: str
    submitted_by_user_id: UUID
    blank_ballots: int
    null_ballots: int
    valid_ballots: int | None
    ballots_counted: int | None
    correction_reason: str | None
    notes: str | None
    created_at: datetime
    submitted_at: datetime | None
    results: list[ElectionActResultRead]
    evidence: list[ElectionActEvidenceRead]


class ElectionActReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    act_id: UUID
    revision_id: UUID
    reviewer_user_id: UUID
    review_source: str
    action: str
    reason: str | None
    created_at: datetime


class ElectionActRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    campaign_id: UUID
    operation_id: UUID
    polling_place_id: UUID
    electoral_board_id: UUID
    electoral_contest_id: UUID
    status: str
    latest_revision_number: int
    validated_revision_id: UUID | None
    review_claimed_by_user_id: UUID | None
    review_claimed_at: datetime | None
    review_claim_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ElectionActListResponse(BaseModel):
    items: list[ElectionActRead]
    total: int


class ElectionActDetail(BaseModel):
    act: ElectionActRead
    polling_place_name: str
    electoral_board_code: str
    electoral_contest_name: str
    revisions: list[ElectionActRevisionRead]
    reviews: list[ElectionActReviewRead]


class ElectionActDraftResponse(BaseModel):
    act: ElectionActRead
    revision: ElectionActRevisionRead


class ElectionActCandidateOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    full_name: str
    display_name: str | None
    list_number: str | None
    ballot_order: int | None


class ElectionActContestOption(BaseModel):
    id: UUID
    name: str
    office_type: str
    vote_method: str
    candidates: list[ElectionActCandidateOption]


class ElectionActCoverageSummary(BaseModel):
    expected_boards: int
    received: int
    validated: int
    in_review: int
    observed: int
    pending: int
    received_coverage_pct: float
    validated_coverage_pct: float


# ---------- Centro de Control Electoral (Fase 3) — consolidado factual ----------
# Todo lo de aquí abajo se deriva EXCLUSIVAMENTE de ElectionAct.status ==
# 'VALIDATED' vía ElectionAct.validated_revision_id — nunca de RECEIVED/
# IN_REVIEW/OBSERVED ni de una revisión que ya no es la validada. Nunca
# incluye predicción, proyección, probabilidad ni ganador: es un conteo
# interno NO OFICIAL de lo efectivamente validado hasta el momento.


class ControlCenterCandidateResult(BaseModel):
    candidate_id: UUID
    display_name: str
    list_number: str | None
    ballot_order: int | None
    votes: int
    pct_valid_votes: float


class ControlCenterContestSummary(BaseModel):
    contest_id: UUID
    contest_name: str
    office_type: str
    vote_method: str
    validated_acts: int
    expected_acts: int
    valid_votes: int
    blank_votes: int
    null_votes: int
    ballots_counted: int
    candidates: list[ControlCenterCandidateResult]


class ControlCenterPollingPlaceSummary(BaseModel):
    polling_place_id: UUID
    polling_place_name: str
    parish_id: int
    expected_boards: int
    received: int
    validated: int
    in_review: int
    observed: int
    pending: int
    coverage_validated_pct: float


class ControlCenterParishSummary(BaseModel):
    parish_id: int
    parish_name: str
    expected_boards: int
    validated: int
    coverage_validated_pct: float
    valid_votes: int
    blank_votes: int
    null_votes: int


class ControlCenterSummary(BaseModel):
    acts_coverage: ElectionActCoverageSummary
    contests: list[ControlCenterContestSummary]
    polling_places: list[ControlCenterPollingPlaceSummary]
    parishes: list[ControlCenterParishSummary]
