import { FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  createExecutionIncidentNote,
  getExecutionIncidents,
  getExecutionQuality,
  getPositions,
  getRiskParameters,
  getStatus,
  getTradeFills,
  getTrades,
  setMode,
  updateAgentParameters,
  updateRiskParameters
} from "../api/endpoints";
import {
  RISK_PRESETS,
  type RiskParameters,
  type RiskField,
  type RiskFormErrors,
  type RiskFormValues,
  toRiskFormValues,
  validateRiskValues
} from "../features/riskControls";
import type { AgentStatus, ExecutionIncidentNote, ExecutionQuality, Position, Trade, TradeFill } from "../types";

type Props = { clientId: string };
type ExecutionAlertSeverity = "warning" | "critical";
type AutoRemediationAction = "none" | "apply_conservative" | "pause_autonomous";
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
type AutoRemediationFormValues = {
  enabled: boolean;
  warningAction: AutoRemediationAction;
  criticalAction: AutoRemediationAction;
  cooldownMinutes: string;
  maxActionsPerHour: string;
};
type AutoRemediationFormErrors = {
  cooldownMinutes?: string;
  maxActionsPerHour?: string;
};

const AUTO_REMEDIATION_ACTION_LABELS: Record<AutoRemediationAction, string> = {
  none: "No Action",
  apply_conservative: "Apply Conservative Preset",
  pause_autonomous: "Pause Autonomous Mode"
};
const AUTO_REMEDIATION_ACTIONS: AutoRemediationAction[] = ["none", "apply_conservative", "pause_autonomous"];

