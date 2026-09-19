from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ElectionDayOperation(Base):
    """El centro operativo del día de la elección — nunca un sistema paralelo
    de resultados. Un solo row por (campaign, electoral_process): transiciona
    PREPARATION → ACTIVE → SCRUTINY → CLOSED en el mismo registro en lugar de
    crear filas nuevas, lo que hace que "no dos jornadas ACTIVE del mismo
    proceso" (§6) sea una consecuencia directa de la unicidad, no una regla
    aparte que mantener.
    """
    __tablename__ = "election_day_operations"
    __table_args__ = (
        CheckConstraint("status IN ('PREPARATION','ACTIVE','SCRUTINY','CLOSED')", name="status"),
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
    scrutiny_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scrutiny_started_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
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
    la jornada como personal operativo. POLLING_PLACE_DELEGATE trabaja sobre
    todo un recinto (nunca sobre una junta puntual); ACT_VALIDATOR no
    pertenece a ningún recinto (polling_place_id NULL) y opera sobre la cola
    general de actas en una fase posterior. El check-in vive en la misma fila
    (no en una tabla aparte): un reemplazo (§52) marca esta fila REPLACED y
    crea una fila ASSIGNED nueva, preservando el check-in original intacto en
    su fila.
    """
    __tablename__ = "election_day_assignments"
    __table_args__ = (
        CheckConstraint("assignment_role IN ('POLLING_PLACE_DELEGATE','ACT_VALIDATOR')", name="assignment_role"),
        CheckConstraint("status IN ('ASSIGNED','CONFIRMED','CHECKED_IN','ABSENT','REPLACED','COMPLETED')", name="status"),
        CheckConstraint(
            "(assignment_role = 'POLLING_PLACE_DELEGATE' AND polling_place_id IS NOT NULL) "
            "OR (assignment_role = 'ACT_VALIDATOR' AND polling_place_id IS NULL)",
            name="polling_place_matches_role",
        ),
        Index("ix_election_day_assignments_operation_id", "operation_id"),
        Index("ix_election_day_assignments_user_id", "user_id"),
        Index("ix_election_day_assignments_polling_place_id", "polling_place_id"),
        Index("ix_election_day_assignments_status", "status"),
        # Un mismo delegado puede cubrir varios recintos, pero no dos veces el
        # mismo recinto activo (§13). "Activa" excluye REPLACED: la fila
        # reemplazada queda como historial, nunca como duplicado vigente.
        Index(
            "uq_election_day_assignments_active_delegate_place",
            "operation_id", "user_id", "polling_place_id",
            unique=True,
            postgresql_where=text("assignment_role = 'POLLING_PLACE_DELEGATE' AND status != 'REPLACED'"),
            sqlite_where=text("assignment_role = 'POLLING_PLACE_DELEGATE' AND status != 'REPLACED'"),
        ),
        # A lo sumo una asignación ACT_VALIDATOR activa por usuario/jornada (§13).
        Index(
            "uq_election_day_assignments_active_validator",
            "operation_id", "user_id",
            unique=True,
            postgresql_where=text("assignment_role = 'ACT_VALIDATOR' AND status != 'REPLACED'"),
            sqlite_where=text("assignment_role = 'ACT_VALIDATOR' AND status != 'REPLACED'"),
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    operation_id: Mapped[UUID] = mapped_column(ForeignKey("election_day_operations.id", ondelete="RESTRICT"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    polling_place_id: Mapped[UUID | None] = mapped_column(ForeignKey("polling_places.id", ondelete="RESTRICT"))
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


class ElectionDayAdminSupportSession(Base):
    """Modo soporte administrativo explícito (§6): el privilegio global de
    ADMIN nunca equivale por sí solo a acceso operativo de Jornada Electoral.
    Un ADMIN solo entra al Centro de Control mientras tiene una fila activa
    (ended_at IS NULL) aquí, para una campaña a la vez — nunca propietario
    operativo, solo soporte auditado y de solo lectura."""
    __tablename__ = "election_day_admin_support_sessions"
    __table_args__ = (
        Index("ix_election_day_admin_support_sessions_admin_user_id", "admin_user_id"),
        Index("ix_election_day_admin_support_sessions_campaign_id", "campaign_id"),
        Index("ix_election_day_admin_support_sessions_operation_id", "operation_id"),
        Index(
            "uq_election_day_admin_support_sessions_one_active_per_admin",
            "admin_user_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
            sqlite_where=text("ended_at IS NULL"),
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    admin_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)
    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(ForeignKey("election_day_operations.id", ondelete="RESTRICT"), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ElectionDayStaffInvitation(Base):
    """Invitación de personal operativo de Jornada Electoral (Fase 1B, §4).

    Deliberadamente NO crea CampaignUser/OrganizationMembership/
    TerritorialAssignment/UserRole al aceptarse: un Delegado de recinto o
    Validador de actas invitado aquí obtiene acceso exclusivamente vía
    ElectionDayAssignment, nunca acceso general de campaña. El token en texto
    plano nunca se persiste — solo su SHA-256 (token_hash); el original se
    devuelve una única vez, al crear o reemitir."""
    __tablename__ = "election_day_staff_invitations"
    __table_args__ = (
        CheckConstraint("staff_type IN ('POLLING_PLACE_DELEGATE','ACT_VALIDATOR')", name="staff_type"),
        CheckConstraint("status IN ('PENDING','ACCEPTED','REVOKED','EXPIRED')", name="status"),
        CheckConstraint("(status = 'ACCEPTED') = (accepted_user_id IS NOT NULL AND accepted_at IS NOT NULL)", name="accepted_fields_consistent"),
        CheckConstraint("(status = 'REVOKED') = (revoked_at IS NOT NULL AND revoked_by_user_id IS NOT NULL)", name="revoked_fields_consistent"),
        Index("ix_election_day_staff_invitations_organization_id", "organization_id"),
        Index("ix_election_day_staff_invitations_campaign_id", "campaign_id"),
        Index("ix_election_day_staff_invitations_operation_id", "operation_id"),
        Index("ix_election_day_staff_invitations_email", "email"),
        Index("ix_election_day_staff_invitations_status", "status"),
        Index("ix_election_day_staff_invitations_token_hash", "token_hash", unique=True),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)
    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False)
    # nombre explícito: el autogenerado por la convención (con sufijo de
    # tabla referida) excede el límite de 63 caracteres de PostgreSQL.
    operation_id: Mapped[UUID] = mapped_column(ForeignKey("election_day_operations.id", ondelete="RESTRICT", name="fk_election_day_staff_invitations_operation_id"), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    staff_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", server_default="PENDING")
    invited_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    accepted_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ElectionDayStaffInvitationPollingPlace(Base):
    """Recintos cubiertos por una invitación de Delegado (§5). ACT_VALIDATOR
    nunca tiene filas aquí; POLLING_PLACE_DELEGATE requiere al menos una."""
    __tablename__ = "election_day_staff_invitation_polling_places"
    # Nombres de constraint/index acortados a propósito (sin sufijo de tabla
    # referida): el nombre completo de esta tabla ya deja poco margen bajo el
    # límite de 63 caracteres de PostgreSQL para identificadores.
    __table_args__ = (
        UniqueConstraint("invitation_id", "polling_place_id", name="uq_election_day_staff_invitation_polling_places_pair"),
        Index("ix_election_day_staff_invitation_polling_places_invitation_id", "invitation_id"),
        Index("ix_election_day_staff_invitation_polling_places_place_id", "polling_place_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    invitation_id: Mapped[UUID] = mapped_column(ForeignKey("election_day_staff_invitations.id", ondelete="CASCADE", name="fk_election_day_staff_invitation_polling_places_invitation_id"), nullable=False)
    polling_place_id: Mapped[UUID] = mapped_column(ForeignKey("polling_places.id", ondelete="RESTRICT", name="fk_election_day_staff_invitation_polling_places_place_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


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


class ElectionAct(Base):
    """Identidad canónica del acta (Fase 2 §3): a lo sumo UNA fila por
    (operation_id, electoral_board_id, electoral_contest_id) — el UNIQUE de
    abajo es lo que convierte "dos delegados intentan registrar la misma
    JRV+contienda" en una carrera resuelta por la propia base de datos, nunca
    por lógica de aplicación. La fila se crea al iniciar el primer borrador
    (§12: es ahí donde debe fallar el segundo intento, con 409), no al
    enviarlo — por eso `status` arranca en 'RECEIVED' aunque su primera
    revisión siga en DRAFT; la cola de validación (§15) solo debe mostrar
    actas cuya última revisión ya esté SUBMITTED, nunca las que siguen en
    borrador."""
    __tablename__ = "election_acts"
    __table_args__ = (
        CheckConstraint("status IN ('RECEIVED','IN_REVIEW','OBSERVED','VALIDATED')", name="status"),
        UniqueConstraint("operation_id", "electoral_board_id", "electoral_contest_id", name="uq_election_acts_identity"),
        # FK compuesta (§8 auditoría Fase 2): una FK simple sobre
        # validated_revision_id solo garantiza que la fila exista en
        # election_act_revisions — nunca que pertenezca a ESTA acta. Al
        # referenciar (id, validated_revision_id) contra
        # revisions(act_id, id), Postgres rechaza cualquier intento de
        # apuntar a la revisión de otra acta; con MATCH SIMPLE (default) la
        # constraint no se evalúa mientras validated_revision_id sea NULL,
        # que es el caso normal antes de validar.
        ForeignKeyConstraint(
            ["id", "validated_revision_id"], ["election_act_revisions.act_id", "election_act_revisions.id"],
            ondelete="RESTRICT", use_alter=True, name="fk_election_acts_validated_revision_id_election_act_revisions",
        ),
        Index("ix_election_acts_operation_id", "operation_id"),
        Index("ix_election_acts_status", "status"),
        Index("ix_election_acts_polling_place_id", "polling_place_id"),
        Index("ix_election_acts_electoral_board_id", "electoral_board_id"),
        Index("ix_election_acts_electoral_contest_id", "electoral_contest_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)
    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(ForeignKey("election_day_operations.id", ondelete="RESTRICT"), nullable=False)
    polling_place_id: Mapped[UUID] = mapped_column(ForeignKey("polling_places.id", ondelete="RESTRICT"), nullable=False)
    electoral_board_id: Mapped[UUID] = mapped_column(ForeignKey("electoral_boards.id", ondelete="RESTRICT"), nullable=False)
    electoral_contest_id: Mapped[UUID] = mapped_column(ForeignKey("electoral_contests.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="RECEIVED", server_default="RECEIVED")
    latest_revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    # use_alter=True: referencia circular con election_act_revisions
    # (revision.act_id -> acts.id) — SQLAlchemy/Alembic la agregan vía ALTER
    # TABLE después de crear ambas tablas, nunca dentro del CREATE TABLE. La
    # FK real (compuesta) vive en __table_args__ de arriba; esta columna
    # solo declara el tipo.
    validated_revision_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    review_claimed_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    review_claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ElectionActRevision(Base):
    """Una revisión SUBMITTED es inmutable (§5): nunca hay un UPDATE sobre
    los campos de conteo de una revisión ya enviada — toda corrección crea
    una fila nueva con revision_number+1. client_generated_id da
    idempotencia por (act, autor): un reintento offline con el mismo id no
    crea una segunda revisión."""
    __tablename__ = "election_act_revisions"
    __table_args__ = (
        CheckConstraint("revision_number >= 1", name="revision_number_positive"),
        CheckConstraint("revision_type IN ('INITIAL','CORRECTION')", name="revision_type"),
        CheckConstraint("status IN ('DRAFT','SUBMITTED')", name="status"),
        CheckConstraint("blank_ballots >= 0", name="blank_ballots_nonnegative"),
        CheckConstraint("null_ballots >= 0", name="null_ballots_nonnegative"),
        CheckConstraint("valid_ballots IS NULL OR valid_ballots >= 0", name="valid_ballots_nonnegative"),
        CheckConstraint("ballots_counted IS NULL OR ballots_counted >= 0", name="ballots_counted_nonnegative"),
        CheckConstraint("revision_type = 'INITIAL' OR correction_reason IS NOT NULL", name="correction_requires_reason"),
        UniqueConstraint("act_id", "revision_number", name="uq_election_act_revisions_act_number"),
        # Objetivo de la FK compuesta de election_acts.validated_revision_id
        # (§8 auditoría Fase 2) — trivialmente única ya que `id` ya es PK,
        # pero Postgres exige una UNIQUE/PK real sobre las columnas
        # referenciadas por una FK compuesta.
        UniqueConstraint("act_id", "id", name="uq_election_act_revisions_act_id_id"),
        Index("ix_election_act_revisions_act_id", "act_id"),
        Index("ix_election_act_revisions_status", "status"),
        Index(
            "uq_election_act_revisions_client_id", "act_id", "submitted_by_user_id", "client_generated_id",
            unique=True,
            postgresql_where=text("client_generated_id IS NOT NULL"),
            sqlite_where=text("client_generated_id IS NOT NULL"),
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    act_id: Mapped[UUID] = mapped_column(ForeignKey("election_acts.id", ondelete="RESTRICT"), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    revision_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT", server_default="DRAFT")
    submitted_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    client_generated_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    offline_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    blank_ballots: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    null_ballots: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    valid_ballots: Mapped[int | None] = mapped_column(Integer)
    ballots_counted: Mapped[int | None] = mapped_column(Integer)
    correction_reason: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ElectionActResult(Base):
    """Un voto por candidato por revisión — nunca texto libre (§6): el
    frontend solo puede enviar electoral_candidate_id tomados de
    ElectoralCandidate, y el backend revalida que pertenezcan exactamente al
    ElectoralContest del acta y estén activos."""
    __tablename__ = "election_act_results"
    __table_args__ = (
        CheckConstraint("votes >= 0", name="votes_nonnegative"),
        UniqueConstraint("revision_id", "electoral_candidate_id", name="uq_election_act_results_revision_candidate"),
        Index("ix_election_act_results_revision_id", "revision_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    revision_id: Mapped[UUID] = mapped_column(ForeignKey("election_act_revisions.id", ondelete="CASCADE"), nullable=False)
    # Nombre acortado (sin sufijo de tabla referida): el nombre completo
    # excede el límite de 63 caracteres de PostgreSQL. Debe coincidir
    # exactamente con el `name=` explícito de la migración.
    electoral_candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("electoral_candidates.id", ondelete="RESTRICT", name="fk_election_act_results_electoral_candidate_id"),
        nullable=False,
    )
    votes: Mapped[int] = mapped_column(Integer, nullable=False)


class ElectionActEvidence(Base):
    """Fotografía/evidencia del acta física — entidad propia (§7), nunca
    ElectionDayDocument (ese modelo es para documentación operativa general,
    no la evidencia legal del acta). Reutiliza la misma abstracción
    EvidenceStorage que ElectionDayDocument (LocalEvidenceStorage hoy,
    intercambiable por S3 después sin tocar este modelo)."""
    __tablename__ = "election_act_evidence"
    __table_args__ = (
        Index("ix_election_act_evidence_revision_id", "revision_id"),
        Index("uq_election_act_evidence_storage_key", "storage_key", unique=True),
        Index(
            "uq_election_act_evidence_client_id", "revision_id", "uploaded_by_user_id", "client_generated_id",
            unique=True,
            postgresql_where=text("client_generated_id IS NOT NULL"),
            sqlite_where=text("client_generated_id IS NOT NULL"),
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    revision_id: Mapped[UUID] = mapped_column(ForeignKey("election_act_revisions.id", ondelete="CASCADE"), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    uploaded_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    client_generated_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)


class ElectionActReview(Base):
    """Cada review apunta a la revisión EXACTA inspeccionada (§18) — nunca al
    acta en general — para que el historial quede trazable incluso después
    de que una corrección reemplace la revisión observada."""
    __tablename__ = "election_act_reviews"
    __table_args__ = (
        CheckConstraint("review_source IN ('CAMPAIGN_VALIDATOR','ADMIN_SUPPORT')", name="review_source"),
        CheckConstraint("action IN ('VALIDATED','OBSERVED')", name="action"),
        CheckConstraint("action = 'VALIDATED' OR reason IS NOT NULL", name="observed_requires_reason"),
        Index("ix_election_act_reviews_act_id", "act_id"),
        Index("ix_election_act_reviews_revision_id", "revision_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    act_id: Mapped[UUID] = mapped_column(ForeignKey("election_acts.id", ondelete="RESTRICT"), nullable=False)
    revision_id: Mapped[UUID] = mapped_column(ForeignKey("election_act_revisions.id", ondelete="RESTRICT"), nullable=False)
    reviewer_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    review_source: Mapped[str] = mapped_column(String(30), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
