import { expect, test } from "@playwright/test";

test("login -> chat proposal -> approve/reject (real backend, mock broker)", async ({ page, request }) => {
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

  await page.getByPlaceholder("Ask the agent...").fill("Rebalance now");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(/Proposal #\d+/).first()).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).first().click();
  await expect(page.getByText(/Proposal #\d+ approved\./).first()).toBeVisible();

  await page.getByPlaceholder("Ask the agent...").fill("Rebalance now");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(/Proposal #\d+/).first()).toBeVisible();
  await page.getByRole("button", { name: "Reject" }).first().click();
  await expect(page.getByText(/Proposal #\d+ rejected\./).first()).toBeVisible();
});
