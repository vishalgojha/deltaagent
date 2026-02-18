# Postgres RLS Tenant Debugging Runbook

## Purpose
Debug tenant-isolation issues with row-level security (RLS) and DB session context.

## Expected Model
- App layer enforces tenant scope by `client_id`.
- Postgres RLS enforces tenant scope for:
  - `positions`
  - `trades`
  - `proposals`
  - `audit_log`
  - `agent_memory`
- Session vars used by policies:
  - `app.current_client_id`
  - `app.is_admin`

## Quick Verification SQL (Postgres)
```sql
SHOW row_security;
SELECT current_setting('app.current_client_id', true), current_setting('app.is_admin', true);
```

## Confirm Policies Exist
```sql
SELECT schemaname, tablename, policyname, permissive, cmd
FROM pg_policies
WHERE tablename IN ('positions','trades','proposals','audit_log','agent_memory')
ORDER BY tablename, policyname;
```

## Confirm RLS Enabled/Forced
```sql
SELECT relname, relrowsecurity, relforcerowsecurity
FROM pg_class
WHERE relname IN ('positions','trades','proposals','audit_log','agent_memory')
ORDER BY relname;
```

## Common Failure Modes
1. Missing DB context in request flow.
2. Admin context accidentally retained across pooled connections.
3. Running against non-Postgres DB (RLS migration is Postgres-only).
4. App-level checks bypassed in custom code path.

## What This Repo Already Does
- Sets tenant/admin DB context in API deps (`backend/api/deps.py`).
- Resets context on pooled connection checkout (`backend/db/session.py`).
- Keeps app-layer tenant assertions (`assert_client_scope`) as second layer.

## Incident Response
1. Capture request path and authenticated client id.
2. Capture returned data tenant ids.
3. Verify RLS settings and policies above.
4. Verify app context variables at runtime.
5. Patch and add regression test before release.

