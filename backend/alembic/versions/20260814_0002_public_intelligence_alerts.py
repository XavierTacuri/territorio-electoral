"""public intelligence alert module

Revision ID: 20260814_0002
Revises: 20260814_0001
"""
from alembic import op
revision="20260814_0002";down_revision="20260814_0001";branch_labels=None;depends_on=None
def upgrade():
    op.execute("ALTER TABLE alert_rules DROP CONSTRAINT ck_alert_rules_module")
    op.execute("ALTER TABLE alert_rules ADD CONSTRAINT ck_alert_rules_module CHECK (module IN ('OPERATIONS','COMMITMENTS','SURVEYS','DATA_IMPORTS','ELECTORAL_DATA','DEMOGRAPHICS','GEOMETRY','DATA_QUALITY','PUBLIC_INTELLIGENCE'))")
    op.execute("ALTER TABLE report_templates DROP CONSTRAINT ck_report_templates_report_type")
    op.execute("ALTER TABLE report_templates ADD CONSTRAINT ck_report_templates_report_type CHECK (report_type IN ('CAMPAIGN_EXECUTIVE_SUMMARY','OPERATIONAL_ACTIVITY','TERRITORIAL_COVERAGE','NEEDS','COMMITMENTS','SURVEY_RESULTS','SURVEY_STUDY','ELECTORAL_HISTORY','DEMOGRAPHIC_PROFILE','DATA_QUALITY','GEOGRAPHIC_AVAILABILITY','PUBLIC_INTELLIGENCE'))")
def downgrade():
    op.execute("ALTER TABLE report_templates DROP CONSTRAINT ck_report_templates_report_type")
    op.execute("ALTER TABLE report_templates ADD CONSTRAINT ck_report_templates_report_type CHECK (report_type IN ('CAMPAIGN_EXECUTIVE_SUMMARY','OPERATIONAL_ACTIVITY','TERRITORIAL_COVERAGE','NEEDS','COMMITMENTS','SURVEY_RESULTS','SURVEY_STUDY','ELECTORAL_HISTORY','DEMOGRAPHIC_PROFILE','DATA_QUALITY','GEOGRAPHIC_AVAILABILITY'))")
    op.execute("ALTER TABLE alert_rules DROP CONSTRAINT ck_alert_rules_module")
    op.execute("ALTER TABLE alert_rules ADD CONSTRAINT ck_alert_rules_module CHECK (module IN ('OPERATIONS','COMMITMENTS','SURVEYS','DATA_IMPORTS','ELECTORAL_DATA','DEMOGRAPHICS','GEOMETRY','DATA_QUALITY'))")
