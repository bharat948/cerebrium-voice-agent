> **Superseded for v3.9 RC.** See [current release status](RELEASE_STATUS_FINAL.md), [build report](BUILD_REPORT.md) and [validation checklist](VALIDATION_FINAL.md). The older v3.2 feature list below is retained for historical traceability.

# Voice Foundry v3.2 feature workstreams: implementation status

The 64 accepted product decisions define the **target product**, not the feature-completion status of this codebase. This document deliberately distinguishes working code from interface contracts and planned work.

## Implemented and covered by offline tests

- V2 compatible outbound call planning, Twilio webhook verification, GPT-Live-1 session bridge, interruption buffer clear, optional Deepgram fallback, demo conversation and transcript event storage.
- Shared SQLAlchemy persistence adapter that targets PostgreSQL in deployment and SQLite for developer tests.
- Four templates (`news`, `markets`, `appointments`, `tasks`), with explicit draft and publish actions; published prompt config pinned when a new call record is created.
- Contact CRUD including consent-aware update and soft deactivation (create/list/update/deactivate), duplicate-phone validation, CSV import, outbound/email consent flags and agent-contact permission table.
- Scoped memory creation/listing/tombstoning/correction with event history and vector erasure with sensitivity restrictions and denylist for obvious secrets.
- Built-in local task creation, policy-gated read-only tool gateway with audit trail, and a fixed integration catalog.
- Durable queued research missions with pause/resume/revision/cancel, event log, cancellation-before-email fence, atomic claim, demo-mode no-network simulation, and live-mode email delivery requiring recorded contact consent and configured SMTP.
- Versioned API routes and dashboard screens for contact consent, memories, release restoration, missions, and agent architect proposals.
- Google OIDC single-owner authentication routes with server session; deployment configuration requires `GOOGLE_OWNER_SUB`.
- Regression checks (offline pytest + JavaScript syntax test), Docker Compose, and Render Blueprint.

## Partial or needs real-provider validation

- `pgvector` memory index and semantic search: code paths implemented, **not validated** against a running PostgreSQL/pgvector deployment in this environment; lexical search remains the fallback.
- PostgreSQL and SQLite one-time migration: migration utility implemented, **requires dry run and source/target verification against your actual database**.
- Google OIDC callback/login: code implemented, **not live-tested with your credentials**.
- Research/email worker: implemented with Brave/Google News, OpenAI and SMTP, **not live-tested or reviewed for deliverability**. Search metadata is not verified full article content.
- Agent Studio advanced editor: versioned APIs, restore and prompt preview exist; the dashboard currently provides template creation and the basic agent form, not the planned full visual editor.
- Memory: stored preferences can be preloaded; continuous extraction/consolidation and comprehensive self-service controls are deferred.
- Inbound routing: limited routing for recognized contacts with exactly one authorized shared agent; a full conversational routing receptionist is deferred.

## Not implemented yet

- Owner/caller OTP verification and privileged voice actions; Google Contacts synchronization; Google Calendar scheduling and booking verification; live NSE/BSE licensed feeds; full speech-time tool execution using GPT-Live delegation; comprehensive browser microphone playground; call takeover/conferencing; contact-facing memory portal; continuous agent evolution; automated knowledge ingestion/RAG across arbitrary uploaded documents; cross-node distribution; comprehensive mission DAG orchestration; complete metered cost prediction; approval inbox and push notifications.

## Critical release gates

1. Validate PostgreSQL startup, Alembic baseline, credentials and disk backup.
2. Test Google OIDC authentication and contact access isolation.
3. Run live Twilio/GPT-Live calls and measure interruption latency.
4. Confirm consent processes, data retention compliance and provider licensing.
5. Conduct threat model and penetration testing before unknown public callers are accepted.

The current release is intended for iterative development and explicitly authorized trials, not unattended use with arbitrary recipients.
