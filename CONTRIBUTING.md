# Contributing

We welcome documentation, tests, accessibility improvements, and provider adapters.

## Development

1. Fork and create a feature branch from `main`.
2. Copy `.env.example` to `.env`, enable `DEMO_MODE=true` and use test credentials only.
3. Run `python -m pip install -r requirements.txt -r requirements-dev.txt`.
4. Run `python -m pytest -q` and `node --check web/app.js`.
5. Open a PR with scope, tests, risks, schema changes, and screenshots for UI changes.

Do not commit credentials, real recordings, contact lists, phone numbers, or raw call transcripts.

## Code guidelines

- Preserve existing Twilio webhook and GPT-Live streaming contracts.
- Keep domain code in `app/v3/` and guard external effects in the backend.
- Every new API write requires owner authorization and input validation.
- Avoid cross-agent memory leakage; scope queries to agent and contact.
- Treat web/news/documents as untrusted data, not system instructions.
- Make paid provider calls opt-in; include a no-network test path.
- Provide both success and failure tests for new features.

## Security

Do not open an issue containing a security vulnerability or customer data. Follow [SECURITY.md](SECURITY.md) for responsible disclosure.
