from datetime import date
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AlertRuleRead(BaseModel):
    id: UUID
    code: str
    name: str
    description: str | None
    module: str
    condition_type: str
    default_severity: str
    configuration: dict[str, Any]
    is_system: bool
    is_active: bool


class AlertEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_codes: list[str] = Field(default_factory=list, max_length=20)
    as_of_date: date
    parish_id: int | None = None
    community_id: UUID | None = None
    sector_id: UUID | None = None

    @model_validator(mode="after")
    def hierarchy(self):
        if self.community_id and not self.parish_id:
            raise ValueError("community_id requiere parish_id")
        if self.sector_id and not self.community_id:
            raise ValueError("sector_id requiere community_id")
        return self


class AlertEvaluationResponse(BaseModel):
    evaluated_rules: int
    created: int
    updated: int
    resolved: int
    unchanged: int


class AlertActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_date: date
    note: str | None = Field(None, max_length=1000)

    @field_validator("note")
    @classmethod
    def safe_note(cls, value):
        if value is None:
            return value
        value = value.strip()
        if "<script" in value.lower():
            raise ValueError("La nota debe ser texto plano")
        return value or None


class AlertAcknowledgementRead(BaseModel):
    id: UUID
    action: str
    action_date: date
    note: str | None
    performed_by_user_id: UUID


class OperationalAlertRead(BaseModel):
    id: UUID
    rule_code: str
    module: str
    severity: str
    status: str
    title: str
    message: str
    detected_date: date
    last_seen_date: date
    resolved_date: date | None
    parish_id: int | None
    community_id: UUID | None
    sector_id: UUID | None
    resource_type: str | None
    resource_id: UUID | None
    evidence: dict[str, Any]
    acknowledgements: list[AlertAcknowledgementRead] = []


class OperationalAlertSummary(BaseModel):
    open: int
    acknowledged: int
    resolved: int
    dismissed: int


class AlertListResponse(BaseModel):
    items: list[OperationalAlertRead]
    page: int
    page_size: int
    total: int
    total: int


class AlertSummaryRead(BaseModel):
    statuses: dict[str, int]
    by_severity: list[dict[str, Any]]
    by_module: list[dict[str, Any]]
    by_territory: list[dict[str, Any]]
    new_in_period: int
    overdue: int
    top_alerts: list[OperationalAlertRead]
