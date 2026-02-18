import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    client_id: uuid.UUID


class OnboardRequest(BaseModel):
    email: EmailStr
    password: str
    broker_type: Literal["ibkr", "phillip"]
    broker_credentials: dict
    risk_parameters: dict = Field(default_factory=dict)
    subscription_tier: str = "basic"


class ModeUpdateRequest(BaseModel):
    mode: Literal["confirmation", "autonomous"]


class ParametersUpdateRequest(BaseModel):
    risk_parameters: dict


class ChatRequest(BaseModel):
    message: str


class ToolCallEntry(BaseModel):
    tool_name: str | None = None
    name: str | None = None
    tool_input: dict = Field(default_factory=dict)
    input: dict = Field(default_factory=dict)
    tool_use_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    status: str = "completed"
    duration_ms: float | None = None


class ToolResultEntry(BaseModel):
    tool_name: str | None = None
    name: str | None = None
    tool_use_id: str | None = None
    ok: bool = True
    success: bool | None = None
    result: dict | list | str | float | int | None = None
    output: dict | list | str | float | int | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: float | None = None


class ChatResponse(BaseModel):
    mode: str
    message: str
    executed: bool | None = None
    proposal_id: int | None = None
    proposal: dict | None = None
    execution: dict | None = None
    tool_trace_id: str | None = None
    planned_tools: list[dict | str] = Field(default_factory=list)
    tool_calls: list[ToolCallEntry] = Field(default_factory=list)
    tool_results: list[ToolResultEntry] = Field(default_factory=list)
    latency_ms: float | None = None


class ApproveRejectResponse(BaseModel):
    proposal_id: int
    status: str


class PositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    symbol: str
    instrument_type: str
    strike: float | None
    expiry: str | None
    qty: int
    delta: float
    gamma: float
    theta: float
    vega: float
    avg_price: float
    updated_at: datetime


class TradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    timestamp: datetime
    action: str
    symbol: str
    instrument: str
    qty: int
    fill_price: float | None
    order_id: str | None
    agent_reasoning: str
    mode: str
    status: str
    pnl: float


class ProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    timestamp: datetime
    trade_payload: dict
    agent_reasoning: str
    status: str
    resolved_at: datetime | None


class AgentStatusOut(BaseModel):
    client_id: uuid.UUID
    mode: str
    last_action: str | None
    healthy: bool
    net_greeks: dict[str, float]


class BrokerConnectRequest(BaseModel):
    broker_credentials: dict | None = None


class EmergencyHaltRequest(BaseModel):
    halted: bool
    reason: str = ""


class EmergencyHaltResponse(BaseModel):
    halted: bool
    reason: str
    updated_at: datetime
    updated_by: str


class ClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: EmailStr
    broker_type: str
    risk_params: dict
    mode: str
    tier: str
    is_active: bool
    created_at: datetime


class InstrumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    symbol: str
    asset_class: str
    exchange: str
    currency: str
    multiplier: float | None
    tick_size: float | None
    contract_rules: dict
    aliases: list
    is_active: bool
    created_at: datetime
    updated_at: datetime


class StrategyProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    strategy_id: str
    name: str
    description: str
    allowed_asset_classes: list
    allowed_symbols: list
    max_legs: int
    require_defined_risk: bool
    tier_allowlist: list
    entry_rules: dict
    exit_rules: dict
    risk_template: dict
    execution_template: dict
    is_active: bool
    created_at: datetime
    updated_at: datetime


class StrategyTemplateCreateRequest(BaseModel):
    name: str
    strategy_type: Literal["butterfly", "iron_fly", "broken_wing_butterfly"]
    underlying_symbol: str
    dte_min: int = Field(ge=0)
    dte_max: int = Field(ge=0)
    center_delta_target: float = Field(gt=0, lt=1)
    wing_width: float = Field(gt=0)
    max_risk_per_trade: float = Field(gt=0)
    sizing_method: Literal["fixed_contracts", "risk_based"]
    max_contracts: int = Field(gt=0)
    hedge_enabled: bool = False
    auto_execute: bool = False


class StrategyTemplateUpdateRequest(BaseModel):
    name: str
    strategy_type: Literal["butterfly", "iron_fly", "broken_wing_butterfly"]
    underlying_symbol: str
    dte_min: int = Field(ge=0)
    dte_max: int = Field(ge=0)
    center_delta_target: float = Field(gt=0, lt=1)
    wing_width: float = Field(gt=0)
    max_risk_per_trade: float = Field(gt=0)
    sizing_method: Literal["fixed_contracts", "risk_based"]
    max_contracts: int = Field(gt=0)
    hedge_enabled: bool = False
    auto_execute: bool = False


class StrategyTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    strategy_type: str
    underlying_symbol: str
    dte_min: int
    dte_max: int
    center_delta_target: float
    wing_width: float
    max_risk_per_trade: float
    sizing_method: str
    max_contracts: int
    hedge_enabled: bool
    auto_execute: bool
    created_at: datetime
    updated_at: datetime


class StrategyLegOut(BaseModel):
    action: Literal["BUY", "SELL"]
    ratio: int
    symbol: str
    instrument: str
    expiry: str
    strike: float
    right: Literal["C", "P"]
    exchange: str = "CME"
    trading_class: str | None = None
    multiplier: str | None = None
    delta: float | None = None
    mid_price: float | None = None


class StrategyPreviewOut(BaseModel):
    template_id: int
    strategy_type: str
    expiry: str
    dte: int
    center_strike: float
    estimated_net_premium: float
    estimated_max_risk: float
    estimated_net_delta: float
    contracts: int
    greeks: dict[str, float]
    pnl_curve: list[dict[str, float]]
    legs: list[StrategyLegOut]


class StrategyExecutionOut(BaseModel):
    id: int
    template_id: int
    order_id: str | None
    status: str
    avg_fill_price: float | None
    execution_timestamp: datetime
    payload: dict
