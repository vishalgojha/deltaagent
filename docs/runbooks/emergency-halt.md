# Emergency Halt Runbook

## Purpose
Stop all trade execution globally (including proposal approval execution) without changing tenant mode settings.

## Prerequisites
- `ADMIN_API_KEY` configured in backend environment.
- API reachable at `http://localhost:8000` (replace with your env URL).

## Check Current Halt State
```bash
curl -sS -H "X-Admin-Key: $ADMIN_API_KEY" \
  http://localhost:8000/admin/emergency-halt
```

Expected response fields:
- `halted`
- `reason`
- `updated_at`
- `updated_by`

## Engage Global Halt
```bash
curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -d '{"halted": true, "reason": "manual incident stop"}' \
  http://localhost:8000/admin/emergency-halt
```

## Release Global Halt
```bash
curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -d '{"halted": false, "reason": "incident resolved"}' \
  http://localhost:8000/admin/emergency-halt
```

## Verify Behavior
- New trade execution attempts should fail while halted.
- Proposal approval execution should fail while halted.
- Agent mode (`confirmation`/`autonomous`) remains unchanged.

## Audit Verification
Check `audit_log` for `event_type = emergency_halt_updated` per tenant.

