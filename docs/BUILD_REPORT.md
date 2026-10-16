# Build verification report

**Build:** Voice Foundry `3.9.0-rc1`
**Date:** 2026-10-16
**Package:** single-server modular-monolith source release

## Reproducible checks completed in artifact environment

| Check | Result |
|---|---|
| `python -m pytest -q` | **50 passed** in ~2.0 seconds |
| `python -m compileall -q app scripts` | Passed |
| `node --check web/app.js` | Passed |
| Fresh SQLite Alembic upgrade | Passed to revision `0004`; 28 tables |
| `render.yaml`, `docker-compose.yml`, CI workflow YAML | Parsed successfully |
| FastAPI OpenAPI schema generation | Succeeded; 64 documented route paths |

The offline tests use a **test-only Twilio SDK shim** when the actual Twilio Python SDK is absent. This means test success **does not prove** real Twilio HTTP signing or media-stream SDK integration. All dependencies are declared in `requirements.txt` for real installation.

## Checks not performed

- Building/running Docker image and validating Render Blueprint against a live Render account.
- Running Alembic on a live PostgreSQL + pgvector instance (a CI job is provided but not executed here).
- Real OpenAI GPT-Live speech-to-speech and Responses tool delegation, Twilio calls, Deepgram fallback.
- OAuth consent/login and Google Contacts/Calendar API calls, encrypted integration tokens with actual Google refresh cycles.
- Live Brave Search, Google News, Twelve Data financial feeds and authenticated SMTP email delivery.
- Load tests at two or more simultaneous calls, privacy/consent legal review, security penetration testing.

## Current release policy

This release candidate is suitable for local demo, code review, staging, and carefully controlled opt-in provider testing. It must not be described as a fully audited production deployment or a complete implementation of every original product decision. See `RELEASE_STATUS_FINAL.md` and `VALIDATION_FINAL.md`.
