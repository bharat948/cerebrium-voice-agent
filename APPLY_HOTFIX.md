# Voice Foundry call disconnect hotfix

Build: 4.0.0-alpha2. Base: v4.0 alpha1.

Merge the CONTENTS of the included voice-foundry folder into your existing
repository root, commit the source changes and redeploy your Render service.
Do not replace your actual .env file. No database migration is added.

The complete explanation and deployment commands are in
voice-foundry/docs/LIVE_VALIDATION_HOTFIX.md.

After deploying, verify /health shows 4.0.0-alpha2, then run:

    python scripts/check_live_config.py --agent-id receptionist

This short, billable OpenAI check does not dial Twilio. It reports the precise
backend validation error that the old logs omitted. Contact-only tools are
not included in that check. No live provider validation was performed here.

79 offline tests passed. The patch preserves the configured primary model,
adds an optional single model fallback, and keeps recoverable backend errors
from immediately ending the spoken session. If the backend remains invalid,
its tools are unavailable while ordinary voice conversation can continue.
