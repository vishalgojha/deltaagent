# Broker Failure And Reconnect Triage

## Purpose
Triage IBKR/Phillip connection and request failures quickly using API error payloads and broker retry telemetry.

## Where Failures Surface
API errors include structured broker detail:
```json
{
  "type": "broker_error",
  "operation": "connect|get_positions|chat|approve_proposal|...",
  "broker": "ibkr|phillip",
  "code": "...",
  "message": "...",
  "retryable": true,
  "context": {}
}
```

## IBKR Triage
1. Inspect `context` fields like `host`, `port`, `client_id`, `retries`, `last_error`.
2. Verify gateway/TWS availability and account session.
3. Reconnect explicitly:
```bash
curl -sS -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"broker_credentials": null}' \
  http://localhost:8000/clients/$CLIENT_ID/connect-broker
```
4. If symbol mapping fails, check contract payload fields:
- `symbol`, `instrument`, `expiry`, `strike`, `right`, `exchange`.

## Phillip Triage
1. Check `context` fields such as:
- `endpoint`, `status`, `attempt`, `retries`, `last_error_type`, `last_error`.
2. Validate OAuth credentials (`client_id`, `client_secret`).
3. Confirm transient status (`429/5xx`) vs non-retryable failures.
4. Reconnect/update credentials:
```bash
curl -sS -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"broker_credentials":{"client_id":"...","client_secret":"..."}}' \
  http://localhost:8000/clients/$CLIENT_ID/connect-broker
```

## Escalation Checklist
- Error reproducible with same payload?
- Retryable true/false?
- Only one tenant or all tenants?
- Time-correlated upstream outage?
- Attach structured error detail to incident ticket.

