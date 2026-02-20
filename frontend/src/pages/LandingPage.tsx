import { Link } from "react-router-dom";

export function LandingPage() {
  return (
    <main className="landing-page">
      <section className="landing-hero">
        <p className="landing-chip">AGENTIC FUTURES OPTIONS</p>
        <h1>Delta-neutral execution engine for client-linked broker accounts.</h1>
        <p className="landing-copy">
          DeltaAgent monitors portfolio Greeks, proposes or executes hedges, enforces risk limits, and streams live
          lifecycle updates from broker to operator console.
        </p>
        <div className="landing-cta">
          <Link to="/login">
            <button>Sign In</button>
          </Link>
          <Link to="/onboard">
            <button className="secondary">Create Client</button>
          </Link>
        </div>
      </section>

      <section className="landing-grid">
        <article className="landing-card">
          <h3>Execution Modes</h3>
          <p className="muted">
            Confirmation mode for operator approvals and autonomous mode for threshold-driven execution.
          </p>
        </article>
        <article className="landing-card">
          <h3>Broker Integrations</h3>
          <p className="muted">
            Per-client IBKR and Phillip connectivity with reconnect logic, health checks, and encrypted credentials.
          </p>
        </article>
        <article className="landing-card">
          <h3>Risk Enforcement</h3>
          <p className="muted">
            Hard checks for max loss, order size, open positions, spread controls, and emergency global halt.
          </p>
        </article>
        <article className="landing-card">
          <h3>Live Operator View</h3>
          <p className="muted">
            WebSocket timeline, proposals, execution lifecycle, audit trail, and reconnect status in one console.
          </p>
        </article>
      </section>
    </main>
  );
}
