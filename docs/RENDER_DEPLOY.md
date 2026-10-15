# Deploy Voice Foundry to Render (no tunnel or laptop server required)

The `render.yaml` in this repository is a **one-service paid Render Blueprint** that runs both the dashboard and the FastAPI WebSocket voice runtime in the same Docker container. You do NOT need ngrok, Cloudflare Tunnel, Docker Desktop, SSH access, or a permanently running laptop. Twilio and browsers connect directly to your public Render HTTPS/WSS address.

> **Deployment status:** The Blueprint and code can be checked offline, but deployment and live calling with your Twilio/Deepgram/OpenAI accounts have not been verified. Budget for test calls and review your telecom compliance obligations.

## 1. Push the repository to GitHub

**Use a private repository. Never commit `.env` or provider credentials.**

Extract the project, initialize a repository if needed, and push it:

```bash
git init
git add .
git commit -m "Initial Voice Foundry app with Render Blueprint"
git branch -M main
git remote add origin https://github.com/YOUR-USER/voice-foundry.git
git push -u origin main
```

If the remote repository is already set up, use your normal `git push`. You can also upload the files to GitHub through its browser interface from a restricted machine.

## 2. Deploy to Render using the Blueprint

1. Go to https://dashboard.render.com/ and connect your GitHub account.
2. Choose **New > Blueprint**, select the repository and the `main` branch.
3. Confirm the Blueprint reads the root `render.yaml` and review the **paid** web service plus persistent disk before approval.
4. Sync/Apply the Blueprint. Render builds from `Dockerfile` and creates a public address resembling `https://voice-foundry-xxxx.onrender.com`.
5. Open `https://YOUR-SERVICE.onrender.com/health` and check for `{"status":"ok", ...}`.
6. Under Render > your service > **Environment**, reveal or replace the generated `APP_API_KEY` value. This is the dashboard login key. Treat it as a password.
7. Open `https://YOUR-SERVICE.onrender.com` and enter the `APP_API_KEY`. The default `DEMO_MODE=true` lets you plan and simulate calls without provider credentials.

### Why the Blueprint specifies these values

| Setting | Reason |
| --- | --- |
| `runtime: docker` | Builds the existing Dockerfile. |
| `PORT=8000` | The current Dockerfile listens on port 8000, while Render otherwise defaults to 10000. |
| `PUBLIC_BASE_URL` from `RENDER_EXTERNAL_URL` | Twilio webhooks and WebSocket callbacks use Render's actual public HTTPS URL automatically. |
| `healthCheckPath: /health` | Render can detect unhealthy deployments. |
| `disk` mounted at `/data` | SQLite, agent definitions, plans, call records and transcripts survive normal redeploys. |
| `numInstances: 1` | SQLite plus a single attached disk is not suitable for horizontal scaling. |
| `APP_ENV=production` | Ensures production application guardrails are active. |
| `DEMO_MODE=true` | Deployment cannot place real calls until explicitly enabled. |

Render's paid persistent disks and paid compute incur charges, even if `DEMO_MODE=true`. Review the dashboard price before confirming. Do not use Free for reliable inbound calls: Free sleeps after idle and loses its SQLite data whenever the service restarts or redeploys.

## 3. Configure provider credentials in Render

In **Environment**, add these variables **as secret values in Render, not in GitHub**:

```dotenv
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=<your-twilio-auth-token>
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX
DEEPGRAM_API_KEY=<your-deepgram-key>
OPENAI_API_KEY=<your-openai-key>
ALLOWED_OUTBOUND_NUMBERS=+14155552671,+14155552672
DEMO_MODE=false
```

`PUBLIC_BASE_URL` is set by the Blueprint; do not override it unless using a verified custom domain. The default TTS voice `aura-2-thalia-en` is English-only. The language setting in the agent UI alone does not make that voice multilingual. Choose a verified voice/model for other languages.

If your Twilio account is on a trial, outbound destinations may have to be verified first. Calls to Indian destinations can have separate Twilio policy, eligibility and regulatory restrictions. Obtain consent and disclose that the caller is an AI agent; check local rules before placing calls.

**Safety:** The app refuses outbound calls to any number not listed in `ALLOWED_OUTBOUND_NUMBERS`. Each call requires a call plan and an explicit confirmation. Never expose your API key, Twilio auth token, or service environment variables publicly.

## 4. Set Twilio incoming-number webhook

In the Twilio Console: **Phone Numbers > Manage > Active Numbers > [your number] > Voice**.

Set **A call comes in** -> **Webhook** -> **HTTP POST**:

```
https://YOUR-SERVICE.onrender.com/twilio/voice
```

The FastAPI endpoint responds with TwiML instructing Twilio to open a secure bidirectional media stream at:

```
wss://YOUR-SERVICE.onrender.com/twilio/media
```

Do not set `/twilio/media` as the phone webhook. It is a WebSocket endpoint used **after** Twilio receives the TwiML from `/twilio/voice`.

For outbound calls initiated from the dashboard, the application automatically configures Twilio's call and status callbacks using `PUBLIC_BASE_URL`. You do not need a separate Twilio webhook for outbound calls.

## 5. Test sequence

