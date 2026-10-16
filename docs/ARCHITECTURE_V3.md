# Architecture and Module Ownership

## Processes

`uvicorn app.main:app` hosts the HTTP dashboard and Twilio WebSocket endpoint and runs one background polling task. The `db` process in Docker Compose is PostgreSQL with pgvector. On Render, database is a managed resource and the application stays a single instance.

## Code map

- `app/main.py`: backward-compatible HTTP, phone-call lifecycle, Twilio webhook and WebSocket entry points.
- `app/live_voice.py`: OpenAI GPT-Live-1 session, µ-law passthrough, transcript deltas and Twilio playback controls.
- `app/voice.py`: optional Deepgram cascaded voice-engine fallback.
- `app/db.py`: database access facade shared by old and new modules, guarded SQL parameters.
- `app/v3/registry.py`: templates, agent releases and platform-first prompt compilation.
- `app/v3/contacts.py`: contact registration, validation, import.
- `app/v3/memory.py`: scoped retrieval, deletion, optional embeddings.
- `app/v3/tools.py`: built-in news/web/task tools, no arbitrary external tool registration.
- `app/v3/missions.py`: research worker, durable job state, email handoff.
- `app/v3/auth.py`: Google OIDC login routes.
- `app/v3/api.py`: versioned domain routes and permission checks.
- `web/`: zero-build HTML/CSS/JS dashboard.

## Invariants

1. Public caller audio never creates a trusted authorization policy.
2. No cross-contact memory retrieval: `agent_id` AND `contact_id` are mandatory.
3. Tool data is untrusted input; do not reinterpret it as developer instructions.
4. A pre-existing call pins its agent release.
5. No outbound call without explicit owner confirmation and allowed/consenting recipient.
6. Work already marked `sending` is not retried automatically because external delivery status may be unknown.
7. No real external effects in demo mode.

## Future extraction seams

- `app/live_voice.py` → standalone voice gateway service with sticky WebSocket routing.
- `app/v3/missions.py` → containerized workers with shared queue and leases.
- `app/v3/tools.py` → service adapters with per-tool budgets.
- `app/v3/memory.py` → knowledge/memory service after multi-tenant isolation is complete.

Never enable multiple app instances while using the in-process mission polling loop or process-local live-call state.
