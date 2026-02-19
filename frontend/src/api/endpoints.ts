import { api } from "./client";
import type {
  AgentStatus,
  AgentReadiness,
  ChatResponse,
  ClientOut,
  EmergencyHaltStatus,
  LoginResponse,
  Position,
  Proposal,
  StrategyExecution,
  StrategyPreview,
  StrategyTemplate,
  Trade
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

export function getStatus(clientId: string) {
  return api<AgentStatus>(`/clients/${clientId}/agent/status`);
}

export function getReadiness(clientId: string) {
  return api<AgentReadiness>(`/clients/${clientId}/agent/readiness`);
}

export function getEmergencyHaltStatus(clientId: string) {
  return api<EmergencyHaltStatus>(`/clients/${clientId}/agent/emergency-halt`);
}

export function getAdminEmergencyHalt(adminKey: string) {
  return api<EmergencyHaltStatus>("/admin/emergency-halt", {
    headers: { "X-Admin-Key": adminKey }
  });
}

export function setAdminEmergencyHalt(adminKey: string, halted: boolean, reason: string) {
  return api<EmergencyHaltStatus>("/admin/emergency-halt", {
    method: "POST",
    headers: { "X-Admin-Key": adminKey },
    body: JSON.stringify({ halted, reason })
  });
}

export function getPositions(clientId: string) {
  return api<Position[]>(`/clients/${clientId}/positions`);
}

export function getTrades(clientId: string) {
  return api<Trade[]>(`/clients/${clientId}/trades`);
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

export function getRiskParameters(clientId: string) {
  return api<{ client_id: string; risk_parameters: Partial<RiskParameters> }>(
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
