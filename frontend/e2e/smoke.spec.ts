import { expect, test } from "@playwright/test";

test("login -> chat proposal -> modal execute -> reject (real backend, mock broker)", async ({ page, request }) => {
  const suffix = `${Date.now()}-${Math.floor(Math.random() * 10000)}`;
  const email = `smoke-${suffix}@example.com`;
  const password = "SmokePass123!";

  const onboard = await request.post("http://127.0.0.1:8000/clients/onboard", {
    data: {
      email,
      password,
      broker_type: "ibkr",
      broker_credentials: {
        host: "localhost",
        port: 4002,
        client_id: 1,
        underlying_instrument: "IND",
        mock_positions: [
          {
            symbol: "ES",
            instrument_type: "FOP",
            qty: 1,
            delta: 1.0,
            gamma: 0.0,
            theta: 0.0,
            vega: 0.0,
            avg_price: 10.0,
          },
        ],
      },
      risk_parameters: {
        delta_threshold: 0.2,
        max_size: 10,
        max_loss: 5000,
        max_open_positions: 20,
      },
      subscription_tier: "basic",
    },
  });
  expect(onboard.ok()).toBeTruthy();

  await page.goto("/login");
  await page.getByPlaceholder("email").fill(email);
  await page.getByPlaceholder("password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/\/dashboard$/);
  await page.getByRole("link", { name: "Agent Console" }).click();
  await expect(page).toHaveURL(/\/agent$/);
  await expect(page.getByRole("heading", { name: "Safety Policy" })).toBeVisible();

  await page.getByPlaceholder("Ask the agent...").fill("Rebalance now");
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByTestId("execute-confirm-checkbox").click();
  await page.getByTestId("execute-trade-button").click();
  await expect(page.getByRole("dialog", { name: "Trade Ticket Confirmation" })).toBeVisible();
  await page.getByTestId("trade-ticket-confirm-button").click();
  await expect(page.locator("p", { hasText: /Proposal #\d+ approved\./ }).first()).toBeVisible();
  await expect(page.getByText(/Source:\s*(websocket|polling)/)).toBeVisible();

  await page.getByPlaceholder("Ask the agent...").fill("Rebalance now");
  await page.getByRole("button", { name: "Send" }).click();
  const rejectProposalButton = page.locator('[data-testid^="reject-proposal-"]').first();
  await expect(rejectProposalButton).toBeVisible();
  await rejectProposalButton.click();
  await expect(page.locator("p", { hasText: /Proposal #\d+ rejected\./ }).first()).toBeVisible();
});
