# WhatToDo — Operating Protocol v1.1 (Feb 2026)

This file defines how we build, think, and ship in this repo.
It applies to every AI-assisted coding session.

## 1. Core Principles
- System thinking > speed
- Constraints breed quality
- Reflection is mandatory, not optional
- Tradeoffs must be named explicitly

## 2. AI Usage Protocol

### 2.1 Severity Gate (when the full protocol is mandatory)
Treat work as `major` if it includes any of:
- New API endpoint, request/response contract, or schema/model change
- State model change (query keys, cache behavior, session/auth flow)
- UI flow change affecting approval/execution/safety behavior
- Broker/risk/auth/emergency-halt logic changes

For major work, Reflection + Self-Critique blocks are required.
For small/low-risk work, `WHATTODO_FAST.md` is allowed.

### 2.2 While AI Generates Code
After every major code block / feature output, AI MUST append a:

#### Reflection Block
"While This Generates — Think About This"

Must contain (specific to code just produced):
- 3 architecture/design questions to debate
- 2 realistic edge-case scenarios that could break it
- 1 concrete performance concern (e.g., rerender loops, invalidation churn)
- 1 scalability concern (e.g., more brokers/tenants/domains/concurrency)
- 1 deeper topic/pattern/paper/tool to study next (with why it matters here)

No generic fluff. Tie directly to the artifact.

#### Self-Critique Mode
AI must:
- Name one non-trivial design flaw or smell in what was generated
- Propose one concrete alternative approach
- Ask explicitly:
  - "Which direction feels right here, and why — or do you see a third path?"

Goal: surface real decisions, not happy-path agreement.

### 2.3 Feature/Domain Additions
- Propose folder + component impact first
- Include:
  - "How does this respect Operator vs Dev mode separation?"
- Suggest:
  - "What new Zustand slice / hook / type would this need?"

### 2.4 Prompt Evolution
- Version prompt inline (e.g., `Codex Prompt v2.1 — Elite Repo`)
- Include a short diff of what changed and why

## 3. Safety Stops (mandatory pause points)
AI must pause for explicit confirmation before:
- DB migrations affecting production data path
- Auth model changes (token shape, session semantics, admin access)
- Destructive commands (`reset`, deletes, force operations)
- Contract-breaking API changes

## 4. Verification Contract (required in final response)
Every meaningful change must include:
- What was tested
- What was not tested
- Residual risk

## 5. Scope Guard
- Do not silently edit unrelated files
- If unrelated local changes are detected, stop and ask before commit

## 6. Decision Log Rule
For each major feature, record a short ADR-style note:
- Context
- Chosen approach
- One rejected alternative + why

Can be stored in handoff or feature notes.

## 7. Evolution Rules
- Update this file when a ritual proves broken/insufficient
- Commit message MUST explain trigger
  - Example: "saw repeated state sync bugs -> added optimistic updates rule"
- If a section becomes obsolete, archive at bottom with date + reason (do not delete)

## 8. Archive
- None yet

Last updated: 2026-02-20
