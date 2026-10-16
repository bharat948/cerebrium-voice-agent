> **v0.2 GPT-Live update:** The original implementation remains available; see [GPT-Live Upgrade](GPT_LIVE_UPGRADE.md) for the new default engine, API differences, selection, Render migration and validation.

# Local setup: Windows / macOS / Linux

## Recommended hardware

A 2-core laptop with 4+ GiB RAM and internet access is sufficient for local proxying of cloud speech APIs. OpenAI/Deepgram inference is remote. No local GPU is necessary. Each live call uses a few outbound WebSocket/HTTP connections; configure small concurrency initially.

## 1. Install

- Docker Desktop and Docker Compose V2 (Windows: install WSL2 backend).
- For live calling only: ngrok CLI or Cloudflare Tunnel. Both must support inbound secure WebSocket upgrade.

## 2. Start in demo mode

```powershell
Expand-Archive .\voice-foundry.zip -DestinationPath . -Force   # if needed
cd voice-foundry
Copy-Item .env.example .env
docker compose up -d --build
Invoke-RestMethod http://localhost:8000/health
Start-Process http://localhost:8000
```

If your ZIP already extracts into `voice-foundry/`, use that directory. Enter `APP_API_KEY` from `.env` at the UI login.

Try *Call studio* → phone `+14155552671` (a sample E.164 number, don't actually dial it) → write briefing → Create plan → edit → Approve & start preview → type mock caller replies in Call history. With no OpenAI API key, planning and preview responses are templates, not model inference.

## 3. Configure providers (for real calling)

### Twilio

Open the Twilio Console, copy **Account SID**, **Auth Token**, and your voice-enabled purchased phone number. Write to `.env`. If trial: verify a destination phone number and confirm outbound permissions. Twilio regional restrictions / calling permission settings can prevent dialing even if the API accepts the request. Use E.164 format.

### Deepgram

Open [Deepgram Console](https://console.deepgram.com/), create API key. This project directly forwards μ-law 8 kHz audio to `/v1/listen` with the configurable `nova-3` model. It uses `/v1/speak` with `aura-2-thalia-en`, raw μ-law 8 kHz output. This defaults to **English voice output**; do not assume Hindi voices work until your provider model supports them.

### OpenAI

Open [OpenAI API Keys](https://platform.openai.com/api-keys), create key, set `OPENAI_API_KEY`. Set `OPENAI_MODEL=gpt-4o-mini` or another Chat Completions-compatible model that supports streaming. With this key, both agenda generation and demo previews use the model. Avoid sharing secrets in the UI.

### Tunnel

```powershell
# terminal 1
ngrok http 8000
# e.g. https://abc123.ngrok-free.app
```

Add `PUBLIC_BASE_URL=https://abc123.ngrok-free.app` to `.env`. Twilio webhooks go to `/twilio/voice`, while the voice WebSocket is generated as `/twilio/media` with a `wss://` scheme. No query string parameters are added to the Stream URL; a custom Stream Parameter passes `call_id` instead.

For Cloudflare Tunnel, configure a hostname that forwards HTTPS and WebSockets to `http://localhost:8000`. Public hostname and secure stream URLs must be reachable externally.

### Allowlist + enable

```dotenv
APP_API_KEY=<your new random key>
DEMO_MODE=false
TWILIO_VALIDATE_SIGNATURES=true
TWILIO_ALLOW_INBOUND=true
PUBLIC_BASE_URL=https://abc123.ngrok-free.app
ALLOWED_OUTBOUND_NUMBERS=+14155552671,+919876543210
```

Numbers here are illustrative; set only authorized recipients. Restart with `docker compose up -d --build --force-recreate`, then use the new API key to sign in. Ensure no browser extension or logging component reveals it.

## 4. Verify the actual call

1. Verify provider billing, limits, and Twilio caller permissions.
2. Compose an agenda in the web UI and explicitly approve it.
3. Observe *Call history*: `queued → ringing → in-progress → completed` (Twilio may skip steps). Check transcript events and callback errors.
4. Call back your Twilio number to test inbound flow if enabled.
5. Speak over the agent mid-sentence to test interruption and Twilio `clear` behavior.
6. Inspect `docker compose logs -f voice-foundry` for failures. Avoid logging customer speech.
7. Check call duration and balance in Twilio/Deepgram/OpenAI dashboards.

## 5. Day-to-day commands

| Action | Command |
|---|---|
| Start | `docker compose up -d` |
| Start and rebuild | `docker compose up -d --build` |
| Follow logs | `docker compose logs -f voice-foundry` |
| Stop | `docker compose down` |
| Force restart after `.env` edit | `docker compose up -d --force-recreate` |
| Run tests with Python environment | `python -m pytest -q` |
| Remove data permanently | `docker compose down -v` (destructive!) |

## Common issues

- **401 on dashboard:** entered wrong `APP_API_KEY`, clear session storage/sign out and try again.
- **502 on plan creation:** check model/API key and network; without an OpenAI key it uses a template.
- **400 live not ready:** missing HTTPS PUBLIC_BASE_URL or a Twilio/OpenAI/Deepgram key.
- **403 outbound recipient:** add number to `ALLOWED_OUTBOUND_NUMBERS` in E.164 notation, then restart; do not disable allowlist.
- **Twilio 403 signature:** confirm public URL exactly matches what Twilio requested, check Twilio auth token, ensure tunnel is HTTPS. WebSockets may require a trailing slash normalization.
- **Twilio returns no audio:** inspect `wss://` connection; confirm Deepgram TTS voice/encoding and 8 kHz μ-law, inspect streamed Events.
- **Hindi pronunciation poor:** Aura English-only default. Use an appropriate multilingual TTS vendor/voice in a new adapter before production.
- **No inbound:** point phone number voice webhook to `https://<tunnel>/twilio/voice` (POST). A manual outgoing call uses its own TwiML URL and does not require setting the number webhook.
- **Docker doesn't boot:** inspect logs, ensure port 8000 free, Docker daemon up, and `.env` exists.
