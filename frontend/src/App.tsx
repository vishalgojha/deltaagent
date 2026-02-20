import { Component, type ErrorInfo, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Navigate, Outlet, Route, Routes, NavLink, useLocation, useNavigate } from "react-router-dom";
import { getEmergencyHaltStatus } from "./api/endpoints";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { AgentConsolePage } from "./pages/AgentConsolePage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { BrokerSettingsPage } from "./pages/BrokerSettingsPage";
import { StrategyTemplatesPage } from "./pages/StrategyTemplatesPage";
import { AdminSafetyPage } from "./pages/AdminSafetyPage";
import { LandingPage } from "./pages/LandingPage";
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
  const location = useLocation();
  const { token, clientId } = getSession();
  const haltQuery = useQuery({
    queryKey: ["client-emergency-halt", clientId],
    queryFn: () => getEmergencyHaltStatus(clientId),
    refetchInterval: 5000
  });
  const isHalted = Boolean(haltQuery.data?.halted);
  const haltReason = haltQuery.data?.reason || "Emergency trading halt is active";

  const navItems = [
    { to: "/dashboard", label: "Dashboard", icon: "◈" },
    { to: "/agent", label: "Agent Console", icon: "◎" },
    { to: "/settings/broker", label: "Broker Settings", icon: "⊙" },
    { to: "/strategy-templates", label: "Strategy Templates", icon: "◇" },
    { to: "/admin/safety", label: "Admin Safety", icon: "⊘" },
  ];

  const currentLabel = navItems.find((item) => location.pathname.startsWith(item.to))?.label ?? "Console";

  return (
    <div className="shell-app">
      <aside className="shell-sidebar">
        <div className="shell-logo">
          <span className="shell-logo-dot" />
          <span>DELTAAGENT</span>
        </div>
        <nav className="shell-sidebar-nav">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `shell-side-link${isActive ? " active" : ""}`}
            >
              <span className="shell-side-icon">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="shell-sidebar-footer">
          <span className={`shell-status-dot ${isHalted ? "halted" : ""}`} />
          {isHalted ? "Halt Active" : "Agent Active"}
        </div>
      </aside>

      <main className="shell-main">
        <header className="shell-topbar">
          <div>
            <p className="shell-topbar-title">{currentLabel}</p>
            <p className="shell-topbar-sub">Client {clientId.slice(0, 8)}...</p>
          </div>
          <div className="shell-topbar-right">
            <span className={`shell-pill ${isHalted ? "halt" : "ok"}`}>{isHalted ? "Execution Halted" : "Execution Ready"}</span>
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
        </header>

        <div className="layout">
          {isHalted && (
            <section className="card shell-halt-banner">
              <p style={{ margin: 0, color: "#fecaca", fontWeight: 700 }}>Global Emergency Halt Active</p>
              <p style={{ margin: "6px 0 0 0", color: "#fca5a5" }}>{haltReason}</p>
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
      </main>
    </div>
  );
}

export function App() {
  return (
    <RouteErrorBoundary>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/onboard" element={<OnboardingPage />} />
        <Route element={<RequireSession />}>
          <Route path="/*" element={<ShellLayout />} />
        </Route>
      </Routes>
    </RouteErrorBoundary>
  );
}
