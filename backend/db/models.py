import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, CHAR, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class GUID(TypeDecorator):
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PGUUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(value)


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    broker_type: Mapped[str] = mapped_column(String(20))
    encrypted_creds: Mapped[str] = mapped_column(Text)
    risk_params: Mapped[dict] = mapped_column(JSON, default=dict)
    mode: Mapped[str] = mapped_column(String(20), default="confirmation")
    tier: Mapped[str] = mapped_column(String(30), default="basic")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("clients.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    instrument_type: Mapped[str] = mapped_column(String(30))
    strike: Mapped[float | None] = mapped_column(Float, nullable=True)
    expiry: Mapped[str | None] = mapped_column(String(20), nullable=True)
    qty: Mapped[int] = mapped_column(Integer)
    delta: Mapped[float] = mapped_column(Float, default=0.0)
    gamma: Mapped[float] = mapped_column(Float, default=0.0)
    theta: Mapped[float] = mapped_column(Float, default=0.0)
    vega: Mapped[float] = mapped_column(Float, default=0.0)
    avg_price: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("clients.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    action: Mapped[str] = mapped_column(String(10))
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    instrument: Mapped[str] = mapped_column(String(50))
    qty: Mapped[int] = mapped_column(Integer)
    fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    agent_reasoning: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="submitted")
    pnl: Mapped[float] = mapped_column(Float, default=0.0)


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("clients.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    trade_payload: Mapped[dict] = mapped_column(JSON)
    agent_reasoning: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("clients.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_rule_triggered: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AgentMemory(Base):
    __tablename__ = "agent_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("clients.id"), index=True)
    message_role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class StrategyTemplate(Base):
    __tablename__ = "strategy_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("clients.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    strategy_type: Mapped[str] = mapped_column(String(40), index=True)
    underlying_symbol: Mapped[str] = mapped_column(String(20), index=True)
    dte_min: Mapped[int] = mapped_column(Integer)
    dte_max: Mapped[int] = mapped_column(Integer)
    center_delta_target: Mapped[float] = mapped_column(Float)
    wing_width: Mapped[float] = mapped_column(Float)
    max_risk_per_trade: Mapped[float] = mapped_column(Float)
    sizing_method: Mapped[str] = mapped_column(String(40))
    max_contracts: Mapped[int] = mapped_column(Integer)
    hedge_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_execute: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class StrategyExecution(Base):
    __tablename__ = "strategy_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("clients.id"), index=True)
    template_id: Mapped[int] = mapped_column(Integer, ForeignKey("strategy_templates.id"), index=True)
    order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="submitted", index=True)
    avg_fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    execution_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    asset_class: Mapped[str] = mapped_column(String(24), index=True)
    exchange: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(12))
    multiplier: Mapped[float | None] = mapped_column(Float, nullable=True)
    tick_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    contract_rules: Mapped[dict] = mapped_column(JSON, default=dict)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class StrategyProfile(Base):
    __tablename__ = "strategy_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    allowed_asset_classes: Mapped[list] = mapped_column(JSON, default=list)
    allowed_symbols: Mapped[list] = mapped_column(JSON, default=list)
    max_legs: Mapped[int] = mapped_column(Integer, default=4)
    require_defined_risk: Mapped[bool] = mapped_column(Boolean, default=True)
    tier_allowlist: Mapped[list] = mapped_column(JSON, default=list)
    entry_rules: Mapped[dict] = mapped_column(JSON, default=dict)
    exit_rules: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_template: Mapped[dict] = mapped_column(JSON, default=dict)
    execution_template: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
