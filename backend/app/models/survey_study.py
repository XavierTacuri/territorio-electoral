from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SurveyStudy(Base):
    __tablename__ = "survey_studies"
    __table_args__ = (
        UniqueConstraint("campaign_id", "code", name="uq_survey_studies_campaign_code"),
        CheckConstraint("study_type IN ('GENERAL_SURVEY','CNE_EXIT_POLL','POLL','TRACKING_POLL','EXIT_POLL','OTHER')", name="study_type"),
        CheckConstraint("status IN ('DRAFT','VALIDATED','PUBLISHED','ARCHIVED')", name="status"),
        CheckConstraint("geography_level IN ('CANTON','PARISH')", name="geography_level"),
        CheckConstraint("sample_size_total > 0", name="sample_size_positive"),
        CheckConstraint("fieldwork_start_date <= fieldwork_end_date", name="fieldwork_dates"),
        CheckConstraint("confidence_level IS NULL OR confidence_level BETWEEN 0 AND 1", name="confidence_level_range"),
        CheckConstraint("margin_of_error IS NULL OR margin_of_error BETWEEN 0 AND 1", name="margin_of_error_range"),
        Index("ix_survey_studies_campaign_status", "campaign_id", "status"),
        Index("ix_survey_studies_series", "campaign_id", "study_series_code"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False)
    election_process_id: Mapped[UUID | None] = mapped_column(ForeignKey("electoral_processes.id", ondelete="RESTRICT"))
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    study_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT", server_default="DRAFT")
    fieldwork_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    fieldwork_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    publication_date: Mapped[date | None] = mapped_column(Date)
    geography_level: Mapped[str] = mapped_column(String(20), nullable=False)
    sample_size_total: Mapped[int] = mapped_column(Integer, nullable=False)
    universe_description: Mapped[str] = mapped_column(Text, nullable=False)
    sampling_method: Mapped[str] = mapped_column(String(250), nullable=False)
    collection_method: Mapped[str] = mapped_column(String(250), nullable=False)
    confidence_level: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    margin_of_error: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    pollster_name: Mapped[str | None] = mapped_column(String(180))
    sponsor_name: Mapped[str | None] = mapped_column(String(180))
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    source_name: Mapped[str | None] = mapped_column(String(180))
    source_document: Mapped[str | None] = mapped_column(String(500))
    imported_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    notes: Mapped[str | None] = mapped_column(Text)
    is_official: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    study_series_code: Mapped[str | None] = mapped_column(String(80))
    question_code: Mapped[str] = mapped_column(String(80), nullable=False, default="VOTE_INTENTION", server_default="VOTE_INTENTION")
    result_count_notes: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    territories: Mapped[list["SurveyStudyTerritory"]] = relationship(back_populates="study", cascade="all, delete-orphan")
    options: Mapped[list["SurveyStudyOption"]] = relationship(back_populates="study", cascade="all, delete-orphan")


class SurveyStudyTerritory(Base):
    __tablename__ = "survey_study_territories"
    __table_args__ = (
        UniqueConstraint("study_id", "parish_id", name="uq_survey_study_territories_study_parish"),
        CheckConstraint("sample_size > 0", name="sample_size_positive"),
        CheckConstraint("margin_of_error IS NULL OR margin_of_error BETWEEN 0 AND 1", name="margin_of_error_range"),
        Index("ix_survey_study_territories_study", "study_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    study_id: Mapped[UUID] = mapped_column(ForeignKey("survey_studies.id", ondelete="CASCADE"), nullable=False)
    parish_id: Mapped[int | None] = mapped_column(ForeignKey("parishes.id", ondelete="RESTRICT"))
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    margin_of_error: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    coverage_notes: Mapped[str | None] = mapped_column(Text)
    study: Mapped[SurveyStudy] = relationship(back_populates="territories")
    results: Mapped[list["SurveyStudyResult"]] = relationship(back_populates="territory", cascade="all, delete-orphan")


class SurveyStudyOption(Base):
    __tablename__ = "survey_study_options"
    __table_args__ = (
        UniqueConstraint("study_id", "question_code", "code", name="uq_survey_study_options_question_code"),
        CheckConstraint("option_type IN ('CANDIDATE','UNDECIDED','BLANK','NULL_VOTE','OTHER','NO_RESPONSE')", name="option_type"),
        CheckConstraint("question_type IN ('SINGLE_CHOICE','MULTIPLE_CHOICE','SCALE','RATING','VOTE_INTENTION')", name="question_type"),
        CheckConstraint("display_order >= 0", name="display_order"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    study_id: Mapped[UUID] = mapped_column(ForeignKey("survey_studies.id", ondelete="CASCADE"), nullable=False)
    question_code: Mapped[str] = mapped_column(String(80), nullable=False, default="Q1", server_default="Q1")
    question_text: Mapped[str] = mapped_column(Text, nullable=False, default="Pregunta agregada", server_default="Pregunta agregada")
    question_type: Mapped[str] = mapped_column(String(30), nullable=False, default="SINGLE_CHOICE", server_default="SINGLE_CHOICE")
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(180), nullable=False)
    option_type: Mapped[str] = mapped_column(String(20), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    study: Mapped[SurveyStudy] = relationship(back_populates="options")


class SurveyStudyResult(Base):
    __tablename__ = "survey_study_results"
    __table_args__ = (
        UniqueConstraint("study_id", "study_territory_id", "option_id", name="uq_survey_study_results_key"),
        CheckConstraint("percentage BETWEEN 0 AND 1", name="percentage_range"),
        CheckConstraint("response_count IS NULL OR response_count >= 0", name="response_count_nonnegative"),
        Index("ix_survey_study_results_study", "study_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    study_id: Mapped[UUID] = mapped_column(ForeignKey("survey_studies.id", ondelete="CASCADE"), nullable=False)
    study_territory_id: Mapped[UUID] = mapped_column(ForeignKey("survey_study_territories.id", ondelete="CASCADE"), nullable=False)
    option_id: Mapped[UUID] = mapped_column(ForeignKey("survey_study_options.id", ondelete="CASCADE"), nullable=False)
    response_count: Mapped[int | None] = mapped_column(Integer)
    percentage: Mapped[Decimal] = mapped_column(Numeric(9, 8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    territory: Mapped[SurveyStudyTerritory] = relationship(back_populates="results")
