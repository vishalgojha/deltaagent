import { Component, type ErrorInfo, type ReactNode } from "react";
import { Navigate, Outlet, Route, Routes, Link, useNavigate } from "react-router-dom";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { AgentConsolePage } from "./pages/AgentConsolePage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { BrokerSettingsPage } from "./pages/BrokerSettingsPage";
import { StrategyTemplatesPage } from "./pages/StrategyTemplatesPage";
import { clearSession, getSession } from "./store/session";

class RouteErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Route render failure", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="layout">
          <section className="card">
            <h3>Something went wrong</h3>
            <p className="muted">The page failed to render. Reload and try again.</p>
          </section>
        </div>
      );
    }
    return this.props.children;
  }
}

function RequireSession() {
  const { token, clientId } = getSession();
  if (!token || !clientId) return <Navigate to="/login" replace />;
  return <Outlet />;
}

function ShellLayout() {
  const navigate = useNavigate();
  const { token, clientId } = getSession();

  return (
    <div className="layout">
      <div className="row" style={{ marginBottom: 12 }}>
        <Link to="/dashboard">Dashboard</Link>
        <Link to="/agent">Agent Console</Link>
        <Link to="/settings/broker">Broker Settings</Link>
        <Link to="/strategy-templates">Strategy Templates</Link>
        <button
          className="secondary"
          onClick={() => {
            clearSession();
            navigate("/login");
          }}
        >
          Logout
        </button>
      </div>
      <Routes>
        <Route path="/dashboard" element={<DashboardPage clientId={clientId} />} />
        <Route path="/agent" element={<AgentConsolePage clientId={clientId} token={token} />} />
        <Route path="/settings/broker" element={<BrokerSettingsPage clientId={clientId} />} />
        <Route path="/strategy-templates" element={<StrategyTemplatesPage />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </div>
  );
}

export function App() {
  return (
    <RouteErrorBoundary>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/onboard" element={<OnboardingPage />} />
        <Route element={<RequireSession />}>
          <Route path="/*" element={<ShellLayout />} />
        </Route>
      </Routes>
    </RouteErrorBoundary>
  );
}
