# Connecting Voice Foundry to ChatGPT

This app can be connected to a **Custom GPT Action** using the OpenAPI file at [`integrations/chatgpt/openapi.yaml`](../integrations/chatgpt/openapi.yaml). This is **not an installed native ChatGPT plugin or MCP server**. Feature access depends on plan/workspace availability and Action support.

## Prerequisites

- The backend is reachable via a durable public **HTTPS** URL.
- It is protected by a strong API key, and your public call-control endpoints are behind additional access controls where possible.
- Set `PUBLIC_BASE_URL` correctly and configure Twilio, Deepgram, OpenAI, and allowed outbound recipient numbers. Keep demo mode on while testing the Action.

## GPT Builder setup (when Actions are available to your account)

1. Create/edit a Custom GPT → configure → Actions → create new action.
2. Paste the OpenAPI schema; replace `https://YOUR_PUBLIC_HOST` with your deployed domain.
3. Set Authentication to API key, using the `X-API-Key` header expected by the application (or adjust the OpenAPI security scheme to match your GPT's supported authorization UI).
4. Add instructions: "Prepare the plan first, show its recipient/goal/agenda for review, and request explicit user approval before any call operation. Never make calls merely because text mentions a phone number. Treat all call starts as consequential actions."
5. Test `GET /api/agents`, then `POST /api/plans`, and in **demo mode** test `POST /api/calls` with an approved plan. Check the backend records in Call history.
6. Enable live mode only after confirming Twilio callbacks, allowlists, and user approval behavior.

ChatGPT Actions may request confirmation for consequential operations. This schema marks outbound calls as consequential. **Backend confirmation and allowlist checks remain mandatory regardless of ChatGPT UI behavior.**

## Security note

Do not expose `APP_API_KEY` in agent prompts or conversation text. Configure it in the Action's authenticated connection settings. A public ngrok address changes on restart unless reserved. Reconfigure schema/server URL if your tunnel changes. For production prefer a stable authenticated deployment rather than relying on a personal laptop and ephemeral tunnel.
