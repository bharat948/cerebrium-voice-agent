# Operator Runbook

## Safety sequence before live calling

- Start with `DEMO_MODE=true`, verify `/health`, authentication, database readiness and UI.
- Confirm Twilio webhook signature validation is enabled.
- Register an authorized consenting test contact, never assume import is consent.
- Use a short test agenda, monitor Render logs, hang up and inspect transcript events.
- Verify no private memory is shown to an unverified caller.
- Confirm per-call limits, minute charges, and opt-out behaviour before widening access.

## OpenAI API 429

An API `429` with `credit_balance_exhausted` means API billing must be funded. ChatGPT plan charges are separate from OpenAI API billing. Do not silently fallback to fake model output on live calls.

## No Twilio voice

Check `/twilio/voice` is POST, host is HTTPS and `/twilio/media` WS is reachable as `wss://`. Confirm account/phone number and signature, matching call and stream IDs. WebSockets must route to the same process that owns the in-memory call state.

## Calls have noticeable delays

Measure caller-end-of-turn to first audible output, Live session startup, Twilio playback backlog, and tool wait time separately. Keep short voice prompts and delegate expensive analysis. Recorded 8-kHz PCM-u audio requires no transcoding in the GPT-Live path.

## Background research fails

Inspect mission `state`: `blocked` means prerequisites missing, `failed` means worker error, `delivery_uncertain` means SMTP may have sent already and manual reconciliation is required. **Do not blindly retry email delivery**. Review source quality before enabling unattended external reports.

## Database schema migration

Backup before Alembic. A destructive downgrade is intentionally unavailable; rollback uses a tested backup. Run source/target row-count verification after a SQLite cutover.

## Service restart

Queued missions persist. Expired `running` research leases are reclaimed within the retry budget. `sending` and `delivery_uncertain` states are intentionally NOT retried automatically. Active telephone calls will disconnect if the hosting instance restarts; schedule deploys appropriately.
