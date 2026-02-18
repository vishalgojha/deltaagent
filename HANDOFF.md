# Handoff

## Current Baseline

- Branch: `main`
- Stable tag: `v0.1.0`
- Tag commit: `6124c8f` (CI green checkpoint)
- Latest fixes after tag are also on `main` (CI import + flake fixes).
- Current local test status: `39 passed`.

## What Is Working Now

- Backend agent flow is end-to-end:
  - `confirmation` mode creates proposals.
  - `approve/reject` executes or drops proposals.
  - `autonomous` mode is guarded by `AUTONOMOUS_ENABLED`.
- Broker layer:
  - IBKR adapter has contract normalization, chain fetch, market data mode config, reconnect helpers, and combo order support.
  - Phillip adapter is covered by mocked tests.
  - Mock broker is only for tests/dev (`USE_MOCK_BROKER=true`).
- Multi-tenant/session basics:
  - JWT auth + client scoping.
  - Encrypted broker credentials vault.
  - client-scoped state/memory.
- Reference catalog support added:
  - instruments + strategy profiles models/schemas/routes exist.
- Frontend has:
  - login-first flow.
  - onboarding and broker reconnect UI with field-based IBKR form (not raw JSON-only).
  - agent console improvements (tool trace, API status/health indicators, engine selector).

## Important Recent Fixes

- CI import failures resolved:
  - Added missing ORM models in `backend/db/models.py`:
    - `Instrument`
    - `StrategyProfile`
- Chat/API schema compatibility fixed:
  - `ChatResponse` and tool-trace payload fields aligned for tests.
- IBKR compatibility helpers restored for tests/runtime:
  - `_pick_target_expiry`
  - `_ensure_connected`
  - delayed market data type configuration
  - exchange alias + expiry normalization
  - partial ticker response handling in options chain
- Proposal-creation flake fixed:
  - If model output returns invalid/empty trade, deterministic fallback trade is preserved.

## Runbook

1. Start infra:
- `docker compose up -d postgres redis`

2. Backend:
- `.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload`

3. Frontend:
- `cd frontend`
- `npm install`
- `npm run dev`

4. Validate API routes:
- `http://localhost:8000/openapi.json`

5. Run tests:
- `.\.venv\Scripts\python.exe -m pytest -q`

## Environment Notes

- CORS should include frontend origin:
  - `CORS_ORIGINS=["http://localhost:3000","http://localhost:5173","http://127.0.0.1:5173"]`
- Local docker ports in this setup:
  - Postgres `5433`
  - Redis `6380`
- Suggested local `.env` DB/Redis:
  - `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/trading`
  - `REDIS_URL=redis://localhost:6380/0`
- IBKR host:
  - If backend runs on host: usually `localhost`.
  - If backend runs in docker: often `host.docker.internal`.

## Pending Backlog (High-Level)

1. Frontend state hardening:
- move remaining fetch state to TanStack Query
- central session/auth guard and stronger error boundaries

2. Frontend tests:
- unit tests for login/onboarding/proposal/ws flows
- Playwright smoke path: login -> proposal -> approve/reject

3. Backend safety/DB hardening:
- global emergency trading halt endpoint finalization + audit checks
- production-grade Postgres RLS policies (keep app-level tenant checks too)

4. Broker production tuning:
- IBKR/Phillip edge-case mappings, reconnect telemetry, market-data handling refinement

## Known Caveats

- CI warning from `passlib`/`crypt` is currently non-fatal on Python 3.11.
- `Ollama call failed, falling back` in CI is expected when Ollama is not running; fallback path is now deterministic.
