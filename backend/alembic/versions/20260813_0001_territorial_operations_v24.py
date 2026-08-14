"""territorial operations v2.4

Revision ID: 20260813_0001
Revises: 20260811_0001
"""
from alembic import op
import sqlalchemy as sa

revision="20260813_0001";down_revision="20260811_0001";branch_labels=None;depends_on=None

def upgrade():
    op.execute("ALTER TABLE territorial_activities DROP CONSTRAINT ck_territorial_activities_status")
    op.create_check_constraint("status", "territorial_activities", "status IN ('PLANNED','IN_PROGRESS','COMPLETED','CANCELLED')")
    op.add_column("territorial_activities",sa.Column("approval_status",sa.String(30),nullable=False,server_default="DRAFT"))
    op.add_column("territorial_activities",sa.Column("start_time",sa.Time()))
    op.add_column("territorial_activities",sa.Column("end_time",sa.Time()))
    for name in ("submitted_for_approval_at","approved_at","rejected_at"):op.add_column("territorial_activities",sa.Column(name,sa.DateTime(timezone=True)))
    for name in ("submitted_by_user_id","approved_by_user_id","rejected_by_user_id"):
        op.add_column("territorial_activities",sa.Column(name,sa.Uuid()))
        op.create_foreign_key(f"fk_territorial_activities_{name}_users","territorial_activities","users",[name],["id"],ondelete="SET NULL")
    op.add_column("territorial_activities",sa.Column("rejection_reason",sa.Text()))
    op.create_check_constraint("approval_status","territorial_activities","approval_status IN ('DRAFT','PENDING_APPROVAL','APPROVED','REJECTED')")
    op.alter_column("citizen_needs","activity_id",existing_type=sa.Uuid(),nullable=True)
    op.execute("ALTER TABLE citizen_needs DROP CONSTRAINT ck_citizen_needs_status")
    op.create_check_constraint("status","citizen_needs","status IN ('IDENTIFIED','REPORTED','UNDER_REVIEW','VALIDATED','IN_PLAN','INCLUDED_IN_PLAN','CLOSED','ARCHIVED','DISCARDED')")
    columns=(
      sa.Column("source_type",sa.String(30),nullable=False,server_default="OTHER"),sa.Column("reported_date",sa.Date(),nullable=False,server_default=sa.func.current_date()),
      sa.Column("urgency",sa.String(20),nullable=False,server_default="MEDIUM"),sa.Column("scope",sa.String(20),nullable=False,server_default="PARISH"),
      sa.Column("local_sector_description",sa.String(255)),sa.Column("reported_by_user_id",sa.Uuid()),sa.Column("assigned_to_user_id",sa.Uuid()),
      sa.Column("validation_notes",sa.Text()),sa.Column("validated_by_user_id",sa.Uuid()),sa.Column("validated_at",sa.DateTime(timezone=True)),
      sa.Column("resolution_notes",sa.Text()),sa.Column("evidence_notes",sa.Text()),sa.Column("source_reference",sa.String(255)))
    for column in columns:op.add_column("citizen_needs",column)
    for name in ("reported_by_user_id","assigned_to_user_id","validated_by_user_id"):op.create_foreign_key(f"fk_citizen_needs_{name}_users","citizen_needs","users",[name],["id"],ondelete="SET NULL")
    op.execute("UPDATE citizen_needs SET reported_by_user_id=created_by_user_id, reported_date=created_at::date, urgency=priority")
    op.add_column("commitments",sa.Column("need_id",sa.Uuid()))
    op.create_foreign_key("fk_commitments_need_id_citizen_needs","commitments","citizen_needs",["need_id"],["id"],ondelete="RESTRICT")
    op.create_index("ix_commitments_need_id","commitments",["need_id"])

def downgrade():
    op.drop_index("ix_commitments_need_id",table_name="commitments");op.drop_constraint("fk_commitments_need_id_citizen_needs","commitments",type_="foreignkey");op.drop_column("commitments","need_id")
    for name in ("reported_by_user_id","assigned_to_user_id","validated_by_user_id"):op.drop_constraint(f"fk_citizen_needs_{name}_users","citizen_needs",type_="foreignkey")
    for name in ("source_reference","evidence_notes","resolution_notes","validated_at","validated_by_user_id","validation_notes","assigned_to_user_id","reported_by_user_id","local_sector_description","scope","urgency","reported_date","source_type"):op.drop_column("citizen_needs",name)
    op.execute("ALTER TABLE citizen_needs DROP CONSTRAINT ck_citizen_needs_status");op.create_check_constraint("status","citizen_needs","status IN ('IDENTIFIED','UNDER_REVIEW','INCLUDED_IN_PLAN','DISCARDED')");op.alter_column("citizen_needs","activity_id",existing_type=sa.Uuid(),nullable=False)
    op.execute("ALTER TABLE territorial_activities DROP CONSTRAINT ck_territorial_activities_approval_status")
    for name in ("submitted_by_user_id","approved_by_user_id","rejected_by_user_id"):op.drop_constraint(f"fk_territorial_activities_{name}_users","territorial_activities",type_="foreignkey")
    for name in ("rejection_reason","rejected_by_user_id","approved_by_user_id","submitted_by_user_id","rejected_at","approved_at","submitted_for_approval_at","end_time","start_time","approval_status"):op.drop_column("territorial_activities",name)
    op.execute("ALTER TABLE territorial_activities DROP CONSTRAINT ck_territorial_activities_status");op.create_check_constraint("status","territorial_activities","status IN ('PLANNED','COMPLETED','CANCELLED')")
