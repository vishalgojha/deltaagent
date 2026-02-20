# START HERE: HANDOFF

Last updated: 2026-02-20

## 1) Current State (Fast)
- Branch: `main`
- Local status: clean working tree
- Sync status: `main...origin/main` (fully pushed)
- CI baseline: use latest commit below and verify checks on GitHub Actions

## 2) What Was Just Completed
### Agent Console: execution-safe product flow
- Simple execute flow: select proposal -> preflight -> execute -> status/fill tracking
- Lifecycle states: `Pending`, `Sent to broker`, `Partially filled`, `Filled`, `Rejected`
- Trade Ticket modal before execute (`Cancel` / `Confirm Execute`)
- Guardrails:
  - confirmation checkbox required in confirmation mode
  - execute blocked with inline reason when halt/readiness/risk fails
- Keyboard/accessibility:
  - `Esc` closes modal
  - `Enter` confirms execute (when allowed)
  - focus trap + initial focus on `Cancel`
- Coded toasts (non-flashy): `[OK]`, `[WARN]`, `[ERR]`
- Copy action on each toast line

### Agent Console: safety and trust
- Always-visible `Safety Policy` section:
  - mode
  - delta threshold
  - max size
  - max loss
  - max open positions
  - global halt state
- Inline global kill switch UX:
  - admin key + reason + confirmation text (`HALT`)
  - enable halt / resume trading buttons
- Global halt read-only overlay in Trade Assistant area

### Agent Console: reliability and observability
- Broker link badge in state bar (`UP`/`DOWN`) + last check timestamp
- Quick `Reconnect Broker` action in Agent Console
- Reconnect retries/backoff indicator (`attempt x/3`, `next in Ns`)
- Execution Audit panel:
  - last 10 events
  - actor/action/result/detail/timestamp
  - per-row copy line
- Audit entries persisted per client in localStorage

### Broker-native lifecycle updates
- Backend websocket now emits `order_status` events from latest trade changes
- Frontend consumes `order_status` and updates lifecycle from stream
- Lifecycle shows source: `websocket` vs `polling` vs `none`

### Onboarding reliability
- Onboarding no longer hard-fails if broker connect fails
- Guided Broker Setup appears on failure:
  - preflight checklist
  - fix hints
  - one-click `Retry Broker Connect`
  - optional `Continue To Dashboard`
- Copy action for each onboarding fix hint

## 3) Most Recent Commits (Newest First)
- `5ebcb72` Add tests for websocket order status stream mapping
- `94ef0ff` Show lifecycle source as websocket or polling
- `746ebdb` Add websocket order_status stream and live lifecycle updates
- `cdd1a21` Refresh 00_HANDOFF with latest product and delivery state
- `38b5dec` Add copy action for onboarding auto-fix hints
- `07117ef` Add guided broker setup checklist and retry on onboarding
- `bb042e6` Add read-only lock overlay for global halt mode
- `d784a63` Add always-visible safety policy and inline kill switch UX
- `c2b2fe7` Harden AgentConsole tests with stable test ids
- `7e9e733` Persist execution audit entries per client in local storage

## 4) How To Run (Newbie Friendly)
### Easiest
From repo root, double-click:
- `start.bat`
- `status.bat`
- `stop.bat`

### Manual
Terminal A (infra):
```powershell
docker compose up -d postgres redis
```

Terminal B (backend):
```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Terminal C (frontend):
```powershell
cd frontend
npm.cmd run dev
```

## 5) Quick Health Checks
- Backend OpenAPI: `http://localhost:8000/openapi.json`
- Frontend: `http://localhost:5173`
- Agent Console visible checks:
  - `Broker Link` (`UP`/`DOWN`)
  - `Safety Policy`
  - `Execution Audit`
  - lifecycle `Source: websocket|polling|none`

## 6) Known Environment Notes
- PowerShell script policy warning can appear on each command (non-blocking)
- If `npm` alias is blocked, use `npm.cmd`
- In restricted environments, Vitest/Vite may fail with `spawn EPERM`; TypeScript compile still works:
```powershell
cd frontend
npx tsc -b
```

## 7) Pending (Product)
1. Deployment hardening
- Railway/Render deploy profile, env validator, post-deploy smoke checks.

2. Broker-native lifecycle depth
- Add partial-fill/cancel/update transitions from broker adapters (beyond latest-trade row updates).

3. Admin auth hardening
- Replace raw admin-key entry in UI with secure admin session flow.

4. Websocket test depth
- Add multi-transition websocket integration tests over time.

5. E2E refresh
- Update Playwright smoke to assert safety policy, modal confirm, and lifecycle source.

6. Docs sync
- README + screenshots + operator runbook updates for current UX.

## 8) Important Files
- Primary handoff: `00_HANDOFF.md`
- Previous handoff archive: `HANDOFF.md`
- Agent Console: `frontend/src/pages/AgentConsolePage.tsx`
- Agent Console tests: `frontend/src/pages/AgentConsolePage.test.tsx`
- Websocket stream API: `backend/api/websocket.py`
- Websocket test: `backend/tests/test_websocket_order_status.py`
- Onboarding: `frontend/src/pages/OnboardingPage.tsx`
- Onboarding tests: `frontend/src/pages/OnboardingPage.test.tsx`
- Frontend styles: `frontend/src/styles.css`
