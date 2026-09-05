from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ElectionDayOperation(Base):
    """El centro operativo del día de la elección — nunca un sistema paralelo
    de resultados. Un solo row por (campaign, electoral_process): transiciona
    PREPARATION → ACTIVE → CLOSED en el mismo registro en lugar de crear filas
    nuevas, lo que hace que "no dos jornadas ACTIVE del mismo proceso" (§6) sea
    una consecuencia directa de la unicidad, no una regla aparte que mantener.
    """
    __tablename__ = "election_day_operations"
    __table_args__ = (
        CheckConstraint("status IN ('PREPARATION','ACTIVE','CLOSED')", name="status"),
        UniqueConstraint("campaign_id", "electoral_process_id", name="uq_election_day_operations_campaign_process"),
        Index("ix_election_day_operations_campaign_id", "campaign_id"),
        Index("ix_election_day_operations_electoral_process_id", "electoral_process_id"),
        Index("ix_election_day_operations_status", "status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)
    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False)
    electoral_process_id: Mapped[UUID] = mapped_column(ForeignKey("electoral_processes.id", ondelete="RESTRICT"), nullable=False)
    election_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PREPARATION", server_default="PREPARATION")
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opened_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    closed_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class PollingPlace(Base):
    """Recinto electoral oficial. Alcance por electoral_process (compartido
    entre campañas del mismo cantón/proceso), no por campaign — así una
    campaña nunca "inventa" su propio recinto paralelo al oficial."""
    __tablename__ = "polling_places"
    __table_args__ = (
        UniqueConstraint("electoral_process_id", "official_code", name="uq_polling_places_process_code"),
        Index("ix_polling_places_electoral_process_id", "electoral_process_id"),
        Index("ix_polling_places_canton_id", "canton_id"),
        Index("ix_polling_places_parish_id", "parish_id"),
        Index("ix_polling_places_is_active", "is_active"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    electoral_process_id: Mapped[UUID] = mapped_column(ForeignKey("electoral_processes.id", ondelete="RESTRICT"), nullable=False)
    province_id: Mapped[int] = mapped_column(ForeignKey("provinces.id", ondelete="RESTRICT"), nullable=False)
    canton_id: Mapped[int] = mapped_column(ForeignKey("cantons.id", ondelete="RESTRICT"), nullable=False)
    parish_id: Mapped[int] = mapped_column(ForeignKey("parishes.id", ondelete="RESTRICT"), nullable=False)
    official_code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(220), nullable=False)
    address: Mapped[str | None] = mapped_column(String(400))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    data_source_id: Mapped[UUID | None] = mapped_column(ForeignKey("data_sources.id", ondelete="RESTRICT"))
    import_job_id: Mapped[UUID | None] = mapped_column(ForeignKey("data_import_jobs.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ElectoralBoard(Base):
    """Junta receptora del voto. registered_voters es un agregado oficial
    opcional — nunca un microdato de elector individual (§9)."""
    __tablename__ = "electoral_boards"
    __table_args__ = (
        UniqueConstraint("polling_place_id", "official_code", name="uq_electoral_boards_place_code"),
        CheckConstraint("registered_voters IS NULL OR registered_voters >= 0", name="registered_voters_nonnegative"),
        Index("ix_electoral_boards_polling_place_id", "polling_place_id"),
        Index("ix_electoral_boards_is_active", "is_active"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    polling_place_id: Mapped[UUID] = mapped_column(ForeignKey("polling_places.id", ondelete="RESTRICT"), nullable=False)
    official_code: Mapped[str] = mapped_column(String(40), nullable=False)
    board_number: Mapped[int] = mapped_column(Integer, nullable=False)
    sex_category: Mapped[str | None] = mapped_column(String(20))
    registered_voters: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    data_source_id: Mapped[UUID | None] = mapped_column(ForeignKey("data_sources.id", ondelete="RESTRICT"))
    import_job_id: Mapped[UUID | None] = mapped_column(ForeignKey("data_import_jobs.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ElectionDayAssignment(Base):
    """Vincula personal de campaña (no padrón, no UserRole global — §12/§15) a
    un recinto/junta para la jornada. El check-in vive en la misma fila (no en
    una tabla aparte): un reemplazo (§52) marca esta fila REPLACED y crea una
    fila ASSIGNED nueva, preservando el check-in original intacto en su fila.
    """
    __tablename__ = "election_day_assignments"
    __table_args__ = (
        CheckConstraint("assignment_role IN ('POLLING_PLACE_COORDINATOR','BOARD_DELEGATE','MOBILE_SUPPORT')", name="assignment_role"),
        CheckConstraint("status IN ('ASSIGNED','CONFIRMED','CHECKED_IN','ABSENT','REPLACED','COMPLETED')", name="status"),
        Index("ix_election_day_assignments_operation_id", "operation_id"),
        Index("ix_election_day_assignments_user_id", "user_id"),
        Index("ix_election_day_assignments_polling_place_id", "polling_place_id"),
        Index("ix_election_day_assignments_board_id", "board_id"),
        Index("ix_election_day_assignments_status", "status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    operation_id: Mapped[UUID] = mapped_column(ForeignKey("election_day_operations.id", ondelete="RESTRICT"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    polling_place_id: Mapped[UUID] = mapped_column(ForeignKey("polling_places.id", ondelete="RESTRICT"), nullable=False)
    board_id: Mapped[UUID | None] = mapped_column(ForeignKey("electoral_boards.id", ondelete="RESTRICT"))
    assignment_role: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ASSIGNED", server_default="ASSIGNED")
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checkin_latitude: Mapped[float | None] = mapped_column(Float)
    checkin_longitude: Mapped[float | None] = mapped_column(Float)
    checkin_client_generated_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    checkin_offline_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_assignment_id: Mapped[UUID | None] = mapped_column(ForeignKey("election_day_assignments.id", ondelete="SET NULL"))
    assigned_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ElectionDayIncident(Base):
    __tablename__ = "election_day_incidents"
    __table_args__ = (
        CheckConstraint("category IN ('PERSONNEL','ACCESS','LOGISTICS','DOCUMENTATION','CONNECTIVITY','OTHER')", name="category"),
        CheckConstraint("status IN ('OPEN','IN_REVIEW','RESOLVED')", name="status"),
        Index("ix_election_day_incidents_operation_id", "operation_id"),
        Index("ix_election_day_incidents_polling_place_id", "polling_place_id"),
        Index("ix_election_day_incidents_status", "status"),
        Index("uq_election_day_incidents_client_id", "operation_id", "reported_by_user_id", "client_generated_id", unique=True, postgresql_where=text("client_generated_id IS NOT NULL")),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    operation_id: Mapped[UUID] = mapped_column(ForeignKey("election_day_operations.id", ondelete="RESTRICT"), nullable=False)
    polling_place_id: Mapped[UUID] = mapped_column(ForeignKey("polling_places.id", ondelete="RESTRICT"), nullable=False)
    board_id: Mapped[UUID | None] = mapped_column(ForeignKey("electoral_boards.id", ondelete="RESTRICT"))
    reported_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN", server_default="OPEN")
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    client_generated_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    offline_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ElectionDayDocument(Base):
    """Copia/evidencia documental de jornada — nunca un resultado oficial
    (§36). El status 'VALIDATED' es una revisión documental interna, no una
    validación CNE (§38)."""
    __tablename__ = "election_day_documents"
    __table_args__ = (
        CheckConstraint("document_type IN ('ACTA_COPY','INCIDENT_DOCUMENT','OTHER')", name="document_type"),
        CheckConstraint("status IN ('RECEIVED','REQUIRES_REVIEW','VALIDATED')", name="status"),
        Index("ix_election_day_documents_operation_id", "operation_id"),
        Index("ix_election_day_documents_polling_place_id", "polling_place_id"),
        Index("ix_election_day_documents_board_id", "board_id"),
        Index("uq_election_day_documents_storage_key", "storage_key", unique=True, postgresql_where=text("storage_key IS NOT NULL")),
        Index("uq_election_day_documents_client_id", "operation_id", "uploaded_by_user_id", "client_generated_id", unique=True, postgresql_where=text("client_generated_id IS NOT NULL")),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    operation_id: Mapped[UUID] = mapped_column(ForeignKey("election_day_operations.id", ondelete="RESTRICT"), nullable=False)
    polling_place_id: Mapped[UUID] = mapped_column(ForeignKey("polling_places.id", ondelete="RESTRICT"), nullable=False)
    board_id: Mapped[UUID | None] = mapped_column(ForeignKey("electoral_boards.id", ondelete="RESTRICT"))
    document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))
    original_filename: Mapped[str | None] = mapped_column(String(255))
    uploaded_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="RECEIVED", server_default="RECEIVED")
    client_generated_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
