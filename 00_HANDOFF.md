# START HERE: HANDOFF

Last updated: 2026-02-21

## 1) Current State (Fast)
- Branch: `main`
- Sync status: `main...origin/main` (fully pushed through `817e2aa`)
- Local status: **not clean**
  - `M frontend/src/pages/AgentConsolePage.test.tsx` (pre-existing local edit, intentionally not committed by agent)

## 2) What Was Just Completed
### npm registry publish (frontend package)
- Made frontend package publishable and published to npm registry:
  - package name: `@vishalgojha/deltaagent-frontend`
  - version: `0.1.0`
- `frontend/package.json` updates:
  - `private: false`
  - added `publishConfig.access: "public"`
  - added metadata (`repository`, `bugs`, `homepage`, `license`, `author`, `description`)
  - added `files` allowlist for publish contents
- Install command (works globally):
  - `npm install @vishalgojha/deltaagent-frontend`

### OpenRouter support end-to-end
- Added OpenRouter support in backend decision engine + frontend backend selector + CLI helper.
- Backend now supports `decision_backend=openrouter` with env-driven config.
- Frontend Agent Console includes `OpenRouter` in backend dropdown.
- Added helper CLI: `scripts/agent_cli.py` (`login`, `set-backend`, `chat`).

### IBKR reconnect reliability (no manual client-id rotation needed)
- Added automatic IBKR `client_id` fallback on connect collisions (`326`):
  - tries `base`, `base+1`, `base+2`, ... (configurable via `client_id_fallback_attempts`, default `5`)
- Persists selected successful `active_client_id` back into saved encrypted broker credentials
- `POST /clients/{id}/connect-broker` now returns:
  - `active_client_id`
  - `broker_credentials` (updated)
- Files:
  - `backend/brokers/ibkr.py`
  - `backend/api/clients.py`
  - `backend/tests/test_brokers.py`

### Frontend UX updates
- Password visibility eye toggle added to:
  - Login page
  - Onboarding page (user password + Phillip client secret)
  - Admin Safety page (admin API key)
- Files:
  - `frontend/src/pages/LoginPage.tsx`
  - `frontend/src/pages/OnboardingPage.tsx`
  - `frontend/src/pages/AdminSafetyPage.tsx`
  - `frontend/src/styles.css`

### Scrolling and layout hardening
- Added global/custom scrollbars (WebKit + Firefox)
- Ensured shell sidebar and main layout have explicit scrolling behavior for long content
- File:
  - `frontend/src/styles.css`

### Startup reliability
- `start.bat` now checks `docker info` first and shows clear message if Docker Engine is not running
- File:
  - `start.bat`

### Earlier same-day visual polish
- Scoped reskin for Dashboard, Broker Settings, Strategy Templates, Admin Safety, Login, Onboarding
- Accessibility additions: `:focus-visible`, reduced motion, mobile topbar wrapping

## 3) Most Recent Commits (Newest First)
- `4187b2a` Add OpenRouter support across backend frontend and CLI helper
- `817e2aa` Auto-fallback IBKR client IDs on connect collisions
- `14f14cc` Add global/custom scrollbars and shell content scrolling
- `4d9c82e` Add password visibility toggles and harden start script Docker check
- `8d56690` Polish frontend accessibility and update handoff
- `0f9b01a` Reskin remaining frontend pages with scoped visual styles
- `ca1bb6a` Add repo-level AI operating protocol and fast mode
- `dc6fd39` Reskin agent console internals with scoped operator styling
- `449aa36` Reskin app shell with operator-style navigation layout
- `1e6cc9d` Add one-click screenshot capture runner
- `c6e4203` Add Playwright automation for docs screenshots

## 4) How To Run (Newbie Friendly)
### Easiest
From repo root, double-click:
- `start.bat`
- `status.bat`
- `stop.bat`

### Manual
Terminal A:
```powershell
docker compose up -d postgres redis
```

Terminal B:
```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Terminal C:
```powershell
cd frontend
npm.cmd run dev
```

## 5) Quick Health Checks
- Backend OpenAPI: `http://localhost:8000/openapi.json`
- Frontend: `http://localhost:5173`
- Reconnect broker endpoint returns `active_client_id` when fallback occurs
- UI checks:
  - password eye toggles render and work
  - scrollbars visible on long pages/panels
  - Agent console still shows `Safety Policy`, `Broker Link`, `Execution Audit`

## 6) Verified Tests / Commands
- Backend:
  - `.\.venv\Scripts\python.exe -m pytest backend/tests/test_brokers.py -q` (passed)
  - `.\.venv\Scripts\python.exe -m pytest backend/tests/test_clients_preflight.py -q` (passed)
- Frontend compile:
  - `cd frontend && npx.cmd tsc -b` (passed)

## 7) Known Environment Notes
- PowerShell execution-policy warning appears in this environment (non-blocking)
- If `npm` command is blocked by policy, use `npm.cmd`
- In restricted environments, Vite/Vitest/Playwright may fail with `spawn EPERM`
  - fallback verification: TypeScript compile + manual UI test

## 8) Pending (Product)
1. Capture and publish screenshots/GIF
- Run `capture_screenshots.bat` locally and commit `docs/screenshots/*.png`
- In this environment it may fail with `spawn EPERM`

2. Sanity test reconnect fallback UX
- From Broker Settings:
  - set an in-use `client_id`
  - click reconnect
  - verify connect succeeds and returned `active_client_id` differs (auto-fallback path)

3. Optional repo hygiene
- Decide what to do with local modified `frontend/src/pages/AgentConsolePage.test.tsx`
  - commit intentionally, or revert locally if unintended

4. Optional npm package follow-up
- Add explicit library exports/entrypoint if package should be consumed as a component library (currently published as app source package)
- Publish patch release (`0.1.1`) if export shape or docs are adjusted

## 9) Important Files
- `00_HANDOFF.md`
- `start.bat`
- `backend/api/clients.py`
- `backend/brokers/ibkr.py`
- `backend/tests/test_brokers.py`
- `frontend/src/pages/LoginPage.tsx`
- `frontend/src/pages/OnboardingPage.tsx`
- `frontend/src/pages/AdminSafetyPage.tsx`
- `frontend/src/styles.css`
- `capture_screenshots.bat`
