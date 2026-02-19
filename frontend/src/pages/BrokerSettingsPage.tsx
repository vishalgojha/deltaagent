import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { brokerPreflight, connectBroker, getStatus } from "../api/endpoints";
import type { BrokerPreflight } from "../types";

type Props = { clientId: string };

export function BrokerSettingsPage({ clientId }: Props) {
  const queryClient = useQueryClient();
  const [useSavedCredentials, setUseSavedCredentials] = useState(true);
  const [ibkrHost, setIbkrHost] = useState("host.docker.internal");
  const [ibkrPort, setIbkrPort] = useState("4002");
  const [ibkrClientId, setIbkrClientId] = useState("901");
  const [underlyingInstrument, setUnderlyingInstrument] = useState("IND");
  const [delayedMarketData, setDelayedMarketData] = useState(true);
  const [connectError, setConnectError] = useState("");
  const [connectResult, setConnectResult] = useState("");
  const [preflightError, setPreflightError] = useState("");
  const [preflightResult, setPreflightResult] = useState<BrokerPreflight | null>(null);

  const healthQuery = useQuery({
    queryKey: ["agent-status", clientId],
    queryFn: () => getStatus(clientId)
  });

  const connectMutation = useMutation({
    mutationFn: (credentials?: Record<string, unknown>) => connectBroker(clientId, credentials),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["agent-status", clientId] });
    }
  });

  const preflightMutation = useMutation({
    mutationFn: (credentials?: Record<string, unknown>) => brokerPreflight(clientId, credentials)
  });

  function buildCredentials(): { credentials?: Record<string, unknown>; error?: string } {
    if (useSavedCredentials) return { credentials: undefined };
    const port = Number(ibkrPort);
    const clientIdValue = Number(ibkrClientId);
    if (!ibkrHost.trim()) return { error: "IBKR host is required" };
    if (!Number.isFinite(port)) return { error: "IBKR port must be a valid number" };
    if (!Number.isFinite(clientIdValue)) return { error: "Client ID must be a valid number" };
    return {
      credentials: {
        host: ibkrHost.trim(),
        port,
        client_id: clientIdValue,
        underlying_instrument: underlyingInstrument.trim() || "IND",
        delayed_market_data: delayedMarketData
      }
    };
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setConnectError("");
    setConnectResult("");
    setPreflightError("");

    const built = buildCredentials();
    if (built.error) {
      setConnectError(built.error);
      return;
    }

    try {
      const result = await connectMutation.mutateAsync(built.credentials);
      setConnectResult(`Connection successful: connected=${String(result.connected)} broker=${String(result.broker)}`);
    } catch (err) {
      setConnectError(err instanceof Error ? err.message : "Broker connection failed");
    }
  }

  async function onPreflight() {
    setPreflightError("");
    const built = buildCredentials();
    if (built.error) {
      setPreflightError(built.error);
      return;
    }
    try {
      const result = await preflightMutation.mutateAsync(built.credentials);
      setPreflightResult(result);
    } catch (err) {
      setPreflightError(err instanceof Error ? err.message : "Preflight failed");
    }
  }

  return (
    <div className="grid">
      <section className="card">
        <div className="section-head">
          <div>
            <h3>Broker Settings</h3>
            <p className="muted">Reconnect broker access, run diagnostics, and inspect health state.</p>
          </div>
        </div>
        <div className="metric-grid" style={{ marginTop: 12 }}>
          <article className="metric-card">
            <p className="metric-label">Healthy</p>
            <p className="metric-value">{String(healthQuery.data?.healthy ?? "-")}</p>
          </article>
          <article className="metric-card">
            <p className="metric-label">Agent Mode</p>
            <p className="metric-value">{healthQuery.data?.mode ?? "-"}</p>
          </article>
          <article className="metric-card">
            <p className="metric-label">Last Action</p>
            <p className="metric-value">{healthQuery.data?.last_action ?? "none"}</p>
          </article>
          <article className="metric-card">
            <p className="metric-label">Preflight</p>
            <p className="metric-value">{preflightResult ? (preflightResult.ok ? "PASS" : "FAIL") : "not run"}</p>
          </article>
        </div>
      </section>

      <div className="grid grid-2">
      <section className="card">
        <h3>Broker Connection Health</h3>
        {healthQuery.isLoading ? (
          <p className="muted">Loading broker health...</p>
        ) : (
          <>
            <p>Healthy: {String(healthQuery.data?.healthy ?? "-")}</p>
            <p>Mode: {healthQuery.data?.mode ?? "-"}</p>
            <p>Last Action: {healthQuery.data?.last_action ?? "none"}</p>
          </>
        )}
        <div className="row">
          <button
            type="button"
            className="secondary"
            onClick={() => void healthQuery.refetch()}
            disabled={healthQuery.isFetching}
          >
            {healthQuery.isFetching ? "Refreshing..." : "Refresh Health"}
          </button>
        </div>
        {healthQuery.error && (
          <p style={{ color: "#991b1b" }}>
            {healthQuery.error instanceof Error ? healthQuery.error.message : "Failed to fetch health"}
          </p>
        )}
      </section>

      <section className="card">
        <h3>Broker Credentials & Reconnect</h3>
        <form className="grid" onSubmit={onSubmit}>
          <label className="row">
            <input
              type="checkbox"
              checked={useSavedCredentials}
              onChange={(e) => setUseSavedCredentials(e.target.checked)}
            />
            Use saved credentials
          </label>
          {useSavedCredentials ? (
            <p className="muted" style={{ margin: 0 }}>
              Reconnect using encrypted credentials stored in your account.
            </p>
          ) : (
            <div className="grid grid-2">
              <label className="grid">
                IBKR Host
                <input value={ibkrHost} onChange={(e) => setIbkrHost(e.target.value)} placeholder="host.docker.internal" />
              </label>
              <label className="grid">
                IBKR Port
                <input value={ibkrPort} onChange={(e) => setIbkrPort(e.target.value)} inputMode="numeric" placeholder="4002" />
              </label>
              <label className="grid">
                Client ID
                <input value={ibkrClientId} onChange={(e) => setIbkrClientId(e.target.value)} inputMode="numeric" placeholder="901" />
              </label>
              <label className="grid">
                Underlying Instrument
                <input
                  value={underlyingInstrument}
                  onChange={(e) => setUnderlyingInstrument(e.target.value)}
                  placeholder="IND"
                />
              </label>
              <label className="row">
                <input
                  type="checkbox"
                  checked={delayedMarketData}
                  onChange={(e) => setDelayedMarketData(e.target.checked)}
                />
                Use delayed market data
              </label>
            </div>
          )}
          <button type="submit" disabled={connectMutation.isPending}>
            {connectMutation.isPending ? "Connecting..." : "Reconnect Broker"}
          </button>
          <button type="button" className="secondary" onClick={() => void onPreflight()} disabled={preflightMutation.isPending}>
            {preflightMutation.isPending ? "Running Preflight..." : "Run Preflight"}
          </button>
        </form>
        {connectResult && <p style={{ color: "#166534" }}>{connectResult}</p>}
        {connectError && <p style={{ color: "#991b1b" }}>{connectError}</p>}
        {preflightError && <p style={{ color: "#991b1b" }}>{preflightError}</p>}
      </section>
      </div>

      <section className="card">
        <h3>Broker Preflight Checklist</h3>
        {!preflightResult ? (
          <p className="muted">Run preflight to validate credentials, socket reachability, and market data.</p>
        ) : (
          <div className="grid">
            <p>
              Overall:{" "}
              <strong style={{ color: preflightResult.ok ? "#166534" : "#991b1b" }}>
                {preflightResult.ok ? "PASS" : "FAIL"}
              </strong>
            </p>
            {preflightResult.checks.map((check) => {
              const color = check.status === "pass" ? "#166534" : check.status === "warn" ? "#92400e" : "#991b1b";
              return (
                <div key={check.key} className="preflight-check">
                  <strong style={{ color }}>{check.title}</strong>
                  <span className="muted">{check.detail}</span>
                </div>
              );
            })}
            {preflightResult.blocking_issues.length > 0 && (
              <div>
                <strong style={{ color: "#991b1b" }}>Blocking issues</strong>
                {preflightResult.blocking_issues.map((item, idx) => (
                  <p key={`${item}-${idx}`} className="muted">
                    {item}
                  </p>
                ))}
              </div>
            )}
            {preflightResult.warnings.length > 0 && (
              <div>
                <strong style={{ color: "#92400e" }}>Warnings</strong>
                {preflightResult.warnings.map((item, idx) => (
                  <p key={`${item}-${idx}`} className="muted">
                    {item}
                  </p>
                ))}
              </div>
            )}
            {preflightResult.fix_hints.length > 0 && (
              <div>
                <strong>Fix hints</strong>
                {preflightResult.fix_hints.map((item, idx) => (
                  <p key={`${item}-${idx}`} className="muted">
                    {item}
                  </p>
                ))}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
