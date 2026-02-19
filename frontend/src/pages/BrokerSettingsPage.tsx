import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { connectBroker, getStatus } from "../api/endpoints";

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

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setConnectError("");
    setConnectResult("");

    let credentials: Record<string, unknown> | undefined;
    if (!useSavedCredentials) {
      const port = Number(ibkrPort);
      const clientIdValue = Number(ibkrClientId);
      if (!ibkrHost.trim()) {
        setConnectError("IBKR host is required");
        return;
      }
      if (!Number.isFinite(port)) {
        setConnectError("IBKR port must be a valid number");
        return;
      }
      if (!Number.isFinite(clientIdValue)) {
        setConnectError("Client ID must be a valid number");
        return;
      }
      credentials = {
        host: ibkrHost.trim(),
        port,
        client_id: clientIdValue,
        underlying_instrument: underlyingInstrument.trim() || "IND",
        delayed_market_data: delayedMarketData
      };
    }

    try {
      const result = await connectMutation.mutateAsync(credentials);
      setConnectResult(`Connection successful: connected=${String(result.connected)} broker=${String(result.broker)}`);
    } catch (err) {
      setConnectError(err instanceof Error ? err.message : "Broker connection failed");
    }
  }

  return (
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
        </form>
        {connectResult && <p style={{ color: "#166534" }}>{connectResult}</p>}
        {connectError && <p style={{ color: "#991b1b" }}>{connectError}</p>}
      </section>
    </div>
  );
}
