# REST API cookbook

Base: `http://localhost:8000`. All `/api` methods require `X-API-Key` matching `.env` and return JSON. Browser UI uses exactly these endpoints.

## Authenticate and check configuration

```bash
curl -H 'X-API-Key: dev-local-only-change-me' http://localhost:8000/api/config
```

Response (demo):

```json
{"name":"Voice Foundry","demo_mode":true,"ready_for_calls":false,"openai_enabled":false,"model":"gpt-4o-mini","allowed_numbers":0,"max_call_seconds":300}
```

## Create an agent

```bash
curl -X POST 'http://localhost:8000/api/agents' \
 -H 'X-API-Key: dev-local-only-change-me' -H 'Content-Type: application/json' \
 -d '{"name":"Mira","role":"Dental receptionist","language":"English","instructions":"Disclose you are an AI assistant. Ask one question at a time. Never invent availability."}'
```

Copy `id` from JSON for use as `agent_id` (or use seeded `receptionist`).

## Create an agenda

```bash
curl -X POST http://localhost:8000/api/plans \
 -H 'X-API-Key: dev-local-only-change-me' -H 'Content-Type: application/json' \
 -d '{"agent_id":"receptionist","phone":"+14155552671","message":"Ask whether they want an appointment follow-up next week; collect preferred times but do not book anything."}'
```

The `phone` value must be valid E.164. `agenda` is a JSON array; `state` is `draft` until used. Note this action never dials.

## Edit a draft

```bash
curl -X PATCH http://localhost:8000/api/plans/PLAN_ID \
 -H 'X-API-Key: dev-local-only-change-me' -H 'Content-Type: application/json' \
 -d '{"goal":"Collect preferred appointment time","agenda":["Disclose AI identity","Ask preferred day","Confirm next steps"],"script":"Hello, this is an AI assistant calling about appointment availability."}'
```

## Approve and place a call

```bash
curl -X POST http://localhost:8000/api/calls \
 -H 'X-API-Key: dev-local-only-change-me' -H 'Content-Type: application/json' \
 -d '{"plan_id":"PLAN_ID","confirm":true}'
```

In demo, `status` = `simulated`, and no phone call occurs. In live mode this invokes the Twilio API and returns call detail including a Twilio SID on success. This action consumes the plan once. The backend rejects any recipient not on the environment allowlist.

## Preview a simulated conversation

```bash
curl -X POST http://localhost:8000/api/calls/CALL_ID/preview \
 -H 'X-API-Key: dev-local-only-change-me' -H 'Content-Type: application/json' \
 -d '{"text":"Tuesday afternoon is best."}'
```

Returns updated call details with `events` for caller and assistant.

## Check or end call

```bash
curl -H 'X-API-Key: dev-local-only-change-me' http://localhost:8000/api/calls/CALL_ID
curl -X POST -H 'X-API-Key: dev-local-only-change-me' http://localhost:8000/api/calls/CALL_ID/hangup
```

## Error codes

- `400`: confirmation missing, unconfigured live calling
- `401`: missing/invalid control-plane key
- `403`: recipient not allowlisted / invalid Twilio signature
- `404`: invalid agent, plan, or call identifier
- `409`: plan already used or preview not available
- `422`: invalid JSON, phone E.164, or fields
- `429`: per-hour/concurrency call limit reached
- `502`: upstream OpenAI or Twilio request failed

## Twilio endpoints

`POST /twilio/voice`: TwiML response with `<Connect><Stream>` pointing to `/twilio/media`. For outgoing calls includes `?call_id=...` in the TwiML **webhook URL**, not the Stream URL. `POST /twilio/status`: signed call status callbacks. `WS /twilio/media`: signed WebSocket opening and authenticated `start.callSid` association. Do not send your control-plane key to Twilio; signatures use the Twilio Auth Token.

## Summarize the transcript

`POST /api/calls/{call_id}/summary` with API key creates a summary event. With an OpenAI key it generates a concise grounded summary; otherwise it extracts recent caller statements and states that business actions were unverified.
