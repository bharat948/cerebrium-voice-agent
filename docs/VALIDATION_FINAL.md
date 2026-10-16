# Verification, staging rollout and acceptance gates

## Offline commands

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m compileall -q app scripts
python -m pytest -q
node --check web/app.js
```

Fresh development migration using a disposable database:

```bash
DATABASE_URL= DB_PATH=/tmp/voice-foundry-smoke.db python -m alembic upgrade head
```

A GitHub Actions job also runs Alembic against `pgvector/pgvector:pg17`, but the current artifact creation environment did not run that CI job or a local Docker container.

## Live staging smoke-test checklist

- [ ] Sign in as the exact owner via Google OIDC. A different Google account is rejected.
- [ ] Verify both managed PostgreSQL and `vector` extension exist, and migration revision is `0004`.
- [ ] Create Aria, Kuber, Mira, Atlas; publish an agent release and ensure a new call references it.
- [ ] Import a test contact, explicitly record calling consent and grant the correct agent access.
- [ ] Keep `DEMO_MODE=true` and validate call plans, simulated calls, missions and read-only endpoints.
- [ ] Configure OpenAI, Twilio and a consenting test recipient; turn off demo mode for a **single short** phone call.
- [ ] Confirm opening AI disclosure, listen/speak audio, one interruption, and transcript attribution.
- [ ] Test delegated Google News/Brave search and ensure sources are labeled as search results, not validated full articles.
- [ ] Test a local appointment proposal; inspect approval, then book using the exact approved arguments.
- [ ] Test OAuth connection for Google Contacts/Calendar with separately granted permissions. Confirm imported contacts have no automatic contact consent.
- [ ] Ingest a private document for Aria and prove that Kuber cannot retrieve it. Try vector indexing on staging PostgreSQL.
- [ ] Test browser voice with microphone permission. Confirm demo and live-test modes remain isolated.
- [ ] Test authorized research email delivery once, using your own verified test mailbox; ensure successful SMTP response and follow-up state.
- [ ] Test the owner stop/hangup controls and verify Twilio terminates the call as expected.
- [ ] Restart the service with a queued research mission; verify mission recovery and no duplicate email.
- [ ] Record first audible audio, end-of-turn latency, tool latency, provider costs, 95th percentile over several calls and failure rate.
- [ ] Restore from a backup to a staging database before merging.

## Observability and release safety

- Never log Twilio auth tokens, OpenAI keys, Google refresh tokens or sensitive transcripts in plaintext logs.
- Mark estimates as estimates. `expenses` does not automatically reconcile external OpenAI/Twilio invoices.
- Do not infer OTP-verified caller identity from phone number alone.
- Ensure business/contact permission and data-retention compliance before opening the inbound number to unknown callers.
- Treat any unverified provider path above as **pending validation**, not as a verified production feature.

## Reporting

The release ZIP bundles `docs/BUILD_REPORT.md` with verified local test count, syntax checks, migration revision, file count and relevant limitations.
