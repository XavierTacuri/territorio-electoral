from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
import geoalchemy2  # noqa: F401 - registers PostGIS reflection

from app.core.config import settings
from app.db.base import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
MANAGED_TABLES = {"roles", "users", "user_roles", "provinces", "cantons", "parishes", "communities", "sectors", "campaigns", "candidates", "campaign_users", "territorial_assignments", "activity_types", "territorial_activities", "activity_participant_summaries", "need_categories", "citizen_needs", "commitments", "activity_evidence", "surveys", "survey_sections", "survey_questions", "survey_options", "survey_responses", "survey_answers", "survey_answer_options", "survey_studies", "survey_study_territories", "survey_study_options", "survey_study_results", "data_sources", "data_import_jobs", "data_import_errors", "electoral_processes", "electoral_contests", "political_organizations", "electoral_geographies", "electoral_candidates", "electoral_turnout", "electoral_candidate_results", "demographic_indicators", "demographic_observations", "electoral_roll_snapshots", "electoral_roll_snapshot_entries", "participation_projection_runs", "participation_projection_results", "report_templates", "report_runs", "report_artifacts", "alert_rules", "operational_alerts", "alert_acknowledgements", "auth_sessions", "security_audit_events", "public_sources", "public_intelligence_items", "public_item_revisions", "public_source_fetch_runs", "public_topics", "public_item_topics", "public_item_territories", "public_item_need_links", "campaign_feature_entitlements", "ai_usage_events", "territory_ai_conversations", "territory_ai_messages"}

def include_name(name: str | None, type_: str, parent_names: dict[str, str | None]) -> bool:
    return type_ != "table" or name in MANAGED_TABLES


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_name=include_name,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

