## 4.0.0-alpha2 (2026-10-16)

- Keep voice sessions open for recoverable `responses_validation_failed` events before or after startup.
- Retain bounded, credential-redacted provider error messages in logs and owner call events.
- Optional single backend-model retry using `session.update`, preserving authorized tools.
- Apply the same recovery to the browser sandbox and bound startup waits to one deadline.
- Add a short GPT-Live configuration probe that does not dial Twilio or execute custom tools.
- Provider account access and live call behavior still require deployment verification.

## 4.0.0-alpha1 (2026-10-16)

- Temporal and consent-aware agent/contact memory consolidation with contradiction review.
- Privacy opt-out, expiry/provenance metadata, and improved rank/filter logic.
- Bounded per-agent speech policies integrated into GPT-Live prompts and local barge-in thresholds.
- Human-review-backed, owner-approved agent improvement drafts.
- Owner v4 APIs, UI controls, 0005 migration, 11 additional tests, documentation.
- Still requires live-provider, PostgreSQL, load and security validation.

## v3.2.0-dev (16 October 2026)

- Agent architect proposes editable expert configurations with review-first publication.
- Contact edits, consent changes and soft deactivation with authorization revocation.
- Immutable agent release restore-to-draft with historical version preservation.
- Fixed read-only tool gateway with bounded timeouts, permissions and audit events.
- Mission pause/revise/resume/cancel; timeline events; cancel-before-delivery fence.
- Manual memory correction/forget audit and pgvector erasure for forgotten items.
- Dashboard owner controls and Alembic revision 0002.
- Regression suite expanded to 36 passing offline tests.

**Not production validated:** Live provider credentials, Render deployment, PostgreSQL data migration, and advanced voice tool-delegation remain release gates.

# Changelog

## [3.1.0-alpha] - 2026-10-16

- Preserved v2 Twilio and GPT-Live voice bridge, planner and demo paths.
- Introduced one shared SQLAlchemy persistence facade for PostgreSQL + test SQLite.
- Added PostgreSQL/pgvector Compose and Render Blueprint and an Alembic baseline.
- Added specialist templates, versioned agent releases, prompt compiler and call-version pinning.
- Added contact registry, CSV import, outbound/email consent, scoped memory management.
- Added fixed tools, mission records, background worker, safe demo simulation and SMTP report delivery.
- Added owner Google OIDC routes, contacts/missions/studio UI surfaces, CI and expanded docs.
- Added v3 domain tests (26 passing offline total).

**Known gaps:** Real-provider smoke tests, advanced caller OTP, Google Contacts/Calendar,
in-call tools, full agent architect, RAG ingestion, complete mission DAGs, and load testing
are not included. See docs/IMPLEMENTATION_STATUS.md.

## Legacy v2

Previous release notes and deployment docs are preserved in `docs/legacy/`.

## [3.9.0-rc1] - 2026-10-16

- Integrated voice runtime, agent studio, contact consent, memory, knowledge and durable research into a single FastAPI modular monolith.
- Added actual GPT-Live delegated built-in functions: research, knowledge, memory, scoped task and appointment proposals, plus NSE/BSE quote adapter.
- Added owner approvals, estimated spending controls, notifications, intervention state, post-call reports, and the browser voice sandbox.
- Added encrypted Google Contacts/Calendar connection, controlled imports and Google calendar read.
- Added trust-tiered PDF/DOCX knowledge ingestion, PostgreSQL vector indexing (`0004`) and an ACL-filtered semantic fallback.
- Added research scheduling, worker steps, idempotent occurrence enqueue, parallel query discovery and SMTP consent checks.
- Expanded UI, CI, Render/Docker settings and test suite; documented live-provider and privacy release gates.
