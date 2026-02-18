import { FormEvent, useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { connectBroker, login, onboardClient } from "../api/endpoints";
import { saveSession } from "../store/session";

const DEFAULT_RISK = {
  delta_threshold: "0.2",
  max_size: "10",
  max_loss: "5000",
  max_open_positions: "20"
};

const DEFAULT_IBKR = {
  host: "localhost",
  port: "4002",
  client_id: "1",
  underlying_instrument: "IND"
};

const DEFAULT_PHILLIP = {
  client_id: "",
  client_secret: ""
};

export function OnboardingPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [brokerType, setBrokerType] = useState<"ibkr" | "phillip">("ibkr");
  const [subscriptionTier, setSubscriptionTier] = useState("basic");
  const [risk, setRisk] = useState(DEFAULT_RISK);
  const [ibkrCreds, setIbkrCreds] = useState(DEFAULT_IBKR);
  const [phillipCreds, setPhillipCreds] = useState(DEFAULT_PHILLIP);
  const [connectNow, setConnectNow] = useState(true);
  const [error, setError] = useState("");

  const onboardingMutation = useMutation({
    mutationFn: async (payload: {
      email: string;
      password: string;
      brokerType: "ibkr" | "phillip";
      brokerCreds: Record<string, unknown>;
      riskParameters: Record<string, unknown>;
      subscriptionTier: string;
      connectNow: boolean;
    }) => {
      const onboarded = await onboardClient({
        email: payload.email,
        password: payload.password,
        broker_type: payload.brokerType,
        broker_credentials: payload.brokerCreds,
        risk_parameters: payload.riskParameters,
        subscription_tier: payload.subscriptionTier
      });
      const auth = await login(payload.email, payload.password);
      if (payload.connectNow) {
        await connectBroker(onboarded.id, payload.brokerCreds);
      }
      return { auth };
    }
  });

  const activeBrokerSummary = useMemo(
    () => (brokerType === "ibkr" ? "IBKR gateway credentials" : "Phillip API credentials"),
    [brokerType]
  );

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const brokerCreds: Record<string, unknown> =
        brokerType === "ibkr"
          ? {
              host: ibkrCreds.host.trim(),
              port: Number(ibkrCreds.port),
              client_id: Number(ibkrCreds.client_id),
              underlying_instrument: ibkrCreds.underlying_instrument.trim() || "IND"
            }
          : {
              client_id: phillipCreds.client_id.trim(),
              client_secret: phillipCreds.client_secret
            };

      const riskParameters: Record<string, unknown> = {
        delta_threshold: Number(risk.delta_threshold),
        max_size: Number(risk.max_size),
        max_loss: Number(risk.max_loss),
        max_open_positions: Number(risk.max_open_positions)
      };

      if (brokerType === "ibkr") {
        if (!brokerCreds.host || !Number.isFinite(brokerCreds.port) || !Number.isFinite(brokerCreds.client_id)) {
          setError("Please enter valid IBKR host, port, and client ID");
          return;
        }
      } else if (!phillipCreds.client_id.trim() || !phillipCreds.client_secret.trim()) {
        setError("Please enter Phillip client ID and client secret");
        return;
      }

      if (
        !Number.isFinite(riskParameters.delta_threshold) ||
        !Number.isFinite(riskParameters.max_size) ||
        !Number.isFinite(riskParameters.max_loss) ||
        !Number.isFinite(riskParameters.max_open_positions)
      ) {
        setError("Risk parameters must be valid numbers");
        return;
      }

      const { auth } = await onboardingMutation.mutateAsync({
        email,
        password,
        brokerType,
        brokerCreds,
        riskParameters,
        subscriptionTier,
        connectNow
      });
      saveSession(auth.access_token, auth.client_id);
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Onboarding failed");
    }
  }

  return (
    <div className="auth-shell">
      <section className="auth-hero">
        <span className="auth-chip">ONBOARD CLIENT</span>
        <h1 className="auth-title">Launch A New Trading Tenant</h1>
        <p className="auth-subtitle">
          Configure broker access, assign risk limits, and create a secure client workspace in minutes.
        </p>
        <p className="auth-branding">Built by Chaos Craft Labs</p>
      </section>

      <section className="auth-form-wrap">
        <div className="card" style={{ width: "100%", maxWidth: 760 }}>
          <h2>Client Onboarding</h2>
          <form onSubmit={onSubmit} className="grid">
            <div className="row">
              <input
                style={{ flex: 1 }}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="client email"
              />
              <input
                style={{ flex: 1 }}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="password"
                type="password"
              />
            </div>

            <div className="row">
              <select
                value={brokerType}
                onChange={(e) => {
                  const next = e.target.value as "ibkr" | "phillip";
                  setBrokerType(next);
                }}
              >
                <option value="ibkr">IBKR</option>
                <option value="phillip">PhillipCapital</option>
              </select>
              <input
                value={subscriptionTier}
                onChange={(e) => setSubscriptionTier(e.target.value)}
                placeholder="subscription tier"
              />
              <label className="row">
                <input
                  type="checkbox"
                  checked={connectNow}
                  onChange={(e) => setConnectNow(e.target.checked)}
                />
                Connect broker now
              </label>
            </div>

            <p className="muted" style={{ margin: 0 }}>
              {activeBrokerSummary}
            </p>
            {brokerType === "ibkr" ? (
              <div className="grid grid-2">
                <label className="grid">
                  IBKR Host
                  <input
                    value={ibkrCreds.host}
                    onChange={(e) => setIbkrCreds((prev) => ({ ...prev, host: e.target.value }))}
                    placeholder="localhost"
                  />
                </label>
                <label className="grid">
                  IBKR Port
                  <input
                    value={ibkrCreds.port}
                    onChange={(e) => setIbkrCreds((prev) => ({ ...prev, port: e.target.value }))}
                    inputMode="numeric"
                    placeholder="4002"
                  />
                </label>
                <label className="grid">
                  Client ID
                  <input
                    value={ibkrCreds.client_id}
                    onChange={(e) => setIbkrCreds((prev) => ({ ...prev, client_id: e.target.value }))}
                    inputMode="numeric"
                    placeholder="1"
                  />
                </label>
                <label className="grid">
                  Underlying Instrument
                  <input
                    value={ibkrCreds.underlying_instrument}
                    onChange={(e) => setIbkrCreds((prev) => ({ ...prev, underlying_instrument: e.target.value }))}
                    placeholder="IND"
                  />
                </label>
              </div>
            ) : (
              <div className="grid grid-2">
                <label className="grid">
                  Phillip Client ID
                  <input
                    value={phillipCreds.client_id}
                    onChange={(e) => setPhillipCreds((prev) => ({ ...prev, client_id: e.target.value }))}
                    placeholder="client-id"
                  />
                </label>
                <label className="grid">
                  Phillip Client Secret
                  <input
                    type="password"
                    value={phillipCreds.client_secret}
                    onChange={(e) => setPhillipCreds((prev) => ({ ...prev, client_secret: e.target.value }))}
                    placeholder="client-secret"
                  />
                </label>
              </div>
            )}

            <div className="grid grid-2">
              <label className="grid">
                Delta Threshold
                <input
                  value={risk.delta_threshold}
                  onChange={(e) => setRisk((prev) => ({ ...prev, delta_threshold: e.target.value }))}
                  inputMode="decimal"
                />
              </label>
              <label className="grid">
                Max Size
                <input
                  value={risk.max_size}
                  onChange={(e) => setRisk((prev) => ({ ...prev, max_size: e.target.value }))}
                  inputMode="numeric"
                />
              </label>
              <label className="grid">
                Max Loss
                <input
                  value={risk.max_loss}
                  onChange={(e) => setRisk((prev) => ({ ...prev, max_loss: e.target.value }))}
                  inputMode="decimal"
                />
              </label>
              <label className="grid">
                Max Open Positions
                <input
                  value={risk.max_open_positions}
                  onChange={(e) => setRisk((prev) => ({ ...prev, max_open_positions: e.target.value }))}
                  inputMode="numeric"
                />
              </label>
            </div>

            <button disabled={onboardingMutation.isPending}>
              {onboardingMutation.isPending ? "Creating client..." : "Create Client"}
            </button>
          </form>
          {error && <p style={{ color: "#991b1b" }}>{error}</p>}
        </div>
      </section>
    </div>
  );
}
