import { FormEvent, useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { connectBroker, login, onboardClient } from "../api/endpoints";
import { saveSession } from "../store/session";

const DEFAULT_RISK = JSON.stringify(
  {
    delta_threshold: 0.2,
    max_size: 10,
    max_loss: 5000,
    max_open_positions: 20
  },
  null,
  2
);

const DEFAULT_IBKR = JSON.stringify(
  {
    host: "localhost",
    port: 4002,
    client_id: 1,
    underlying_instrument: "IND"
  },
  null,
  2
);

const DEFAULT_PHILLIP = JSON.stringify(
  {
    client_id: "",
    client_secret: ""
  },
  null,
  2
);

export function OnboardingPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [brokerType, setBrokerType] = useState<"ibkr" | "phillip">("ibkr");
  const [subscriptionTier, setSubscriptionTier] = useState("basic");
  const [riskJson, setRiskJson] = useState(DEFAULT_RISK);
  const [credsJson, setCredsJson] = useState(DEFAULT_IBKR);
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

  const placeholderCreds = useMemo(
    () => (brokerType === "ibkr" ? DEFAULT_IBKR : DEFAULT_PHILLIP),
    [brokerType]
  );

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const brokerCreds = JSON.parse(credsJson) as Record<string, unknown>;
      const riskParameters = JSON.parse(riskJson) as Record<string, unknown>;
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
                  setCredsJson(next === "ibkr" ? DEFAULT_IBKR : DEFAULT_PHILLIP);
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

            <label>
              Broker Credentials (JSON)
              <textarea
                rows={8}
                value={credsJson}
                placeholder={placeholderCreds}
                onChange={(e) => setCredsJson(e.target.value)}
              />
            </label>

            <label>
              Risk Parameters (JSON)
              <textarea rows={8} value={riskJson} onChange={(e) => setRiskJson(e.target.value)} />
            </label>

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
