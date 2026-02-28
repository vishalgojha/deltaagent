import { api } from "./client";
import type {
  AgentStatus,
  AdminSessionLogin,
  BrokerPreflight,
  AgentReadiness,
  ChatResponse,
  ClientOut,
  EmergencyHaltStatus,
  ExecutionIncidentNote,
  ExecutionQuality,
  LlmCredentialsStatus,
  LoginResponse,
  Position,
  Proposal,
  StrategyExecution,
  StrategyPreview,
  StrategyTemplate,
  Trade,
  TradeFill
} from "../types";
import type { RiskParameters } from "../features/riskControls";

export function login(email: string, password: string) {
  return api<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password })
  });
}

export function getHealth() {
  return api<{ status: string }>("/health");
}

export function onboardClient(payload: {
  email: string;
  password: string;
  broker_type: "ibkr" | "phillip";
  broker_credentials: Record<string, unknown>;
  risk_parameters: Record<string, unknown>;
  subscription_tier: string;
}) {
  return api<ClientOut>("/clients/onboard", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function connectBroker(clientId: string, brokerCredentials?: Record<string, unknown>) {
  return api<Record<string, unknown>>(`/clients/${clientId}/connect-broker`, {
    method: "POST",
    body: JSON.stringify({
      broker_credentials: brokerCredentials ?? null
    })
  });
}

export function brokerPreflight(clientId: string, brokerCredentials?: Record<string, unknown>) {
  return api<BrokerPreflight>(`/clients/${clientId}/broker/preflight`, {
    method: "POST",
    body: JSON.stringify({
      broker_credentials: brokerCredentials ?? null
    })
  });
}

export function getStatus(clientId: string) {
  return api<AgentStatus>(`/clients/${clientId}/agent/status`);
}

export function getReadiness(clientId: string) {
  return api<AgentReadiness>(`/clients/${clientId}/agent/readiness`);
}

export function getEmergencyHaltStatus(clientId: string) {
  return api<EmergencyHaltStatus>(`/clients/${clientId}/agent/emergency-halt`);
}

export function adminSessionLogin(adminKey: string) {
  return api<AdminSessionLogin>("/admin/session/login", {
    method: "POST",
    body: JSON.stringify({ admin_key: adminKey })
  });
}

export function getAdminEmergencyHalt(adminToken: string) {
  return api<EmergencyHaltStatus>("/admin/emergency-halt", {
    headers: { Authorization: `Bearer ${adminToken}` }
  });
}

export function setAdminEmergencyHalt(adminToken: string, halted: boolean, reason: string) {
  return api<EmergencyHaltStatus>("/admin/emergency-halt", {
    method: "POST",
    headers: { Authorization: `Bearer ${adminToken}` },
    body: JSON.stringify({ halted, reason })
  });
}

export function getPositions(clientId: string) {
  return api<Position[]>(`/clients/${clientId}/positions`);
}

export function getTrades(clientId: string) {
  return api<Trade[]>(`/clients/${clientId}/trades`);
}

export function getTradeFills(clientId: string, tradeId: number) {
  return api<TradeFill[]>(`/clients/${clientId}/trades/${tradeId}/fills`);
}

export function ingestTradeFill(
  clientId: string,
  tradeId: number,
  payload: {
    status: string;
    qty: number;
    fill_price: number;
    expected_price?: number;
    fees?: number;
    realized_pnl?: number;
    fill_timestamp?: string;
    broker_fill_id?: string;
    idempotency_key?: string;
    raw_payload?: Record<string, unknown>;
  },
  options?: { idempotencyKey?: string }
) {
  const headers: Record<string, string> = {};
  if (options?.idempotencyKey) {
    headers["Idempotency-Key"] = options.idempotencyKey;
  }
  return api<TradeFill>(`/clients/${clientId}/trades/${tradeId}/fills`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload)
  });
}

