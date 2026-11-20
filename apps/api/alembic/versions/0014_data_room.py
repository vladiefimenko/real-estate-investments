"""Data room: documents.data_room, and deal share expiry and download permission

Revision ID: 0014
Revises: 0013
"""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("data_room", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("deal_shares", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("deal_shares", sa.Column("can_download", sa.Boolean(), server_default=sa.true(), nullable=False))


def downgrade() -> None:
    op.drop_column("deal_shares", "can_download")
    op.drop_column("deal_shares", "expires_at")
    op.drop_column("documents", "data_room")
