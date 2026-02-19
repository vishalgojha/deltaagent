import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { OnboardingPage } from "./OnboardingPage";
import * as endpoints from "../api/endpoints";
import * as sessionStore from "../store/session";
import { renderWithProviders } from "../test/renderWithProviders";

const navigateMock = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => navigateMock
  };
});

vi.mock("../api/endpoints", async () => {
  const actual = await vi.importActual<typeof import("../api/endpoints")>("../api/endpoints");
  return {
    ...actual,
    onboardClient: vi.fn(),
    login: vi.fn(),
    connectBroker: vi.fn(),
    brokerPreflight: vi.fn()
  };
});

vi.mock("../store/session", async () => {
  const actual = await vi.importActual<typeof import("../store/session")>("../store/session");
  return {
    ...actual,
    saveSession: vi.fn()
  };
});

describe("OnboardingPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("onboards client, logs in, optionally connects broker, and navigates", async () => {
    const user = userEvent.setup();
    vi.mocked(endpoints.onboardClient).mockResolvedValue({
      id: "client-42",
      email: "client@desk.io",
      broker_type: "ibkr",
      risk_params: {},
      mode: "confirmation",
      tier: "basic",
      is_active: true,
      created_at: "2026-02-17T00:00:00Z"
    });
    vi.mocked(endpoints.login).mockResolvedValue({
      access_token: "token-42",
      token_type: "bearer",
      client_id: "client-42"
    });
    vi.mocked(endpoints.connectBroker).mockResolvedValue({
      connected: true,
      broker: "ibkr"
    });

    renderWithProviders(
      <MemoryRouter>
        <OnboardingPage />
      </MemoryRouter>
    );

    await user.type(screen.getByPlaceholderText("client email"), "client@desk.io");
    await user.type(screen.getByPlaceholderText("password"), "secret");
    await user.clear(screen.getByPlaceholderText("1"));
    await user.type(screen.getByPlaceholderText("1"), "42");
    await user.click(screen.getByRole("button", { name: "Create Client" }));

    await waitFor(() => {
      expect(vi.mocked(endpoints.onboardClient)).toHaveBeenCalledWith(
        expect.objectContaining({
          email: "client@desk.io",
          password: "secret",
          broker_type: "ibkr",
          broker_credentials: expect.objectContaining({
            host: "localhost",
            port: 4002,
            client_id: 42,
            underlying_instrument: "IND"
          }),
          risk_parameters: expect.objectContaining({
            delta_threshold: 0.2,
            max_size: 10,
            max_loss: 5000,
            max_open_positions: 20
          }),
          subscription_tier: "basic"
        })
      );
      expect(vi.mocked(endpoints.login)).toHaveBeenCalledWith("client@desk.io", "secret");
      expect(vi.mocked(sessionStore.saveSession)).toHaveBeenCalledWith("token-42", "client-42");
      expect(vi.mocked(endpoints.connectBroker)).toHaveBeenCalled();
      expect(navigateMock).toHaveBeenCalledWith("/dashboard");
    });
  });

  it("shows guided setup and allows retry when broker connect fails", async () => {
    const user = userEvent.setup();
    vi.mocked(endpoints.onboardClient).mockResolvedValue({
      id: "client-99",
      email: "client@desk.io",
      broker_type: "ibkr",
      risk_params: {},
      mode: "confirmation",
      tier: "basic",
      is_active: true,
      created_at: "2026-02-17T00:00:00Z"
    });
    vi.mocked(endpoints.login).mockResolvedValue({
      access_token: "token-99",
      token_type: "bearer",
      client_id: "client-99"
    });
    vi.mocked(endpoints.connectBroker)
      .mockRejectedValueOnce(new Error("Failed to connect"))
      .mockResolvedValueOnce({ connected: true, broker: "ibkr" });
    vi.mocked(endpoints.brokerPreflight).mockResolvedValue({
      ok: false,
      broker: "ibkr",
      checks: [{ key: "socket", title: "Socket", status: "fail", detail: "Port closed" }],
      blocking_issues: ["Port closed"],
      warnings: [],
      fix_hints: ["Enable API socket in IBKR Gateway"],
      checked_at: "2026-02-19T00:00:00Z"
    });

    renderWithProviders(
      <MemoryRouter>
        <OnboardingPage />
      </MemoryRouter>
    );

    await user.type(screen.getByPlaceholderText("client email"), "client@desk.io");
    await user.type(screen.getByPlaceholderText("password"), "secret");
    await user.click(screen.getByRole("button", { name: "Create Client" }));

    expect(await screen.findByText("Guided Broker Setup")).toBeInTheDocument();
    expect(await screen.findByText("Enable API socket in IBKR Gateway")).toBeInTheDocument();
    expect(vi.mocked(sessionStore.saveSession)).toHaveBeenCalledWith("token-99", "client-99");
    expect(navigateMock).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Retry Broker Connect" }));
    await waitFor(() => {
      expect(vi.mocked(endpoints.connectBroker)).toHaveBeenCalledTimes(2);
      expect(navigateMock).toHaveBeenCalledWith("/dashboard");
    });
  });
});
