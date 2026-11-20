"""organization_members.preferences: personal per-workspace settings (AI analyst instructions)

Revision ID: 0010
Revises: 0009
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organization_members",
                  sa.Column("preferences", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()),
                                                                  "postgresql"), nullable=True))


def downgrade() -> None:
    op.drop_column("organization_members", "preferences")
