# Implementation Plan: Voice Foundry v3

**Status:** Approved product direction; `v3.1.0-alpha` implementation in this repository. **Deployment approach:** one FastAPI web instance on Render (or one local application process) + PostgreSQL/pgvector. Later: Docker cluster with extracted workers and shared routing.

## Product constraints carried forward

- Single owner; registered contacts; private/shared/public agents.
- Inbound receptionist routing and outbound calls with owner confirmation.
- Versioned layered instructions; stable identity and bounded adaptive expressive speech.
- GPT-Live handles real-time speech; bounded workers handle long-form research.
- Memory isolated by agent/contact, consent-aware, time-aware and source-backed.
- Fixed integrations initially, no user-defined arbitrary tools or cross-agent delegation.
- Missions survive application restarts and must avoid duplicate external effects.
- Automatic report email only with verified, revocable recipient consent.
- Preserve the working v2 Twilio route, media bridge, and call plan API during migration.

## Architectural decisions

| Concern | Decision | Rationale |
|---|---|---|
| Deployment | Modular monolith | Single operational unit, clear future extraction boundaries |
| Persistence | PostgreSQL + pgvector | Relational correctness + scoped semantic search |
| Realtime | Twilio 8-kHz µ-law → GPT-Live WS | Avoid separate STT and TTS latency |
| Speech personality | Layered compiled instructions | Testability and consistent guardrails |
| Background research | DB-backed durable worker | Recoverable, inexpensive single-instance start |
| Authentication | Google OIDC allowlisted subject | One-owner security boundary |
| Tooling | Curated integrations | Reduced attack surface |
| Tests | Human voice evaluation + automated software tests | Quality first, correctness baseline |

## Delivery roadmap

### M0: Baseline preservation (completed in alpha)

- Import exact v2 calling implementation, retain endpoints, add regression suite.
- Set trunk repo conventions, CI, sample environment and local run commands.
- **Acceptance:** original v2 tests pass; demo cannot place outbound calls.

### M1: Domain foundation (initial implementation in alpha)

- PostgreSQL adapter, schema bootstrapping, Alembic baseline, verified SQLite migration script.
- Agent templates, draft/publish, stable release references.
- Contact Registry with CSV import, consent fields and per-agent grants.
- Memory scope and candidate storage with restricted-secret filtering.
- **Acceptance:** test setup works offline; Postgres and Google live integration remain release gates.

### M2: Production readiness for v3.1 (next priority)

- End-to-end PostgreSQL migration dry run and deterministic consistency checks.
- Google OAuth production smoke tests, session/CSRF hardening, grant revocation tests.
- Agent Studio visual editor, voice browser sandbox using WebRTC.
- Robust contact permissions for inbound selection, recipient verification and opt-outs.
- Hardened call budgeting and live-metrics dashboard.
- **Acceptance:** stable deployment with real authorized calls, no cross-contact disclosure.

### M3: Tool and memory intelligence

- Trusted news and web adapters with freshness/provenance; financial data licensed for NSE/BSE.
- Google Calendar and Contacts OAuth scopes; appointment booking with confirmation and idempotency.
- Automatic post-call memory extraction with consent, temporal consolidation and human review.
- In-call GPT-Live tool delegation with deadlines and cancellation.
- **Acceptance:** measured real tool latency, source attribution, and correct authorized writes.

### M4: Durable missions and outgoing reports

- Mission step DAG, lease recovery, budget checkpoints, approval inbox.
- Source-backed worker reports with verifiable attribution and email provider receipts.
- Scheduling, pause/resume, cancellation and deduplication.
- **Acceptance:** restart mid-job neither loses a mission nor silently duplicates a call/email.

### M5: Operational maturity

- Full live takeover and intervention, typed tool audit, notification policies, cost estimates and spending limits.
- Knowledge ingestion / RAG, scheduled trusted-source updates, semantic recall evaluations.
- Docker cluster extraction only after real concurrent-call benchmarks.
- **Acceptance:** reproducible load tests, rollback drills, threat-model signoff, documented operator runbooks.

## Implementation work packages / acceptance checks

| ID | Work package | Required evidence |
|---|---|---|
| VF-101 | Postgres production migration | Full backup, counts, FK/integrity validation, rollback drill |
| VF-102 | Owner Google OIDC | Correct `sub`, session expiration, denied unknown Google account |
| VF-103 | Contact authorization | No auto-call on import, revoked consent stops future calls |
| VF-104 | Prompt compiler | Stable release, no overriding platform rules |
| VF-105 | Voice bridge | 8-kHz audio integrity, barge-in under measured target |
| VF-106 | Memory scope | Cross-agent/contact access tests and erasure |
| VF-107 | Tool gateway | Schema validation, audit, timeouts, idempotency |
| VF-108 | Worker reliability | Crash/restart/duplicate-delivery fault injection |
| VF-109 | Owner monitoring | Live transcript, status, pause/hangup, audit trail |
| VF-110 | Agent Studio | Draft/edit/publish/rollback UX, manual sandbox checklist |
| VF-111 | Browser testing | WebRTC verified, no real effects in sandbox |
| VF-112 | Budget governance | Per-call budget and provider reconciliation |

## Release disciplines

- Feature changes land through PRs with unit/integration tests and a change log.
- Database migrations have forward scripts and rollback-by-backup runbooks; never silently rewrite production records.
- Real-world write tools must have idempotency keys and post-operation verification.
- Any new model/provider needs a smoke test and documented fallback.
- Explicitly separate paid-provider staging from safe local demo behaviour.
