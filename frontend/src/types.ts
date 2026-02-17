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
