"""financing_structures.mezzanine: optional subordinate loan for a structure

Revision ID: 0011
Revises: 0010
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("financing_structures",
                  sa.Column("mezzanine", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()),
                                                                "postgresql"), nullable=True))


def downgrade() -> None:
    op.drop_column("financing_structures", "mezzanine")
