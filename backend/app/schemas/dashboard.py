from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DashboardPeriod(StrEnum):
    THIS_WEEK = "THIS_WEEK"
    LAST_7_DAYS = "LAST_7_DAYS"
    LAST_30_DAYS = "LAST_30_DAYS"
    CAMPAIGN_TO_DATE = "CAMPAIGN_TO_DATE"
    CUSTOM = "CUSTOM"


class DashboardDataStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    SUPPRESSED = "SUPPRESSED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class DashboardFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date_from: date | None = None
    date_to: date | None = None
    period: DashboardPeriod | None = None
    parish_id: int | None = None
    community_id: UUID | None = None
    sector_id: UUID | None = None
    compare_previous_period: bool = False
    survey_ids: list[UUID] | None = Field(None, max_length=20)
    electoral_process_ids: list[UUID] | None = Field(None, max_length=10)
    demographic_indicator_codes: list[str] | None = Field(None, max_length=50)

    @model_validator(mode="after")
    def validate_hierarchy(self):
        if self.community_id is not None and self.parish_id is None:
            raise ValueError("community_id requiere parish_id")
        if self.sector_id is not None and self.community_id is None:
            raise ValueError("sector_id requiere community_id")
        if self.period == DashboardPeriod.CUSTOM and (not self.date_from or not self.date_to):
            raise ValueError("CUSTOM requiere date_from y date_to")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from no puede ser posterior a date_to")
        return self


class DashboardPeriodRead(BaseModel):
    date_from: date
    date_to: date
    previous_date_from: date | None = None
    previous_date_to: date | None = None


class DashboardScopeRead(BaseModel):
    type: str
    parish_ids: list[int] = []
    community_ids: list[UUID] = []
    sector_ids: list[UUID] = []


class DashboardMetricRead(BaseModel):
    code: str
    label: str
    value: Decimal | int | None
    unit: str
    denominator: Decimal | int | None = None
    previous_value: Decimal | int | None = None
    absolute_change: Decimal | int | None = None
    percentage_change: Decimal | None = None
    is_comparable: bool = False
    data_status: DashboardDataStatus = DashboardDataStatus.AVAILABLE
    note: str | None = None


class DashboardMetricComparisonRead(DashboardMetricRead):
    pass


class DashboardDataSourceRead(BaseModel):
    code: str
    institution: str
    dataset_name: str
    is_official: bool


class DashboardDataAvailabilityRead(BaseModel):
    module: str
    status: DashboardDataStatus
    count: int = 0


class DashboardFilterOptionsRead(BaseModel):
    periods: list[str]
    parishes: list[dict[str, Any]]
    communities: list[dict[str, Any]]
    sectors: list[dict[str, Any]]
    surveys: list[dict[str, Any]]
    electoral_processes: list[dict[str, Any]]
    demographic_indicators: list[dict[str, Any]]
    min_date: date | None
    max_date: date | None
    scope: DashboardScopeRead


class CampaignDashboardOverviewRead(BaseModel):
    campaign: dict[str, Any]
    scope: DashboardScopeRead
    period: DashboardPeriodRead
    as_of_date: date
    metrics: list[DashboardMetricRead]
    territorial_coverage: dict[str, Any]
    top_needs: list[dict[str, Any]]
    commitment_summary: dict[str, Any]
    survey_summary: dict[str, Any]
    data_quality: dict[str, Any]
    summary_text: str


class CampaignDashboardRead(BaseModel):
    overview: CampaignDashboardOverviewRead
    top_needs: list[dict[str, Any]]
    commitments: dict[str, Any]
    surveys: dict[str, Any]
    coverage: dict[str, Any]
    quality: dict[str, Any]


class TerritorialDashboardItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int | UUID
    name: str
    territory_type: str


class TerritorialDashboardRead(BaseModel):
    items: list[TerritorialDashboardItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class ActivityTrendPoint(BaseModel):
    period_start: date
    completed: int
    planned: int
    cancelled: int
    estimated_attendees: int
    distinct_activity_types: int


class ActivityTrendRead(BaseModel):
    period: DashboardPeriodRead
    group_by: str
    points: list[ActivityTrendPoint]


class NeedCategoryDashboardItem(BaseModel):
    code: str
    name: str
    needs: int
    mentions: int
    activities: int
    territories: int


class NeedDashboardRead(BaseModel):
    model_config = ConfigDict(extra="allow")
    total_needs: int
    total_mentions: int
    categories: list[NeedCategoryDashboardItem]


class CommitmentDashboardRead(BaseModel):
    model_config = ConfigDict(extra="allow")
    total: int
    completion_rate: Decimal | None


class SurveyDashboardItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    survey_id: UUID
    title: str


class SurveyDashboardRead(BaseModel):
    model_config = ConfigDict(extra="allow")
    surveys: list[SurveyDashboardItem]


class ElectoralHistoryDashboardRead(BaseModel):
    model_config = ConfigDict(extra="allow")
    data_available: bool
    processes: list[dict[str, Any]]


class DemographicDashboardItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    indicator_code: str
    name: str


class DemographicDashboardRead(BaseModel):
    model_config = ConfigDict(extra="allow")
    items: list[DemographicDashboardItem]


class DataQualityIssueRead(BaseModel):
    code: str
    description: str
    count: int
    scope: str
    source: str
    status: str
    technical_action: str | None = None


class DataQualityDashboardRead(BaseModel):
    status: str
    issues: list[DataQualityIssueRead]
