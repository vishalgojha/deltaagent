import { Component, type ErrorInfo, type ReactNode } from "react";
import { Navigate, Outlet, Route, Routes, Link, useLocation, useNavigate } from "react-router-dom";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { AgentConsolePage } from "./pages/AgentConsolePage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { BrokerSettingsPage } from "./pages/BrokerSettingsPage";
import { clearSession } from "./store/session";
import { useSession } from "./hooks/useSession";
import { queryClient } from "./queryClient";

class RouteErrorBoundary extends Component<{ children: ReactNode; resetKey: string }, { hasError: boolean }> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidUpdate(prevProps: { resetKey: string }) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false });
    }
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
            <div className="row">
              <button type="button" onClick={() => this.setState({ hasError: false })}>
                Try Again
              </button>
              <button type="button" className="secondary" onClick={() => window.location.assign("/dashboard")}>
                Go Dashboard
              </button>
            </div>
          </section>
        </div>
      );
    }
    return this.props.children;
  }
}

function RequireSession() {
  const { token, clientId } = useSession();
  if (!token || !clientId) return <Navigate to="/login" replace />;
  return <Outlet />;
}

function ShellLayout() {
  const navigate = useNavigate();
  const { token, clientId } = useSession();

  return (
    <div className="layout">
      <div className="row" style={{ marginBottom: 12 }}>
        <Link to="/dashboard">Dashboard</Link>
        <Link to="/agent">Agent Console</Link>
        <Link to="/settings/broker">Broker Settings</Link>
        <button
          className="secondary"
          onClick={() => {
            clearSession();
            queryClient.clear();
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
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </div>
  );
}

function AppRoutes() {
  const location = useLocation();

  return (
    <RouteErrorBoundary resetKey={location.pathname}>
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

export function App() {
  return <AppRoutes />;
}
