"""saved_views table: per-user dashboard layouts (tenant-scoped, with row-level security)

Revision ID: 0009
Revises: 0008
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

TENANT = "NULLIF(current_setting('app.current_org_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "saved_views",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("page", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("config", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
                  nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_saved_views_org_id", "saved_views", ["org_id"])
    op.create_index("ix_saved_views_user_id", "saved_views", ["user_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE saved_views ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE saved_views FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON saved_views USING (org_id = {TENANT}) "
                   f"WITH CHECK (org_id = {TENANT})")


def downgrade() -> None:
    op.drop_index("ix_saved_views_user_id", table_name="saved_views")
    op.drop_index("ix_saved_views_org_id", table_name="saved_views")
    op.drop_table("saved_views")
