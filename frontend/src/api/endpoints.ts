import { api } from "./client";
import type { AgentStatus, ChatResponse, ClientOut, LoginResponse, Position, Proposal, Trade } from "../types";
import type { RiskParameters } from "../features/riskControls";

export function login(email: string, password: string) {
  return api<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password })
  });
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
