"""underwriting_results.label: named versions of a scenario's underwriting

Revision ID: 0013
Revises: 0012
"""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("underwriting_results", sa.Column("label", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("underwriting_results", "label")
