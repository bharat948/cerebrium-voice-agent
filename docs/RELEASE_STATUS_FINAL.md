# Voice Foundry v3.9 RC: evidence-based completion status

This repository integrates the approved Voice Foundry product direction into a **single deployable modular monolith**. It is a release candidate for evaluation, **not** proof that every planned feature works against external accounts. Never enable outbound live calling for unconsenting recipients.

## Functional, covered by offline tests

| Capability | Scope of delivery |
|---|---|
| Twilio + GPT-Live-1 | Twilio HTTP signature validation, bidirectional μ-law WebSocket bridge, session initialization, playback clearing, transcript events, per-call engine selection; Deepgram fallback retained. |
| Agent Studio | Specialist news/markets/appointment/task templates, drafts, publication, immutable release rollback, compiled platform/agent/mission/persona instructions, natural-language architect draft. |
| Contacts | Create/edit/deactivate, CSV import, agent-contact access grants, E.164 validation, consent flags, searchable dashboard selectors. |
| Memory | Agent-contact-scoped storage, routine memory extraction after calls, lookup, correction, deletion, optional pgvector similarity for indexed memory. |
| Built-in tools | Google News RSS, Brave web search, optional NSE/BSE licensed quote via Twelve Data, knowledge search, task proposals and local appointment availability/proposal. Runtime GPT-Live Responses delegation with backend checks. |
| Background missions | Postgres-backed research jobs, leases, steps, revision, cancellation, schedules, bounded research, conditional SMTP delivery and outcome notifications. |
| Knowledge | TXT/MD/CSV/PDF/DOCX upload, parsing and chunking, private/shared ACL, trust tiers, lexical retrieval and optional PostgreSQL vector indexing/search. |
| Owner operations | Approval inbox, budget estimates and thresholds, live instruction/pause/stop controls, notifications, call history, conservative call outcomes, voice lab route. |
| Integrations | Google OIDC owner login, separate opt-in Contacts and Calendar API connection with Fernet-encrypted credentials, local appointment bookings requiring exact owner-approved scopes. |
| Delivery | Docker Compose, Render Blueprint, baseline and additive Alembic revisions, CI including PostgreSQL migration job, SQLite migration utility, docs, and tests. |

## What needs real provider validation

- OpenAI GPT-Live session startup, function-delegation completions, browser microphone audio, and interruption quality on a live call.
- Twilio webhook validation under Render's exact proxy URL and inbound traffic; actual cost and latency.
- Google owner OAuth callbacks, Calendar/Contacts scopes and token refresh against your Google Cloud consent screen.
- PostgreSQL/pgvector **vector embedding index** and semantic query; a GitHub Actions job is supplied, but did not execute in this environment.
- Financial data entitlements for NSE/BSE, Brave API, Google News RSS availability, SMTP deliverability, OpenAI token permissions.
- CPU/memory limits, restart recovery and concurrency under production loads.

## Planned requirements not fully delivered in this candidate

- Verified caller identity with phone OTP or an equivalent strong credential for privileged phone access; a recognized phone number alone remains insufficient.
- Dynamic receptionist dialogue that switches agent **within the same live call**, and Twilio conference-based human takeover.
- Full native Google Calendar write-through and authoritative availability reconciliation. The implemented booking backend operates against the **local** calendar only; Google Calendar read is independent.
- Long-term memory deduplication / temporal consolidation, caller self-service privacy dashboard, comprehensive deletion cascade into all backups/providers, automatic expiry of every data class.
- Autonomous cross-call multi-step workflow DAGs and cross-server distributed execution. Current persistent research worker supports bounded research and simple recurring schedules, not arbitrary workflows.
- Automated source monitoring/revalidation; embedding index jobs for arbitrary large corpora; verified extraction of complete web article text; production-grade reranking.
- Full mobile push/email escalations, secure live audio monitoring by the owner, voice human takeover, real billing reconciliation, 100% naturalness evaluations, automated agent self-improvement proposals.
- A complete, externally audited security review, accessibility audit, full CI provider integration suite and high concurrency load testing.

**Release gate:** deploy to staging, perform a PostgreSQL migration dry run and run a short consenting Twilio call. Keep `DEMO_MODE=true` until those checks and privacy disclosures pass. See [Verification](VALIDATION_FINAL.md).
