import { FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { getExecutionQuality, getPositions, getRiskParameters, getStatus, getTradeFills, getTrades, updateRiskParameters } from "../api/endpoints";
import {
  RISK_PRESETS,
  type RiskParameters,
  type RiskField,
  type RiskFormErrors,
  type RiskFormValues,
  toRiskFormValues,
  validateRiskValues
} from "../features/riskControls";
import type { AgentStatus, ExecutionQuality, Position, Trade, TradeFill } from "../types";

type Props = { clientId: string };
type ExecutionAlertSeverity = "warning" | "critical";
type ExecutionAlert = {
  id: string;
  severity: ExecutionAlertSeverity;
  label: string;
  message: string;
};

type ExecutionAlertThresholds = {
  slippageWarnBps: number;
  slippageCriticalBps: number;
  latencyWarnMs: number;
  latencyCriticalMs: number;
  fillCoverageWarnPct: number;
  fillCoverageCriticalPct: number;
};

function buildExecutionAlerts(metrics: ExecutionQuality | null, thresholds: ExecutionAlertThresholds): ExecutionAlert[] {
  if (!metrics) return [];

  const alerts: ExecutionAlert[] = [];
  const avgSlippageAbs = metrics.avg_slippage_bps === null ? null : Math.abs(metrics.avg_slippage_bps);
  if (avgSlippageAbs !== null && avgSlippageAbs >= thresholds.slippageWarnBps) {
    const critical = avgSlippageAbs >= thresholds.slippageCriticalBps;
    alerts.push({
      id: "avg-slippage",
      severity: critical ? "critical" : "warning",
      label: "Slippage",
      message: `Avg slippage ${metrics.avg_slippage_bps?.toFixed(1)} bps exceeds ${critical ? thresholds.slippageCriticalBps : thresholds.slippageWarnBps} bps threshold.`
    });
  }

  if (metrics.avg_first_fill_latency_ms !== null && metrics.avg_first_fill_latency_ms >= thresholds.latencyWarnMs) {
    const critical = metrics.avg_first_fill_latency_ms >= thresholds.latencyCriticalMs;
    alerts.push({
      id: "first-fill-latency",
      severity: critical ? "critical" : "warning",
      label: "Latency",
      message: `Avg first-fill latency ${metrics.avg_first_fill_latency_ms.toFixed(0)}ms exceeds ${critical ? thresholds.latencyCriticalMs : thresholds.latencyWarnMs}ms threshold.`
    });
  }

  if (metrics.trades_total > 0) {
    const fillCoveragePct = (metrics.trades_with_fills / metrics.trades_total) * 100;
    if (fillCoveragePct < thresholds.fillCoverageWarnPct) {
      const critical = fillCoveragePct < thresholds.fillCoverageCriticalPct;
      alerts.push({
        id: "fill-coverage",
        severity: critical ? "critical" : "warning",
        label: "Fill Coverage",
        message: `Fill coverage ${fillCoveragePct.toFixed(0)}% is below ${critical ? thresholds.fillCoverageCriticalPct : thresholds.fillCoverageWarnPct}% target.`
      });
    }
  }

  return alerts;
}

function parseRiskNumber(raw: string, fallback: number): number {
  const numeric = Number(raw);
  return Number.isFinite(numeric) ? numeric : fallback;
}

export function DashboardPage({ clientId }: Props) {
  const [riskValues, setRiskValues] = useState<RiskFormValues>(toRiskFormValues(null));
  const [riskErrors, setRiskErrors] = useState<RiskFormErrors>({});
  const [riskStatus, setRiskStatus] = useState("");
  const [riskServerError, setRiskServerError] = useState("");
  const [selectedTradeId, setSelectedTradeId] = useState<number | null>(null);

  const dashboardQuery = useQuery({
    queryKey: ["dashboard", clientId],
    queryFn: async () => {
      const [s, p, t] = await Promise.all([getStatus(clientId), getPositions(clientId), getTrades(clientId)]);
      return { status: s, positions: p, trades: t.slice(0, 10) };
    }
  });

  const riskQuery = useQuery({
    queryKey: ["risk-parameters", clientId],
    queryFn: () => getRiskParameters(clientId)
  });

  const status: AgentStatus | null = dashboardQuery.data?.status ?? null;
  const positions: Position[] = dashboardQuery.data?.positions ?? [];
  const trades: Trade[] = dashboardQuery.data?.trades ?? [];
  const executionQualityQuery = useQuery({
    queryKey: ["execution-quality", clientId],
    queryFn: () => getExecutionQuality(clientId)
  });
  const executionQuality: ExecutionQuality | null = executionQualityQuery.data ?? null;
  const executionThresholds = useMemo<ExecutionAlertThresholds>(
    () => ({
      slippageWarnBps: parseRiskNumber(
        riskValues.execution_alert_slippage_warn_bps,
        RISK_PRESETS.balanced.execution_alert_slippage_warn_bps
      ),
      slippageCriticalBps: parseRiskNumber(
        riskValues.execution_alert_slippage_critical_bps,
        RISK_PRESETS.balanced.execution_alert_slippage_critical_bps
      ),
      latencyWarnMs: parseRiskNumber(
        riskValues.execution_alert_latency_warn_ms,
        RISK_PRESETS.balanced.execution_alert_latency_warn_ms
      ),
      latencyCriticalMs: parseRiskNumber(
        riskValues.execution_alert_latency_critical_ms,
        RISK_PRESETS.balanced.execution_alert_latency_critical_ms
      ),
      fillCoverageWarnPct: parseRiskNumber(
        riskValues.execution_alert_fill_coverage_warn_pct,
        RISK_PRESETS.balanced.execution_alert_fill_coverage_warn_pct
      ),
      fillCoverageCriticalPct: parseRiskNumber(
        riskValues.execution_alert_fill_coverage_critical_pct,
        RISK_PRESETS.balanced.execution_alert_fill_coverage_critical_pct
      )
    }),
    [riskValues]
  );
  const executionAlerts = useMemo(
    () => buildExecutionAlerts(executionQuality, executionThresholds),
    [executionQuality, executionThresholds]
  );
  const tradeFillsQuery = useQuery({
    queryKey: ["trade-fills", clientId, selectedTradeId],
    queryFn: () => getTradeFills(clientId, selectedTradeId as number),
    enabled: selectedTradeId !== null
  });
  const tradeFills: TradeFill[] = tradeFillsQuery.data ?? [];
  const dashboardError = useMemo(
    () =>
      dashboardQuery.error instanceof Error ? dashboardQuery.error.message : dashboardQuery.error ? "Failed to load dashboard" : "",
    [dashboardQuery.error]
  );

  useEffect(() => {
    if (riskQuery.data) {
      setRiskValues(toRiskFormValues(riskQuery.data.risk_parameters));
    }
    if (riskQuery.error) {
      setRiskServerError(riskQuery.error instanceof Error ? riskQuery.error.message : "Failed to load risk controls");
    }
  }, [riskQuery.data, riskQuery.error]);

  useEffect(() => {
    if (!trades.length) {
      if (selectedTradeId !== null) setSelectedTradeId(null);
      return;
    }
    if (selectedTradeId === null || !trades.some((trade) => trade.id === selectedTradeId)) {
      setSelectedTradeId(trades[0].id);
    }
  }, [trades, selectedTradeId]);

  const saveRiskMutation = useMutation({
    mutationFn: (payload: RiskParameters) => updateRiskParameters(clientId, payload)
  });

  function onRiskFieldChange(field: RiskField, value: string) {
    setRiskValues((prev) => ({ ...prev, [field]: value }));
    setRiskErrors((prev) => ({ ...prev, [field]: undefined }));
    setRiskStatus("");
    setRiskServerError("");
  }

  function applyPreset(name: keyof typeof RISK_PRESETS) {
    setRiskValues(toRiskFormValues(RISK_PRESETS[name]));
    setRiskErrors({});
    setRiskStatus(`Applied ${name} preset`);
    setRiskServerError("");
  }

  async function onRiskSubmit(event: FormEvent) {
    event.preventDefault();
    setRiskStatus("");
    setRiskServerError("");

    const validation = validateRiskValues(riskValues);
    if (!validation.parsed) {
      setRiskErrors(validation.errors);
      return;
    }

    setRiskErrors({});
    try {
      const response = await saveRiskMutation.mutateAsync(validation.parsed);
      setRiskValues(toRiskFormValues(response.risk_parameters));
      setRiskStatus("Risk controls updated");
    } catch (err) {
      setRiskServerError(err instanceof Error ? err.message : "Failed to update risk controls");
    }
  }

  return (
    <div className="grid dashboard-page">
      <section className="card">
        <div className="section-head">
          <div>
            <h3>Portfolio Overview</h3>
            <p className="muted">Live status, exposure snapshot, and risk controls.</p>
          </div>
        </div>
        <div className="metric-grid" style={{ marginTop: 12 }}>
          <article className="metric-card">
            <p className="metric-label">Mode</p>
            <p className="metric-value">{status?.mode ?? "-"}</p>
          </article>
          <article className="metric-card">
            <p className="metric-label">Healthy</p>
            <p className="metric-value">{String(status?.healthy ?? "-")}</p>
          </article>
          <article className="metric-card">
            <p className="metric-label">Positions</p>
            <p className="metric-value">{positions.length}</p>
          </article>
          <article className="metric-card">
            <p className="metric-label">Recent Trades</p>
            <p className="metric-value">{trades.length}</p>
          </article>
          <article className="metric-card">
            <p className="metric-label">Avg Slippage (bps)</p>
            <p className="metric-value">
              {executionQualityQuery.isLoading
                ? "..."
                : executionQuality?.avg_slippage_bps?.toFixed(1) ?? "-"}
            </p>
          </article>
        </div>
        {status && (
          <p className="muted" style={{ marginTop: 12 }}>
            Last Action: {status.last_action ?? "none"} | Net Greeks: {JSON.stringify(status.net_greeks)}
          </p>
        )}
      </section>

      <section className="card">
        <h3>Execution Alerts</h3>
        <p className="muted" style={{ marginBottom: 8 }}>
          Thresholds: Slippage {executionThresholds.slippageWarnBps}/{executionThresholds.slippageCriticalBps} bps,
          Latency {executionThresholds.latencyWarnMs}/{executionThresholds.latencyCriticalMs} ms,
          Fill Coverage {executionThresholds.fillCoverageWarnPct}/{executionThresholds.fillCoverageCriticalPct}%.
        </p>
        {executionQualityQuery.isLoading ? (
          <p className="muted">Evaluating execution quality...</p>
        ) : !executionQuality ? (
          <p className="muted">No execution metrics yet.</p>
        ) : !executionAlerts.length ? (
          <p className="muted">No active execution alerts.</p>
        ) : (
          <ul className="execution-alert-list">
            {executionAlerts.map((alert) => (
              <li key={alert.id} className={`execution-alert ${alert.severity}`}>
                <div className="execution-alert-head">
                  <span className={`execution-alert-badge ${alert.severity}`}>
                    {alert.severity === "critical" ? "Critical" : "Warning"}
                  </span>
                  <strong>{alert.label}</strong>
                </div>
                <p>{alert.message}</p>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="grid grid-2">
      <section className="card">
        <h3>Agent Status</h3>
        {status ? (
          <>
            <p>Mode: {status.mode}</p>
            <p>Healthy: {String(status.healthy)}</p>
            <p>Last Action: {status.last_action ?? "none"}</p>
            <p className="muted">Net Greeks: {JSON.stringify(status.net_greeks)}</p>
          </>
        ) : (
          <p className="muted">{dashboardQuery.isLoading ? "Loading..." : "No status data"}</p>
        )}
      </section>

      <section className="card">
        <h3>Positions</h3>
        <p className="muted" style={{ marginBottom: 8 }}>
          Current contract-level exposure.
        </p>
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Qty</th>
              <th>Delta</th>
              <th>Gamma</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => (
              <tr key={p.id}>
                <td>{p.symbol}</td>
                <td>{p.qty}</td>
                <td>{p.delta}</td>
                <td>{p.gamma}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      </div>

      <section className="card">
        <div className="section-head">
          <div>
            <h3>Risk Controls</h3>
            <p className="muted">Apply presets or tune parameters manually.</p>
          </div>
        </div>
        {riskQuery.isLoading ? (
          <p className="muted">Loading risk controls...</p>
        ) : (
          <form className="grid" onSubmit={onRiskSubmit}>
            <div className="row">
              <button type="button" className="secondary" onClick={() => applyPreset("conservative")}>
                Conservative
              </button>
              <button type="button" className="secondary" onClick={() => applyPreset("balanced")}>
                Balanced
              </button>
              <button type="button" className="secondary" onClick={() => applyPreset("aggressive")}>
                Aggressive
              </button>
            </div>

            <label className="grid">
              Delta Threshold
              <input
                value={riskValues.delta_threshold}
                onChange={(e) => onRiskFieldChange("delta_threshold", e.target.value)}
                inputMode="decimal"
              />
              {riskErrors.delta_threshold && (
                <span className="field-error">{riskErrors.delta_threshold}</span>
              )}
            </label>

            <label className="grid">
              Max Size
              <input
                value={riskValues.max_size}
                onChange={(e) => onRiskFieldChange("max_size", e.target.value)}
                inputMode="numeric"
              />
              {riskErrors.max_size && <span className="field-error">{riskErrors.max_size}</span>}
            </label>

            <label className="grid">
              Max Loss
              <input
                value={riskValues.max_loss}
                onChange={(e) => onRiskFieldChange("max_loss", e.target.value)}
                inputMode="decimal"
              />
              {riskErrors.max_loss && <span className="field-error">{riskErrors.max_loss}</span>}
            </label>

            <label className="grid">
              Max Open Positions
              <input
                value={riskValues.max_open_positions}
                onChange={(e) => onRiskFieldChange("max_open_positions", e.target.value)}
                inputMode="numeric"
              />
              {riskErrors.max_open_positions && <span className="field-error">{riskErrors.max_open_positions}</span>}
            </label>

            <h4 style={{ margin: "6px 0 0 0" }}>Execution Alert Thresholds</h4>

            <label className="grid">
              Slippage Warning (bps)
              <input
                value={riskValues.execution_alert_slippage_warn_bps}
                onChange={(e) => onRiskFieldChange("execution_alert_slippage_warn_bps", e.target.value)}
                inputMode="decimal"
              />
              {riskErrors.execution_alert_slippage_warn_bps && (
                <span className="field-error">{riskErrors.execution_alert_slippage_warn_bps}</span>
              )}
            </label>

            <label className="grid">
              Slippage Critical (bps)
              <input
                value={riskValues.execution_alert_slippage_critical_bps}
                onChange={(e) => onRiskFieldChange("execution_alert_slippage_critical_bps", e.target.value)}
                inputMode="decimal"
              />
              {riskErrors.execution_alert_slippage_critical_bps && (
                <span className="field-error">{riskErrors.execution_alert_slippage_critical_bps}</span>
              )}
            </label>

            <label className="grid">
              Latency Warning (ms)
              <input
                value={riskValues.execution_alert_latency_warn_ms}
                onChange={(e) => onRiskFieldChange("execution_alert_latency_warn_ms", e.target.value)}
                inputMode="numeric"
              />
              {riskErrors.execution_alert_latency_warn_ms && (
                <span className="field-error">{riskErrors.execution_alert_latency_warn_ms}</span>
              )}
            </label>

            <label className="grid">
              Latency Critical (ms)
              <input
                value={riskValues.execution_alert_latency_critical_ms}
                onChange={(e) => onRiskFieldChange("execution_alert_latency_critical_ms", e.target.value)}
                inputMode="numeric"
              />
              {riskErrors.execution_alert_latency_critical_ms && (
                <span className="field-error">{riskErrors.execution_alert_latency_critical_ms}</span>
              )}
            </label>

            <label className="grid">
              Fill Coverage Warning (%)
              <input
                value={riskValues.execution_alert_fill_coverage_warn_pct}
                onChange={(e) => onRiskFieldChange("execution_alert_fill_coverage_warn_pct", e.target.value)}
                inputMode="decimal"
              />
              {riskErrors.execution_alert_fill_coverage_warn_pct && (
                <span className="field-error">{riskErrors.execution_alert_fill_coverage_warn_pct}</span>
              )}
            </label>

            <label className="grid">
              Fill Coverage Critical (%)
              <input
                value={riskValues.execution_alert_fill_coverage_critical_pct}
                onChange={(e) => onRiskFieldChange("execution_alert_fill_coverage_critical_pct", e.target.value)}
                inputMode="decimal"
              />
              {riskErrors.execution_alert_fill_coverage_critical_pct && (
                <span className="field-error">{riskErrors.execution_alert_fill_coverage_critical_pct}</span>
              )}
            </label>

            <button type="submit" disabled={saveRiskMutation.isPending}>
              {saveRiskMutation.isPending ? "Saving..." : "Save Risk Controls"}
            </button>
            {riskStatus && <p style={{ color: "#166534", margin: 0 }}>{riskStatus}</p>}
            {riskServerError && <p style={{ color: "#991b1b", margin: 0 }}>{riskServerError}</p>}
          </form>
        )}
      </section>

      <section className="card">
        <h3>Recent Trades</h3>
        <p className="muted" style={{ marginBottom: 8 }}>
          Latest executions and statuses.
        </p>
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Action</th>
              <th>Symbol</th>
              <th>Qty</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t) => (
              <tr
                key={t.id}
                onClick={() => setSelectedTradeId(t.id)}
                style={{
                  cursor: "pointer",
                  backgroundColor: selectedTradeId === t.id ? "rgba(11,59,143,0.08)" : "transparent"
                }}
              >
                <td>{new Date(t.timestamp).toLocaleString()}</td>
                <td>{t.action}</td>
                <td>{t.symbol}</td>
                <td>{t.qty}</td>
                <td>{t.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="card">
        <h3>Execution Quality</h3>
        {executionQuality ? (
          <>
            <p>Trades in Window: {executionQuality.trades_total}</p>
            <p>Trades With Fills: {executionQuality.trades_with_fills}</p>
            <p>Fill Events: {executionQuality.fill_events}</p>
            <p>Avg Slippage (bps): {executionQuality.avg_slippage_bps?.toFixed(2) ?? "-"}</p>
            <p>Median Slippage (bps): {executionQuality.median_slippage_bps?.toFixed(2) ?? "-"}</p>
            <p>Avg First Fill Latency (ms): {executionQuality.avg_first_fill_latency_ms?.toFixed(0) ?? "-"}</p>
          </>
        ) : (
          <p className="muted">{executionQualityQuery.isLoading ? "Loading execution quality..." : "No execution metrics yet"}</p>
        )}
      </section>
      <section className="card">
        <h3>Trade Fill Timeline</h3>
        {!selectedTradeId ? (
          <p className="muted">Select a trade to inspect fill events.</p>
        ) : tradeFillsQuery.isLoading ? (
          <p className="muted">Loading fill timeline...</p>
        ) : !tradeFills.length ? (
          <p className="muted">No fill events for trade #{selectedTradeId}.</p>
        ) : (
          <>
            <p className="muted">Trade #{selectedTradeId}</p>
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Status</th>
                  <th>Qty</th>
                  <th>Fill</th>
                  <th>Expected</th>
                  <th>Slippage (bps)</th>
                </tr>
              </thead>
              <tbody>
                {tradeFills.map((fill) => (
                  <tr key={fill.id}>
                    <td>{new Date(fill.fill_timestamp).toLocaleString()}</td>
                    <td>{fill.status}</td>
                    <td>{fill.qty}</td>
                    <td>{fill.fill_price}</td>
                    <td>{fill.expected_price ?? "-"}</td>
                    <td>{fill.slippage_bps?.toFixed(2) ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>
      {dashboardError && <p style={{ color: "#991b1b" }}>{dashboardError}</p>}
    </div>
  );
}
