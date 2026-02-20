import { FormEvent, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { login } from "../api/endpoints";
import { saveSession } from "../store/session";

function EyeIcon({ visible }: { visible: boolean }) {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
      {visible ? (
        <path d="M3 3l18 18M10.6 10.6a2 2 0 0 0 2.8 2.8M9.9 5.2A10 10 0 0 1 12 5c4.9 0 8.7 3.1 10 7-0.6 1.7-1.7 3.2-3.3 4.4M6.1 6.1C4.5 7.3 3.3 8.9 2.6 11c1.3 3.9 5.1 7 10 7 1 0 1.9-0.1 2.8-0.4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      ) : (
        <path d="M2 12c1.3-3.9 5.1-7 10-7s8.7 3.1 10 7c-1.3 3.9-5.1 7-10 7S3.3 15.9 2 12zm10-3a3 3 0 1 0 0 6 3 3 0 0 0 0-6z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      )}
    </svg>
  );
}

export function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");

  const loginMutation = useMutation({
    mutationFn: (payload: { email: string; password: string }) => login(payload.email, payload.password)
  });

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const data = await loginMutation.mutateAsync({ email, password });
      saveSession(data.access_token, data.client_id);
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    }
  }

  return (
    <div className="auth-shell login-page">
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
            <div className="password-field">
              <input
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="password"
                type={showPassword ? "text" : "password"}
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowPassword((prev) => !prev)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                title={showPassword ? "Hide password" : "Show password"}
              >
                <EyeIcon visible={showPassword} />
              </button>
            </div>
            <button disabled={loginMutation.isPending}>{loginMutation.isPending ? "Signing in..." : "Sign in"}</button>
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
