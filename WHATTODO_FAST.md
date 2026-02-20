# WhatToDo — Fast Mode v1.0 (Feb 2026)

Use this mode only for low-risk, bounded edits.

## Eligibility (all must be true)
- No API contract change
- No auth/session/risk/emergency-halt behavior change
- No schema/migration change
- No cross-page UX flow change
- Touches are limited and reversible

If any condition fails, use `WHATTODO.md` full protocol.

## Fast Mode Output Contract
For each change, AI should provide:
- 1 short intent line
- 1 risk note
- 1 verification step

## Fast Mode Reflection (minimal)
- 1 edge case
- 1 performance watchpoint
- 1 follow-up suggestion (optional)

## Stop Conditions
Immediately escalate to full protocol if:
- Scope expands unexpectedly
- Unrelated file modifications appear
- Tests reveal behavior regressions

Last updated: 2026-02-20
