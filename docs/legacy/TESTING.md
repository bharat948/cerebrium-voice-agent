> **v0.2 GPT-Live update:** The original implementation remains available; see [GPT-Live Upgrade](GPT_LIVE_UPGRADE.md) for the new default engine, API differences, selection, Render migration and validation.

# Test plan & acceptance criteria

## Automated test run

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q app
```

The tests are offline, simulate provider access, use temporary SQLite databases, and verify no actual telephone calls are created. They check authentication, default agent, phone validation, plan edit/approval, duplicate prevention, preview conversation, hangup, and unsigned Twilio webhook rejection. If the Twilio SDK is absent in an offline test environment, `tests/conftest.py` substitutes minimal fake transport classes *for the tests only*. Production still requires the Twilio SDK.

## Manual acceptance matrix

| Case | Preconditions | Expected |
|---|---|---|
| Fresh install | `.env` demo true, no APIs | UI opens and local health check passes |
| Invalid UI API key | Wrong key | 401 / login rejected |
| New plan without OpenAI key | Demo / proper E.164 | Deterministic agenda; no Twilio call |
| New plan with OpenAI | Valid OpenAI key | Custom agenda; still no call |
| Edit goal | Draft plan | Changes reflected in inspector |
| Duplicate approval | Same plan twice | Second POST 409 |
| Demo preview | Simulated call | Mock caller and assistant transcript events |
| Hang up demo | Simulated call | Completed; additional mock turns fail |
| Live no allowlist | Demo false, empty allowlist | 403 for outbound |
| Live approved recipient | Configured accounts + tunnel | Real outbound call created |
| Webhook unauthorized | No valid signature | 403 |
| WebSocket signed | Real Twilio + matching CallSid | Real-time audio starts |
| Barge-in | Real voice call | Buffered assistant audio clears |
| Carrier busy | Destination unavailable | Twilio status updates |
| Long call | `MAX_CALL_SECONDS` reached | Twilio call terminated |
| Restart | Named Docker volume | Prior agents, plans, and calls remain |
| India / non-English | Compatible models and permitted numbers | Verify STT/TTS and legality before use |

## Not automatically verified in this package

- Real Twilio credentials, authenticated webhook URL canonicalization across ngrok/Cloudflare, actual external WebSocket upgrade
- Deepgram billing model availability or first-byte/turn latency
- Full-duplex audio under network packet loss and telephony echo
- High concurrency, cloud autoscaling, complete provider-outage recovery

Use provider sandbox/test numbers for integration testing and a consented destination when switching to real PSTN. Do not interpret API unit tests as proof of production readiness.
