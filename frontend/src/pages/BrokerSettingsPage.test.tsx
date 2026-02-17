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
    connectBroker: vi.fn()
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
  });

  it("submits parsed credentials and shows connection result", async () => {
    const user = userEvent.setup();
    vi.mocked(endpoints.connectBroker).mockResolvedValue({
      connected: true,
      broker: "ibkr"
    });

    renderWithProviders(<BrokerSettingsPage clientId="client-1" />);
    await screen.findByText("Broker Connection Health");

    fireEvent.change(screen.getByLabelText("Broker Credentials (JSON, optional)"), {
      target: { value: '{"host":"localhost","port":4002,"client_id":1}' }
    });
    await user.click(screen.getByRole("button", { name: "Reconnect Broker" }));

    await waitFor(() =>
      expect(vi.mocked(endpoints.connectBroker)).toHaveBeenCalledWith("client-1", {
        host: "localhost",
        port: 4002,
        client_id: 1
      })
    );
    expect(await screen.findByText("Connection successful: connected=true broker=ibkr")).toBeInTheDocument();
  });

  it("blocks submit for invalid JSON and renders error", async () => {
    const user = userEvent.setup();

    renderWithProviders(<BrokerSettingsPage clientId="client-1" />);
    await screen.findByText("Broker Connection Health");

    fireEvent.change(screen.getByLabelText("Broker Credentials (JSON, optional)"), {
      target: { value: '{"host"' }
    });
    await user.click(screen.getByRole("button", { name: "Reconnect Broker" }));

    expect(await screen.findByText("Broker credentials must be valid JSON")).toBeInTheDocument();
    expect(vi.mocked(endpoints.connectBroker)).not.toHaveBeenCalled();
  });
});
