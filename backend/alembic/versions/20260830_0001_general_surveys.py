"""Canonical general surveys and CNE exit polls.

Revision ID: 20260830_0001
Revises: 20260824_0002
"""
from alembic import op
import sqlalchemy as sa

revision = "20260830_0001"
down_revision = "20260824_0002"
branch_labels = None
depends_on = None

def upgrade():
    op.drop_constraint(op.f("ck_survey_studies_study_type"), "survey_studies", type_="check")
    op.create_check_constraint("study_type", "survey_studies", "study_type IN ('GENERAL_SURVEY','CNE_EXIT_POLL','POLL','TRACKING_POLL','EXIT_POLL','OTHER')")
    op.add_column("survey_studies", sa.Column("source_name", sa.String(180)))
    op.add_column("survey_studies", sa.Column("source_document", sa.String(500)))
    op.add_column("survey_studies", sa.Column("imported_by_user_id", sa.Uuid()))
    op.create_foreign_key("fk_survey_studies_imported_by_user_id_users", "survey_studies", "users", ["imported_by_user_id"], ["id"], ondelete="RESTRICT")
    op.add_column("survey_study_options", sa.Column("question_code", sa.String(80), nullable=False, server_default="Q1"))
    op.add_column("survey_study_options", sa.Column("question_text", sa.Text(), nullable=False, server_default="Pregunta agregada"))
    op.add_column("survey_study_options", sa.Column("question_type", sa.String(30), nullable=False, server_default="SINGLE_CHOICE"))
    op.create_check_constraint("question_type", "survey_study_options", "question_type IN ('SINGLE_CHOICE','MULTIPLE_CHOICE','SCALE','RATING','VOTE_INTENTION')")
    op.drop_constraint("uq_survey_study_options_study_code", "survey_study_options", type_="unique")
    op.create_unique_constraint("uq_survey_study_options_question_code", "survey_study_options", ["study_id", "question_code", "code"])

def downgrade():
    op.drop_constraint("uq_survey_study_options_question_code", "survey_study_options", type_="unique")
    op.create_unique_constraint("uq_survey_study_options_study_code", "survey_study_options", ["study_id", "code"])
    op.drop_constraint(op.f("ck_survey_study_options_question_type"), "survey_study_options", type_="check")
    op.drop_column("survey_study_options", "question_type")
    op.drop_column("survey_study_options", "question_text")
    op.drop_column("survey_study_options", "question_code")
    op.drop_constraint("fk_survey_studies_imported_by_user_id_users", "survey_studies", type_="foreignkey")
    op.drop_column("survey_studies", "imported_by_user_id")
    op.drop_column("survey_studies", "source_document")
    op.drop_column("survey_studies", "source_name")
    op.drop_constraint(op.f("ck_survey_studies_study_type"), "survey_studies", type_="check")
    op.create_check_constraint("study_type", "survey_studies", "study_type IN ('POLL','TRACKING_POLL','EXIT_POLL','OTHER')")
