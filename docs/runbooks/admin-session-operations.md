# Admin Session Operations Runbook

## Purpose
Operate privileged admin actions without repeatedly transmitting raw admin key on every request.

## Backend API
- `POST /admin/session/login` with `{"admin_key":"..."}`
- `GET /admin/emergency-halt` with `Authorization: Bearer <token>`
- `POST /admin/emergency-halt` with `Authorization: Bearer <token>`

## Recommended Operator Flow
1. Unlock admin session from UI (`Unlock Admin`).
2. Perform required safety actions.
3. Lock admin session from UI (`Lock Admin`) once complete.

## CLI Example
```bash
# 1) Login
ADMIN_TOKEN=$(curl -sS -X POST \
  -H "Content-Type: application/json" \
  -d "{\"admin_key\":\"$ADMIN_API_KEY\"}" \
  http://localhost:8000/admin/session/login | jq -r ".access_token")

# 2) Query halt status
curl -sS -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/admin/emergency-halt
```

## Troubleshooting
- `401 Invalid admin key` on login:
  - Verify `ADMIN_API_KEY` in backend `.env`.
  - Confirm key copy/paste has no spaces/newline.
- `401 Invalid admin token` on halt endpoints:
  - Token expired or malformed.
  - Re-login and retry.
- `503 Admin API key is not configured`:
  - Backend is missing `ADMIN_API_KEY`.
  - Set it, restart backend, retry.

## Security Notes
- Keep admin key out of browser storage and logs.
- Admin token is short-lived (`jwt_expire_minutes` based).
- Backend still supports `X-Admin-Key` fallback for compatibility; prefer bearer token path.
