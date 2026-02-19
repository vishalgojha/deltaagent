import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BrokerSettingsPage } from "./BrokerSettingsPage";
import * as endpoints from "../api/endpoints";
import { renderWithProviders } from "../test/renderWithProviders";

vi.mock("../api/endpoints", async () => {
  const actual = await vi.importActual<typeof import("../api/endpoints")>("../api/endpoints");
  return {
    ...actual,
    getStatus: vi.fn(),
    connectBroker: vi.fn(),
    brokerPreflight: vi.fn()
  };
});

describe("BrokerSettingsPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(endpoints.getStatus).mockResolvedValue({
      client_id: "client-1",
      mode: "confirmation",
      healthy: true,
      last_action: null,
      net_greeks: { delta: 0, gamma: 0, theta: 0, vega: 0 }
    });
    vi.mocked(endpoints.brokerPreflight).mockResolvedValue({
      ok: true,
      broker: "ibkr",
      checks: [{ key: "host", title: "IBKR host", status: "pass", detail: "Host=localhost" }],
      blocking_issues: [],
      warnings: [],
      fix_hints: [],
      checked_at: "2026-02-19T00:00:00Z"
    });
  });

  it("submits parsed credentials and shows connection result", async () => {
    const user = userEvent.setup();
    vi.mocked(endpoints.connectBroker).mockResolvedValue({
      connected: true,
      broker: "ibkr"
    });

    renderWithProviders(<BrokerSettingsPage clientId="client-1" />);
    await screen.findByText("Broker Connection Health");

    await user.click(screen.getByLabelText("Use saved credentials"));
    fireEvent.change(screen.getByLabelText("IBKR Host"), { target: { value: "localhost" } });
    fireEvent.change(screen.getByLabelText("IBKR Port"), { target: { value: "4002" } });
    fireEvent.change(screen.getByLabelText("Client ID"), { target: { value: "1" } });
    await user.click(screen.getByRole("button", { name: "Reconnect Broker" }));

    await waitFor(() =>
      expect(vi.mocked(endpoints.connectBroker)).toHaveBeenCalledWith("client-1", {
        host: "localhost",
        port: 4002,
        client_id: 1,
        underlying_instrument: "IND",
        delayed_market_data: true
      })
    );
    expect(await screen.findByText("Connection successful: connected=true broker=ibkr")).toBeInTheDocument();
  });

  it("reconnects with saved credentials by default", async () => {
    const user = userEvent.setup();
    vi.mocked(endpoints.connectBroker).mockResolvedValue({
      connected: true,
      broker: "ibkr"
    });

    renderWithProviders(<BrokerSettingsPage clientId="client-1" />);
    await screen.findByText("Broker Connection Health");

    await user.click(screen.getByRole("button", { name: "Reconnect Broker" }));

    await waitFor(() => expect(vi.mocked(endpoints.connectBroker)).toHaveBeenCalledWith("client-1", undefined));
  });

  it("blocks submit for invalid numeric fields and renders error", async () => {
    const user = userEvent.setup();

    renderWithProviders(<BrokerSettingsPage clientId="client-1" />);
    await screen.findByText("Broker Connection Health");

    await user.click(screen.getByLabelText("Use saved credentials"));
    fireEvent.change(screen.getByLabelText("IBKR Port"), { target: { value: "abc" } });
    await user.click(screen.getByRole("button", { name: "Reconnect Broker" }));

    expect(await screen.findByText("IBKR port must be a valid number")).toBeInTheDocument();
    expect(vi.mocked(endpoints.connectBroker)).not.toHaveBeenCalled();
  });

  it("runs preflight and renders checklist result", async () => {
    const user = userEvent.setup();

    renderWithProviders(<BrokerSettingsPage clientId="client-1" />);
    await screen.findByText("Broker Connection Health");

    await user.click(screen.getByRole("button", { name: "Run Preflight" }));

    await waitFor(() => expect(vi.mocked(endpoints.brokerPreflight)).toHaveBeenCalledWith("client-1", undefined));
    expect(await screen.findByText("Overall:")).toBeInTheDocument();
    expect(await screen.findByText("PASS")).toBeInTheDocument();
    expect(await screen.findByText("IBKR host")).toBeInTheDocument();
  });
});
