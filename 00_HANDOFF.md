# START HERE: HANDOFF

Last updated: 2026-02-27

## 1) Current State (Fast)
- Branch: `main`
- Sync status: `main...origin/main`
- Local status: clean
- Latest CI: Run `#86` succeeded (`c32cb65`)
  - URL: `https://github.com/vishalgojha/deltaagent/actions/runs/22487816674`

## 2) What Was Completed Most Recently
### CI stability and release hardening fixes (runs #83 -> #86)
- Fixed Playwright screenshot spec in ESM context (`__dirname` resolution).
- Stabilized smoke reject action selector to avoid flaky class-based selection.
- Kept execution source visible after proposal approval path.
- Fixed strict env validation failure in CI by quoting `ENCRYPTION_KEY`.
- Fixed release migration path in CI by invoking Alembic as module:
  - `python -m alembic -c backend/db/alembic.ini upgrade head`
- Fixed `CORS_ORIGINS` env contract in CI (JSON list form) to satisfy settings parsing in migration context.

### Files touched in latest CI hardening
- `frontend/e2e/screenshots.spec.ts`
- `frontend/e2e/smoke.spec.ts`
- `.github/workflows/ci.yml`

## 3) Most Recent Commits (Newest First)
- `c32cb65` Use JSON CORS origins in release hardening CI env
- `e5e13ea` Run Alembic via python module in release hardening CI
- `0df3f94` Fix CI env key quoting and stabilize Playwright smoke specs
- `06b8a82` Keep execution source visible after proposal approval
- `5aec067` Add execution auto-remediation policies with dashboard controls
- `90f1e48` feat: add alert actions, runbook guidance, and release hardening gates
- `e48215b` feat: add execution quality monitoring, fill idempotency, and safer defaults
- `9efe7f8` test: harden frontend suite for storage and execution assertions

## 4) Run Locally
### Easiest
From repo root:
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
- Production/staging must use non-default secrets for:
  - `JWT_SECRET`
  - `ADMIN_API_KEY`

## 7) Pending
1. Capture and commit docs screenshots:
   - run `capture_screenshots.bat`
   - commit `docs/screenshots/*.png`
2. Railway deploy:
   - ensure Railway service vars satisfy the env contract above
   - deploy backend service from `main`
   - run post-deploy smoke
3. Live broker reconnect sanity check (IBKR collision path) in real integration environment.

## 8) Important Files
- `00_HANDOFF.md`
- `.github/workflows/ci.yml`
- `frontend/e2e/screenshots.spec.ts`
- `frontend/e2e/smoke.spec.ts`
- `scripts/validate_env.py`
- `scripts/post_deploy_smoke.py`
- `backend/db/alembic.ini`