1. With `DEMO_MODE=true`, create an agent and a call agenda and execute a preview. Check that call history remains after a deploy.
2. Configure provider secrets, allowlist only a test number you control, and set `DEMO_MODE=false`.
3. Open the dashboard, prepare the call agenda, review it, and explicitly approve the call. Confirm it rings and that speech is audible in both directions.
4. Inspect the call transcript and logs from **Render > Logs**. Check Twilio's call logs if the call does not connect.
5. Test an inbound call to your Twilio number using `/twilio/voice`.
6. Test speaking over the assistant's response to verify Twilio `clear` interruption handling.

This is an MVP. Do not assume that every telephony edge case is production-ready until you have exercised live calls (transcription, latency, codec handling, WebSocket signature validation, disconnects, retries and service restarts).

## 6. Troubleshooting

| Symptom | Check |
| --- | --- |
| Render reports no open port | Blueprint must set `PORT=8000` because Dockerfile uses 8000. |
| `APP_API_KEY` login fails | Use the generated key in Render > Environment; don't use the old local demo password. |
| Calls rejected as not configured | Verify `DEMO_MODE=false`, all provider credentials, `TWILIO_PHONE_NUMBER`, and `PUBLIC_BASE_URL`. |
| Outbound 403 | Recipient not in the exact `ALLOWED_OUTBOUND_NUMBERS` list. |
| Twilio 403 on callback | Check `TWILIO_AUTH_TOKEN`, public HTTPS domain, and webhook method POST. Keep `TWILIO_VALIDATE_SIGNATURES=true`. |
| Voice connects but no audio | Inspect Twilio, Render and Deepgram logs. Verify Twilio μ-law audio frames and STT/TTS responses. |
| Dashboard works, calls have long delay | Avoid Free tier; use paid always-on instance and review service region/provider latency. |
| History disappears | Free/ephemeral filesystem, or disk not attached to `/data`. |
| Service restarts during call | A deploy or platform restart can terminate active WebSockets. Avoid deployments during live calls. |

## Free demo-only deployment (manual alternative)

You can deploy a **Free** Render Web Service from the same GitHub repository with **Docker** runtime, without the paid `render.yaml` Blueprint. Set the following under **Environment**:

```
PORT=8000
APP_ENV=production
APP_API_KEY=<strong-random-key>
DEMO_MODE=true
DB_PATH=/data/voice_foundry.db
```

This is for **disposable previewing only**. Free instances spin down after inactivity and lose stored agents/calls whenever they restart or redeploy. There is no persistent disk. You can still test the UI and demo conversations. Never use the Free option for reliable business telephone service.

## Limits of this version

- Single-process SQLite-backed architecture; one paid instance with a disk. Scaling requires PostgreSQL and shared runtime coordination.
- The browser UI uses a workspace API key and is designed for a trusted single-user prototype, not multi-user SaaS authentication.
- ChatGPT Action schema is present in `integrations/chatgpt`, but must be imported/configured separately, with authentication.
- No recording consent flow, contact DNC integration, full provider retry orchestration, SLA, or validated production load-testing yet.

## Official docs

- https://render.com/docs/websocket
- https://render.com/docs/infrastructure-as-code
- https://render.com/docs/blueprint-spec
- https://render.com/docs/disks
- https://render.com/docs/free
- https://www.twilio.com/docs/voice/twiml/stream

## Dashboard error: `Unable to generate plan (HTTPStatusError)`

This message (from the first release) means the **OpenAI Chat Completions API rejected
our call-planning request**; it is not a Render Blueprint-generation problem.

1. Go to **Render > Web Service > Logs**, press **Create Plan** again, and locate
   `Plan generation error`. In the first release, the log exception contains an
   HTTP status, for example `401 Unauthorized` or `429 Too Many Requests`.
2. Go to **Render > Environment**. Configure `OPENAI_API_KEY` with a valid
   [OpenAI API platform](https://platform.openai.com/api-keys) key; ensure
   `OPENAI_MODEL=gpt-4o-mini`. A ChatGPT Plus subscription does **not** pay for
   OpenAI API usage. Review [API billing](https://platform.openai.com/settings/organization/billing/overview)
   separately. Save/deploy the configuration changes.
3. Try again. The updated repository shows a sanitized HTTP status/error code
   plus a next action in the dashboard rather than the opaque `HTTPStatusError`.

| OpenAI HTTP status | Common reason | Next action |
| --- | --- | --- |
| 401 | Bad or revoked API key | Replace `OPENAI_API_KEY` |
| 429 | No credits, spend limit, or request rate limit | Check API billing and limits; use error code to distinguish |
| 400 | Model or request parameter incompatible | Verify `OPENAI_MODEL=gpt-4o-mini` |
| 403/404 | Access or model availability issue | Review project/model permissions |

If you only want to test the dashboard without OpenAI, delete/clear
`OPENAI_API_KEY` and set `DEMO_MODE=true`. The app builds a **template agenda**
instead of contacting OpenAI. Keep `DEMO_MODE=true` until live credentials are tested.
This does not perform real calls.

Do **not** paste API keys, auth tokens, or other secrets in screenshots or support requests.
