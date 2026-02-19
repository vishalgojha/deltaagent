# START HERE: HANDOFF

Last updated: 2026-02-19

## 1) Current State (Fast)
- Branch: `main`
- Local status: clean working tree
- Sync status: `main...origin/main` (fully pushed)
- CI baseline: use latest commit below and verify checks on GitHub Actions

## 2) What Was Just Completed
### Agent Console: execution-safe product flow
- Simple execute flow: select proposal -> preflight -> execute -> status/fill tracking
- Lifecycle states added: `Pending`, `Sent to broker`, `Partially filled`, `Filled`, `Rejected`
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
- Inline global kill switch UX in Agent Console:
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

### Onboarding reliability
- Onboarding no longer hard-fails if broker connect fails
- Guided Broker Setup section appears on failure:
  - preflight checklist
  - fix hints
  - one-click `Retry Broker Connect`
  - optional `Continue To Dashboard`
- Copy action added for each onboarding fix hint

## 3) Most Recent Commits (Newest First)
- `38b5dec` Add copy action for onboarding auto-fix hints
- `07117ef` Add guided broker setup checklist and retry on onboarding
- `bb042e6` Add read-only lock overlay for global halt mode
- `d784a63` Add always-visible safety policy and inline kill switch UX
- `c2b2fe7` Harden AgentConsole tests with stable test ids
- `7e9e733` Persist execution audit entries per client in local storage
- `fa82691` Add execution audit panel with copyable event lines
- `75993cd` Add broker reconnect retry/backoff indicator
- `96f357c` Add broker link badge and quick reconnect in agent console
- `79a85d4` Add copy action for coded toast lines

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
npm run dev
```

## 5) Quick Health Checks
- Backend OpenAPI: `http://localhost:8000/openapi.json`
- Frontend: `http://localhost:5173`
- Agent Console: check these visible indicators:
  - `Broker Link` (`UP`/`DOWN`)
  - `Safety Policy`
  - `Execution Audit`

## 6) Known Environment Notes
- PowerShell script policy warning can appear on each command (non-blocking)
- If `npm` alias is blocked, use `npm.cmd`
- In restricted environments, Vitest/Vite may fail with `spawn EPERM`; TypeScript compile still works:
```powershell
cd frontend
npx tsc -b
```

## 7) Next Recommended Product Work
1. Broker-native execution status stream
- Replace/augment polling with websocket/order-status feed from broker for authoritative fills.

2. Strategy preview UX
- Better visual risk narrative (max loss, breakeven bands, scenario table) before execution.

3. Admin safety hardening
- Role-gated admin key handling (do not type raw key repeatedly in UI), with secure session-based admin mode.

4. Deployment readiness
- One-click deployment profile (Railway/Render), env validator, and post-deploy smoke checks.

## 8) Important Files
- Primary handoff: `00_HANDOFF.md`
- Previous handoff archive: `HANDOFF.md`
- Agent Console: `frontend/src/pages/AgentConsolePage.tsx`
- Agent Console tests: `frontend/src/pages/AgentConsolePage.test.tsx`
- Onboarding: `frontend/src/pages/OnboardingPage.tsx`
- Onboarding tests: `frontend/src/pages/OnboardingPage.test.tsx`
- Frontend styles: `frontend/src/styles.css`
