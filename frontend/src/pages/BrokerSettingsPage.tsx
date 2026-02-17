import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { connectBroker, getStatus } from "../api/endpoints";

type Props = { clientId: string };

export function BrokerSettingsPage({ clientId }: Props) {
  const [credsJson, setCredsJson] = useState("");
  const [connectError, setConnectError] = useState("");
  const [connectResult, setConnectResult] = useState("");

  const healthQuery = useQuery({
    queryKey: ["agent-status", clientId],
    queryFn: () => getStatus(clientId)
  });

  const connectMutation = useMutation({
    mutationFn: (credentials?: Record<string, unknown>) => connectBroker(clientId, credentials)
  });

  useEffect(() => {
    if (connectMutation.error) {
      setConnectError(connectMutation.error instanceof Error ? connectMutation.error.message : "Broker connection failed");
    }
  }, [connectMutation.error]);

  useEffect(() => {
    if (connectMutation.data) {
      setConnectResult(
        `Connection successful: connected=${String(connectMutation.data.connected)} broker=${String(connectMutation.data.broker)}`
      );
      void healthQuery.refetch();
    }
  }, [connectMutation.data, healthQuery]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setConnectError("");
    setConnectResult("");

    let parsed: Record<string, unknown> | undefined;
    const trimmed = credsJson.trim();
    if (trimmed) {
      try {
        const payload = JSON.parse(trimmed) as unknown;
        if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
          setConnectError("Broker credentials must be a JSON object");
          return;
        }
        parsed = payload as Record<string, unknown>;
      } catch {
        setConnectError("Broker credentials must be valid JSON");
        return;
      }
    }

    try {
      await connectMutation.mutateAsync(parsed);
    } catch {
      // handled by mutation state
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
          <label className="grid">
            Broker Credentials (JSON, optional)
            <textarea
              rows={10}
              value={credsJson}
              onChange={(e) => setCredsJson(e.target.value)}
              placeholder='{"host":"localhost","port":4002,"client_id":1}'
            />
          </label>
          <p className="muted" style={{ margin: 0 }}>
            Leave blank to reconnect with saved credentials.
          </p>
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
