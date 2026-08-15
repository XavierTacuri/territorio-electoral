from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

JSON_VALUE = JSON().with_variant(JSONB, "postgresql")


class PublicSource(Base):
    __tablename__ = "public_sources"
    __table_args__ = (UniqueConstraint("campaign_id", "code", name="uq_public_sources_campaign_code"), Index("ix_public_sources_campaign_active", "campaign_id", "active"))
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    publisher: Mapped[str] = mapped_column(String(180), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    base_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    feed_url: Mapped[str | None] = mapped_column(String(1000))
    api_url: Mapped[str | None] = mapped_column(String(1000))
    jurisdiction: Mapped[str | None] = mapped_column(String(180))
    country: Mapped[str] = mapped_column(String(80), default="EC", server_default="EC", nullable=False)
    province: Mapped[str | None] = mapped_column(String(120))
    canton: Mapped[str | None] = mapped_column(String(120))
    official: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    retrieval_method: Mapped[str] = mapped_column(String(30), nullable=False)
    refresh_interval_minutes: Mapped[int | None] = mapped_column(Integer)
    terms_notes: Mapped[str | None] = mapped_column(Text)
    license_notes: Mapped[str | None] = mapped_column(Text)
    credential_reference: Mapped[str | None] = mapped_column(String(180))
    adapter_config: Mapped[dict] = mapped_column(JSON_VALUE, default=dict, server_default="{}", nullable=False)
    etag: Mapped[str | None] = mapped_column(String(255))
    last_modified: Mapped[str | None] = mapped_column(String(255))
    last_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    items_last_fetch: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class PublicIntelligenceItem(Base):
    __tablename__ = "public_intelligence_items"
    __table_args__ = (Index("ix_public_items_source", "source_id"), Index("ix_public_items_published", "published_at"), Index("ix_public_items_status", "status"), Index("ix_public_items_hash", "content_hash"), UniqueConstraint("source_id", "canonical_url", name="uq_public_items_source_canonical"))
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("public_sources.id", ondelete="RESTRICT"), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    item_type: Mapped[str] = mapped_column(String(40), nullable=False)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    author: Mapped[str | None] = mapped_column(String(255))
    content_excerpt: Mapped[str | None] = mapped_column(Text)
    normalized_text: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(12), default="es", server_default="es", nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", server_default="ACTIVE", nullable=False)
    original_metadata: Mapped[dict] = mapped_column(JSON_VALUE, default=dict, server_default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class PublicItemRevision(Base):
    __tablename__ = "public_item_revisions"
    __table_args__ = (Index("ix_public_item_revisions_item", "item_id"), UniqueConstraint("item_id", "content_hash", name="uq_public_item_revision_hash"))
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    item_id: Mapped[UUID] = mapped_column(ForeignKey("public_intelligence_items.id", ondelete="CASCADE"), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    change_detected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    metadata_snapshot: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False)


class PublicSourceFetchRun(Base):
    __tablename__ = "public_source_fetch_runs"
    __table_args__ = (Index("ix_public_fetch_runs_source_started", "source_id", "started_at"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("public_sources.id", ondelete="RESTRICT"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    items_discovered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_unchanged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_summary: Mapped[str | None] = mapped_column(Text)
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)


class PublicTopic(Base):
    __tablename__ = "public_topics"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    keywords: Mapped[list] = mapped_column(JSON_VALUE, default=list, server_default="[]", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)


class PublicItemTopic(Base):
    __tablename__ = "public_item_topics"
    __table_args__ = (UniqueConstraint("item_id", "topic_id", name="uq_public_item_topics_item_topic"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    item_id: Mapped[UUID] = mapped_column(ForeignKey("public_intelligence_items.id", ondelete="CASCADE"), nullable=False)
    topic_id: Mapped[int] = mapped_column(ForeignKey("public_topics.id", ondelete="RESTRICT"), nullable=False)
    association_method: Mapped[str] = mapped_column(String(30), nullable=False)


class PublicItemTerritory(Base):
    __tablename__ = "public_item_territories"
    __table_args__ = (UniqueConstraint("item_id", "parish_id", name="uq_public_item_territories_item_parish"), Index("ix_public_item_territories_parish", "parish_id"))
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    item_id: Mapped[UUID] = mapped_column(ForeignKey("public_intelligence_items.id", ondelete="CASCADE"), nullable=False)
    territory_level: Mapped[str] = mapped_column(String(20), nullable=False)
    parish_id: Mapped[int | None] = mapped_column(ForeignKey("parishes.id", ondelete="RESTRICT"))
    association_method: Mapped[str] = mapped_column(String(30), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)


class PublicItemNeedLink(Base):
    __tablename__ = "public_item_need_links"
    __table_args__ = (UniqueConstraint("item_id", "need_id", name="uq_public_item_need_links_item_need"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    item_id: Mapped[UUID] = mapped_column(ForeignKey("public_intelligence_items.id", ondelete="CASCADE"), nullable=False)
    need_id: Mapped[UUID] = mapped_column(ForeignKey("citizen_needs.id", ondelete="RESTRICT"), nullable=False)
    linked_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
