"""add strategy template and execution tables

Revision ID: 20260218_0004
Revises: 20260218_0003
Create Date: 2026-02-18
"""

from alembic import op
import sqlalchemy as sa


revision = "20260218_0004"
down_revision = "20260218_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("strategy_type", sa.String(length=40), nullable=False),
        sa.Column("underlying_symbol", sa.String(length=20), nullable=False),
        sa.Column("dte_min", sa.Integer(), nullable=False),
        sa.Column("dte_max", sa.Integer(), nullable=False),
        sa.Column("center_delta_target", sa.Float(), nullable=False),
        sa.Column("wing_width", sa.Float(), nullable=False),
        sa.Column("max_risk_per_trade", sa.Float(), nullable=False),
        sa.Column("sizing_method", sa.String(length=40), nullable=False),
        sa.Column("max_contracts", sa.Integer(), nullable=False),
        sa.Column("hedge_enabled", sa.Boolean(), nullable=False),
        sa.Column("auto_execute", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_strategy_templates_client_id", "strategy_templates", ["client_id"])
    op.create_index("ix_strategy_templates_name", "strategy_templates", ["name"])
    op.create_index("ix_strategy_templates_strategy_type", "strategy_templates", ["strategy_type"])
    op.create_index("ix_strategy_templates_underlying_symbol", "strategy_templates", ["underlying_symbol"])

    op.create_table(
        "strategy_executions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.String(length=36), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("avg_fill_price", sa.Float(), nullable=True),
        sa.Column("execution_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.ForeignKeyConstraint(["template_id"], ["strategy_templates.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_strategy_executions_client_id", "strategy_executions", ["client_id"])
    op.create_index("ix_strategy_executions_template_id", "strategy_executions", ["template_id"])
    op.create_index("ix_strategy_executions_status", "strategy_executions", ["status"])
    op.create_index("ix_strategy_executions_execution_timestamp", "strategy_executions", ["execution_timestamp"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        condition = (
            "(current_setting('app.is_admin', true) = 'true') OR "
            "(nullif(current_setting('app.current_client_id', true), '')::uuid = client_id)"
        )
        for table in ("strategy_templates", "strategy_executions"):
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
    if bind.dialect.name == "postgresql":
        for table in ("strategy_executions", "strategy_templates"):
            op.execute(f"DROP POLICY IF EXISTS {table}_tenant_delete ON {table}")
            op.execute(f"DROP POLICY IF EXISTS {table}_tenant_update ON {table}")
            op.execute(f"DROP POLICY IF EXISTS {table}_tenant_insert ON {table}")
            op.execute(f"DROP POLICY IF EXISTS {table}_tenant_select ON {table}")
            op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_strategy_executions_execution_timestamp", table_name="strategy_executions")
    op.drop_index("ix_strategy_executions_status", table_name="strategy_executions")
    op.drop_index("ix_strategy_executions_template_id", table_name="strategy_executions")
    op.drop_index("ix_strategy_executions_client_id", table_name="strategy_executions")
    op.drop_table("strategy_executions")

    op.drop_index("ix_strategy_templates_underlying_symbol", table_name="strategy_templates")
    op.drop_index("ix_strategy_templates_strategy_type", table_name="strategy_templates")
    op.drop_index("ix_strategy_templates_name", table_name="strategy_templates")
    op.drop_index("ix_strategy_templates_client_id", table_name="strategy_templates")
    op.drop_table("strategy_templates")
