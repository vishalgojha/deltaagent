import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DashboardPage } from "./DashboardPage";
import * as endpoints from "../api/endpoints";
import { RISK_PRESETS } from "../features/riskControls";
import { renderWithProviders } from "../test/renderWithProviders";

vi.mock("../api/endpoints", async () => {
  const actual = await vi.importActual<typeof import("../api/endpoints")>("../api/endpoints");
  return {
    ...actual,
    getStatus: vi.fn(),
    getPositions: vi.fn(),
    getTrades: vi.fn(),
    getTradeFills: vi.fn(),
    getExecutionQuality: vi.fn(),
    getExecutionIncidents: vi.fn(),
    createExecutionIncidentNote: vi.fn(),
    setMode: vi.fn(),
    getRiskParameters: vi.fn(),
    updateRiskParameters: vi.fn(),
    updateAgentParameters: vi.fn()
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
  vi.mocked(endpoints.getTradeFills).mockResolvedValue([]);
  vi.mocked(endpoints.getExecutionQuality).mockResolvedValue({
    client_id: "client-1",
    window_start: null,
    window_end: null,
    trades_total: 0,
    trades_with_fills: 0,
    fill_events: 0,
    backfilled_trades: 0,
    backfilled_fill_events: 0,
    avg_slippage_bps: null,
    median_slippage_bps: null,
    avg_first_fill_latency_ms: null,
    generated_at: new Date().toISOString()
  });
  vi.mocked(endpoints.getExecutionIncidents).mockResolvedValue([]);
  vi.mocked(endpoints.createExecutionIncidentNote).mockResolvedValue({
    id: 1,
    client_id: "client-1",
    alert_id: "avg-slippage",
    severity: "warning",
    label: "Slippage",
    note: "note",
    context: {},
    created_at: new Date().toISOString()
  });
  vi.mocked(endpoints.setMode).mockResolvedValue({ ok: true });
  vi.mocked(endpoints.getRiskParameters).mockResolvedValue({
    client_id: "client-1",
    risk_parameters: {
      delta_threshold: 0.2,
      max_size: 10,
      max_loss: 5000,
      max_open_positions: 20,
      execution_alert_slippage_warn_bps: 15,
      execution_alert_slippage_critical_bps: 30,
      execution_alert_latency_warn_ms: 3000,
      execution_alert_latency_critical_ms: 8000,
      execution_alert_fill_coverage_warn_pct: 75,
      execution_alert_fill_coverage_critical_pct: 50,
      auto_remediation_enabled: false,
      auto_remediation_warning_action: "none",
      auto_remediation_critical_action: "pause_autonomous",
      auto_remediation_cooldown_minutes: 20,
      auto_remediation_max_actions_per_hour: 2
    }
  });
  vi.mocked(endpoints.updateAgentParameters).mockResolvedValue({
    client_id: "client-1",
    risk_parameters: {
      auto_remediation_enabled: true,
      auto_remediation_warning_action: "apply_conservative",
      auto_remediation_critical_action: "pause_autonomous",
      auto_remediation_cooldown_minutes: 15,
      auto_remediation_max_actions_per_hour: 3
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
    expect(screen.getByLabelText("Slippage Warning (bps)")).toHaveValue("10");
    expect(screen.getByLabelText("Fill Coverage Critical (%)")).toHaveValue("70");
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
        max_open_positions: 25,
        execution_alert_slippage_warn_bps: 15,
        execution_alert_slippage_critical_bps: 30,
        execution_alert_latency_warn_ms: 3000,
        execution_alert_latency_critical_ms: 8000,
        execution_alert_fill_coverage_warn_pct: 75,
        execution_alert_fill_coverage_critical_pct: 50
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
        max_open_positions: 25,
        execution_alert_slippage_warn_bps: 15,
        execution_alert_slippage_critical_bps: 30,
        execution_alert_latency_warn_ms: 3000,
        execution_alert_latency_critical_ms: 8000,
        execution_alert_fill_coverage_warn_pct: 75,
        execution_alert_fill_coverage_critical_pct: 50
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

  it("updates auto-remediation policy parameters", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DashboardPage clientId="client-1" />);

    await screen.findByRole("button", { name: "Save Auto-Remediation Policy" });
    await user.click(screen.getByLabelText("Enable Auto-Remediation"));
    await user.selectOptions(screen.getByLabelText("Warning Action"), "apply_conservative");
    await user.selectOptions(screen.getByLabelText("Critical Action"), "pause_autonomous");
    await user.clear(screen.getByLabelText("Cooldown (minutes)"));
    await user.type(screen.getByLabelText("Cooldown (minutes)"), "15");
    await user.clear(screen.getByLabelText("Max Actions Per Hour"));
    await user.type(screen.getByLabelText("Max Actions Per Hour"), "3");
    await user.click(screen.getByRole("button", { name: "Save Auto-Remediation Policy" }));

    await waitFor(() => {
      expect(vi.mocked(endpoints.updateAgentParameters)).toHaveBeenCalledWith("client-1", {
        auto_remediation_enabled: true,
        auto_remediation_warning_action: "apply_conservative",
        auto_remediation_critical_action: "pause_autonomous",
        auto_remediation_cooldown_minutes: 15,
        auto_remediation_max_actions_per_hour: 3
      });
    });
    expect(await screen.findByText("Auto-remediation policy updated")).toBeInTheDocument();
  });

  it("renders execution alerts when metrics breach thresholds", async () => {
    vi.mocked(endpoints.getExecutionQuality).mockResolvedValue({
      client_id: "client-1",
      window_start: null,
      window_end: null,
      trades_total: 10,
      trades_with_fills: 4,
      fill_events: 4,
      backfilled_trades: 2,
      backfilled_fill_events: 2,
      avg_slippage_bps: 36.5,
      median_slippage_bps: 20.2,
      avg_first_fill_latency_ms: 9100,
      generated_at: new Date().toISOString()
    });

    renderWithProviders(<DashboardPage clientId="client-1" />);

    expect(await screen.findByRole("heading", { name: "Execution Alerts" })).toBeInTheDocument();
    expect(await screen.findByText(/Avg slippage/i)).toBeInTheDocument();
    expect(await screen.findByText(/Avg first-fill latency/i)).toBeInTheDocument();
    expect(await screen.findByText(/Fill coverage .* is below .* target\./i)).toBeInTheDocument();
    const runbookHeadings = await screen.findAllByText(/What To Do Now/i);
    expect(runbookHeadings.length).toBeGreaterThan(0);
  });

  it("uses client-configured alert thresholds", async () => {
    vi.mocked(endpoints.getRiskParameters).mockResolvedValue({
      client_id: "client-1",
      risk_parameters: {
        delta_threshold: 0.2,
        max_size: 10,
        max_loss: 5000,
        max_open_positions: 20,
        execution_alert_slippage_warn_bps: 40,
        execution_alert_slippage_critical_bps: 60,
        execution_alert_latency_warn_ms: 10000,
        execution_alert_latency_critical_ms: 20000,
        execution_alert_fill_coverage_warn_pct: 50,
        execution_alert_fill_coverage_critical_pct: 25
      }
    });
    vi.mocked(endpoints.getExecutionQuality).mockResolvedValue({
      client_id: "client-1",
      window_start: null,
      window_end: null,
      trades_total: 10,
      trades_with_fills: 8,
      fill_events: 8,
      backfilled_trades: 0,
      backfilled_fill_events: 0,
      avg_slippage_bps: 30,
      median_slippage_bps: 20,
      avg_first_fill_latency_ms: 9000,
      generated_at: new Date().toISOString()
    });

    renderWithProviders(<DashboardPage clientId="client-1" />);
    expect(await screen.findByRole("heading", { name: "Execution Alerts" })).toBeInTheDocument();
    expect(await screen.findByText(/No active execution alerts/i)).toBeInTheDocument();
  });

  it("pauses autonomous mode from an alert action", async () => {
    const user = userEvent.setup();
    vi.mocked(endpoints.getStatus).mockResolvedValue({
      client_id: "client-1",
      mode: "autonomous",
      healthy: true,
      last_action: null,
      net_greeks: { delta: 0, gamma: 0, theta: 0, vega: 0 }
    });
    vi.mocked(endpoints.getExecutionQuality).mockResolvedValue({
      client_id: "client-1",
      window_start: null,
      window_end: null,
      trades_total: 5,
      trades_with_fills: 1,
      fill_events: 1,
      backfilled_trades: 0,
      backfilled_fill_events: 0,
      avg_slippage_bps: 45,
      median_slippage_bps: 45,
      avg_first_fill_latency_ms: 9000,
      generated_at: new Date().toISOString()
    });
    renderWithProviders(<DashboardPage clientId="client-1" />);

    await screen.findByRole("heading", { name: "Execution Alerts" });
    await screen.findByText(/Avg slippage/i);
    await user.click(screen.getAllByRole("button", { name: "Pause Autonomous" })[0]);

    await waitFor(() => {
      expect(vi.mocked(endpoints.setMode)).toHaveBeenCalledWith("client-1", "confirmation");
    });
  });

  it("applies conservative preset from an alert action", async () => {
    const user = userEvent.setup();
    vi.mocked(endpoints.getExecutionQuality).mockResolvedValue({
      client_id: "client-1",
      window_start: null,
      window_end: null,
      trades_total: 5,
      trades_with_fills: 2,
      fill_events: 2,
      backfilled_trades: 0,
      backfilled_fill_events: 0,
      avg_slippage_bps: 45,
      median_slippage_bps: 45,
      avg_first_fill_latency_ms: 9000,
      generated_at: new Date().toISOString()
    });
    vi.mocked(endpoints.updateRiskParameters).mockResolvedValue({
      client_id: "client-1",
      risk_parameters: RISK_PRESETS.conservative
    });

    renderWithProviders(<DashboardPage clientId="client-1" />);
    await screen.findByRole("heading", { name: "Execution Alerts" });
    await screen.findByText(/Avg slippage/i);
    await user.click(screen.getAllByRole("button", { name: "Apply Conservative Preset" })[0]);

    await waitFor(() => {
      expect(vi.mocked(endpoints.updateRiskParameters)).toHaveBeenCalledWith("client-1", RISK_PRESETS.conservative);
    });
  });

  it("creates an incident note from an alert card", async () => {
    const user = userEvent.setup();
    vi.mocked(endpoints.getExecutionQuality).mockResolvedValue({
      client_id: "client-1",
      window_start: null,
      window_end: null,
      trades_total: 5,
      trades_with_fills: 1,
      fill_events: 1,
      backfilled_trades: 0,
      backfilled_fill_events: 0,
      avg_slippage_bps: 45,
      median_slippage_bps: 45,
      avg_first_fill_latency_ms: 9000,
      generated_at: new Date().toISOString()
    });

    renderWithProviders(<DashboardPage clientId="client-1" />);
    await screen.findByRole("heading", { name: "Execution Alerts" });
    await screen.findByText(/Avg slippage/i);

    const noteAreas = screen.getAllByLabelText("Incident Note");
    await user.type(noteAreas[0], "Paused and switched to conservative profile.");
    await user.click(screen.getAllByRole("button", { name: "Create Incident Note" })[0]);

    await waitFor(() => {
      expect(vi.mocked(endpoints.createExecutionIncidentNote)).toHaveBeenCalledWith(
        "client-1",
        expect.objectContaining({
          alert_id: "avg-slippage",
          severity: "critical",
          label: "Slippage",
          note: "Paused and switched to conservative profile."
        })
      );
    });
  });
});
