# Voice Foundry feature workstreams

This is **one deployable modular monolith**, not six microservices. The local Git bundle contains reviewable, **stacked snapshot branches** created against the previous local feature commit. They are not independent branches from your remote GitHub `main` and should not be opened as separate remote PRs without rebasing onto that repository.

| Local branch | What it implements | Main code | Verification |
|---|---|---|---|
| `feature/contact-registry` | Contact edits, consent revocation, soft deactivation, identity-safe lookup | `app/v3/contacts.py`, `app/main.py` | `tests/test_feature_contacts.py` |
| `feature/agent-studio-releases` | Immutable restoration of archived agent config to reviewable draft | `app/v3/registry.py` | `tests/test_feature_versions.py` |
| `feature/tool-gateway` | Bounded read-only tool executions with fixed authorization and audit | `app/v3/tool_gateway.py` | `tests/test_feature_gateway.py` |
| `feature/durable-mission-control` | Pause/resume/revise/cancel, event timeline, cancel-before-email check | `app/v3/missions.py` | `tests/test_feature_missions.py` |
| `feature/owner-dashboard` | Contact, memory and mission controls; memory corrections and deletion | `web/app.js`, `app/v3/memory.py` | `tests/test_feature_memory.py` |
| `feature/conversational-agent-architect` | Natural-language proposals, owner review, unpublished draft generation | `app/v3/architect.py`, `web/index.html` | `tests/test_feature_architect.py` |
| `feature/v3.2-integration` | Latest combined code and migration/release docs | Whole repository | `python -m pytest -q` |

## Implementation boundaries

### Implemented

- Agent templates, versioned drafts/publishing and immutable restore history.
- Explicit contact register/import/edit/consent revocation/deactivation.
- Scoped memory create/search/correct/forget, vector erasure for forgotten memory, event history. Manual memory controls only.
- Curated news search adapters, policy-gated read-only tool calls and audited results. In demo mode, network tools are simulated.
- Durable research-email mission with worker leases, owner cancellation, pause/resume/revisions and mission events. Approved email delivery is automatic; once sending starts, delivery may be uncertain if SMTP disconnects.
- Configurable GPT-Live and existing Deepgram paths carried from v2; no changes to phone audio frame protocol in this release.
- Agent architect proposal preview and unpublished draft creation, with no automatic calls, permissions grants, or publishing.

### Not implemented or not live-verified

- Live GPT-Live tool-delegation wiring, browser microphone conversation, Google Contacts and Calendar provider sync, licensed NSE/BSE feeds, owner takeover, and advanced event-driven follow-up scheduler.
- Automatic post-call memory extraction/consolidation, document knowledge ingestion/RAG, personalized caller OTP verification, full durable multi-step DAG execution, and full spending reconciliations.
- Real Twilio/OpenAI/SMTP/Google OAuth and Render production smoke tests. PostgreSQL extensions and migration must be verified on a running target deployment.

## Branch review notes

Feature branches are progressively stacked and are **not cleanly isolated diffs from the original GitHub repository**. The recommended single PR to your current GitHub repository is `feature/v3.2-integration` created **from its remote `main`**, then overlaying the release ZIP. Use `docs/GITHUB_IMPORT.md` to avoid unrelated history.

Our initial service footprint remains: FastAPI monolith + PostgreSQL with pgvector, one Render service process and a managed DB. `docker-compose.yml` supports local testing. A Docker cluster is deliberately out of scope until stateful voice session routing is designed and load-tested.
