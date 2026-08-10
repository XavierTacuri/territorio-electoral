from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

JSON_VALUE = JSON().with_variant(JSONB, "postgresql")


class ReportTemplate(Base):
    __tablename__ = "report_templates"
    __table_args__ = (
        CheckConstraint("report_type IN ('CAMPAIGN_EXECUTIVE_SUMMARY','OPERATIONAL_ACTIVITY','TERRITORIAL_COVERAGE','NEEDS','COMMITMENTS','SURVEY_RESULTS','ELECTORAL_HISTORY','DEMOGRAPHIC_PROFILE','DATA_QUALITY','GEOGRAPHIC_AVAILABILITY')", name="report_type"),
        Index("ix_report_templates_code", "code", unique=True),
        Index("ix_report_templates_report_type", "report_type"),
        Index("ix_report_templates_is_active", "is_active"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    report_type: Mapped[str] = mapped_column(String(50), nullable=False)
    allowed_formats: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ReportRun(Base):
    __tablename__ = "report_runs"
    __table_args__ = (
        CheckConstraint("requested_format IN ('PDF','XLSX')", name="requested_format"),
        CheckConstraint("status IN ('PENDING','GENERATING','COMPLETED','FAILED','CANCELLED')", name="status"),
        CheckConstraint("date_from IS NULL OR date_to IS NULL OR date_from <= date_to", name="date_range"),
        Index("ix_report_runs_campaign_id", "campaign_id"),
        Index("ix_report_runs_report_template_id", "report_template_id"),
        Index("ix_report_runs_status", "status"),
        Index("ix_report_runs_report_date", "report_date"),
        Index("ix_report_runs_requested_by_user_id", "requested_by_user_id"),
        Index("ix_report_runs_campaign_report_date", "campaign_id", "report_date"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False)
    report_template_id: Mapped[UUID] = mapped_column(ForeignKey("report_templates.id", ondelete="RESTRICT"), nullable=False)
    requested_format: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    date_from: Mapped[date | None] = mapped_column(Date)
    date_to: Mapped[date | None] = mapped_column(Date)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    resolved_scope: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    requested_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ReportArtifact(Base):
    __tablename__ = "report_artifacts"
    __table_args__ = (
        CheckConstraint("format IN ('PDF','XLSX')", name="format"),
        CheckConstraint("size_bytes >= 0", name="size_nonnegative"),
        Index("ix_report_artifacts_report_run_id", "report_run_id", unique=True),
        Index("ix_report_artifacts_storage_key", "storage_key", unique=True),
        Index("ix_report_artifacts_expires_on", "expires_on"),
        Index("ix_report_artifacts_is_available", "is_available"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    report_run_id: Mapped[UUID] = mapped_column(ForeignKey("report_runs.id", ondelete="RESTRICT"), nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    original_download_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_on: Mapped[date] = mapped_column(Date, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
