import { expect, test } from "@playwright/test";

test("login -> chat proposal -> approve/reject", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => {
    pageErrors.push(error.message);
  });
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      pageErrors.push(msg.text());
    }
  });

  let nextProposalId = 1;
  const proposals: Array<{
    id: number;
    status: "pending" | "approved" | "rejected";
    trade_payload: Record<string, unknown>;
    agent_reasoning: string;
  }> = [];

  await page.route("**/auth/login", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        access_token: "token-1",
        token_type: "bearer",
        client_id: "client-1"
      })
    });
  });

  await page.route("**/clients/client-1/agent/status", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        client_id: "client-1",
        mode: "confirmation",
        healthy: true,
        last_action: null,
        net_greeks: { delta: 0, gamma: 0, theta: 0, vega: 0 }
      })
    });
  });

  await page.route("**/clients/client-1/positions", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
  });

  await page.route("**/clients/client-1/trades", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
  });

  await page.route("**/clients/client-1/agent/parameters", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        client_id: "client-1",
        risk_parameters: {
          delta_threshold: 0.2,
          max_size: 10,
          max_loss: 5000,
          max_open_positions: 20
        }
      })
    });
  });

  await page.route("**/clients/client-1/agent/proposals", async (route) => {
    const pending = proposals
      .filter((proposal) => proposal.status === "pending")
      .map((proposal) => ({
        id: proposal.id,
        timestamp: "2026-02-17T00:00:00Z",
        trade_payload: proposal.trade_payload,
        agent_reasoning: proposal.agent_reasoning,
        status: proposal.status,
        resolved_at: null
      }));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(pending)
    });
  });

  await page.route("**/clients/client-1/agent/chat", async (route) => {
    const id = nextProposalId++;
    const toolUseId = `tool-${id}`;
    proposals.push({
      id,
      status: "pending",
      trade_payload: { action: "SELL", symbol: "ES", qty: 1 },
      agent_reasoning: "proposal generated"
    });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        mode: "confirmation",
        message: "proposal generated",
        proposal_id: id,
        proposal: { action: "SELL", symbol: "ES", qty: 1 },
        tool_trace_id: `trace-${id}`,
        planned_tools: [{ name: "get_portfolio_greeks", input: {} }],
        tool_calls: [
          {
            tool_use_id: toolUseId,
            name: "get_portfolio_greeks",
            input: {},
            started_at: "2026-02-18T00:00:00Z",
            completed_at: "2026-02-18T00:00:00Z",
            duration_ms: 12
          }
        ],
        tool_results: [
          {
            tool_use_id: toolUseId,
            name: "get_portfolio_greeks",
            output: { net_greeks: { delta: 0.5 } },
            success: true,
            error: null,
            started_at: "2026-02-18T00:00:00Z",
            completed_at: "2026-02-18T00:00:00Z",
            duration_ms: 12
          }
        ]
      })
    });
  });

  await page.route("**/clients/client-1/agent/approve/*", async (route) => {
    const id = Number(route.request().url().split("/").pop());
    const proposal = proposals.find((row) => row.id === id);
    if (proposal) proposal.status = "approved";
    await route.fulfill({ status: 200, contentType: "application/json", body: '{"status":"approved"}' });
  });

  await page.route("**/clients/client-1/agent/reject/*", async (route) => {
    const id = Number(route.request().url().split("/").pop());
    const proposal = proposals.find((row) => row.id === id);
    if (proposal) proposal.status = "rejected";
    await route.fulfill({ status: 200, contentType: "application/json", body: '{"status":"rejected"}' });
  });

  await page.goto("/login");
  await page.getByPlaceholder("email").fill("trader@desk.io");
  await page.getByPlaceholder("password").fill("secret");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/\/dashboard$/);
  expect(pageErrors, `Browser errors on dashboard: ${pageErrors.join(" | ")}`).toEqual([]);
  await page.getByRole("link", { name: "Agent Console" }).click();
  await expect(page).toHaveURL(/\/agent$/);

  await page.getByPlaceholder("Ask the agent...").fill("create hedge 1");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Tool Calling Workflow")).toBeVisible();
  await expect(page.getByText("Step 1: get_portfolio_greeks")).toBeVisible();
  await expect(page.getByText("Proposal #1")).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).first().click();
  await expect(page.getByText("Proposal #1 approved.")).toBeVisible();

  await page.getByPlaceholder("Ask the agent...").fill("create hedge 2");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Proposal #2")).toBeVisible();
  await page.getByRole("button", { name: "Reject" }).first().click();
  await expect(page.getByText("Proposal #2 rejected.")).toBeVisible();
});
