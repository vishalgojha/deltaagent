import { Component, type ErrorInfo, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Navigate, Outlet, Route, Routes, Link, useNavigate } from "react-router-dom";
import { getEmergencyHaltStatus } from "./api/endpoints";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { AgentConsolePage } from "./pages/AgentConsolePage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { BrokerSettingsPage } from "./pages/BrokerSettingsPage";
import { StrategyTemplatesPage } from "./pages/StrategyTemplatesPage";
import { AdminSafetyPage } from "./pages/AdminSafetyPage";
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
  const haltQuery = useQuery({
    queryKey: ["client-emergency-halt", clientId],
    queryFn: () => getEmergencyHaltStatus(clientId),
    refetchInterval: 5000
  });
  const isHalted = Boolean(haltQuery.data?.halted);
  const haltReason = haltQuery.data?.reason || "Emergency trading halt is active";

  return (
    <div className="layout">
      <div className="shell-nav">
        <Link className="shell-link" to="/dashboard">Dashboard</Link>
        <Link className="shell-link" to="/agent">Agent Console</Link>
        <Link className="shell-link" to="/settings/broker">Broker Settings</Link>
        <Link className="shell-link" to="/strategy-templates">Strategy Templates</Link>
        <Link className="shell-link" to="/admin/safety">Admin Safety</Link>
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
      {isHalted && (
        <section className="card" style={{ borderColor: "#fecaca", background: "#fef2f2", marginBottom: 12 }}>
          <p style={{ margin: 0, color: "#991b1b", fontWeight: 700 }}>Global Emergency Halt Active</p>
          <p style={{ margin: "6px 0 0 0", color: "#7f1d1d" }}>{haltReason}</p>
        </section>
      )}
      <Routes>
        <Route path="/dashboard" element={<DashboardPage clientId={clientId} />} />
        <Route path="/agent" element={<AgentConsolePage clientId={clientId} token={token} isHalted={isHalted} haltReason={haltReason} />} />
        <Route path="/settings/broker" element={<BrokerSettingsPage clientId={clientId} />} />
        <Route path="/strategy-templates" element={<StrategyTemplatesPage isHalted={isHalted} haltReason={haltReason} />} />
        <Route path="/admin/safety" element={<AdminSafetyPage />} />
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
