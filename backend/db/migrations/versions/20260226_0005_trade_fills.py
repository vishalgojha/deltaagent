"""add trade fills table for execution lifecycle analytics

Revision ID: 20260226_0005
Revises: 20260218_0004
Create Date: 2026-02-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20260226_0005"
down_revision = "20260218_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trade_fills",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.String(length=36), nullable=False),
        sa.Column("trade_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.String(length=128), nullable=True),
        sa.Column("broker_fill_id", sa.String(length=128), nullable=True),
        sa.Column("ingest_idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("fill_price", sa.Float(), nullable=False),
        sa.Column("expected_price", sa.Float(), nullable=True),
        sa.Column("slippage_bps", sa.Float(), nullable=True),
        sa.Column("fees", sa.Float(), nullable=False),
        sa.Column("realized_pnl", sa.Float(), nullable=True),
        sa.Column("fill_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.ForeignKeyConstraint(["trade_id"], ["trades.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trade_fills_client_id", "trade_fills", ["client_id"])
    op.create_index("ix_trade_fills_trade_id", "trade_fills", ["trade_id"])
    op.create_index("ix_trade_fills_order_id", "trade_fills", ["order_id"])
    op.create_index("ix_trade_fills_broker_fill_id", "trade_fills", ["broker_fill_id"])
    op.create_index("ix_trade_fills_ingest_idempotency_key", "trade_fills", ["ingest_idempotency_key"])
    op.create_index("ix_trade_fills_status", "trade_fills", ["status"])
    op.create_index("ix_trade_fills_fill_timestamp", "trade_fills", ["fill_timestamp"])
    op.create_index("ix_trade_fills_created_at", "trade_fills", ["created_at"])
    op.create_index(
        "uq_trade_fills_client_trade_broker_fill",
        "trade_fills",
        ["client_id", "trade_id", "broker_fill_id"],
        unique=True,
    )
    op.create_index(
        "uq_trade_fills_client_trade_idempotency",
        "trade_fills",
        ["client_id", "trade_id", "ingest_idempotency_key"],
        unique=True,
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        condition = (
            "(current_setting('app.is_admin', true) = 'true') OR "
            "(nullif(current_setting('app.current_client_id', true), '')::uuid = client_id)"
        )
        op.execute("ALTER TABLE trade_fills ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE trade_fills FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY trade_fills_tenant_select ON trade_fills FOR SELECT USING ({condition})"
        )
        op.execute(
            f"CREATE POLICY trade_fills_tenant_insert ON trade_fills FOR INSERT WITH CHECK ({condition})"
        )
        op.execute(
            f"CREATE POLICY trade_fills_tenant_update ON trade_fills FOR UPDATE USING ({condition}) WITH CHECK ({condition})"
        )
        op.execute(
            f"CREATE POLICY trade_fills_tenant_delete ON trade_fills FOR DELETE USING ({condition})"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS trade_fills_tenant_delete ON trade_fills")
        op.execute("DROP POLICY IF EXISTS trade_fills_tenant_update ON trade_fills")
        op.execute("DROP POLICY IF EXISTS trade_fills_tenant_insert ON trade_fills")
        op.execute("DROP POLICY IF EXISTS trade_fills_tenant_select ON trade_fills")
        op.execute("ALTER TABLE trade_fills NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE trade_fills DISABLE ROW LEVEL SECURITY")

    op.drop_index("uq_trade_fills_client_trade_idempotency", table_name="trade_fills")
    op.drop_index("uq_trade_fills_client_trade_broker_fill", table_name="trade_fills")
    op.drop_index("ix_trade_fills_created_at", table_name="trade_fills")
    op.drop_index("ix_trade_fills_fill_timestamp", table_name="trade_fills")
    op.drop_index("ix_trade_fills_status", table_name="trade_fills")
    op.drop_index("ix_trade_fills_ingest_idempotency_key", table_name="trade_fills")
    op.drop_index("ix_trade_fills_broker_fill_id", table_name="trade_fills")
    op.drop_index("ix_trade_fills_order_id", table_name="trade_fills")
    op.drop_index("ix_trade_fills_trade_id", table_name="trade_fills")
    op.drop_index("ix_trade_fills_client_id", table_name="trade_fills")
    op.drop_table("trade_fills")