const RUNBOOK_BY_ALERT: Record<string, string[]> = {
  "avg-slippage": [
    "Pause autonomous mode to stop new executions while pricing is reviewed.",
    "Compare expected vs filled prices on the last 5 fills and validate market-data freshness.",
    "Apply the Conservative risk preset until slippage returns under warning threshold."
  ],
  "first-fill-latency": [
    "Pause autonomous mode and verify broker/API latency from the connectivity console.",
    "Retry broker session and inspect order lifecycle timestamps in the fill timeline.",
    "Escalate to broker support if latency remains above threshold for 3+ trades."
  ],
  "fill-coverage": [
    "Pause autonomous mode and inspect partially filled/open orders for stale routing.",
    "Reduce order aggressiveness using the Conservative preset while monitoring coverage recovery.",
    "Record an incident note with trade IDs impacted and mitigation steps taken."
  ]
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

function normalizeAutoRemediationAction(raw: unknown, fallback: AutoRemediationAction): AutoRemediationAction {
  const value = typeof raw === "string" ? raw.trim().toLowerCase() : "";
  if (value === "none" || value === "apply_conservative" || value === "pause_autonomous") {
    return value;
  }
  return fallback;
}

function parseBoolean(raw: unknown, fallback: boolean): boolean {
  if (typeof raw === "boolean") return raw;
  if (typeof raw === "string") {
    const normalized = raw.trim().toLowerCase();
    if (normalized === "true" || normalized === "1" || normalized === "yes" || normalized === "on") return true;
    if (normalized === "false" || normalized === "0" || normalized === "no" || normalized === "off") return false;
  }
  if (typeof raw === "number") return raw !== 0;
  return fallback;
}

function toAutoRemediationFormValues(parameters: Record<string, unknown> | null | undefined): AutoRemediationFormValues {
  return {
    enabled: parseBoolean(parameters?.auto_remediation_enabled, false),
    warningAction: normalizeAutoRemediationAction(parameters?.auto_remediation_warning_action, "none"),
    criticalAction: normalizeAutoRemediationAction(parameters?.auto_remediation_critical_action, "pause_autonomous"),
    cooldownMinutes: String(parameters?.auto_remediation_cooldown_minutes ?? 20),
    maxActionsPerHour: String(parameters?.auto_remediation_max_actions_per_hour ?? 2)
  };
}

function validateAutoRemediationValues(
  values: AutoRemediationFormValues
): { parsed: Record<string, unknown> | null; errors: AutoRemediationFormErrors } {
  const errors: AutoRemediationFormErrors = {};
  const cooldown = Number(values.cooldownMinutes.trim());
  const maxActions = Number(values.maxActionsPerHour.trim());

  if (!Number.isInteger(cooldown) || cooldown < 1 || cooldown > 1440) {
    errors.cooldownMinutes = "Cooldown must be an integer between 1 and 1440 minutes";
  }
  if (!Number.isInteger(maxActions) || maxActions < 1 || maxActions > 50) {
    errors.maxActionsPerHour = "Max actions/hour must be an integer between 1 and 50";
  }

  if (Object.keys(errors).length > 0) {
    return { parsed: null, errors };
  }

  return {
    parsed: {
      auto_remediation_enabled: values.enabled,
      auto_remediation_warning_action: values.warningAction,
      auto_remediation_critical_action: values.criticalAction,
      auto_remediation_cooldown_minutes: cooldown,
      auto_remediation_max_actions_per_hour: maxActions
    },
    errors
  };
}

export function DashboardPage({ clientId }: Props) {
  const [riskValues, setRiskValues] = useState<RiskFormValues>(toRiskFormValues(null));
  const [riskErrors, setRiskErrors] = useState<RiskFormErrors>({});
  const [riskStatus, setRiskStatus] = useState("");
  const [riskServerError, setRiskServerError] = useState("");
  const [selectedTradeId, setSelectedTradeId] = useState<number | null>(null);
  const [executionActionStatus, setExecutionActionStatus] = useState("");
  const [executionActionError, setExecutionActionError] = useState("");
  const [incidentDrafts, setIncidentDrafts] = useState<Record<string, string>>({});
  const [autoRemediationValues, setAutoRemediationValues] = useState<AutoRemediationFormValues>(
    toAutoRemediationFormValues(null)
  );
  const [autoRemediationErrors, setAutoRemediationErrors] = useState<AutoRemediationFormErrors>({});
  const [autoRemediationStatus, setAutoRemediationStatus] = useState("");
  const [autoRemediationServerError, setAutoRemediationServerError] = useState("");

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
  const autoRemediationRuntime = executionQuality?.auto_remediation ?? null;
  const incidentNotesQuery = useQuery({
    queryKey: ["execution-incidents", clientId],
    queryFn: () => getExecutionIncidents(clientId, 10)
  });
  const incidentNotes: ExecutionIncidentNote[] = incidentNotesQuery.data ?? [];
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
      setRiskValues(toRiskFormValues(riskQuery.data.risk_parameters as Partial<RiskParameters>));
      setAutoRemediationValues(toAutoRemediationFormValues(riskQuery.data.risk_parameters));
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
  const pauseAutonomousMutation = useMutation({
    mutationFn: () => setMode(clientId, "confirmation")
  });
  const applyConservativeMutation = useMutation({
    mutationFn: () => updateRiskParameters(clientId, RISK_PRESETS.conservative)
  });
  const createIncidentMutation = useMutation({
    mutationFn: (payload: {
      alert_id: string;
      severity: ExecutionAlertSeverity;
      label: string;
      note: string;
      context: Record<string, unknown>;
    }) => createExecutionIncidentNote(clientId, payload)
  });
  const saveAutoRemediationMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => updateAgentParameters(clientId, payload)
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

  function onAutoRemediationFieldChange<K extends keyof AutoRemediationFormValues>(
    field: K,
    value: AutoRemediationFormValues[K]
  ) {
    setAutoRemediationValues((prev) => ({ ...prev, [field]: value }));
    setAutoRemediationErrors({});
    setAutoRemediationStatus("");
    setAutoRemediationServerError("");
  }

  async function onAutoRemediationSubmit(event: FormEvent) {
    event.preventDefault();
    setAutoRemediationStatus("");
    setAutoRemediationServerError("");

    const validation = validateAutoRemediationValues(autoRemediationValues);
    if (!validation.parsed) {
      setAutoRemediationErrors(validation.errors);
      return;
    }

    setAutoRemediationErrors({});
    try {
      const response = await saveAutoRemediationMutation.mutateAsync(validation.parsed);
      setAutoRemediationValues(toAutoRemediationFormValues(response.risk_parameters));
      setAutoRemediationStatus("Auto-remediation policy updated");
    } catch (err) {
      setAutoRemediationServerError(err instanceof Error ? err.message : "Failed to update auto-remediation policy");
    }
  }

  function clearExecutionActionMessages() {
    setExecutionActionStatus("");
    setExecutionActionError("");
  }

  async function onPauseAutonomous(alert: ExecutionAlert) {
    clearExecutionActionMessages();
    try {
      await pauseAutonomousMutation.mutateAsync();
      await dashboardQuery.refetch();
      setExecutionActionStatus(`Autonomous mode paused from ${alert.label} alert.`);
    } catch (err) {
      setExecutionActionError(err instanceof Error ? err.message : "Failed to pause autonomous mode");
    }
  }

  async function onApplyConservative(alert: ExecutionAlert) {
    clearExecutionActionMessages();
    try {
      const response = await applyConservativeMutation.mutateAsync();
      setRiskValues(toRiskFormValues(response.risk_parameters));
      setRiskErrors({});
      setRiskStatus("Conservative preset applied from execution alert.");
      setExecutionActionStatus(`Conservative preset applied from ${alert.label} alert.`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to apply conservative preset";
      setRiskServerError(message);
      setExecutionActionError(message);
    }
  }

  function onIncidentDraftChange(alertId: string, note: string) {
    setIncidentDrafts((prev) => ({ ...prev, [alertId]: note }));
  }

  async function onCreateIncident(alert: ExecutionAlert) {
    clearExecutionActionMessages();
    const trimmed = (incidentDrafts[alert.id] ?? "").trim();
    const note = trimmed || `${alert.label}: ${alert.message}`;
    try {
      await createIncidentMutation.mutateAsync({
        alert_id: alert.id,
        severity: alert.severity,
        label: alert.label,
        note,
        context: {
          alert_message: alert.message,
          source: "dashboard_execution_alert",
          generated_at: new Date().toISOString()
        }
      });
      setIncidentDrafts((prev) => ({ ...prev, [alert.id]: "" }));
      await incidentNotesQuery.refetch();
      setExecutionActionStatus(`Incident note created for ${alert.label}.`);
    } catch (err) {
      setExecutionActionError(err instanceof Error ? err.message : "Failed to create incident note");
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
        <div className="execution-policy-panel">
          <h4>Auto-Remediation Policy</h4>
          <form className="grid" onSubmit={onAutoRemediationSubmit}>
            <label className="row">
              <input
                type="checkbox"
                checked={autoRemediationValues.enabled}
                onChange={(event) => onAutoRemediationFieldChange("enabled", event.target.checked)}
                style={{ width: "auto" }}
              />
              Enable Auto-Remediation
            </label>
            <div className="grid grid-2">
              <label className="grid">
                Warning Action
                <select
                  value={autoRemediationValues.warningAction}
                  onChange={(event) =>
                    onAutoRemediationFieldChange(
                      "warningAction",
                      normalizeAutoRemediationAction(event.target.value, autoRemediationValues.warningAction)
                    )
                  }
                >
                  {AUTO_REMEDIATION_ACTIONS.map((action) => (
                    <option key={action} value={action}>
                      {AUTO_REMEDIATION_ACTION_LABELS[action]}
                    </option>
                  ))}
                </select>
              </label>
              <label className="grid">
                Critical Action
                <select
                  value={autoRemediationValues.criticalAction}
                  onChange={(event) =>
                    onAutoRemediationFieldChange(
                      "criticalAction",
                      normalizeAutoRemediationAction(event.target.value, autoRemediationValues.criticalAction)
                    )
                  }
                >
                  {AUTO_REMEDIATION_ACTIONS.map((action) => (
                    <option key={action} value={action}>
                      {AUTO_REMEDIATION_ACTION_LABELS[action]}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="grid grid-2">
              <label className="grid">
                Cooldown (minutes)
                <input
                  value={autoRemediationValues.cooldownMinutes}
                  onChange={(event) => onAutoRemediationFieldChange("cooldownMinutes", event.target.value)}
                  inputMode="numeric"
                />
                {autoRemediationErrors.cooldownMinutes && (
                  <span className="field-error">{autoRemediationErrors.cooldownMinutes}</span>
                )}
              </label>
              <label className="grid">
                Max Actions Per Hour
                <input
                  value={autoRemediationValues.maxActionsPerHour}
                  onChange={(event) => onAutoRemediationFieldChange("maxActionsPerHour", event.target.value)}
                  inputMode="numeric"
                />
                {autoRemediationErrors.maxActionsPerHour && (
                  <span className="field-error">{autoRemediationErrors.maxActionsPerHour}</span>
                )}
              </label>
            </div>
            <button type="submit" disabled={saveAutoRemediationMutation.isPending}>
              {saveAutoRemediationMutation.isPending ? "Saving..." : "Save Auto-Remediation Policy"}
            </button>
            {autoRemediationStatus && <p style={{ color: "#166534", margin: 0 }}>{autoRemediationStatus}</p>}
            {autoRemediationServerError && <p style={{ color: "#991b1b", margin: 0 }}>{autoRemediationServerError}</p>}
          </form>
          {autoRemediationRuntime && (
            <div className="policy-grid" style={{ marginTop: 10 }}>
              <article className="policy-chip">
                <p className="metric-label">Outcome</p>
                <p className="metric-value">{autoRemediationRuntime.outcome}</p>
              </article>
              <article className="policy-chip">
                <p className="metric-label">Planned Action</p>
                <p className="metric-value">
                  {AUTO_REMEDIATION_ACTION_LABELS[
                    normalizeAutoRemediationAction(autoRemediationRuntime.planned_action, "none")
                  ]}
                </p>
              </article>
              <article className="policy-chip">
                <p className="metric-label">Last Action</p>
                <p className="metric-value">
                  {autoRemediationRuntime.last_action
                    ? AUTO_REMEDIATION_ACTION_LABELS[
                        normalizeAutoRemediationAction(autoRemediationRuntime.last_action, "none")
                      ]
                    : "-"}
                </p>
              </article>
              <article className="policy-chip">
                <p className="metric-label">Cooldown</p>
                <p className="metric-value">
                  {autoRemediationRuntime.cooldown_remaining_seconds > 0
                    ? `${autoRemediationRuntime.cooldown_remaining_seconds}s`
                    : "ready"}
                </p>
              </article>
              <article className="policy-chip">
                <p className="metric-label">Hourly Budget</p>
                <p className="metric-value">
                  {autoRemediationRuntime.actions_last_hour}/{autoRemediationRuntime.max_actions_per_hour}
                </p>
              </article>
            </div>
          )}
          {autoRemediationRuntime?.message && (
            <p className="muted" style={{ marginTop: 8 }}>
              {autoRemediationRuntime.message}
            </p>
          )}
        </div>
        <p className="muted" style={{ marginBottom: 8 }}>
          Thresholds: Slippage {executionThresholds.slippageWarnBps}/{executionThresholds.slippageCriticalBps} bps,
          Latency {executionThresholds.latencyWarnMs}/{executionThresholds.latencyCriticalMs} ms,
          Fill Coverage {executionThresholds.fillCoverageWarnPct}/{executionThresholds.fillCoverageCriticalPct}%.
        </p>
        {executionActionStatus && <p style={{ color: "#166534", margin: "0 0 8px 0" }}>{executionActionStatus}</p>}
        {executionActionError && <p style={{ color: "#991b1b", margin: "0 0 8px 0" }}>{executionActionError}</p>}
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
                <div className="execution-alert-actions">
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => onPauseAutonomous(alert)}
                    disabled={pauseAutonomousMutation.isPending || status?.mode !== "autonomous"}
                  >
                    {status?.mode === "autonomous" ? "Pause Autonomous" : "Autonomous Paused"}
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => onApplyConservative(alert)}
                    disabled={applyConservativeMutation.isPending}
                  >
                    {applyConservativeMutation.isPending ? "Applying..." : "Apply Conservative Preset"}
                  </button>
                </div>
                <div className="execution-incident-note">
                  <label className="grid">
                    Incident Note
                    <textarea
                      value={incidentDrafts[alert.id] ?? ""}
                      onChange={(event) => onIncidentDraftChange(alert.id, event.target.value)}
                      placeholder="Summarize what happened and what you changed..."
                      rows={2}
                    />
                  </label>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => onCreateIncident(alert)}
                    disabled={createIncidentMutation.isPending}
                  >
                    {createIncidentMutation.isPending ? "Saving..." : "Create Incident Note"}
                  </button>
                </div>
                <div className="execution-runbook">
                  <h4>What To Do Now</h4>
                  <ol>
                    {(RUNBOOK_BY_ALERT[alert.id] ?? []).map((step) => (
                      <li key={step}>{step}</li>
                    ))}
                  </ol>
                </div>
              </li>
            ))}
          </ul>
        )}
        {incidentNotes.length > 0 && (
          <div className="execution-incident-history">
            <h4>Recent Incident Notes</h4>
            <ul>
              {incidentNotes.slice(0, 5).map((item) => (
                <li key={item.id}>
                  <strong>{item.label}</strong> [{item.severity}] - {item.note}
                </li>
              ))}
            </ul>
          </div>
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
            <p>Backfilled Trades: {executionQuality.backfilled_trades}</p>
            <p>Avg Slippage (bps): {executionQuality.avg_slippage_bps?.toFixed(2) ?? "-"}</p>
            <p>Median Slippage (bps): {executionQuality.median_slippage_bps?.toFixed(2) ?? "-"}</p>
            <p>Avg First Fill Latency (ms): {executionQuality.avg_first_fill_latency_ms?.toFixed(0) ?? "-"}</p>
            {executionQuality.backfilled_trades > 0 && (
              <p className="muted">Includes backfilled metrics from legacy filled trades without fill events.</p>
            )}
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
