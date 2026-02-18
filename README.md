# Trading Agent Backend

Production-oriented async backend for multi-tenant delta-neutral futures options agent trading.

## Features

- FastAPI + asyncio backend with JWT auth
- Multi-tenant client isolation via `client_id` scoping
- Agent modes:
- `confirmation`: analysis and proposal generation only
- `autonomous`: risk-checked direct execution
- Risk governor hard stops:
- max net delta
- max order size
- max daily loss
- max open legs
- market-hours guard
- spread guard
- circuit breaker on 3 consecutive >$500 losses
- Broker abstraction + adapters:
- IBKR (`ib_insync`)
- PhillipCapital REST (`httpx`)
- Mock broker for local/test operation
- PostgreSQL models + Redis-ready app state
- Celery worker scaffold for async tasks
- Structured JSON logging

## Project Layout

`backend/main.py` FastAPI entrypoint
`backend/agent/` agent orchestration, tools, prompts, risk, memory
`backend/brokers/` broker abstractions and integrations
`backend/api/` REST + websocket endpoints
`backend/db/models.py` SQLAlchemy models
`backend/tests/` pytest coverage for risk, broker, and agent flows

## Environment

Copy `.env.example` to `.env` and fill values.

Minimum local safe setup:

- `DATABASE_URL=sqlite+aiosqlite:///./trading.db`
- `REDIS_URL=redis://localhost:6379/0`
- `JWT_SECRET=change_me`
- `ENCRYPTION_KEY=<32-char raw key>`
- `USE_MOCK_BROKER=true` (default in settings)
- `AUTONOMOUS_ENABLED=false`
- `ADMIN_API_KEY=<strong-random-secret-for-admin-endpoints>`
- `AUTO_CREATE_TABLES=true` (dev only)
- `CORS_ORIGINS=http://localhost:3000,http://localhost:5173`

## Run Locally

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

## Run With Docker

```bash
docker compose up --build
```

API starts at `http://localhost:8000`.

## Frontend (Step 1)

```bash
cd frontend
npm install
npm run dev
```

Frontend default URL: `http://localhost:5173`

## Test

```bash
pytest backend/tests -q
```

## API Endpoints

- `POST /auth/login`
- `POST /clients/onboard`
- `POST /clients/{id}/connect-broker`
- `GET /clients/{id}/positions`
- `GET /clients/{id}/trades`
- `POST /clients/{id}/agent/mode`
- `POST /clients/{id}/agent/parameters`
- `POST /clients/{id}/agent/chat`
- `POST /clients/{id}/agent/approve/{trade_id}`
- `POST /clients/{id}/agent/reject/{trade_id}`
- `GET /clients/{id}/agent/status`
- `GET /clients/{id}/agent/proposals`
- `GET /admin/emergency-halt` (requires `X-Admin-Key`)
- `POST /admin/emergency-halt` (requires `X-Admin-Key`)
- `WS /clients/{id}/stream`
- `GET /health`
- `GET /health/ready`

## Notes

- `USE_MOCK_BROKER=true` keeps development deterministic and removes live broker dependency.
- Enable real broker adapters only after validating risk logic and proposal flow.
- Audit log rows are written for decisions, executions, mode changes, and risk violations.
- `AUTONOMOUS_ENABLED=false` is a global kill switch. Autonomous mode requests are blocked and audited.
- Emergency trading halt is independent of autonomous mode and blocks all trade executions (including proposal approval), with audit entries written per tenant.
- Postgres RLS is enabled for tenant tables (`positions`, `trades`, `proposals`, `audit_log`, `agent_memory`) and enforced using DB session context (`app.current_client_id`, `app.is_admin`) in addition to existing application-level tenant checks.
- Redis keys are namespaced per tenant (for example `client:{client_id}:greeks` and `client:{client_id}:events`) to keep real-time state isolated.
- WebSocket stream emits `agent_status`, `greeks`, and incremental `agent_message` events for live frontend updates.

Broker-related API failures now return structured `detail` payloads for telemetry:
`{"type":"broker_error","operation":"...","broker":"ibkr|phillip","code":"...","message":"...","retryable":true|false,"context":{...}}`.

## Runbooks

- Emergency halt operations: `docs/runbooks/emergency-halt.md`
- Broker reconnect/failure triage: `docs/runbooks/broker-failure-triage.md`
- Postgres RLS tenant debugging: `docs/runbooks/rls-tenant-debugging.md`

## Migrations (Alembic)

Config: `backend/db/alembic.ini`

Run upgrade:

```bash
alembic -c backend/db/alembic.ini upgrade head
```

Create new revision:

```bash
alembic -c backend/db/alembic.ini revision -m "your_change"
```

For production, set `AUTO_CREATE_TABLES=false` and run Alembic migrations explicitly.

## Live Broker Mode

Set `USE_MOCK_BROKER=false` to run real adapters.

Per-client credential payloads expected in onboarding/connect:

- IBKR:
- `{"host":"localhost","port":4002,"client_id":1,"underlying_instrument":"IND","underlying_expiry":"202603","connect_retries":3,"connect_backoff_seconds":0.5,"exchange_overrides":{"YM":"CBOT"},"trading_class":"EX1","multiplier":"50"}`
- Phillip:
- `{"client_id":"...","client_secret":"...","request_retries":3,"request_backoff_seconds":0.4,"exchange":"CME","currency":"USD"}`

Credentials are encrypted at rest and decrypted only for broker session creation.
