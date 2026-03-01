import { act, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { getEmergencyHaltStatus } from "./api/endpoints";
import { clearSession, saveSession } from "./store/session";
import { renderWithProviders } from "./test/renderWithProviders";

vi.mock("./api/endpoints", async () => {
  const actual = await vi.importActual<typeof import("./api/endpoints")>("./api/endpoints");
  return {
    ...actual,
    getEmergencyHaltStatus: vi.fn()
  };
});

vi.mock("./pages/DashboardPage", () => ({
  DashboardPage: () => <div>Dashboard Page</div>
}));

vi.mock("./pages/LoginPage", () => ({
  LoginPage: () => <div>Login Page</div>
}));

vi.mock("./pages/AgentConsolePage", () => ({
  AgentConsolePage: () => <div>Agent Console Page</div>
}));

vi.mock("./pages/OnboardingPage", () => ({
  OnboardingPage: () => <div>Onboarding Page</div>
}));

vi.mock("./pages/BrokerSettingsPage", () => ({
  BrokerSettingsPage: () => <div>Broker Settings Page</div>
}));

vi.mock("./pages/ApiKeysPage", () => ({
  ApiKeysPage: () => <div>API Keys Page</div>
}));

vi.mock("./pages/StrategyTemplatesPage", () => ({
  StrategyTemplatesPage: () => <div>Strategy Templates Page</div>
}));

vi.mock("./pages/AdminSafetyPage", () => ({
  AdminSafetyPage: () => <div>Admin Safety Page</div>
}));

vi.mock("./pages/LandingPage", () => ({
  LandingPage: () => <div>Landing Page</div>
}));

describe("App session routing", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    sessionStorage.clear();
    vi.mocked(getEmergencyHaltStatus).mockResolvedValue({
      halted: false,
      reason: null,
      updated_at: null,
      updated_by: null
    });
  });

  it("redirects to login when the session is cleared while on a protected route", async () => {
    saveSession("token-1", "client-1");
    renderWithProviders(
      <MemoryRouter initialEntries={["/agent"]}>
        <App />
      </MemoryRouter>
    );

    expect(await screen.findByText("Agent Console Page")).toBeInTheDocument();

    act(() => {
      clearSession();
    });

    await waitFor(() => {
      expect(screen.getByText("Login Page")).toBeInTheDocument();
    });
  });
});
