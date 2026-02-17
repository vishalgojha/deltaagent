import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LoginPage } from "./LoginPage";
import * as endpoints from "../api/endpoints";
import * as sessionStore from "../store/session";

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
    login: vi.fn()
  };
});

vi.mock("../store/session", async () => {
  const actual = await vi.importActual<typeof import("../store/session")>("../store/session");
  return {
    ...actual,
    saveSession: vi.fn()
  };
});

describe("LoginPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("logs in, stores session, and navigates to dashboard", async () => {
    const user = userEvent.setup();
    vi.mocked(endpoints.login).mockResolvedValue({
      access_token: "token-1",
      token_type: "bearer",
      client_id: "client-1"
    });

    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    );

    await user.type(screen.getByPlaceholderText("email"), "trader@desk.io");
    await user.type(screen.getByPlaceholderText("password"), "secret");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(vi.mocked(endpoints.login)).toHaveBeenCalledWith("trader@desk.io", "secret");
      expect(vi.mocked(sessionStore.saveSession)).toHaveBeenCalledWith("token-1", "client-1");
      expect(navigateMock).toHaveBeenCalledWith("/dashboard");
    });
  });
});

