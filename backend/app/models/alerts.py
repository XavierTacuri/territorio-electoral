from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, JSON, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

JSON_VALUE = JSON().with_variant(JSONB, "postgresql")


class AlertRule(Base):
    __tablename__ = "alert_rules"
    __table_args__ = (
        CheckConstraint("module IN ('OPERATIONS','COMMITMENTS','SURVEYS','DATA_IMPORTS','ELECTORAL_DATA','DEMOGRAPHICS','GEOMETRY','DATA_QUALITY')", name="module"),
        CheckConstraint("default_severity IN ('INFO','WARNING','CRITICAL')", name="severity"),
        Index("ix_alert_rules_code", "code", unique=True),
        Index("ix_alert_rules_module", "module"),
        Index("ix_alert_rules_condition_type", "condition_type"),
        Index("ix_alert_rules_is_active", "is_active"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    module: Mapped[str] = mapped_column(String(30), nullable=False)
    condition_type: Mapped[str] = mapped_column(String(80), nullable=False)
    default_severity: Mapped[str] = mapped_column(String(20), nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class OperationalAlert(Base):
    __tablename__ = "operational_alerts"
    __table_args__ = (
        CheckConstraint("severity IN ('INFO','WARNING','CRITICAL')", name="severity"),
        CheckConstraint("status IN ('OPEN','ACKNOWLEDGED','RESOLVED','DISMISSED')", name="status"),
        Index("ix_operational_alerts_campaign_id", "campaign_id"),
        Index("ix_operational_alerts_alert_rule_id", "alert_rule_id"),
        Index("ix_operational_alerts_status", "status"),
        Index("ix_operational_alerts_severity", "severity"),
        Index("ix_operational_alerts_detected_date", "detected_date"),
        Index("ix_operational_alerts_parish_id", "parish_id"),
        Index("ix_operational_alerts_resource", "resource_type", "resource_id"),
        Index("ix_operational_alerts_campaign_status", "campaign_id", "status"),
        Index("ix_operational_alerts_campaign_severity", "campaign_id", "severity"),
        Index("uq_operational_alerts_campaign_fingerprint", "campaign_id", "fingerprint", unique=True),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    alert_rule_id: Mapped[UUID] = mapped_column(ForeignKey("alert_rules.id", ondelete="RESTRICT"), nullable=False)
    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    detected_date: Mapped[date] = mapped_column(Date, nullable=False)
    last_seen_date: Mapped[date] = mapped_column(Date, nullable=False)
    resolved_date: Mapped[date | None] = mapped_column(Date)
    parish_id: Mapped[int | None] = mapped_column(ForeignKey("parishes.id", ondelete="RESTRICT"))
    community_id: Mapped[UUID | None] = mapped_column(ForeignKey("communities.id", ondelete="RESTRICT"))
    sector_id: Mapped[UUID | None] = mapped_column(ForeignKey("sectors.id", ondelete="RESTRICT"))
    resource_type: Mapped[str | None] = mapped_column(String(50))
    resource_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AlertAcknowledgement(Base):
    __tablename__ = "alert_acknowledgements"
    __table_args__ = (
        CheckConstraint("action IN ('ACKNOWLEDGE','RESOLVE','DISMISS','REOPEN')", name="action"),
        Index("ix_alert_acknowledgements_alert_id", "alert_id"),
        Index("ix_alert_acknowledgements_performed_by_user_id", "performed_by_user_id"),
        Index("ix_alert_acknowledgements_action", "action"),
        Index("ix_alert_acknowledgements_action_date", "action_date"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    alert_id: Mapped[UUID] = mapped_column(ForeignKey("operational_alerts.id", ondelete="RESTRICT"), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    action_date: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    performed_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
