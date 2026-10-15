> **v0.2 GPT-Live update:** The original implementation remains available; see [GPT-Live Upgrade](GPT_LIVE_UPGRADE.md) for the new default engine, API differences, selection, Render migration and validation.

# Security, privacy, safety & production hardening

## Implemented safeguards

- API key protected `/api/*` routes. Browser keeps token in session storage; it is not embedded in JS bundle.
- Twilio-signed HTTP webhooks and WebSocket handshake in live mode.
- Outbound numbers restricted to explicit `ALLOWED_OUTBOUND_NUMBERS` in environment (empty means **no outbound calls**).
- Explicit plan review and `confirm=true` for call initiation. Atomic plan claim reduces accidental double dials.
- `MAX_CONCURRENT_CALLS`, `MAX_CALLS_PER_HOUR`, and `MAX_CALL_SECONDS` throttles.
- The system prompt discloses AI identity and forbids claiming unverified bookings.
- Only text transcripts, status changes, and diagnostics are stored; **audio recordings are not implemented**.
- Database and runtime files ignored by Git.
- `DEMO_MODE=true` default; live-mode startup rejects sample API key or disabled Twilio validation.

## Risk register

| Risk | Current mitigation | Must add before production |
|---|---|---|
| Public control plane compromise | API key + live-mode sample-key check | Per-user login, MFA, RBAC, TLS access gateway, token rotation, audit logs |
| Unwanted calls | Allowlists + approval + hourly limit | Verified contact consent registry, opt-out suppression list, rate limits per recipient, local-time windows |
| Twilio spoofing | Signed requests + CallSid binding | Validate full webhook/proxy deployment, run signed WS tests behind intended tunnel |
| Data privacy | No audio at rest, TTL text purge on startup | Scheduled retention job, encryption at rest/backups, deletion/export APIs, consent records, redaction |
| Fraud / provider overspend | Duration, concurrency, calls/hour | Spend budget, provider alerts, circuit breaker, admin kill switch |
| Prompt injection | System policy, no executable business tools | Stronger action policy engine, guarded tool gateway, review of external context |
| State/data loss | SQLite WAL + Docker named volume | PostgreSQL, managed backups, queue, distributed lock, migrations |
| Streaming service error | Error events, cancellation | Retries where safe, backoff, fallback announcements, watchdog, traces, typed state machine |
| Live scaling | Single-container runtime | Multi-replica session affinity, warm workers, durable event bus, call routing |
| API endpoint abuse | API key | IP allowlists, WAF, network rate-limiting (current API calls have no per-user limit) |
| Insider data exposure | No browser secrets except API key | Central secrets manager, least-privilege tokens, explicit access audit |

## Telephony compliance

Telemarketing, automated calling, voice recording, AI disclosure and consent requirements vary by jurisdiction. This service does not grant consent. **Before calling**, ensure the destination is legally contactable, properly consented, not on a suppression/do-not-call list, and within permitted calling hours. India has specific telecommunication and unsolicited commercial communication requirements; check current TRAI/provider rules for your intended category and number type. Never misrepresent the assistant as human.

## Production launch checklist

- [ ] Change API key to a long random secret; rotate regularly.
- [ ] Restrict external access to dashboard through authenticated reverse proxy (e.g. Cloudflare Access).
- [ ] Test Twilio signed POST and WS through your actual proxy/tunnel domain.
- [ ] Validate outgoing caller ID, country permissions, consent, AI notice, and suppression lists.
- [ ] Add recipient-level contact policy and quiet hours.
- [ ] Move from SQLite to PostgreSQL and add migrations.
- [ ] Add structured tracing, metrics, p95 latency alarms, provider-error alerting.
- [ ] Add secure webhook replay handling/idempotency, durable jobs, cost accounting.
- [ ] Implement configurable retention sweep (currently runs **only on startup**).
- [ ] Add roles and encrypted customer-data storage.
- [ ] Add integration tests in a real provider test account and test interruptions across carrier routes.
- [ ] Apply provider data usage and deletion settings per your obligations.
- [ ] Deploy to a monitored host with always-on WebSocket access, backups, and clear rollback process.

## Threat boundaries

Phone audio from Twilio/Deepgram and caller speech are **untrusted input**. A caller cannot authorize the model to book, pay, expose secrets, or dial other people. The current app has no business tools; when adding tools, use an independent authorization/confirmation gateway that checks an explicit approved schema and idempotency key before any side effects.
