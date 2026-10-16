# Data Migration: Voice Foundry v2 SQLite → v3 PostgreSQL

**Never point a production v3 release at a new empty Postgres database and assume legacy data migrated automatically.** The v2 SQLite and v3 PostgreSQL records are separate until you run the migration.

1. Schedule a short maintenance window. Stop new call plans and ensure existing calls complete.
2. Preserve the exact production SQLite DB and take a provider-level disk snapshot or offline copy.
3. Create a new PostgreSQL instance with pgvector enabled. Back up its initial empty state.
4. From a trusted machine/container with both DBs accessible, export `DATABASE_URL` to the target, run:

```bash
python scripts/migrate_sqlite_to_postgres.py \
  --sqlite /data/voice_foundry.db \
  --backup /data/voice_foundry-before-v3.db \
  --dry-run
```

5. Confirm the backup and source record counts; then run the same command **without `--dry-run`**, choosing a new backup path because the utility will refuse an existing destination.
6. Confirm row counts in `agents`, `plans`, `calls`, `events`; inspect sample records and linked identifiers.
7. Run `python -m alembic upgrade head`, then boot the app against Postgres.
8. Check agent lists, old transcripts, call-plan creation and a demo conversation before setting `DEMO_MODE=false`.
9. Retain SQLite backup for rollback. Post-cutover PostgreSQL writes are **not** automatically synced back to SQLite.

The migration is idempotent at the primary-key level (`ON CONFLICT DO NOTHING`). It does not automatically merge conflicting updates. Failure to validate source/target records is a blocking release issue.
