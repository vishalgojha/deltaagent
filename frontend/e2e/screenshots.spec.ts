import { expect, test } from "@playwright/test";
import path from "node:path";

function shotPath(filename: string): string {
  return path.resolve(__dirname, "..", "..", "docs", "screenshots", filename);
}

test("capture product screenshots for docs", async ({ page, request }) => {
  const suffix = `${Date.now()}-${Math.floor(Math.random() * 10000)}`;
  const email = `shots-${suffix}@example.com`;
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
            avg_price: 10.0
          }
        ]
      },
      risk_parameters: {
        delta_threshold: 0.2,
        max_size: 10,
        max_loss: 5000,
        max_open_positions: 20
      },
      subscription_tier: "basic"
    }
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
  await page.screenshot({ path: shotPath("agent-console-safety-policy.png"), fullPage: true });

  await page.getByPlaceholder("Ask the agent...").fill("Rebalance now");
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByTestId("execute-confirm-checkbox").click();
  await page.getByTestId("execute-trade-button").click();
  await expect(page.getByRole("dialog", { name: "Trade Ticket Confirmation" })).toBeVisible();
  await page.screenshot({ path: shotPath("agent-console-trade-ticket-modal.png"), fullPage: true });
  await page.getByTestId("trade-ticket-confirm-button").click();

  await expect(page.getByText(/Source:\s*(websocket|polling)/)).toBeVisible();
  await page.screenshot({ path: shotPath("agent-console-lifecycle-source.png"), fullPage: true });

  await page.getByRole("link", { name: "Admin Safety" }).click();
  await expect(page).toHaveURL(/\/admin\/safety$/);
  await expect(page.getByRole("button", { name: "Unlock Admin" })).toBeVisible();
  await page.screenshot({ path: shotPath("admin-safety-unlock.png"), fullPage: true });
});