export function getExecutionQuality(
  clientId: string,
  from?: string,
  to?: string,
  options?: { backfillMissing?: boolean }
) {
  const params = new URLSearchParams();
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  if (options?.backfillMissing === false) {
    params.set("backfill_missing", "false");
  }
  const qs = params.toString();
  const path = qs
    ? `/clients/${clientId}/metrics/execution-quality?${qs}`
    : `/clients/${clientId}/metrics/execution-quality`;
  return api<ExecutionQuality>(path);
}

export function getExecutionIncidents(clientId: string, limit = 20) {
  return api<ExecutionIncidentNote[]>(`/clients/${clientId}/metrics/incidents?limit=${limit}`);
}

export function createExecutionIncidentNote(
  clientId: string,
  payload: {
    alert_id: string;
    severity: "warning" | "critical";
    label: string;
    note: string;
    context?: Record<string, unknown>;
  }
) {
  return api<ExecutionIncidentNote>(`/clients/${clientId}/metrics/incidents`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getProposals(clientId: string) {
  return api<Proposal[]>(`/clients/${clientId}/agent/proposals`);
}

export function sendChat(clientId: string, message: string) {
  return api<ChatResponse>(`/clients/${clientId}/agent/chat`, {
    method: "POST",
    body: JSON.stringify({ message })
  });
}

export function setMode(clientId: string, mode: "confirmation" | "autonomous") {
  return api<Record<string, unknown>>(`/clients/${clientId}/agent/mode`, {
    method: "POST",
    body: JSON.stringify({ mode })
  });
}

export function getLlmCredentialsStatus(clientId: string) {
  return api<LlmCredentialsStatus>(`/clients/${clientId}/agent/llm-credentials`);
}

export function updateLlmCredentials(
  clientId: string,
  payload: {
    openai_api_key?: string;
    anthropic_api_key?: string;
    openrouter_api_key?: string;
    xai_api_key?: string;
  }
) {
  return api<LlmCredentialsStatus>(`/clients/${clientId}/agent/llm-credentials`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getRiskParameters(clientId: string) {
  return api<{ client_id: string; risk_parameters: Record<string, unknown> }>(
    `/clients/${clientId}/agent/parameters`
  );
}

export function updateRiskParameters(clientId: string, riskParameters: RiskParameters) {
  return api<{ client_id: string; risk_parameters: RiskParameters }>(`/clients/${clientId}/agent/parameters`, {
    method: "POST",
    body: JSON.stringify({ risk_parameters: riskParameters })
  });
}

export function updateAgentParameters(clientId: string, parameters: Record<string, unknown>) {
  return api<{ client_id: string; risk_parameters: Record<string, unknown> }>(`/clients/${clientId}/agent/parameters`, {
    method: "POST",
    body: JSON.stringify({ risk_parameters: parameters })
  });
}

export function approveProposal(clientId: string, proposalId: number) {
  return api<Record<string, unknown>>(`/clients/${clientId}/agent/approve/${proposalId}`, {
    method: "POST"
  });
}

export function rejectProposal(clientId: string, proposalId: number) {
  return api<Record<string, unknown>>(`/clients/${clientId}/agent/reject/${proposalId}`, {
    method: "POST"
  });
}

export function createStrategyTemplate(payload: {
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
}) {
  return api<StrategyTemplate>("/strategy-template", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function listStrategyTemplates() {
  return api<StrategyTemplate[]>("/strategy-template");
}

export function resolveStrategyTemplate(templateId: number) {
  return api<StrategyPreview>(`/strategy-template/${templateId}/resolve`, { method: "POST" });
}

export function executeStrategyTemplate(templateId: number) {
  return api<StrategyExecution>(`/strategy-template/${templateId}/execute`, { method: "POST" });
}

export function updateStrategyTemplate(
  templateId: number,
  payload: {
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
  }
) {
  return api<StrategyTemplate>(`/strategy-template/${templateId}`, {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export function deleteStrategyTemplate(templateId: number) {
  return api<void>(`/strategy-template/${templateId}`, { method: "DELETE" });
}
