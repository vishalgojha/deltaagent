import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgentConsolePage } from "./AgentConsolePage";
import * as endpoints from "../api/endpoints";
import { renderWithProviders } from "../test/renderWithProviders";

vi.mock("../hooks/useAgentStream", () => ({
  useAgentStream: () => ({ connected: true, lastEvent: null })
}));

vi.mock("../api/endpoints", async () => {
  const actual = await vi.importActual<typeof import("../api/endpoints")>("../api/endpoints");
  return {
    ...actual,
    getStatus: vi.fn(),
    getProposals: vi.fn(),
    sendChat: vi.fn(),
    approveProposal: vi.fn(),
    rejectProposal: vi.fn(),
    setMode: vi.fn()
  };
});

describe("AgentConsolePage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    localStorage.clear();
    vi.mocked(endpoints.getStatus).mockResolvedValue({
      client_id: "client-1",
      mode: "confirmation",
      healthy: true,
      last_action: null,
      net_greeks: { delta: 0, gamma: 0, theta: 0, vega: 0 }
    });
    vi.mocked(endpoints.setMode).mockResolvedValue({ ok: true });
  });

  it("creates proposal from chat and approves it", async () => {
    const user = userEvent.setup();
    vi.mocked(endpoints.getProposals)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        {
          id: 101,
          timestamp: "2026-02-17T00:00:00Z",
          trade_payload: { action: "SELL", symbol: "ES", qty: 1 },
          agent_reasoning: "hedge",
          status: "pending",
          resolved_at: null
        }
      ])
      .mockResolvedValue([]);
    vi.mocked(endpoints.sendChat).mockResolvedValue({ message: "proposal generated" });
    vi.mocked(endpoints.approveProposal).mockResolvedValue({ status: "approved" });

    renderWithProviders(<AgentConsolePage clientId="client-1" token="token-1" />);

    await screen.findByText("No timeline entries yet.");
    await user.type(screen.getByPlaceholderText("Ask the agent..."), "hedge delta");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Proposal #101")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() => {
      expect(vi.mocked(endpoints.approveProposal)).toHaveBeenCalledWith("client-1", 101);
    });
    expect(await screen.findByText("Approved")).toBeInTheDocument();
  });

  it("rejects a pending proposal", async () => {
    const user = userEvent.setup();
    vi.mocked(endpoints.getProposals)
      .mockResolvedValueOnce([
        {
          id: 202,
          timestamp: "2026-02-17T00:00:00Z",
          trade_payload: { action: "BUY", symbol: "ES", qty: 1 },
          agent_reasoning: "rebalance",
          status: "pending",
          resolved_at: null
        }
      ])
      .mockResolvedValue([]);
    vi.mocked(endpoints.rejectProposal).mockResolvedValue({ status: "rejected" });

    renderWithProviders(<AgentConsolePage clientId="client-1" token="token-1" />);
    expect(await screen.findByText("Proposal #202")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reject" }));
    await waitFor(() => {
      expect(vi.mocked(endpoints.rejectProposal)).toHaveBeenCalledWith("client-1", 202);
    });
    expect(await screen.findByText("Rejected")).toBeInTheDocument();
  });

  it("restores persisted timeline runs on load", async () => {
    localStorage.setItem(
      "ta_agent_timeline_client-1",
      JSON.stringify({
        version: 1,
        runs: [
          {
            id: "run-1",
            title: "persisted run",
            status: "completed",
            createdAt: "2026-02-17T00:00:00Z",
            items: [
              {
                id: "item-1",
                kind: "assistant",
                text: "restored from storage",
                createdAt: "2026-02-17T00:00:01Z"
              }
            ]
          }
        ],
        resolvedProposals: {},
        proposalRunEntries: []
      })
    );

    vi.mocked(endpoints.getProposals).mockResolvedValue([]);
    renderWithProviders(<AgentConsolePage clientId="client-1" token="token-1" />);

    expect(await screen.findByText("Run: persisted run")).toBeInTheDocument();
    expect(await screen.findByText("restored from storage")).toBeInTheDocument();
  });
});
