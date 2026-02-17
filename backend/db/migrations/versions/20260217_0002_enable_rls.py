"""enable postgres row level security for tenant tables

Revision ID: 20260217_0002
Revises: 20260217_0001
Create Date: 2026-02-17
"""

from alembic import op


revision = "20260217_0002"
down_revision = "20260217_0001"
branch_labels = None
depends_on = None


TENANT_TABLES = ["positions", "trades", "proposals", "audit_log", "agent_memory"]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    condition = (
        "(current_setting('app.is_admin', true) = 'true') OR "
        "(nullif(current_setting('app.current_client_id', true), '')::uuid = client_id)"
    )

    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_select ON {table} FOR SELECT USING ({condition})"
        )
        op.execute(
            f"CREATE POLICY {table}_tenant_insert ON {table} FOR INSERT WITH CHECK ({condition})"
        )
        op.execute(
            f"CREATE POLICY {table}_tenant_update ON {table} FOR UPDATE USING ({condition}) WITH CHECK ({condition})"
        )
        op.execute(
            f"CREATE POLICY {table}_tenant_delete ON {table} FOR DELETE USING ({condition})"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_delete ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_update ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_insert ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_select ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

