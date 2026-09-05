"""Normalize official websites without an automatic adapter as manual sources.

Revision ID: 20260816_0002
Revises: 20260816_0001
"""
from alembic import op
import sqlalchemy as sa

revision = "20260816_0002"
down_revision = "20260816_0001"
branch_labels = None
depends_on = None

def upgrade():
    sources=sa.table("public_sources",sa.column("source_type",sa.String),sa.column("retrieval_method",sa.String),sa.column("feed_url",sa.String),sa.column("api_url",sa.String),sa.column("refresh_interval_minutes",sa.Integer),sa.column("consecutive_failures",sa.Integer))
    op.execute(sources.update().where(sources.c.source_type=="OFFICIAL_WEBSITE",sources.c.feed_url.is_(None),sources.c.api_url.is_(None)).values(retrieval_method="MANUAL",refresh_interval_minutes=None,consecutive_failures=0))

def downgrade():
    # The previous invalid retrieval method cannot be inferred safely.
    pass
