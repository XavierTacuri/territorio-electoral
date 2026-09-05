"""Centro de Informes: add THEMATIC report_type for cross-topic reports.

Revision ID: 20260906_0001
Revises: 20260905_0001
"""
from alembic import op

revision = "20260906_0001"
down_revision = "20260905_0001"
branch_labels = None
depends_on = None

OLD_TYPES = "'CAMPAIGN_EXECUTIVE_SUMMARY','OPERATIONAL_ACTIVITY','TERRITORIAL_COVERAGE','NEEDS','COMMITMENTS','SURVEY_RESULTS','SURVEY_STUDY','ELECTORAL_HISTORY','DEMOGRAPHIC_PROFILE','DATA_QUALITY','GEOGRAPHIC_AVAILABILITY','PUBLIC_INTELLIGENCE'"
NEW_TYPES = OLD_TYPES + ",'THEMATIC'"


def upgrade():
    op.execute("ALTER TABLE report_templates DROP CONSTRAINT ck_report_templates_report_type")
    op.execute(f"ALTER TABLE report_templates ADD CONSTRAINT ck_report_templates_report_type CHECK (report_type IN ({NEW_TYPES}))")


def downgrade():
    op.execute("ALTER TABLE report_templates DROP CONSTRAINT ck_report_templates_report_type")
    op.execute(f"ALTER TABLE report_templates ADD CONSTRAINT ck_report_templates_report_type CHECK (report_type IN ({OLD_TYPES}))")
