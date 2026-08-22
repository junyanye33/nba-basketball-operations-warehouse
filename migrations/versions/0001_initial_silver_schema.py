"""Initial silver schema: dims, staging facts, quarantine, run audit.

Revision ID: 0001
Revises:
Create Date: 2026-08-22
"""
from alembic import op

from nba_warehouse.silver.schema import metadata

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata.create_all(op.get_bind())


def downgrade() -> None:
    metadata.drop_all(op.get_bind())
