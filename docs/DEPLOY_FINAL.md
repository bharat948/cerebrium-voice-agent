# Deploy Voice Foundry v3 to Render without a laptop tunnel

## Local developer setup

```bash
cp .env.example .env
# Replace demo APP_API_KEY, SESSION_SECRET and POSTGRES_PASSWORD with new random strings.
docker compose up --build -d
docker compose logs -f voice-foundry
```

Open `http://localhost:8000` and sign in with the local `APP_API_KEY`. Windows: replace `cp` with `Copy-Item`. Local demo does not require provider credentials or an open inbound port.

## Render Blueprint

1. Upload the extracted repository to GitHub without `.env` or local database data.
2. Create **New → Blueprint** from this repository root. Review current Render Web Service and managed PostgreSQL pricing before accepting.
3. Verify `vector` extension is available in PostgreSQL. Container startup runs Alembic migrations before Uvicorn.
4. Configure Google OIDC: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_OWNER_SUB`, and the redirect `https://<your-render-host>/auth/google/callback`. Confirm it rejects other Google users.
5. Set `INTEGRATION_ENCRYPTION_KEY` to a persistent Fernet key, generated offline with:

   ```bash
   python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
   ```

6. Optionally connect Contacts/Calendar separately at `/auth/google/connect`. Their OAuth callback path is `https://<your-render-host>/auth/google/connect/callback`.
7. Set `OPENAI_API_KEY`, Twilio credentials, optional Brave Search, Twelve Data and SMTP credentials in Render Environment, never in Git.
8. Keep `DEMO_MODE=true` until staging security and consent checks pass. For private agents set `OWNER_PHONE`; record contact-specific call permissions and consent before enabling real calls.
9. Set Twilio phone voice webhook to `POST https://<your-render-host>/twilio/voice`. Test with one authorized number.

The service uses `PUBLIC_BASE_URL` from `RENDER_EXTERNAL_URL` in `render.yaml`.

### Important: migrating your existing v2 SQLite database

**Do not redeploy against a fresh empty PostgreSQL database and expect prior calls to magically appear.** Take a validated SQLite backup and follow [`DATA_MIGRATION_V3.md`](DATA_MIGRATION_V3.md). Production migrations require a maintenance window, row count comparison and rollback plan.

### Production security conditions

- Paid, always-on Render instance is recommended for active calls. Free instances sleeping during a phone call are unsuitable.
- Do not enable outbound calls without proper recipient authorization, quiet hours and local legal requirements.
- The current candidate recognizes inbound callers by their phone number, but **does not provide OTP-based caller verification**; do not enable privileged financial, private-task or other high-impact voice actions for unverified callers.
- In-process mission worker and voice sessions require `numInstances: 1`. Do not scale to multiple Render instances without new concurrency architecture.
- `MONTHLY_BUDGET_USD` is an application estimate guardrail, not a guaranteed provider cost ceiling.

### Rollback

1. Disable live calls (`DEMO_MODE=true`) and wait for ongoing calls to end.
2. Back up the PostgreSQL database and export changes since the last known-good release.
3. Restore known-good application image and matching schema state; automatic destructive Alembic downgrades are deliberately unsupported.
4. Run health, login, call planning and memory-scope smoke tests before re-enabling provider integrations.
