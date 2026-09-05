from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ElectionDayOperationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    electoral_process_id: UUID
    election_date: date
    notes: str | None = None


class ElectionDayOperationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    campaign_id: UUID
    electoral_process_id: UUID
    election_date: date
    status: str
    opened_at: datetime | None
    closed_at: datetime | None
    opened_by_user_id: UUID | None
    closed_by_user_id: UUID | None
    notes: str | None


class ElectionDayCloseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: str | None = None


class PollingPlaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    official_code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=220)
    parish_id: int
    address: str | None = None
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)


class PollingPlaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    electoral_process_id: UUID
    province_id: int
    canton_id: int
    parish_id: int
    official_code: str
    name: str
    address: str | None
    latitude: float | None
    longitude: float | None
    is_active: bool


class ElectoralBoardCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    official_code: str = Field(min_length=1, max_length=40)
    board_number: int = Field(ge=1)
    sex_category: str | None = None
    registered_voters: int | None = Field(None, ge=0)


class ElectoralBoardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    polling_place_id: UUID
    official_code: str
    board_number: int
    sex_category: str | None
    registered_voters: int | None
    is_active: bool


class ElectionDayAssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    polling_place_id: UUID
    board_id: UUID | None = None
    assignment_role: str


class ElectionDayAssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    operation_id: UUID
    user_id: UUID
    polling_place_id: UUID
    board_id: UUID | None
    assignment_role: str
    status: str
    checked_in_at: datetime | None
    checkin_latitude: float | None
    checkin_longitude: float | None
    replaced_by_assignment_id: UUID | None


class ElectionDayAssignmentReplace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    reason: str | None = None


class ElectionDayEligibleUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    username: str
    first_name: str
    last_name: str


class CheckInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    client_generated_id: UUID | None = None
    offline_created_at: datetime | None = None


class ElectionDayIncidentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    polling_place_id: UUID
    board_id: UUID | None = None
    category: str
    description: str = Field(min_length=1, max_length=4000)
    client_generated_id: UUID | None = None
    offline_created_at: datetime | None = None


class ElectionDayIncidentResolve(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    resolution_notes: str | None = None


class ElectionDayIncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    operation_id: UUID
    polling_place_id: UUID
    board_id: UUID | None
    reported_by_user_id: UUID
    category: str
    description: str
    status: str
    reported_at: datetime
    resolved_at: datetime | None
    resolution_notes: str | None


class ElectionDayDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    operation_id: UUID
    polling_place_id: UUID
    board_id: UUID | None
    document_type: str
    mime_type: str | None
    size_bytes: int | None
    original_filename: str | None
    uploaded_by_user_id: UUID
    status: str


class ElectionDayDocumentStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str


class CoverageSummary(BaseModel):
    total_polling_places: int
    covered_polling_places: int
    total_boards: int
    covered_boards: int
    personnel_confirmed: int
    personnel_checked_in: int
    open_incidents: int
    documents_received: int
    expected_documents: int


class PollingPlaceListResponse(BaseModel):
    items: list[PollingPlaceRead]
    total: int


class ElectionDayAssignmentListResponse(BaseModel):
    items: list[ElectionDayAssignmentRead]
    total: int


class ElectionDayIncidentListResponse(BaseModel):
    items: list[ElectionDayIncidentRead]
    total: int


class ElectionDayDocumentListResponse(BaseModel):
    items: list[ElectionDayDocumentRead]
    total: int
