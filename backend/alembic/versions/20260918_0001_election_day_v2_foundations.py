"""Election Day V2 foundations: SCRUTINY lifecycle stage, delegate/validator
assignment model (drops board_id, makes polling_place_id nullable), and the
ElectionDayAdminSupportSession entity for explicit ADMIN support mode.

Revision ID: 20260918_0001
Revises: 20260910_0001
"""
from alembic import op
import sqlalchemy as sa

revision = "20260918_0001"
down_revision = "20260910_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------- Operation lifecycle: PREPARATION -> ACTIVE -> SCRUTINY -> CLOSED ----------
    op.execute("ALTER TABLE election_day_operations DROP CONSTRAINT ck_election_day_operations_status")
    op.execute("ALTER TABLE election_day_operations ADD CONSTRAINT ck_election_day_operations_status CHECK (status IN ('PREPARATION','ACTIVE','SCRUTINY','CLOSED'))")
    op.add_column("election_day_operations", sa.Column("scrutiny_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("election_day_operations", sa.Column("scrutiny_started_by_user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_election_day_operations_scrutiny_started_by_user_id_users"),
        "election_day_operations", "users", ["scrutiny_started_by_user_id"], ["id"], ondelete="RESTRICT",
    )

    # ---------- Assignment model: POLLING_PLACE_DELEGATE / ACT_VALIDATOR only ----------
    # Normalize legacy/test roles to POLLING_PLACE_DELEGATE before the check
    # constraint is narrowed — no record is dropped, only relabeled.
    op.execute(
        "UPDATE election_day_assignments SET assignment_role = 'POLLING_PLACE_DELEGATE' "
        "WHERE assignment_role IN ('POLLING_PLACE_COORDINATOR','BOARD_DELEGATE','MOBILE_SUPPORT')"
    )
    # Deduplicate: two legacy roles pointing the same person at the same
    # recinto would collide under the new "one active delegate row per
    # (operation, user, polling_place)" constraint. Keep the most advanced
    # row (CHECKED_IN > CONFIRMED > ASSIGNED > ABSENT > COMPLETED) and mark
    # the rest REPLACED, wired to the kept row — history is preserved, no
    # row is deleted.
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   FIRST_VALUE(id) OVER (
                       PARTITION BY operation_id, user_id, polling_place_id
                       ORDER BY CASE status
                           WHEN 'CHECKED_IN' THEN 0 WHEN 'CONFIRMED' THEN 1 WHEN 'ASSIGNED' THEN 2
                           WHEN 'ABSENT' THEN 3 ELSE 4 END, created_at ASC
                   ) AS keep_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY operation_id, user_id, polling_place_id
                       ORDER BY CASE status
                           WHEN 'CHECKED_IN' THEN 0 WHEN 'CONFIRMED' THEN 1 WHEN 'ASSIGNED' THEN 2
                           WHEN 'ABSENT' THEN 3 ELSE 4 END, created_at ASC
                   ) AS rn
            FROM election_day_assignments
            WHERE assignment_role = 'POLLING_PLACE_DELEGATE' AND status != 'REPLACED'
        )
        UPDATE election_day_assignments AS t
        SET status = 'REPLACED', replaced_by_assignment_id = ranked.keep_id
        FROM ranked
        WHERE t.id = ranked.id AND ranked.rn > 1
        """
    )
    op.drop_constraint("fk_election_day_assignments_board_id_electoral_boards", "election_day_assignments", type_="foreignkey")
    op.drop_index("ix_election_day_assignments_board_id", table_name="election_day_assignments")
    op.drop_column("election_day_assignments", "board_id")
    op.alter_column("election_day_assignments", "polling_place_id", existing_type=sa.Uuid(), nullable=True)
    op.execute("ALTER TABLE election_day_assignments DROP CONSTRAINT ck_election_day_assignments_assignment_role")
    op.execute("ALTER TABLE election_day_assignments ADD CONSTRAINT ck_election_day_assignments_assignment_role CHECK (assignment_role IN ('POLLING_PLACE_DELEGATE','ACT_VALIDATOR'))")
    op.execute(
        "ALTER TABLE election_day_assignments ADD CONSTRAINT ck_election_day_assignments_polling_place_matches_role "
        "CHECK ((assignment_role = 'POLLING_PLACE_DELEGATE' AND polling_place_id IS NOT NULL) "
        "OR (assignment_role = 'ACT_VALIDATOR' AND polling_place_id IS NULL))"
    )
    op.create_index(
        "uq_election_day_assignments_active_delegate_place", "election_day_assignments",
        ["operation_id", "user_id", "polling_place_id"], unique=True,
        postgresql_where=sa.text("assignment_role = 'POLLING_PLACE_DELEGATE' AND status != 'REPLACED'"),
    )
    op.create_index(
        "uq_election_day_assignments_active_validator", "election_day_assignments",
        ["operation_id", "user_id"], unique=True,
        postgresql_where=sa.text("assignment_role = 'ACT_VALIDATOR' AND status != 'REPLACED'"),
    )

    # ---------- Admin support sessions ----------
    op.create_table(
        "election_day_admin_support_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("admin_user_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["admin_user_id"], ["users.id"], name=op.f("fk_election_day_admin_support_sessions_admin_user_id_users"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], name=op.f("fk_election_day_admin_support_sessions_campaign_id_campaigns"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["operation_id"], ["election_day_operations.id"], name=op.f("fk_election_day_admin_support_sessions_operation_id_election_day_operations"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_election_day_admin_support_sessions_organization_id_organizations"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_election_day_admin_support_sessions")),
    )
    op.create_index("ix_election_day_admin_support_sessions_admin_user_id", "election_day_admin_support_sessions", ["admin_user_id"], unique=False)
    op.create_index("ix_election_day_admin_support_sessions_campaign_id", "election_day_admin_support_sessions", ["campaign_id"], unique=False)
    op.create_index("ix_election_day_admin_support_sessions_operation_id", "election_day_admin_support_sessions", ["operation_id"], unique=False)
    op.create_index(
        "uq_election_day_admin_support_sessions_one_active_per_admin", "election_day_admin_support_sessions",
        ["admin_user_id"], unique=True, postgresql_where=sa.text("ended_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_election_day_admin_support_sessions_one_active_per_admin", table_name="election_day_admin_support_sessions", postgresql_where=sa.text("ended_at IS NULL"))
    op.drop_index("ix_election_day_admin_support_sessions_operation_id", table_name="election_day_admin_support_sessions")
    op.drop_index("ix_election_day_admin_support_sessions_campaign_id", table_name="election_day_admin_support_sessions")
    op.drop_index("ix_election_day_admin_support_sessions_admin_user_id", table_name="election_day_admin_support_sessions")
    op.drop_table("election_day_admin_support_sessions")

    op.drop_index("uq_election_day_assignments_active_validator", table_name="election_day_assignments", postgresql_where=sa.text("assignment_role = 'ACT_VALIDATOR' AND status != 'REPLACED'"))
    op.drop_index("uq_election_day_assignments_active_delegate_place", table_name="election_day_assignments", postgresql_where=sa.text("assignment_role = 'POLLING_PLACE_DELEGATE' AND status != 'REPLACED'"))
    op.execute("ALTER TABLE election_day_assignments DROP CONSTRAINT ck_election_day_assignments_polling_place_matches_role")
    op.execute("ALTER TABLE election_day_assignments DROP CONSTRAINT ck_election_day_assignments_assignment_role")
    op.execute("ALTER TABLE election_day_assignments ADD CONSTRAINT ck_election_day_assignments_assignment_role CHECK (assignment_role IN ('POLLING_PLACE_COORDINATOR','BOARD_DELEGATE','MOBILE_SUPPORT'))")
    op.execute("UPDATE election_day_assignments SET assignment_role = 'BOARD_DELEGATE' WHERE assignment_role = 'POLLING_PLACE_DELEGATE'")
    op.execute("UPDATE election_day_assignments SET assignment_role = 'MOBILE_SUPPORT' WHERE assignment_role = 'ACT_VALIDATOR'")
    # A validator row has no polling_place_id to restore; downgrading past
    # this migration is a last resort and such rows must be re-pointed
    # manually before the NOT NULL constraint below can succeed again.
    op.alter_column("election_day_assignments", "polling_place_id", existing_type=sa.Uuid(), nullable=False)
    op.add_column("election_day_assignments", sa.Column("board_id", sa.Uuid(), nullable=True))
    op.create_index("ix_election_day_assignments_board_id", "election_day_assignments", ["board_id"], unique=False)
    op.create_foreign_key(
        "fk_election_day_assignments_board_id_electoral_boards", "election_day_assignments", "electoral_boards", ["board_id"], ["id"], ondelete="RESTRICT",
    )

    op.drop_constraint(op.f("fk_election_day_operations_scrutiny_started_by_user_id_users"), "election_day_operations", type_="foreignkey")
    op.drop_column("election_day_operations", "scrutiny_started_by_user_id")
    op.drop_column("election_day_operations", "scrutiny_started_at")
    op.execute("ALTER TABLE election_day_operations DROP CONSTRAINT ck_election_day_operations_status")
    op.execute("ALTER TABLE election_day_operations ADD CONSTRAINT ck_election_day_operations_status CHECK (status IN ('PREPARATION','ACTIVE','CLOSED'))")
