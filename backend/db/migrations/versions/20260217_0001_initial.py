"""initial schema

Revision ID: 20260217_0001
Revises:
Create Date: 2026-02-17
"""

from alembic import op
import sqlalchemy as sa


revision = "20260217_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("broker_type", sa.String(length=20), nullable=False),
        sa.Column("encrypted_creds", sa.Text(), nullable=False),
        sa.Column("risk_params", sa.JSON(), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("tier", sa.String(length=30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_clients_email", "clients", ["email"])

    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("instrument_type", sa.String(length=30), nullable=False),
        sa.Column("strike", sa.Float(), nullable=True),
        sa.Column("expiry", sa.String(length=20), nullable=True),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("delta", sa.Float(), nullable=False),
        sa.Column("gamma", sa.Float(), nullable=False),
        sa.Column("theta", sa.Float(), nullable=False),
        sa.Column("vega", sa.Float(), nullable=False),
        sa.Column("avg_price", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_positions_client_id", "positions", ["client_id"])
    op.create_index("ix_positions_symbol", "positions", ["symbol"])

    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.String(length=36), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("instrument", sa.String(length=50), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("fill_price", sa.Float(), nullable=True),
        sa.Column("order_id", sa.String(length=128), nullable=True),
        sa.Column("agent_reasoning", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("pnl", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trades_client_id", "trades", ["client_id"])
    op.create_index("ix_trades_symbol", "trades", ["symbol"])
    op.create_index("ix_trades_timestamp", "trades", ["timestamp"])

    op.create_table(
        "proposals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.String(length=36), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trade_payload", sa.JSON(), nullable=False),
        sa.Column("agent_reasoning", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_proposals_client_id", "proposals", ["client_id"])
    op.create_index("ix_proposals_timestamp", "proposals", ["timestamp"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.String(length=36), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("risk_rule_triggered", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_client_id", "audit_log", ["client_id"])
    op.create_index("ix_audit_log_event_type", "audit_log", ["event_type"])
    op.create_index("ix_audit_log_timestamp", "audit_log", ["timestamp"])

    op.create_table(
        "agent_memory",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.String(length=36), nullable=False),
        sa.Column("message_role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_memory_client_id", "agent_memory", ["client_id"])
    op.create_index("ix_agent_memory_timestamp", "agent_memory", ["timestamp"])


def downgrade() -> None:
    op.drop_index("ix_agent_memory_timestamp", table_name="agent_memory")
    op.drop_index("ix_agent_memory_client_id", table_name="agent_memory")
    op.drop_table("agent_memory")

    op.drop_index("ix_audit_log_timestamp", table_name="audit_log")
    op.drop_index("ix_audit_log_event_type", table_name="audit_log")
    op.drop_index("ix_audit_log_client_id", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("ix_proposals_timestamp", table_name="proposals")
    op.drop_index("ix_proposals_client_id", table_name="proposals")
    op.drop_table("proposals")

    op.drop_index("ix_trades_timestamp", table_name="trades")
    op.drop_index("ix_trades_symbol", table_name="trades")
    op.drop_index("ix_trades_client_id", table_name="trades")
    op.drop_table("trades")

    op.drop_index("ix_positions_symbol", table_name="positions")
    op.drop_index("ix_positions_client_id", table_name="positions")
    op.drop_table("positions")

    op.drop_index("ix_clients_email", table_name="clients")
    op.drop_table("clients")
