# START HERE: HANDOFF

Last updated: 2026-02-28

## 1) Current State (Fast)
- Branch: `main`
- Sync status: `main...origin/main`
- Local status: dirty (18 modified, 3 untracked test files, local `trading.db`)
- Latest local commit: `89dad45` (handoff refresh)
- Latest known CI: Run `#91` succeeded for `2282218`
  - URL: `https://github.com/vishalgojha/deltaagent/actions/runs/22515797674`

## 2) What Was Completed Most Recently
### Local dev install/start reliability
- Updated `start.bat` to auto-detect `.venv` Python path variants.
- README now documents Windows `py` alias/runtime pitfalls (`py install 3.11`) and PowerShell invocation notes (`.\start.bat`).

### Login/CORS + frontend network handling
- Hardened CORS configuration parsing in `backend/config.py` and middleware setup in `backend/main.py`.
- Added frontend API timeout and clearer network/timeout errors in `frontend/src/api/client.ts`.

### Strategy builder robustness
- Improved expiry parsing and DTE matching in `backend/strategy_templates/service.py` (handles more formats including `YYYYMM`).
- Improved butterfly wing strike selection and one-sided chain error messages.
- Updated UI default DTE range on strategy templates page (`7-45`).
- Added tests:
  - `backend/tests/test_strategy_template_expiry_selection.py`
  - `backend/tests/test_strategy_template_wing_selection.py`

### Agent LLM provider and key management work
- Added client-scoped LLM credential endpoints:
  - `GET /clients/{id}/agent/llm-credentials`
  - `POST /clients/{id}/agent/llm-credentials`
- Added schema models for LLM credential status/update in `backend/schemas.py`.
- Updated `AgentManager` and `TradingAgent` for provider-aware routing with backends:
  - `openai`, `anthropic`, `openrouter`, `xai`, `ollama`, `deterministic`
- Added OpenAI/xAI key resolution (client credential first, env fallback) and improved symbol alias parsing (including "esmini").
- Updated frontend Agent Console to expose backend selector + API key form/status.
- Updated CLI/options and env validation/docs:
  - `scripts/agent_cli.py`
  - `scripts/validate_env.py`
  - `.env.example`
  - `README.md`

## 3) Most Recent Commits (Newest First)
- `89dad45` Refresh handoff with Railway continuity and next-session actions
- `2282218` Add root endpoint for base URL health response
- `aeaf306` Fix startup launcher import path for container runtime
- `b3dfcef` Fix Railway port handling with Python startup entrypoint
- `141a80b` Fix Railway startup command and normalize Postgres DB URLs

## 4) Run Locally
### Easiest
From repo root:
- `.\start.bat`
- `status.bat`
- `stop.bat`

If Python 3.11 is missing:
```powershell
py install 3.11
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

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

## 5) Deploy Readiness Checklist
- Validate env:
```powershell
python scripts/validate_env.py --target staging --strict-warnings
```
- Run migrations:
```powershell
python -m alembic -c backend/db/alembic.ini upgrade head
```
- Post-deploy smoke:
```powershell
python scripts/post_deploy_smoke.py --base-url https://YOUR_BACKEND_URL --require-ready
```

## 6) Required Env Contract (important)
- `ENCRYPTION_KEY` must be exactly 32 characters.
- `CORS_ORIGINS` should be a JSON list string for strict/deploy contexts:
  - example: `["https://your-frontend-domain.com"]`
- `REDIS_URL` must point to a reachable Redis instance for `/health/ready` to pass.
- LLM backends require matching keys:
  - `AGENT_LLM_BACKEND=openai` -> `OPENAI_API_KEY`
  - `AGENT_LLM_BACKEND=xai` -> `XAI_API_KEY`
  - `AGENT_LLM_BACKEND=anthropic` -> `ANTHROPIC_API_KEY`
  - `AGENT_LLM_BACKEND=openrouter` -> `OPENROUTER_API_KEY`
- Production/staging must use non-default secrets for:
  - `JWT_SECRET`
  - `ADMIN_API_KEY`

## 7) Pending
1. Commit and push current local work:
   - review and stage modified files (exclude local `trading.db`)
   - include new tests under `backend/tests/`
   - run final pre-push test sweep
2. Verify sign-in flow end to end from browser:
   - confirm preflight `OPTIONS /auth/login` no longer returns `400`
   - ensure backend `CORS_ORIGINS` includes active frontend origin(s)
3. Verify per-client LLM key flow:
   - open Agent Console
   - save key for each backend as needed (`openai`/`anthropic`/`openrouter`/`xai`)
   - run a chat action and confirm non-deterministic backend is used
4. Re-test strategy builder with live chain edge cases:
   - ensure DTE window returns contracts for common underlyings
   - verify butterfly construction on sparse chains
5. Railway readiness follow-up:
   - attach/configure Redis service
   - set backend `REDIS_URL`
   - verify `/health/ready` returns `200`
6. Re-run deploy smoke after Redis is healthy:
   - `python scripts/post_deploy_smoke.py --base-url https://<backend-url> --require-ready`

## 8) Important Files
- `00_HANDOFF.md`
- `README.md`
- `.env.example`
- `start.bat`
- `backend/config.py`
- `backend/main.py`
- `backend/api/agent.py`
- `backend/agent/core.py`
- `backend/agent/manager.py`
- `backend/schemas.py`
- `backend/strategy_templates/service.py`
- `backend/tests/test_agent_llm_credentials_api.py`
- `backend/tests/test_strategy_template_expiry_selection.py`
- `backend/tests/test_strategy_template_wing_selection.py`
- `frontend/src/pages/AgentConsolePage.tsx`
- `frontend/src/pages/StrategyTemplatesPage.tsx`
- `frontend/src/api/client.ts`
- `frontend/src/api/endpoints.ts`
- `frontend/src/types.ts`
- `scripts/validate_env.py`
- `scripts/post_deploy_smoke.py`
