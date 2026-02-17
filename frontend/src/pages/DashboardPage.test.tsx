import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DashboardPage } from "./DashboardPage";
import * as endpoints from "../api/endpoints";
import { renderWithProviders } from "../test/renderWithProviders";

vi.mock("../api/endpoints", async () => {
  const actual = await vi.importActual<typeof import("../api/endpoints")>("../api/endpoints");
  return {
    ...actual,
    getStatus: vi.fn(),
    getPositions: vi.fn(),
    getTrades: vi.fn(),
    getRiskParameters: vi.fn(),
    updateRiskParameters: vi.fn()
  };
});

function mockDashboardLoad() {
  vi.mocked(endpoints.getStatus).mockResolvedValue({
    client_id: "client-1",
    mode: "confirmation",
    healthy: true,
    last_action: null,
    net_greeks: { delta: 0, gamma: 0, theta: 0, vega: 0 }
  });
  vi.mocked(endpoints.getPositions).mockResolvedValue([]);
  vi.mocked(endpoints.getTrades).mockResolvedValue([]);
  vi.mocked(endpoints.getRiskParameters).mockResolvedValue({
    client_id: "client-1",
    risk_parameters: {
      delta_threshold: 0.2,
      max_size: 10,
      max_loss: 5000,
      max_open_positions: 20
    }
  });
}

describe("DashboardPage Risk Controls", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockDashboardLoad();
  });

  it("applies preset values", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DashboardPage clientId="client-1" />);

    await screen.findByRole("button", { name: "Conservative" });
    await user.click(screen.getByRole("button", { name: "Conservative" }));

    expect(screen.getByLabelText("Delta Threshold")).toHaveValue("0.1");
    expect(screen.getByLabelText("Max Size")).toHaveValue("5");
    expect(screen.getByLabelText("Max Loss")).toHaveValue("2500");
    expect(screen.getByLabelText("Max Open Positions")).toHaveValue("10");
  });

  it("shows validation errors and blocks submit", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DashboardPage clientId="client-1" />);

    await screen.findByLabelText("Max Open Positions");
    await user.clear(screen.getByLabelText("Max Open Positions"));
    await user.type(screen.getByLabelText("Max Open Positions"), "0");
    await user.click(screen.getByRole("button", { name: "Save Risk Controls" }));

    expect(await screen.findByText("Max open positions must be between 1 and 10000")).toBeInTheDocument();
    expect(vi.mocked(endpoints.updateRiskParameters)).not.toHaveBeenCalled();
  });

  it("submits parsed risk payload", async () => {
    const user = userEvent.setup();
    vi.mocked(endpoints.updateRiskParameters).mockResolvedValue({
      client_id: "client-1",
      risk_parameters: {
        delta_threshold: 0.35,
        max_size: 15,
        max_loss: 8000,
        max_open_positions: 25
      }
    });

    renderWithProviders(<DashboardPage clientId="client-1" />);
    await screen.findByLabelText("Delta Threshold");

    await user.clear(screen.getByLabelText("Delta Threshold"));
    await user.type(screen.getByLabelText("Delta Threshold"), "0.35");
    await user.clear(screen.getByLabelText("Max Size"));
    await user.type(screen.getByLabelText("Max Size"), "15");
    await user.clear(screen.getByLabelText("Max Loss"));
    await user.type(screen.getByLabelText("Max Loss"), "8000");
    await user.clear(screen.getByLabelText("Max Open Positions"));
    await user.type(screen.getByLabelText("Max Open Positions"), "25");
    await user.click(screen.getByRole("button", { name: "Save Risk Controls" }));

    await waitFor(() =>
      expect(vi.mocked(endpoints.updateRiskParameters)).toHaveBeenCalledWith("client-1", {
        delta_threshold: 0.35,
        max_size: 15,
        max_loss: 8000,
        max_open_positions: 25
      })
    );
    expect(await screen.findByText("Risk controls updated")).toBeInTheDocument();
  });

  it("renders API error when save fails", async () => {
    const user = userEvent.setup();
    vi.mocked(endpoints.updateRiskParameters).mockRejectedValue(new Error("backend unavailable"));

    renderWithProviders(<DashboardPage clientId="client-1" />);
    await screen.findByRole("button", { name: "Save Risk Controls" });
    await user.click(screen.getByRole("button", { name: "Save Risk Controls" }));

    expect(await screen.findByText("backend unavailable")).toBeInTheDocument();
  });
});
