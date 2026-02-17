# Handoff

## Current Status

- Backend core is implemented and connected end-to-end.
- Test suite is passing (`10 passed` reported by you).
- Frontend step-2 scaffold is added (`frontend/`): login, onboarding, dashboard, agent console, websocket feed.
- Multi-tenant credential isolation is implemented (encrypted at rest, decrypted per client session).
- IBKR adapter is no longer a placeholder path (contracts, orders, quotes/greeks, chain, stream loop).
- Phillip adapter is covered with mocked integration tests.
- Global autonomous kill switch is enforced (`AUTONOMOUS_ENABLED`).
- Readiness endpoint exists: `GET /health/ready` (DB + Redis + broker reachability checks).
- Alembic baseline migration scaffold has been added.
- CORS is enabled via `CORS_ORIGINS`.

## Files Added/Updated In Latest Step

- `backend/config.py`
- `backend/main.py`
- `.env.example`
- `README.md`
- `HANDOFF.md`
- `frontend/*`

## Environment Flags (Important)

- `USE_MOCK_BROKER=true|false`
- `AUTONOMOUS_ENABLED=false` (recommended until paper-trade validation)
- `AUTO_CREATE_TABLES=true` (dev only)
- `CORS_ORIGINS=http://localhost:3000,http://localhost:5173`

## Runbook (Backend)

1. Activate venv and install:
- `python -m pip install -r requirements.txt`

2. Migrate (recommended path):
- `alembic -c backend/db/alembic.ini upgrade head`

3. Start API:
- `uvicorn backend.main:app --reload`

4. Verify health:
- `GET /health`
- `GET /health/ready`

5. Run tests:
- `python -m pytest backend/tests -q`

## Frontend Integration Contract (Step-by-Step)

1. Login
- `POST /auth/login` -> keep `access_token`, `client_id`

2. Use bearer token for all REST calls
- Header: `Authorization: Bearer <token>`

3. Dashboard data
- `GET /clients/{id}/positions`
- `GET /clients/{id}/trades`
- `GET /clients/{id}/agent/status`

4. Agent console actions
- `POST /clients/{id}/agent/chat`
- `POST /clients/{id}/agent/mode`
- `POST /clients/{id}/agent/parameters`
- `POST /clients/{id}/agent/approve/{trade_id}`
- `POST /clients/{id}/agent/reject/{trade_id}`

5. Realtime updates
- `WS /clients/{id}/stream?token=<jwt>`

## Recommended Next Implementation Steps

1. Add risk parameter editor and guardrails UI.
2. Add broker reconnect form on settings page.
3. Add contract tests that validate frontend payload schemas against backend responses.
4. Add a global emergency trading halt endpoint (`/admin/trading-halt`) with audit trail.
5. Add production RLS policies at DB level (currently enforced in application layer).

## Known Gaps

- IBKR/Phillip live APIs still need environment-specific tuning (market data permissions, exact exchange/contract mappings).
- Alembic workflow is scaffolded; future schema changes need proper generated revisions.
