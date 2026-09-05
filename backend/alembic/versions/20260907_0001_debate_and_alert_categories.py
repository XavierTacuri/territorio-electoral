"""Centro de Informes: add DEBATE_BRIEF report_type and EVIDENCE/REPORTS alert modules.

Revision ID: 20260907_0001
Revises: 20260906_0001
"""
from alembic import op

revision = "20260907_0001"
down_revision = "20260906_0001"
branch_labels = None
depends_on = None

OLD_REPORT_TYPES = "'CAMPAIGN_EXECUTIVE_SUMMARY','OPERATIONAL_ACTIVITY','TERRITORIAL_COVERAGE','NEEDS','COMMITMENTS','SURVEY_RESULTS','SURVEY_STUDY','ELECTORAL_HISTORY','DEMOGRAPHIC_PROFILE','DATA_QUALITY','GEOGRAPHIC_AVAILABILITY','PUBLIC_INTELLIGENCE','THEMATIC'"
NEW_REPORT_TYPES = OLD_REPORT_TYPES + ",'DEBATE_BRIEF'"

OLD_MODULES = "'OPERATIONS','COMMITMENTS','SURVEYS','DATA_IMPORTS','ELECTORAL_DATA','DEMOGRAPHICS','GEOMETRY','DATA_QUALITY','PUBLIC_INTELLIGENCE'"
NEW_MODULES = OLD_MODULES + ",'EVIDENCE','REPORTS'"


def upgrade():
    op.execute("ALTER TABLE report_templates DROP CONSTRAINT ck_report_templates_report_type")
    op.execute(f"ALTER TABLE report_templates ADD CONSTRAINT ck_report_templates_report_type CHECK (report_type IN ({NEW_REPORT_TYPES}))")
    op.execute("ALTER TABLE alert_rules DROP CONSTRAINT ck_alert_rules_module")
    op.execute(f"ALTER TABLE alert_rules ADD CONSTRAINT ck_alert_rules_module CHECK (module IN ({NEW_MODULES}))")


def downgrade():
    op.execute("ALTER TABLE alert_rules DROP CONSTRAINT ck_alert_rules_module")
    op.execute(f"ALTER TABLE alert_rules ADD CONSTRAINT ck_alert_rules_module CHECK (module IN ({OLD_MODULES}))")
    op.execute("ALTER TABLE report_templates DROP CONSTRAINT ck_report_templates_report_type")
    op.execute(f"ALTER TABLE report_templates ADD CONSTRAINT ck_report_templates_report_type CHECK (report_type IN ({OLD_REPORT_TYPES}))")
