"""deal_shares table (external members' access to individual deals, RLS-enforced)

The new 'auditor' and 'external' roles need no schema change: roles are stored as text.

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

TENANT = "NULLIF(current_setting('app.current_org_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "deal_shares",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("property_id", "user_id", name="uq_deal_share"),
    )
    for col in ("org_id", "property_id", "user_id"):
        op.create_index(f"ix_deal_shares_{col}", "deal_shares", [col])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE deal_shares ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE deal_shares FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON deal_shares USING (org_id = {TENANT}) "
                   f"WITH CHECK (org_id = {TENANT})")


def downgrade() -> None:
    for col in ("org_id", "property_id", "user_id"):
        op.drop_index(f"ix_deal_shares_{col}", table_name="deal_shares")
    op.drop_table("deal_shares")
