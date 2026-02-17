# Frontend (Step 1)

Minimal React + TypeScript UI wired to backend endpoints.

## Setup

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Default app URL: `http://localhost:5173`

## Test

```bash
npm run test
npm run test:e2e
```

## Current Screens

- Login
- Onboarding (create client + optional broker connect)
- Dashboard (status, positions, recent trades)
- Agent Console (chat timeline, mode switch, inline proposal approve/reject, websocket status cards)
- Broker Settings (reconnect broker, update creds, and check health)
- Query-cached API state via TanStack Query
- Central session guard + route-level error boundary
- Unit coverage for login/onboarding/proposal actions/websocket
- Playwright smoke for login -> chat proposal -> approve/reject

## Backend Requirements

- Backend running at `http://localhost:8000`
- CORS must include `http://localhost:5173`
- WebSocket auth uses `?token=<jwt>`

## Next UI Steps

1. Add frontend test coverage for login/onboarding/proposal and websocket flow.
2. Add Playwright smoke flow for login -> proposal -> approve/reject.
