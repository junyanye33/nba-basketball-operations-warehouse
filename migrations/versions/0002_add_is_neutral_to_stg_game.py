"""Add stg_game.is_neutral for neutral-site games.

Discovered via reconciliation failure on 2026-01-15: the NBA Europe game
(MEM/ORL, game 0022500578) marks both teams as away in the source, so game
derivation found no home row. Neutral-site games now get deterministic
home/away slot assignment and an is_neutral flag.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-22
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stg_game",
        sa.Column("is_neutral", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("stg_game", "is_neutral")
