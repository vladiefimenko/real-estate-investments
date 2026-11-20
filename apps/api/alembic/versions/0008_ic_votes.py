"""ic_votes table (Investment Committee votes per deal and round, RLS-enforced)

Stage requirements and IC rounds/decisions live in existing JSON columns
(organizations.settings and properties.attributes).

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

TENANT = "NULLIF(current_setting('app.current_org_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "ic_votes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("vote", sa.String(length=20), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("property_id", "round", "user_id", name="uq_ic_vote"),
    )
    op.create_index("ix_ic_votes_org_id", "ic_votes", ["org_id"])
    op.create_index("ix_ic_votes_property_id", "ic_votes", ["property_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE ic_votes ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE ic_votes FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON ic_votes USING (org_id = {TENANT}) WITH CHECK (org_id = {TENANT})")


def downgrade() -> None:
    op.drop_index("ix_ic_votes_property_id", table_name="ic_votes")
    op.drop_index("ix_ic_votes_org_id", table_name="ic_votes")
    op.drop_table("ic_votes")
