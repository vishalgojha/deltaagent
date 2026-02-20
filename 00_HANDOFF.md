# START HERE: HANDOFF

Last updated: 2026-02-20

## 1) Current State (Fast)
- Branch: `main`
- Local status: clean working tree
- Sync status: `main...origin/main` (fully pushed)
- CI baseline: use latest commit below and verify checks on GitHub Actions

## 2) What Was Just Completed
### Frontend visual + UX polish pass
- Scoped visual reskin applied across:
  - `DashboardPage`
  - `BrokerSettingsPage`
  - `StrategyTemplatesPage`
  - `AdminSafetyPage`
  - `OnboardingPage`
  - `LoginPage`
- Added accessibility and UX hardening:
  - visible keyboard focus rings (`:focus-visible`)
  - reduced-motion safety (`prefers-reduced-motion`)
  - better mobile topbar wrapping/readability
- TypeScript compile check passed:
  - `cd frontend && npx tsc -b`

### Operator docs sync
- Updated emergency halt runbook for admin bearer session flow
- Added admin session operations runbook:
  - `docs/runbooks/admin-session-operations.md`
- Added screenshot shotlist template:
  - `docs/screenshots/SHOTLIST.md`
- Added Playwright screenshot capture spec:
  - `frontend/e2e/screenshots.spec.ts`
  - `npm run screenshots:e2e`
- Added one-click screenshot runner:
  - `capture_screenshots.bat`

### Admin auth hardening
- Added admin session endpoint: `POST /admin/session/login`
- Admin controls now use bearer token session flow (`Unlock Admin` / `Lock Admin`)
- Retained `X-Admin-Key` fallback in backend for compatibility

### Websocket test depth
- Added multi-transition websocket tests for same-order lifecycle updates
- Coverage now includes `submitted -> partially_filled -> filled` sequence assertions

### E2E smoke refresh
- Updated Playwright smoke to assert:
  - `Safety Policy` visibility
  - modal execute flow (`Trade Ticket Confirmation`)
  - lifecycle source label (`Source: websocket|polling`)

### Deployment hardening
- Added Railway deploy profile: `railway.json`
- Added Render blueprint: `render.yaml`
- Added pre-deploy env validator: `scripts/validate_env.py`
- Added post-deploy smoke check runner: `scripts/post_deploy_smoke.py`
- Updated `README.md` with deployment validation/smoke commands

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
- `7b19661` Sync docs with admin session, websocket, and e2e updates
- `4914222` Refresh smoke e2e for safety policy and modal execution
- `e69a9ea` Expand websocket integration coverage for multi-step fills
- `ce1009a` Harden admin controls with session token flow
- `2414111` Emit websocket order status transitions for multiple trades
- `ffabdd2` Add deployment hardening profiles and smoke tooling
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
1. Capture and publish screenshots/GIF
- Run `capture_screenshots.bat` from repo root and commit generated images from `docs/screenshots/`.
- Note: in restricted environments this may fail with `spawn EPERM`; run locally in your normal terminal session.

## 8) Important Files
- Primary handoff: `00_HANDOFF.md`
- Previous handoff archive: `HANDOFF.md`
- Deployment env validator: `scripts/validate_env.py`
- Post-deploy smoke checks: `scripts/post_deploy_smoke.py`
- Railway profile: `railway.json`
- Render profile: `render.yaml`
- Agent Console: `frontend/src/pages/AgentConsolePage.tsx`
- Agent Console tests: `frontend/src/pages/AgentConsolePage.test.tsx`
- Websocket stream API: `backend/api/websocket.py`
- Websocket test: `backend/tests/test_websocket_order_status.py`
- Playwright smoke: `frontend/e2e/smoke.spec.ts`
- Admin session runbook: `docs/runbooks/admin-session-operations.md`
- Screenshot checklist: `docs/screenshots/SHOTLIST.md`
- One-click screenshot runner: `capture_screenshots.bat`
- Onboarding: `frontend/src/pages/OnboardingPage.tsx`
- Onboarding tests: `frontend/src/pages/OnboardingPage.test.tsx`
- Frontend styles: `frontend/src/styles.css`
