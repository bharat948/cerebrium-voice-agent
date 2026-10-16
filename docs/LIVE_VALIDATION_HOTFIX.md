# GPT-Live call disconnect hotfix

Build: **4.0.0-alpha2**. Date: 16 October 2026. Base: Voice Foundry v4.0 alpha1.

## What your log proves

Twilio created the call (HTTP 201), fetched the voice webhook (HTTP 200), and
opened the media WebSocket. The failure occurred when GPT-Live reported
`responses_validation_failed` for its reasoning/tool backend configuration.

The old `app/live_voice.py` startup loop raised `RuntimeError` on every error
event and retained only the error code. That ended the audio runtime and lost
the provider's message and parameter name.

OpenAI documents this specific validation error as asynchronous and recoverable:
the voice session stays open, and supported backend settings can be corrected
with `session.update`. A `session.started` or `session.updated` acknowledgment
does not prove that the reasoning backend passed validation.

**The supplied log does not identify the rejected setting.** Model access,
an unsupported backend setting, or a tool/resource configuration can produce
this error. There is no evidence here of a Twilio credential, webhook or audio
codec failure. Changing API keys or switching voice models without the detailed
provider message would be guesswork.

## Install on your existing deployment

1. Extract the hotfix archive. Merge the files inside `voice-foundry/` into your
   existing repository root, replacing the matching source files. Keep the new
   `app/live_diagnostics.py` together with the updated runtime files.
2. Commit the changes to the branch connected to your Render service and
   redeploy it. This patch adds no database migration or dependency requirement.
3. Open `/health` and verify that it returns `"version":"4.0.0-alpha2"`.
4. Run the configuration check below in the Render service shell. Fix any
   reported setting, save the environment, and redeploy before testing a call.

The archive contains changed source, tests and this guide. It does not contain
your `.env`, credentials, database, or caller records. `.env.example` documents
settings; it is not your deployment's environment file.

## Reveal the rejected setting without a Twilio call

From the repository root in the Render shell:

```bash
python scripts/check_live_config.py --agent-id receptionist
```

For a specialist, replace `receptionist` with that agent's actual ID from the
dashboard. Use the same deployed service and OpenAI project as the failing call.

The command starts a short, billable OpenAI Live session, sends silence while
watching for delayed validation errors, and closes it. It does not dial Twilio
or execute custom tools. It checks the selected agent's configured voice model,
backend model and general tool schemas; contact-only tools are not included.
It does not send call history or caller memories.

Example failure (illustrative, not the recovered cause of your call):

```text
Backend model: configured-backend
FAIL: GPT-Live code=responses_validation_failed type=invalid_request_error param=delegation.responses.model message=Model not accessible
```

Interpret the actual `message=` and `param=` fields:

| Detailed error | Next action |
| --- | --- |
| Model unavailable, inaccessible or unsupported | Set `OPENAI_LIVE_BACKEND_MODEL` to a Responses model accessible to the same project; redeploy and rerun. |
| Invalid tool or tool schema | Correct that tool's definition. The fallback below preserves tools and cannot fix an invalid schema. |
| Inaccessible resource or project permission | Correct access to the named resource in the same OpenAI project. |
| Quota or rate limit | Check that project's billing, quota or rate limits. |

Keep the voice model setting:

```dotenv
OPENAI_LIVE_MODEL=gpt-live-1
```

The backend is selected separately. The current official delegation guide uses
`gpt-6-luna`; this is an option to test if available to your project:

```dotenv
OPENAI_LIVE_BACKEND_MODEL=gpt-6-luna
```

This is not a finding that your original `gpt-4o-mini` setting caused the error,
and the patch does not automatically replace it. No account access has been
verified. `OPENAI_MODEL` controls the separate planner/worker path; changing it
alone does not change the live reasoning backend.

A successful startup check means only that no provider error was observed in
its short window. It does not prove every tool works. If needed, extend the
observation to 10 seconds with `--wait-seconds 10`.

## Optional single model fallback

One optional environment variable was added:

```dotenv
# Empty by default. Set only to a model your project can use.
OPENAI_LIVE_FALLBACK_BACKEND_MODEL=
```

When configured to a different backend model, the runtime retries that model
once with `session.update`. The original voice model, instructions and
authorized tool set stay in place. It does not silently remove tools, change
delegation modes or place another call. Acknowledging the update is not treated
as proof of a successful backend response.

If no fallback is configured, or validation fails again, the spoken session
remains open when the provider permits it. The assistant receives instructions
to explain that its tools are unavailable and continue ordinary conversation.
Backend tool execution is blocked while validation is unresolved. It must not
claim that research, bookings or email delivery succeeded.

## What changed

- Phone and browser startup now distinguish recoverable backend validation from
  fatal session errors.
- Startup has one 15-second total deadline, including repeated provider events.
- Error logs and authenticated call events retain `code`, `type`, `param` and
  `message`, with credential redaction and a size limit.
- Safe startup errors are retained in the call's error field instead of only
  the Python exception class.
- An optional fallback retries once and preserves the permission-controlled
  tool configuration.
- A configuration probe checks delayed errors without dialing a phone.

## Verification

**79 offline tests passed** (the original 61 plus 18 new regressions). Python
compilation, the diagnostic command's help entry point and browser JavaScript
syntax checks also passed. Tests used the installed Twilio 9.12.0 SDK.

Automated tests reproduce validation errors before and after `session.started`,
confirm that phone input/output audio continues, verify bounded fallback and
error redaction, and block business tools while the backend is unavailable.
The probe is also tested with simulated late validation failures.

This patch has not been deployed to your Render service or tested against
your live OpenAI/Twilio credentials. After the configuration check passes,
make one short authorized call and verify greeting, caller audio, agent audio,
one permitted tool request, and the resulting call events.

## Official references

- [GPT-Live delegation: configuration errors and supported updates](https://developers.openai.com/api/docs/guides/live-delegation)
- [Managing GPT-Live sessions: updates, readiness and rejected commands](https://developers.openai.com/api/docs/guides/live-conversations)

Offline checks cannot establish model access or recover the omitted provider
message from the original log. The new diagnostics are needed to determine
and correct the exact rejected configuration.
