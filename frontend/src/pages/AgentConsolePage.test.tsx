import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgentConsolePage } from "./AgentConsolePage";
import * as endpoints from "../api/endpoints";
import { renderWithProviders } from "../test/renderWithProviders";
import { useAgentStream } from "../hooks/useAgentStream";

vi.mock("../hooks/useAgentStream", () => ({ useAgentStream: vi.fn() }));

vi.mock("../api/endpoints", async () => {
  const actual = await vi.importActual<typeof import("../api/endpoints")>("../api/endpoints");
  return {
    ...actual,
    getStatus: vi.fn(),
    getProposals: vi.fn(),
    sendChat: vi.fn(),
    approveProposal: vi.fn(),
    rejectProposal: vi.fn(),
    setMode: vi.fn(),
    getReadiness: vi.fn()
  };
});

describe("AgentConsolePage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    localStorage.clear();
    vi.mocked(useAgentStream).mockReturnValue({ connected: true, lastEvent: null });
    vi.mocked(endpoints.getStatus).mockResolvedValue({
      client_id: "client-1",
      mode: "confirmation",
      healthy: true,
      last_action: null,
      net_greeks: { delta: 0, gamma: 0, theta: 0, vega: 0 }
    });
    vi.mocked(endpoints.getReadiness).mockResolvedValue({
      client_id: "client-1",
      ready: true,
      connected: true,
      market_data_ok: true,
      mode: "confirmation",
      risk_blocked: false,
      last_error: null,
      updated_at: "2026-02-19T00:00:00Z"
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

    await screen.findByText("Trade Assistant");
    await user.type(screen.getByPlaceholderText("Ask the agent..."), "hedge delta");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Proposal #101")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Approve Proposal" }));

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

    await user.click(screen.getByRole("button", { name: "Reject Proposal" }));
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

    await userEvent.setup().click(await screen.findByRole("button", { name: "Show Advanced" }));
    const runTitle = await screen.findByText("Run: persisted run");
    expect(runTitle).toBeInTheDocument();
    const runCard = runTitle.closest(".card");
    expect(runCard).not.toBeNull();
    expect(within(runCard!).getByText("restored from storage")).toBeInTheDocument();
  });

  it("toggles workflow step details and shows duration badge", async () => {
    const user = userEvent.setup();
    vi.mocked(endpoints.getProposals).mockResolvedValue([]);
    vi.mocked(endpoints.sendChat).mockResolvedValue({
      mode: "confirmation",
      message: "proposal generated",
      proposal_id: 301,
      proposal: { action: "SELL", symbol: "ES", qty: 1 },
      tool_trace_id: "trace-301",
      planned_tools: [{ name: "get_portfolio_greeks", input: {} }],
      tool_calls: [
        {
          tool_use_id: "tool-301",
          name: "get_portfolio_greeks",
          input: {},
          started_at: "2026-02-18T00:00:00Z",
          completed_at: "2026-02-18T00:00:00Z",
          duration_ms: 12
        }
      ],
      tool_results: [
        {
          tool_use_id: "tool-301",
          name: "get_portfolio_greeks",
          output: { net_greeks: { delta: 0.5 } },
          success: true,
          error: null,
          started_at: "2026-02-18T00:00:00Z",
          completed_at: "2026-02-18T00:00:00Z",
          duration_ms: 12
        }
      ]
    });

    renderWithProviders(<AgentConsolePage clientId="client-1" token="token-1" />);
    await screen.findByRole("button", { name: "Send" });
    await user.click(screen.getByRole("button", { name: "Show Advanced" }));

    await user.type(screen.getByPlaceholderText("Ask the agent..."), "hedge");
    await user.click(screen.getByRole("button", { name: "Send" }));

    const flow = screen.getByText("Tool Calling Workflow").closest(".agent-flow");
    expect(flow).not.toBeNull();
    const flowUi = within(flow!);
    expect(await flowUi.findByText("Step 1: get_portfolio_greeks")).toBeInTheDocument();
    expect(await flowUi.findByText("12 ms")).toBeInTheDocument();

    const initialToggle = flowUi.getByRole("button", { name: /Details|Hide/ });
    if (initialToggle.textContent === "Details") {
      await user.click(initialToggle);
      expect(await flowUi.findByText(/"delta":\s*0\.5/)).toBeInTheDocument();
    }

    await user.click(flowUi.getByRole("button", { name: "Hide" }));
    await waitFor(() => {
      expect(flowUi.queryByText(/"delta":\s*0\.5/)).not.toBeInTheDocument();
    });

    await user.click(flowUi.getByRole("button", { name: "Details" }));
    expect(await flowUi.findByText(/"delta":\s*0\.5/)).toBeInTheDocument();
  });

  it("shows live status panel and hides greeks/status stream spam from timeline by default", async () => {
    vi.mocked(endpoints.getProposals).mockResolvedValue([]);
    vi.mocked(useAgentStream).mockReturnValue({
      connected: true,
      lastEvent: {
        type: "greeks",
        data: {
          net_greeks: { delta: 0.1, gamma: 0.02, theta: -0.03, vega: 0.04 },
          positions: [],
          updated_at: "2026-02-18T10:02:39.534951+00:00"
        }
      }
    });

    renderWithProviders(<AgentConsolePage clientId="client-1" token="token-1" />);

    await userEvent.setup().click(await screen.findByRole("button", { name: "Show Advanced" }));
    expect(await screen.findByText("Live Status")).toBeInTheDocument();
    expect(await screen.findByText(/"delta":\s*0\.1/)).toBeInTheDocument();
    expect(screen.queryByText("Run: Agent event")).not.toBeInTheDocument();
    expect(screen.queryByText("Debug Stream Events")).not.toBeInTheDocument();
  });

  it("blocks approval when execution readiness is red", async () => {
    const user = userEvent.setup();
    vi.mocked(endpoints.getProposals)
      .mockResolvedValueOnce([
        {
          id: 909,
          timestamp: "2026-02-17T00:00:00Z",
          trade_payload: { action: "SELL", symbol: "ES", qty: 1 },
          agent_reasoning: "hedge",
          status: "pending",
          resolved_at: null
        }
      ])
      .mockResolvedValue([]);
    vi.mocked(endpoints.getReadiness).mockResolvedValue({
      client_id: "client-1",
      ready: false,
      connected: true,
      market_data_ok: false,
      mode: "confirmation",
      risk_blocked: false,
      last_error: "Market data unavailable",
      updated_at: "2026-02-19T00:00:00Z"
    });

    renderWithProviders(<AgentConsolePage clientId="client-1" token="token-1" />);
    await user.click(await screen.findByRole("button", { name: "Show Advanced" }));
    expect(await screen.findByText("Execution Readiness")).toBeInTheDocument();
    const approveButton = await screen.findByRole("button", { name: "Approve" });
    expect(approveButton).toBeDisabled();

    await user.click(approveButton);
    expect(vi.mocked(endpoints.approveProposal)).not.toHaveBeenCalled();
    expect(await screen.findByText("Market data unavailable")).toBeInTheDocument();
  });

  it("blocks send and approve when global halt is active", async () => {
    const user = userEvent.setup();
    vi.mocked(endpoints.getProposals).mockResolvedValueOnce([
      {
        id: 707,
        timestamp: "2026-02-17T00:00:00Z",
        trade_payload: { action: "SELL", symbol: "ES", qty: 1 },
        agent_reasoning: "halt test",
        status: "pending",
        resolved_at: null
      }
    ]);

    renderWithProviders(
      <AgentConsolePage clientId="client-1" token="token-1" isHalted haltReason="Emergency halt enabled by admin" />
    );

    const sendButton = await screen.findByRole("button", { name: "Send" });
    expect(sendButton).toBeDisabled();

    const approveButton = await screen.findByRole("button", { name: "Approve Proposal" });
    expect(approveButton).toBeDisabled();

    await user.click(approveButton);
    expect(vi.mocked(endpoints.approveProposal)).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Show Advanced" }));
    expect(
      await screen.findByText((text, node) => {
        if (!node) return false;
        return node.textContent?.includes("Emergency halt enabled by admin") ?? false;
      })
    ).toBeInTheDocument();
  });
});
