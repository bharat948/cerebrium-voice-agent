# Test Report: v3.1.0-alpha

**Execution environment:** Python 3.13.5, existing test-only Twilio fallback where SDK unavailable. No live external provider credentials used. Results are not a claim of production-readiness.

## Verified

- `python -m pytest -q`: **26 passed**.
- `python -m compileall -q app scripts migrations`: passed.
- `node --check web/app.js`: passed.
- `yaml.safe_load(render.yaml)`: succeeded, 1 web service + 1 managed PostgreSQL declaration.
- Alembic bootstrap against an empty SQLite database: created schema tables; `db.init_db()` seeded the default assistant.

## Not verified

- Docker image build and Compose startup (Docker unavailable in this build environment).
- PostgreSQL/pgvector startup and vector similarity query (no live Postgres service here).
- Google OIDC login and callback against actual Google credentials.
- Twilio Media Streams, GPT-Live real-session audio, Deepgram voice fallback under live network conditions.
- SMTP deliverability, Brave/Google News availability under production quotas.
- Render Blueprint deploy and production data migration.

## Before a live launch

Run a short consented call, database backup/restore, role/access/consent tests, fake interruption scenario, worker crash/restart test, tool timeouts and network-fault checks on the deployed service. Any failure is a stop-ship condition for unattended outbound calling.
