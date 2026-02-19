"""add reference knowledge base tables

Revision ID: 20260218_0003
Revises: 20260217_0002
Create Date: 2026-02-18
"""

from alembic import op
import sqlalchemy as sa


revision = "20260218_0003"
down_revision = "20260217_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instruments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("asset_class", sa.String(length=24), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=12), nullable=False),
        sa.Column("multiplier", sa.Float(), nullable=True),
        sa.Column("tick_size", sa.Float(), nullable=True),
        sa.Column("contract_rules", sa.JSON(), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "asset_class", "exchange", name="uq_instruments_identity"),
    )
    op.create_index("ix_instruments_symbol", "instruments", ["symbol"])
    op.create_index("ix_instruments_asset_class", "instruments", ["asset_class"])
    op.create_index("ix_instruments_is_active", "instruments", ["is_active"])

    op.create_table(
        "strategy_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("allowed_asset_classes", sa.JSON(), nullable=False),
        sa.Column("allowed_symbols", sa.JSON(), nullable=False),
        sa.Column("max_legs", sa.Integer(), nullable=False),
        sa.Column("require_defined_risk", sa.Boolean(), nullable=False),
        sa.Column("tier_allowlist", sa.JSON(), nullable=False),
        sa.Column("entry_rules", sa.JSON(), nullable=False),
        sa.Column("exit_rules", sa.JSON(), nullable=False),
        sa.Column("risk_template", sa.JSON(), nullable=False),
        sa.Column("execution_template", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("strategy_id"),
    )
    op.create_index("ix_strategy_profiles_strategy_id", "strategy_profiles", ["strategy_id"])
    op.create_index("ix_strategy_profiles_is_active", "strategy_profiles", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_strategy_profiles_is_active", table_name="strategy_profiles")
    op.drop_index("ix_strategy_profiles_strategy_id", table_name="strategy_profiles")
    op.drop_table("strategy_profiles")

    op.drop_index("ix_instruments_is_active", table_name="instruments")
    op.drop_index("ix_instruments_asset_class", table_name="instruments")
    op.drop_index("ix_instruments_symbol", table_name="instruments")
    op.drop_table("instruments")
