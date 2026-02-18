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


class ChatToolCall(BaseModel):
    tool_use_id: str
    name: str
    input: dict = Field(default_factory=dict)
    started_at: datetime
    completed_at: datetime
    duration_ms: int


class ChatToolResult(BaseModel):
    tool_use_id: str
    name: str
    output: dict = Field(default_factory=dict)
    success: bool
    error: str | None = None
    started_at: datetime
    completed_at: datetime
    duration_ms: int


class ChatResponse(BaseModel):
    mode: str
    message: str
    executed: bool | None = None
    proposal_id: int | None = None
    proposal: dict | None = None
    execution: dict | None = None
    tool_trace_id: str
    planned_tools: list[dict] = Field(default_factory=list)
    tool_calls: list[ChatToolCall] = Field(default_factory=list)
    tool_results: list[ChatToolResult] = Field(default_factory=list)


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
