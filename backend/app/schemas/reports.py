from datetime import date
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ReportFormat(StrEnum):
    PDF = "PDF"
    XLSX = "XLSX"


KNOWN_SECTIONS = {"COVER", "EXECUTIVE_METRICS", "TERRITORIAL_COVERAGE", "ACTIVITY_SUMMARY", "TOP_NEEDS", "COMMITMENTS", "SURVEYS", "ELECTORAL_HISTORY", "DEMOGRAPHICS", "DATA_QUALITY", "SOURCES"}


class ReportDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sections: list[str] = Field(min_length=1, max_length=11)
    include_comparisons: bool = True
    include_methodology: bool = True
    include_sources: bool = True
    max_items_per_section: int = Field(50, ge=1, le=500)

    @field_validator("sections")
    @classmethod
    def sections_known(cls, value: list[str]):
        normalized = [item.strip().upper() for item in value]
        if len(set(normalized)) != len(normalized) or not set(normalized) <= KNOWN_SECTIONS:
            raise ValueError("Las secciones son inválidas o están duplicadas")
        return normalized


class ReportTemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=180)
    description: str | None = None
    report_type: str
    allowed_formats: list[ReportFormat] = Field(min_length=1, max_length=2)
    definition: ReportDefinition

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str):
        import re
        value = re.sub(r"[^A-Z0-9]+", "_", value.strip().upper()).strip("_")
        if not value:
            raise ValueError("Código inválido")
        return value

    @field_validator("name")
    @classmethod
    def nonempty(cls, value: str):
        if not value.strip():
            raise ValueError("El nombre es obligatorio")
        return value.strip()


class ReportTemplateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(None, min_length=1, max_length=180)
    description: str | None = None
    allowed_formats: list[ReportFormat] | None = Field(None, min_length=1, max_length=2)
    definition: ReportDefinition | None = None
    is_active: bool | None = None


class ReportTemplateRead(BaseModel):
    id: UUID
    code: str
    name: str
    description: str | None
    report_type: str
    allowed_formats: list[str]
    definition: dict[str, Any]
    is_system: bool
    is_active: bool


class ReportGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template_code: str
    format: ReportFormat
    title: str = Field(min_length=1, max_length=220)
    report_date: date
    date_from: date | None = None
    date_to: date | None = None
    period: str | None = None
    parish_id: int | None = None
    community_id: UUID | None = None
    sector_id: UUID | None = None
    survey_ids: list[UUID] = Field(default_factory=list, max_length=20)
    electoral_process_ids: list[UUID] = Field(default_factory=list, max_length=10)
    demographic_indicator_codes: list[str] = Field(default_factory=list, max_length=50)
    include_comparisons: bool = True

    @model_validator(mode="after")
    def validate_request(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from no puede ser posterior a date_to")
        if self.community_id and not self.parish_id:
            raise ValueError("community_id requiere parish_id")
        if self.sector_id and not self.community_id:
            raise ValueError("sector_id requiere community_id")
        return self


class ReportArtifactRead(BaseModel):
    id: UUID
    format: str
    original_download_name: str
    mime_type: str
    size_bytes: int
    expires_on: date
    is_available: bool
    sha256: str | None = None


class ReportRunRead(BaseModel):
    id: UUID
    campaign_id: UUID
    template_code: str
    requested_format: str
    status: str
    report_date: date
    date_from: date | None
    date_to: date | None
    title: str
    error_code: str | None = None
    error_message: str | None = None
    artifact: ReportArtifactRead | None = None


class ReportGenerationResponse(ReportRunRead):
    pass


class ReportListResponse(BaseModel):
    items: list[ReportRunRead]
    page: int
    page_size: int
    total: int
