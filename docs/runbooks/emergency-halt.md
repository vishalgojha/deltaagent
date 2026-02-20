# Emergency Halt Runbook

## Purpose
Stop all trade execution globally (including proposal approval execution) without changing tenant mode settings.

## Prerequisites
- `ADMIN_API_KEY` configured in backend environment.
- API reachable at `http://localhost:8000` (replace with your env URL).

## Step 1: Create Admin Session Token
```bash
ADMIN_TOKEN=$(curl -sS -X POST \
  -H "Content-Type: application/json" \
  -d "{\"admin_key\":\"$ADMIN_API_KEY\"}" \
  http://localhost:8000/admin/session/login | jq -r ".access_token")
```

If your shell has no `jq`, copy the `access_token` manually from response JSON.

## Step 2: Check Current Halt State
```bash
curl -sS -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/admin/emergency-halt
```

Expected response fields:
- `halted`
- `reason`
- `updated_at`
- `updated_by`

## Step 3: Engage Global Halt
```bash
curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"halted": true, "reason": "manual incident stop"}' \
  http://localhost:8000/admin/emergency-halt
```

## Step 4: Release Global Halt
```bash
curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"halted": false, "reason": "incident resolved"}' \
  http://localhost:8000/admin/emergency-halt
```

## UI Flow (Agent Console / Admin Safety)
1. Enter admin key once and click `Unlock Admin`.
2. Enter reason and (for halt) confirmation text `HALT`.
3. Click `Enable Global Halt` or `Resume Trading`.
4. Click `Lock Admin` when done.

## Verify Behavior
- New trade execution attempts should fail while halted.
- Proposal approval execution should fail while halted.
- Agent mode (`confirmation`/`autonomous`) remains unchanged.

## Audit Verification
Check `audit_log` for `event_type = emergency_halt_updated` per tenant.

## Compatibility Note
`X-Admin-Key` header is still accepted as fallback, but bearer token flow is the preferred operational path.
