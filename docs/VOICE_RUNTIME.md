> **v0.2 GPT-Live update:** The original implementation remains available; see [GPT-Live Upgrade](GPT_LIVE_UPGRADE.md) for the new default engine, API differences, selection, Render migration and validation.

# Voice runtime: transport, timing, and debugging

## Wire-format decisions

Twilio `<Connect><Stream>` establishes a bidirectional WebSocket (see [Twilio documentation](https://www.twilio.com/docs/voice/media-streams/websocket-messages)). Incoming `media.payload` is base64 encoded raw **μ-law 8 kHz mono**. Deepgram Nova streaming accepts exactly `encoding=mulaw&sample_rate=8000`; there is no FFmpeg step. We use Deepgram Aura HTTP streaming TTS with `encoding=mulaw&sample_rate=8000&container=none`, returning raw bytes (no WAV header), and frame them as Twilio outbound media messages. Each chunk is ~800 bytes (100 ms of 8 kHz μ-law, 8-bit), without changing sample rate.

## Per-call sequence

1. Twilio sends `connected` and then `start`. FastAPI checks that the Twilio-signed WebSocket, persisted `call_id` and `start.callSid` match.
2. One Deepgram WebSocket opens for each active call.
3. Caller media is immediately forwarded to Deepgram; final transcript segments accumulate until `speech_final` or `UtteranceEnd`.
4. At end-of-turn, OpenAI Chat Completions streams tokens from `gpt-4o-mini`. The first completed sentence immediately flows into Deepgram Aura, and generated audio streams to Twilio. The remaining tokens/sentences continue.
5. If speech resumes during generation or buffered playback, the runtime cancels generation and issues Twilio `clear` to flush previously sent audio.
6. Mark messages provide playback-completion acknowledgements. The UI polls the persisted events. On stop, timeout, or disconnect, the session is cleaned up.

**Known gap:** The implementation is optimized for quick initial audio, but no formal latency benchmark has been run on your specific Twilio region, tunnel, model, and network. It also does not distinguish actual played audio from interrupted, buffered assistant text when auditing transcripts.

## Recommended functional validation

- Inbound call: verify the AI introduces itself before asking anything.
- Outbound call: verify only allowlisted numbers are accepted.
- Silence and background noise: agent does not hallucinate caller speech.
- Barge-in: caller speaks halfway through an answer; Twilio buffered output clears.
- Multiturn: relevant previous user answers remain in the conversation context.
- Long call: clean end after `MAX_CALL_SECONDS`.
- Reject bad signatures: unsigned webhooks return HTTP 403, unsigned WebSockets close 1008.
- Provider outage: records contain an error event; no raw tokens logged.

## Latency budget (measurement plan, not benchmark)

Measure in milliseconds:

`Twilio media -> Deepgram partial -> finalized turn -> OpenAI first token -> first TTS audio -> Twilio first played mark`

Collect p50 and p95 across 50+ real calls, with silence/noise and interruptions, before treating real-time responsiveness as proven. Telephony quality varies by PSTN route and regional restrictions.

## More vendor info

- [Cerebrium reference tutorial](https://cerebrium.ai/docs/v4/examples/twilio-voice-agent)
- [Twilio Stream TwiML](https://www.twilio.com/docs/voice/twiml/stream)
- [Twilio WebSocket messages](https://www.twilio.com/docs/voice/media-streams/websocket-messages)
- [Deepgram Twilio STT example](https://developers.deepgram.com/docs/twilio-and-deepgram-stt)
- [Deepgram TTS raw audio](https://developers.deepgram.com/docs/tts-container)

## Multilingual note

The sample config uses `aura-2-thalia-en`, an English TTS model. Changing agent `language` to Hindi does not automatically enable Hindi generation. Confirm multilingual model language availability and phonetic quality for both STT and TTS; use a pluggable alternative TTS adapter if required. Don't turn on unsolicited multilingual campaigns before testing.
