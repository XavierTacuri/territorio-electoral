from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


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
    scrutiny_started_at: datetime | None
    scrutiny_started_by_user_id: UUID | None
    notes: str | None


class ElectionDayCloseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: str | None = None


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
    assignment_role: str
    polling_place_id: UUID | None = None


class ElectionDayAssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    operation_id: UUID
    user_id: UUID
    polling_place_id: UUID | None
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


class ElectionDayPreflightSummary(BaseModel):
    polling_places: int
    boards: int
    delegates: int
    validators: int
    uncovered_polling_places: int


class ElectionDayPreflightResponse(BaseModel):
    ready: bool
    blockers: list[str]
    warnings: list[str]
    summary: ElectionDayPreflightSummary


class ElectionDayControlCenterResponse(BaseModel):
    operation: ElectionDayOperationRead
    coverage: CoverageSummary


class ElectionDayValidationStatus(BaseModel):
    operation_status: str
    pending_reviews: int


class ElectionDayAdminSupportStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(None, max_length=500)


class ElectionDayAdminSupportSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    admin_user_id: UUID
    organization_id: UUID
    campaign_id: UUID
    operation_id: UUID
    reason: str | None
    started_at: datetime
    ended_at: datetime | None


# ---------- Personal de Jornada: invitaciones de Delegados/Validadores (Fase 1B) ----------
from app.core.security import validate_password  # noqa: E402
from app.schemas.user import clean_name  # noqa: E402

STAFF_TYPES = {"POLLING_PLACE_DELEGATE", "ACT_VALIDATOR"}


class ElectionDayStaffInvitationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    first_name: str
    last_name: str
    email: EmailStr
    staff_type: str
    polling_place_ids: list[UUID] = Field(default_factory=list)

    @field_validator("first_name", "last_name")
    @classmethod
    def names_valid(cls, value: str) -> str:
        return clean_name(value)

    @field_validator("email", mode="before")
    @classmethod
    def email_lower(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("staff_type")
    @classmethod
    def staff_type_valid(cls, value: str) -> str:
        if value not in STAFF_TYPES:
            raise ValueError("Perfil de personal de jornada inválido")
        return value

    @model_validator(mode="after")
    def polling_places_match_role(self) -> "ElectionDayStaffInvitationCreate":
        if self.staff_type == "POLLING_PLACE_DELEGATE" and not self.polling_place_ids:
            raise ValueError("El delegado de recinto requiere al menos un recinto")
        if self.staff_type == "ACT_VALIDATOR" and self.polling_place_ids:
            raise ValueError("El validador de actas no se asigna a recintos")
        if len(self.polling_place_ids) != len(set(self.polling_place_ids)):
            raise ValueError("No se permiten recintos repetidos")
        return self


class ElectionDayStaffInvitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    campaign_id: UUID
    operation_id: UUID
    email: str
    first_name: str
    last_name: str
    staff_type: str
    status: str
    invited_by_user_id: UUID
    accepted_user_id: UUID | None
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    polling_place_ids: list[UUID]


class ElectionDayStaffInvitationListResponse(BaseModel):
    items: list[ElectionDayStaffInvitationRead]
    total: int


class ElectionDayStaffInvitationCreatedResponse(BaseModel):
    invitation: ElectionDayStaffInvitationRead
    invite_token: str
    invite_url: str


class ElectionDayInvitationPollingPlaceSummary(BaseModel):
    id: UUID
    name: str


class ElectionDayInvitationPreview(BaseModel):
    campaign_name: str
    election_date: date
    staff_type: str
    email: str
    first_name: str
    last_name: str
    polling_places: list[ElectionDayInvitationPollingPlaceSummary]
    expires_at: datetime
    requires_login: bool
    status: str


class ElectionDayInvitationTokenRequest(BaseModel):
    """El token viaja únicamente en el body de una petición POST — nunca en
    la URL (ni path ni query param), para que jamás quede en logs de acceso,
    historial del navegador, Referer headers ni caches intermedios."""
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=16)


class ElectionDayInvitationAcceptNewAccount(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=16)
    first_name: str
    last_name: str
    password: str
    password_confirmation: str

    @field_validator("first_name", "last_name")
    @classmethod
    def names_valid(cls, value: str) -> str:
        return clean_name(value)

    @field_validator("password")
    @classmethod
    def password_valid(cls, value: str) -> str:
        validate_password(value)
        return value

    @model_validator(mode="after")
    def passwords_match(self) -> "ElectionDayInvitationAcceptNewAccount":
        if self.password != self.password_confirmation:
            raise ValueError("Las contraseñas no coinciden")
        return self


class ElectionDayInvitationAcceptResponse(BaseModel):
    campaign_id: UUID
    operation_id: UUID
    message: str


class ElectionDayMyContextResponse(BaseModel):
    campaign_id: UUID
    campaign_name: str
    organization_id: UUID
    operation_id: UUID
    election_date: date
    operation_status: str
    staff_types: list[str]
    polling_places: list[ElectionDayInvitationPollingPlaceSummary]


class ElectionDayMyContextSummary(BaseModel):
    campaign_id: UUID
    campaign_name: str
    operation_id: UUID
    election_date: date
    operation_status: str
    staff_types: list[str]
