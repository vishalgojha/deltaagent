import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { login } from "../api/endpoints";
import { saveSession } from "../store/session";

export function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const data = await login(email, password);
      saveSession(data.access_token, data.client_id);
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-shell">
      <section className="auth-hero">
        <span className="auth-chip">FUTURES OPTIONS</span>
        <h1 className="auth-title">Delta Neutral Trading Agent</h1>
        <p className="auth-subtitle">
          Monitor Greeks, review proposals, and execute risk-governed decisions from one control plane.
        </p>
        <p className="auth-branding">Built by Chaos Craft Labs</p>
      </section>

      <section className="auth-form-wrap">
        <div className="card auth-card">
          <h2>Sign In</h2>
          <form onSubmit={onSubmit} className="grid">
            <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email" />
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="password"
              type="password"
            />
            <button disabled={loading}>{loading ? "Signing in..." : "Sign in"}</button>
          </form>
          <p className="muted">
            New client? <Link to="/onboard">Create account</Link>
          </p>
          {error && <p style={{ color: "#991b1b" }}>{error}</p>}
        </div>
      </section>
    </div>
  );
}
