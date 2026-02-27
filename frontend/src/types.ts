export type LoginResponse = {
  access_token: string;
  token_type: string;
  client_id: string;
};

export type AgentStatus = {
  client_id: string;
  mode: "confirmation" | "autonomous";
  last_action: string | null;
  healthy: boolean;
  net_greeks: Record<string, number>;
};

export type AgentReadiness = {
  client_id: string;
  ready: boolean;
  connected: boolean;
  market_data_ok: boolean;
  mode: "confirmation" | "autonomous" | string;
  risk_blocked: boolean;
  last_error: string | null;
  updated_at: string;
};

export type BrokerPreflightCheck = {
  key: string;
  title: string;
  status: "pass" | "warn" | "fail";
  detail: string;
};

export type BrokerPreflight = {
  ok: boolean;
  broker: "ibkr" | "phillip";
  checks: BrokerPreflightCheck[];
  blocking_issues: string[];
  warnings: string[];
  fix_hints: string[];
  checked_at: string;
};

export type EmergencyHaltStatus = {
  halted: boolean;
  reason: string;
  updated_at: string;
  updated_by: string;
};

export type AdminSessionLogin = {
  access_token: string;
  token_type: string;
  expires_in_seconds: number;
  actor: string;
};

export type ChatToolCall = {
  tool_use_id?: string;
  name?: string;
  input?: Record<string, unknown>;
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
};

export type ChatToolResult = {
  tool_use_id?: string;
  name?: string;
  output?: Record<string, unknown>;
  success?: boolean;
  error?: string | null;
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
};

export type ChatResponse = {
  mode: string;
  message: string;
  executed?: boolean;
  proposal_id?: number;
  proposal?: Record<string, unknown>;
  execution?: Record<string, unknown>;
  tool_trace_id?: string;
  planned_tools?: Array<Record<string, unknown>>;
  tool_calls?: ChatToolCall[];
  tool_results?: ChatToolResult[];
};

export type Position = {
  id: number;
  symbol: string;
  instrument_type: string;
  strike: number | null;
  expiry: string | null;
  qty: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  avg_price: number;
  updated_at: string;
};

export type Trade = {
  id: number;
  timestamp: string;
  action: string;
  symbol: string;
  instrument: string;
  qty: number;
  fill_price: number | null;
  order_id: string | null;
  agent_reasoning: string;
  mode: string;
  status: string;
  pnl: number;
};

export type TradeFill = {
  id: number;
  trade_id: number;
  order_id: string | null;
  broker_fill_id: string | null;
  ingest_idempotency_key: string | null;
  status: string;
  qty: number;
  fill_price: number;
  expected_price: number | null;
  slippage_bps: number | null;
  fees: number;
  realized_pnl: number | null;
  fill_timestamp: string;
  raw_payload: Record<string, unknown>;
  created_at: string;
};

export type ExecutionQuality = {
  client_id: string;
  window_start: string | null;
  window_end: string | null;
  trades_total: number;
  trades_with_fills: number;
  fill_events: number;
  backfilled_trades: number;
  backfilled_fill_events: number;
  avg_slippage_bps: number | null;
  median_slippage_bps: number | null;
  avg_first_fill_latency_ms: number | null;
  generated_at: string;
};

export type ExecutionIncidentNote = {
  id: number;
  client_id: string;
  alert_id: string;
  severity: "warning" | "critical";
  label: string;
  note: string;
  context: Record<string, unknown>;
  created_at: string;
};

export type Proposal = {
  id: number;
  timestamp: string;
  trade_payload: Record<string, unknown>;
  agent_reasoning: string;
  status: string;
  resolved_at: string | null;
};

export type ClientOut = {
  id: string;
  email: string;
  broker_type: "ibkr" | "phillip";
  risk_params: Record<string, unknown>;
  mode: "confirmation" | "autonomous";
  tier: string;
  is_active: boolean;
  created_at: string;
};

export type StrategyTemplate = {
  id: number;
  name: string;
  strategy_type: "butterfly" | "iron_fly" | "broken_wing_butterfly";
  underlying_symbol: string;
  dte_min: number;
  dte_max: number;
  center_delta_target: number;
  wing_width: number;
  max_risk_per_trade: number;
  sizing_method: "fixed_contracts" | "risk_based";
  max_contracts: number;
  hedge_enabled: boolean;
  auto_execute: boolean;
  created_at: string;
  updated_at: string;
};

export type StrategyLeg = {
  action: "BUY" | "SELL";
  ratio: number;
  symbol: string;
  instrument: string;
  expiry: string;
  strike: number;
  right: "C" | "P";
  exchange: string;
  trading_class: string | null;
  multiplier: string | null;
  delta: number | null;
  mid_price: number | null;
};

export type StrategyPreview = {
  template_id: number;
  strategy_type: string;
  expiry: string;
  dte: number;
  center_strike: number;
  estimated_net_premium: number;
  estimated_max_risk: number;
  estimated_net_delta: number;
  contracts: number;
  greeks: Record<string, number>;
  pnl_curve: Array<{ underlying: number; pnl: number }>;
  legs: StrategyLeg[];
};

export type StrategyExecution = {
  id: number;
  template_id: number;
  order_id: string | null;
  status: string;
  avg_fill_price: number | null;
  execution_timestamp: string;
  payload: Record<string, unknown>;
};
