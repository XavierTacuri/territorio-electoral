"""Election Day Fase 2: actas electorales, revisiones, resultados,
evidencia y validación (§3-§20). election_acts.validated_revision_id usa
una FK compuesta (id, validated_revision_id) -> revisions(act_id, id)
(§8 auditoría) para que la base de datos, no solo el servicio, impida que
una acta quede "validada" apuntando a la revisión de otra acta.

Revision ID: 20260919_0002
Revises: 20260919_0001
"""
from alembic import op
import sqlalchemy as sa


revision = "20260919_0002"
down_revision = "20260919_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('election_acts',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('campaign_id', sa.Uuid(), nullable=False),
    sa.Column('operation_id', sa.Uuid(), nullable=False),
    sa.Column('polling_place_id', sa.Uuid(), nullable=False),
    sa.Column('electoral_board_id', sa.Uuid(), nullable=False),
    sa.Column('electoral_contest_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='RECEIVED', nullable=False),
    sa.Column('latest_revision_number', sa.Integer(), server_default='1', nullable=False),
    sa.Column('validated_revision_id', sa.Uuid(), nullable=True),
    sa.Column('review_claimed_by_user_id', sa.Uuid(), nullable=True),
    sa.Column('review_claimed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('review_claim_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('RECEIVED','IN_REVIEW','OBSERVED','VALIDATED')", name=op.f('ck_election_acts_status')),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], name=op.f('fk_election_acts_campaign_id_campaigns'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['electoral_board_id'], ['electoral_boards.id'], name=op.f('fk_election_acts_electoral_board_id_electoral_boards'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['electoral_contest_id'], ['electoral_contests.id'], name=op.f('fk_election_acts_electoral_contest_id_electoral_contests'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['operation_id'], ['election_day_operations.id'], name=op.f('fk_election_acts_operation_id_election_day_operations'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_election_acts_organization_id_organizations'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['polling_place_id'], ['polling_places.id'], name=op.f('fk_election_acts_polling_place_id_polling_places'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['review_claimed_by_user_id'], ['users.id'], name=op.f('fk_election_acts_review_claimed_by_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_election_acts')),
    sa.UniqueConstraint('operation_id', 'electoral_board_id', 'electoral_contest_id', name='uq_election_acts_identity')
    )
    op.create_index('ix_election_acts_electoral_board_id', 'election_acts', ['electoral_board_id'], unique=False)
    op.create_index('ix_election_acts_electoral_contest_id', 'election_acts', ['electoral_contest_id'], unique=False)
    op.create_index('ix_election_acts_operation_id', 'election_acts', ['operation_id'], unique=False)
    op.create_index('ix_election_acts_polling_place_id', 'election_acts', ['polling_place_id'], unique=False)
    op.create_index('ix_election_acts_status', 'election_acts', ['status'], unique=False)
    op.create_table('election_act_revisions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('act_id', sa.Uuid(), nullable=False),
    sa.Column('revision_number', sa.Integer(), nullable=False),
    sa.Column('revision_type', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='DRAFT', nullable=False),
    sa.Column('submitted_by_user_id', sa.Uuid(), nullable=False),
    sa.Column('client_generated_id', sa.Uuid(), nullable=True),
    sa.Column('offline_created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('blank_ballots', sa.Integer(), server_default='0', nullable=False),
    sa.Column('null_ballots', sa.Integer(), server_default='0', nullable=False),
    sa.Column('valid_ballots', sa.Integer(), nullable=True),
    sa.Column('ballots_counted', sa.Integer(), nullable=True),
    sa.Column('correction_reason', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("revision_type = 'INITIAL' OR correction_reason IS NOT NULL", name=op.f('ck_election_act_revisions_correction_requires_reason')),
    sa.CheckConstraint("revision_type IN ('INITIAL','CORRECTION')", name=op.f('ck_election_act_revisions_revision_type')),
    sa.CheckConstraint("status IN ('DRAFT','SUBMITTED')", name=op.f('ck_election_act_revisions_status')),
    sa.CheckConstraint('ballots_counted IS NULL OR ballots_counted >= 0', name=op.f('ck_election_act_revisions_ballots_counted_nonnegative')),
    sa.CheckConstraint('blank_ballots >= 0', name=op.f('ck_election_act_revisions_blank_ballots_nonnegative')),
    sa.CheckConstraint('null_ballots >= 0', name=op.f('ck_election_act_revisions_null_ballots_nonnegative')),
    sa.CheckConstraint('revision_number >= 1', name=op.f('ck_election_act_revisions_revision_number_positive')),
    sa.CheckConstraint('valid_ballots IS NULL OR valid_ballots >= 0', name=op.f('ck_election_act_revisions_valid_ballots_nonnegative')),
    sa.ForeignKeyConstraint(['act_id'], ['election_acts.id'], name=op.f('fk_election_act_revisions_act_id_election_acts'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['submitted_by_user_id'], ['users.id'], name=op.f('fk_election_act_revisions_submitted_by_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_election_act_revisions')),
    sa.UniqueConstraint('act_id', 'id', name='uq_election_act_revisions_act_id_id'),
    sa.UniqueConstraint('act_id', 'revision_number', name='uq_election_act_revisions_act_number')
    )
    op.create_index('ix_election_act_revisions_act_id', 'election_act_revisions', ['act_id'], unique=False)
    op.create_index('ix_election_act_revisions_status', 'election_act_revisions', ['status'], unique=False)
    op.create_index('uq_election_act_revisions_client_id', 'election_act_revisions', ['act_id', 'submitted_by_user_id', 'client_generated_id'], unique=True, postgresql_where=sa.text('client_generated_id IS NOT NULL'), sqlite_where=sa.text('client_generated_id IS NOT NULL'))
    # Referencia circular compuesta (§8 auditoría Fase 2): election_acts.
    # validated_revision_id, junto con la propia election_acts.id, debe
    # apuntar a una fila de election_act_revisions cuyo act_id sea
    # exactamente esta acta — nunca la revisión de otra. Se agrega aquí, ya
    # con ambas tablas (y el UNIQUE(act_id, id) de arriba) creadas; un
    # use_alter=True inline dentro de un script ya generado no emite la
    # ALTER TABLE (mismo hallazgo que con la referencia simple anterior).
    op.create_foreign_key(
        'fk_election_acts_validated_revision_id_election_act_revisions',
        'election_acts', 'election_act_revisions',
        ['id', 'validated_revision_id'], ['act_id', 'id'], ondelete='RESTRICT',
    )
    op.create_table('election_act_evidence',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('revision_id', sa.Uuid(), nullable=False),
    sa.Column('storage_key', sa.String(length=255), nullable=False),
    sa.Column('mime_type', sa.String(length=120), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=True),
    sa.Column('uploaded_by_user_id', sa.Uuid(), nullable=False),
    sa.Column('client_generated_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.ForeignKeyConstraint(['revision_id'], ['election_act_revisions.id'], name=op.f('fk_election_act_evidence_revision_id_election_act_revisions'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['users.id'], name=op.f('fk_election_act_evidence_uploaded_by_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_election_act_evidence'))
    )
    op.create_index('ix_election_act_evidence_revision_id', 'election_act_evidence', ['revision_id'], unique=False)
    op.create_index('uq_election_act_evidence_client_id', 'election_act_evidence', ['revision_id', 'uploaded_by_user_id', 'client_generated_id'], unique=True, postgresql_where=sa.text('client_generated_id IS NOT NULL'), sqlite_where=sa.text('client_generated_id IS NOT NULL'))
    op.create_index('uq_election_act_evidence_storage_key', 'election_act_evidence', ['storage_key'], unique=True)
    op.create_table('election_act_results',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('revision_id', sa.Uuid(), nullable=False),
    sa.Column('electoral_candidate_id', sa.Uuid(), nullable=False),
    sa.Column('votes', sa.Integer(), nullable=False),
    sa.CheckConstraint('votes >= 0', name=op.f('ck_election_act_results_votes_nonnegative')),
    sa.ForeignKeyConstraint(['electoral_candidate_id'], ['electoral_candidates.id'], name='fk_election_act_results_electoral_candidate_id', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['revision_id'], ['election_act_revisions.id'], name=op.f('fk_election_act_results_revision_id_election_act_revisions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_election_act_results')),
    sa.UniqueConstraint('revision_id', 'electoral_candidate_id', name='uq_election_act_results_revision_candidate')
    )
    op.create_index('ix_election_act_results_revision_id', 'election_act_results', ['revision_id'], unique=False)
    op.create_table('election_act_reviews',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('act_id', sa.Uuid(), nullable=False),
    sa.Column('revision_id', sa.Uuid(), nullable=False),
    sa.Column('reviewer_user_id', sa.Uuid(), nullable=False),
    sa.Column('review_source', sa.String(length=30), nullable=False),
    sa.Column('action', sa.String(length=20), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("action = 'VALIDATED' OR reason IS NOT NULL", name=op.f('ck_election_act_reviews_observed_requires_reason')),
    sa.CheckConstraint("action IN ('VALIDATED','OBSERVED')", name=op.f('ck_election_act_reviews_action')),
    sa.CheckConstraint("review_source IN ('CAMPAIGN_VALIDATOR','ADMIN_SUPPORT')", name=op.f('ck_election_act_reviews_review_source')),
    sa.ForeignKeyConstraint(['act_id'], ['election_acts.id'], name=op.f('fk_election_act_reviews_act_id_election_acts'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['reviewer_user_id'], ['users.id'], name=op.f('fk_election_act_reviews_reviewer_user_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['revision_id'], ['election_act_revisions.id'], name=op.f('fk_election_act_reviews_revision_id_election_act_revisions'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_election_act_reviews'))
    )
    op.create_index('ix_election_act_reviews_act_id', 'election_act_reviews', ['act_id'], unique=False)
    op.create_index('ix_election_act_reviews_revision_id', 'election_act_reviews', ['revision_id'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('ix_election_act_reviews_revision_id', table_name='election_act_reviews')
    op.drop_index('ix_election_act_reviews_act_id', table_name='election_act_reviews')
    op.drop_table('election_act_reviews')
    op.drop_index('ix_election_act_results_revision_id', table_name='election_act_results')
    op.drop_table('election_act_results')
    op.drop_index('uq_election_act_evidence_storage_key', table_name='election_act_evidence')
    op.drop_index('uq_election_act_evidence_client_id', table_name='election_act_evidence', postgresql_where=sa.text('client_generated_id IS NOT NULL'), sqlite_where=sa.text('client_generated_id IS NOT NULL'))
    op.drop_index('ix_election_act_evidence_revision_id', table_name='election_act_evidence')
    op.drop_table('election_act_evidence')
    op.drop_constraint('fk_election_acts_validated_revision_id_election_act_revisions', 'election_acts', type_='foreignkey')
    op.drop_index('uq_election_act_revisions_client_id', table_name='election_act_revisions', postgresql_where=sa.text('client_generated_id IS NOT NULL'), sqlite_where=sa.text('client_generated_id IS NOT NULL'))
    op.drop_index('ix_election_act_revisions_status', table_name='election_act_revisions')
    op.drop_index('ix_election_act_revisions_act_id', table_name='election_act_revisions')
    op.drop_table('election_act_revisions')
    op.drop_index('ix_election_acts_status', table_name='election_acts')
    op.drop_index('ix_election_acts_polling_place_id', table_name='election_acts')
    op.drop_index('ix_election_acts_operation_id', table_name='election_acts')
    op.drop_index('ix_election_acts_electoral_contest_id', table_name='election_acts')
    op.drop_index('ix_election_acts_electoral_board_id', table_name='election_acts')
    op.drop_table('election_acts')
    # ### end Alembic commands ###

