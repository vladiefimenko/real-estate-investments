"""assumption_libraries table (tenant-scoped, with row-level security)

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TENANT = "NULLIF(current_setting('app.current_org_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "assumption_libraries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("property_type", sa.String(length=40), nullable=True),
        sa.Column("values_json", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
                  nullable=False),
        sa.Column("is_shared", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assumption_libraries_org_id", "assumption_libraries", ["org_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE assumption_libraries ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE assumption_libraries FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON assumption_libraries USING (org_id = {TENANT}) "
                   f"WITH CHECK (org_id = {TENANT})")


def downgrade() -> None:
    op.drop_index("ix_assumption_libraries_org_id", table_name="assumption_libraries")
    op.drop_table("assumption_libraries")
