# Pre-deployment release gates

- [x] Local Python syntax compilation.
- [x] JavaScript syntax compilation (`node --check web/app.js`).
- [x] Offline API, policy and worker tests (see CI).
- [ ] Migrate **a backup copy** of current SQLite using `scripts/migrate_sqlite_to_postgres.py --dry-run`, then execute the migration against staging PostgreSQL.
- [ ] `alembic upgrade head` on staging PostgreSQL with pgvector installed.
- [ ] Confirm OAuth issuer, audience and owner `sub` restrictions with actual Google credentials.
- [ ] Confirm Twilio webhook signature and `wss://` audio frames in a live authorized test.
- [ ] Verify agent-personality prompts do not expose private memory to unverified callers.
- [ ] Test consent revocation during an active mission and SMTP delivery retry reconciliation.
- [ ] Measure end-to-end median and P95 voice latency and interruption recovery.
- [ ] Review provider and communications consent requirements for all outbound recipients.
- [ ] Verify Render Starter instance concurrency and safe restart behavior.
- [ ] Confirm backup, restore and rollback procedures before touching current production.

**The code in this branch is a functional development release, not a completed deployment of all product decisions.**
