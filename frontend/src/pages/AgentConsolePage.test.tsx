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
    getReadiness: vi.fn(),
    getTrades: vi.fn()
  };
});

describe("AgentConsolePage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    if (typeof localStorage?.clear === "function") {
      localStorage.clear();
    }
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
    vi.mocked(endpoints.getTrades).mockResolvedValue([]);
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
    await user.click(screen.getByTestId("approve-proposal-101"));

    await waitFor(() => {
      expect(vi.mocked(endpoints.approveProposal)).toHaveBeenCalledWith("client-1", 101);
    });
    expect(await screen.findByText("Proposal #101 approved.")).toBeInTheDocument();
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

    await user.click(screen.getByTestId("reject-proposal-202"));
    await waitFor(() => {
      expect(vi.mocked(endpoints.rejectProposal)).toHaveBeenCalledWith("client-1", 202);
    });
    expect(await screen.findByText("Proposal #202 rejected.")).toBeInTheDocument();
  });

  it("executes selected proposal from simple flow and shows latest trade status", async () => {
    const user = userEvent.setup();
    vi.mocked(endpoints.getProposals)
      .mockResolvedValueOnce([
        {
          id: 303,
          timestamp: "2026-02-17T00:00:00Z",
          trade_payload: { action: "SELL", symbol: "ES", qty: 1 },
          agent_reasoning: "execute test",
          status: "pending",
          resolved_at: null
        }
      ])
      .mockResolvedValue([]);
    vi.mocked(endpoints.approveProposal).mockResolvedValue({ status: "approved" });
    vi.mocked(endpoints.getTrades).mockResolvedValue([
      {
        id: 1,
        timestamp: "2026-02-19T00:00:00Z",
        action: "SELL",
        symbol: "ES",
        instrument: "FOP",
        qty: 1,
        fill_price: 21.5,
        order_id: "OID-303",
        agent_reasoning: "approved",
        mode: "confirmation",
        status: "filled",
        pnl: 0
      }
    ]);

    renderWithProviders(<AgentConsolePage clientId="client-1" token="token-1" />);
    await screen.findByTestId("execute-trade-button");

    await user.click(await screen.findByTestId("execute-confirm-checkbox"));
    await user.click(await screen.findByTestId("execute-trade-button"));
    expect(await screen.findByRole("dialog", { name: "Trade Ticket Confirmation" })).toBeInTheDocument();
    await user.click(screen.getByTestId("trade-ticket-confirm-button"));

    await waitFor(() => {
      expect(vi.mocked(endpoints.approveProposal)).toHaveBeenCalledWith("client-1", 303);
    });
    await waitFor(() => {
      const matches = screen.getAllByText((_, node) => {
        const text = node?.textContent ?? "";
        return /status=filled/i.test(text) && (/id=OID-303/i.test(text) || /order_id=OID-303/i.test(text));
      });
      expect(matches.length).toBeGreaterThan(0);
    });
  }, 10000);

  it("blocks execute when confirmation checkbox is not checked", async () => {
    const user = userEvent.setup();
    vi.mocked(endpoints.getProposals).mockResolvedValueOnce([
      {
        id: 404,
        timestamp: "2026-02-17T00:00:00Z",
        trade_payload: { action: "SELL", symbol: "ES", qty: 1 },
        agent_reasoning: "guard test",
        status: "pending",
        resolved_at: null
      }
    ]);

    renderWithProviders(<AgentConsolePage clientId="client-1" token="token-1" />);
    await screen.findByTestId("execute-trade-button");

    const executeButton = screen.getByTestId("execute-trade-button");
    expect(executeButton).toBeDisabled();
    expect(screen.getByText("Confirm execution checkbox to continue.")).toBeInTheDocument();

    await user.click(await screen.findByTestId("execute-confirm-checkbox"));
    expect(screen.getByTestId("execute-trade-button")).toBeEnabled();
  });

  it("supports modal keyboard safety shortcuts", async () => {
    const user = userEvent.setup();
    vi.mocked(endpoints.getProposals).mockResolvedValueOnce([
      {
        id: 505,
        timestamp: "2026-02-17T00:00:00Z",
        trade_payload: { action: "SELL", symbol: "ES", qty: 1 },
        agent_reasoning: "keyboard test",
        status: "pending",
        resolved_at: null
      }
    ]);
    vi.mocked(endpoints.approveProposal).mockResolvedValue({ status: "approved" });
    vi.mocked(endpoints.getTrades).mockResolvedValue([
      {
        id: 2,
        timestamp: "2026-02-19T00:00:00Z",
        action: "SELL",
        symbol: "ES",
        instrument: "FOP",
        qty: 1,
        fill_price: 19.25,
        order_id: "OID-505",
        agent_reasoning: "approved",
        mode: "confirmation",
        status: "filled",
        pnl: 0
      }
    ]);

    renderWithProviders(<AgentConsolePage clientId="client-1" token="token-1" />);
    await user.click(await screen.findByTestId("execute-confirm-checkbox"));
    await user.click(await screen.findByTestId("execute-trade-button"));
    expect(await screen.findByRole("dialog", { name: "Trade Ticket Confirmation" })).toBeInTheDocument();

    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Trade Ticket Confirmation" })).not.toBeInTheDocument();
    });

    await user.click(await screen.findByTestId("execute-trade-button"));
    expect(await screen.findByRole("dialog", { name: "Trade Ticket Confirmation" })).toBeInTheDocument();
    await user.keyboard("{Enter}");

    await waitFor(() => {
      expect(vi.mocked(endpoints.approveProposal)).toHaveBeenCalledWith("client-1", 505);
    });
  });

  it("focuses Cancel when trade ticket modal opens", async () => {
    const user = userEvent.setup();
    vi.mocked(endpoints.getProposals).mockResolvedValueOnce([
      {
        id: 606,
        timestamp: "2026-02-17T00:00:00Z",
        trade_payload: { action: "SELL", symbol: "ES", qty: 1 },
        agent_reasoning: "focus test",
        status: "pending",
        resolved_at: null
      }
    ]);

    renderWithProviders(<AgentConsolePage clientId="client-1" token="token-1" />);
    await user.click(await screen.findByTestId("execute-confirm-checkbox"));
    await user.click(await screen.findByTestId("execute-trade-button"));

    expect(await screen.findByRole("dialog", { name: "Trade Ticket Confirmation" })).toBeInTheDocument();
    expect(screen.getByTestId("trade-ticket-cancel-button")).toHaveFocus();
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

    await userEvent.setup().click(await screen.findByTestId("toggle-advanced-button"));
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
    await user.click(screen.getByTestId("toggle-advanced-button"));

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

    await userEvent.setup().click(await screen.findByTestId("toggle-advanced-button"));
    expect(await screen.findByText("Live Status")).toBeInTheDocument();
    expect(await screen.findByText(/"delta":\s*0\.1/)).toBeInTheDocument();
    expect(screen.queryByText("Run: Agent event")).not.toBeInTheDocument();
    expect(screen.queryByText("Debug Stream Events")).not.toBeInTheDocument();
  });

  it("marks lifecycle source as websocket when order_status stream event arrives", async () => {
    vi.mocked(endpoints.getProposals).mockResolvedValueOnce([
      {
        id: 808,
        timestamp: "2026-02-17T00:00:00Z",
        trade_payload: { action: "SELL", symbol: "ES", qty: 1 },
        agent_reasoning: "stream source test",
        status: "pending",
        resolved_at: null
      }
    ]);
    vi.mocked(useAgentStream).mockReturnValue({
      connected: true,
      lastEvent: {
        type: "order_status",
        data: {
          trade_id: 55,
          order_id: "OID-STREAM-55",
          symbol: "ES",
          action: "SELL",
          qty: 1,
          status: "filled",
          fill_price: 20.5,
          timestamp: "2026-02-19T00:00:00Z"
        }
      }
    });

    renderWithProviders(<AgentConsolePage clientId="client-1" token="token-1" />);

    expect(await screen.findByText("Source: websocket")).toBeInTheDocument();
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
    await user.click(await screen.findByTestId("toggle-advanced-button"));
    expect(await screen.findByText("Execution Readiness")).toBeInTheDocument();
    const approveButton = await screen.findByTestId("approve-proposal-909");
    expect(approveButton).toBeDisabled();

    await user.click(approveButton);
    expect(vi.mocked(endpoints.approveProposal)).not.toHaveBeenCalled();
    const marketDataErrors = await screen.findAllByText("Market data unavailable");
    expect(marketDataErrors.length).toBeGreaterThan(0);
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
    expect(screen.getByTestId("halt-readonly-overlay")).toBeInTheDocument();

    const approveButton = await screen.findByTestId("approve-proposal-707");
    expect(approveButton).toBeDisabled();

    await user.click(approveButton);
    expect(vi.mocked(endpoints.approveProposal)).not.toHaveBeenCalled();

    await user.click(screen.getByTestId("toggle-advanced-button"));
    const haltMessages = await screen.findAllByText(/Emergency halt enabled by admin/);
    expect(haltMessages.length).toBeGreaterThan(0);
  });
});
