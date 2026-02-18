import { FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { getPositions, getRiskParameters, getStatus, getTrades, updateRiskParameters } from "../api/endpoints";
import {
  RISK_PRESETS,
  type RiskParameters,
  type RiskField,
  type RiskFormErrors,
  type RiskFormValues,
  toRiskFormValues,
  validateRiskValues
} from "../features/riskControls";
import type { AgentStatus, Position, Trade } from "../types";

type Props = { clientId: string };

export function DashboardPage({ clientId }: Props) {
  const [riskValues, setRiskValues] = useState<RiskFormValues>(toRiskFormValues(null));
  const [riskErrors, setRiskErrors] = useState<RiskFormErrors>({});
  const [riskStatus, setRiskStatus] = useState("");
  const [riskServerError, setRiskServerError] = useState("");

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

      <section className="card">
        <h3>Risk Controls</h3>
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
                <span style={{ color: "#991b1b", fontSize: 13 }}>{riskErrors.delta_threshold}</span>
              )}
            </label>

            <label className="grid">
              Max Size
              <input
                value={riskValues.max_size}
                onChange={(e) => onRiskFieldChange("max_size", e.target.value)}
                inputMode="numeric"
              />
              {riskErrors.max_size && <span style={{ color: "#991b1b", fontSize: 13 }}>{riskErrors.max_size}</span>}
            </label>

            <label className="grid">
              Max Loss
              <input
                value={riskValues.max_loss}
                onChange={(e) => onRiskFieldChange("max_loss", e.target.value)}
                inputMode="decimal"
              />
              {riskErrors.max_loss && <span style={{ color: "#991b1b", fontSize: 13 }}>{riskErrors.max_loss}</span>}
            </label>

            <label className="grid">
              Max Open Positions
              <input
                value={riskValues.max_open_positions}
                onChange={(e) => onRiskFieldChange("max_open_positions", e.target.value)}
                inputMode="numeric"
              />
              {riskErrors.max_open_positions && (
                <span style={{ color: "#991b1b", fontSize: 13 }}>{riskErrors.max_open_positions}</span>
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

      <section className="card" style={{ gridColumn: "1 / -1" }}>
        <h3>Recent Trades</h3>
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
              <tr key={t.id}>
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
      {dashboardError && <p style={{ color: "#991b1b" }}>{dashboardError}</p>}
    </div>
  );
}
