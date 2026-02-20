# Screenshot Shotlist

Capture these images from latest UI build and store in this folder.

## One-command capture
From repo root (recommended):
```bash
capture_screenshots.bat
```

Alternative from `frontend/`:
```bash
npm run screenshots:e2e
```
This writes PNG files directly into `docs/screenshots/`.

## Required Shots
1. `agent-console-safety-policy.png`
- Page: Agent Console
- Must show: `Safety Policy` card with mode + risk limits + Global Halt

2. `agent-console-trade-ticket-modal.png`
- Page: Agent Console
- Must show: `Trade Ticket Confirmation` modal with cancel/confirm buttons

3. `agent-console-lifecycle-source.png`
- Page: Agent Console
- Must show: lifecycle panel and `Source: websocket` (or `Source: polling`)

4. `admin-safety-unlock.png`
- Page: Admin Safety or Agent Console safety section
- Must show: `Unlock Admin` / `Lock Admin` session controls

## Optional GIF
- `agent-console-execute-flow.gif`
- Flow: proposal -> execute checkbox -> modal confirm -> lifecycle update

## Naming Rules
- Lowercase
- Hyphen-separated
- `.png` for static images, `.gif` for flow animation

## Publish Checklist
- Confirm no secrets in screenshots.
- Confirm browser URL or token query params are hidden.
- Confirm timestamps and status badges are readable.
