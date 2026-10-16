# Voice Foundry v4.0 alpha: Intelligence Engine

**Scope:** This release adds bounded voice behaviour, temporal memory consolidation and reviewable agent-improvement proposals on top of v3.9. It is a staged milestone, not a claim that all of the product's original design decisions are complete.

## Implemented

### Caller-scoped temporal memory

- A registered contact can opt out of memory collection and retrieval using the Contacts dashboard or owner API. Opting out does not automatically destroy prior records; the existing delete/correction APIs remain available.
- New routine memories are screened for restricted secrets, high-risk sensitive information and instruction-injection patterns. This screening is intentionally conservative and is not a comprehensive privacy classifier.
- Repeating an identical statement **reinforces** the previous memory; it does not create a second active copy.
- Potentially contradictory statements that share substantial content but differ in negation are **quarantined for manual review**, not treated as either true or false. This heuristic does not catch all semantic contradictions.
- A correction or owner's approval can supersede a memory, retaining an auditable relationship with the previous record.
- Optional validity/expiration and provenance fields support versioned history. Routine retrieval scores lexical relevance, recency, confidence and repetition. pgvector remains optional for semantic retrieval.
- Each memory is scoped to `(agent_id, contact_id)` and is *never* treated as a new system instruction.
- Post-call candidates are limited to exact excerpts spoken by the caller. Agent outputs are not automatically promoted to caller memories. Extraction still requires configured provider access outside demo mode.

### Bounded voice behaviour

- Configurable, versioned policies for pacing, proactivity, expression, pause tolerance and interruption sensitivity.
- A published agent release pins the policy for new calls. Emergency runtime controls and backend tool permission revocations remain independent of prompt settings.
- The GPT-Live prompt compiler incorporates a guarded voice-policy section. Local barge-in handling uses the policy while respecting existing explicit environment thresholds.
- **Limit:** pause tolerance is currently an instruction and configuration surface, not a verified acoustic emotion detector or fully autonomous silence controller. Test with actual Twilio calls before adjusting production thresholds.

### Human-supervised agent improvements

- Owner can save a human voice review, request a specific *allowlisted* improvement, examine supporting review counts/ratings, and create a draft.
- Freeform caller or reviewer text is stored as evidence only and cannot be copied into trusted instruction changes.
- A proposal cannot publish by itself. You must explicitly publish the resulting agent draft after voice testing.

## Owner APIs

All routes below require the same owner authentication as v3. The prefix is `/api/v4`:

| Method | Route | Purpose |
|---|---|---|
| GET/PATCH | `/contacts/{id}/memory-policy` | View/update contact memory preference |
| GET | `/agents/{agent}/contacts/{contact}/ranked-memories?query=...` | Scope-checked ranked retrieval |
| POST | `/agents/{agent}/contacts/{contact}/memory-candidates` | Owner-initiated candidate consolidation |
| GET | `/agents/{agent}/contacts/{contact}/memory-conflicts` | Inspect pending contradictions |
| POST | `/memory-conflicts/{id}/resolve` | Reject or supersede pending conflict |
| GET | `/agents/{agent}/voice-policy` | Effective policy and local interruption settings |
| POST | `/agents/{agent}/evolution/propose` | Generate allowlisted change from human review |
| GET | `/agents/{agent}/evolution` | Proposal history |
| POST | `/evolution/{id}/decision` | Reject or create a review draft |

**Example:**

```bash
curl -X PATCH 'http://localhost:8000/api/v4/contacts/CONTACT_ID/memory-policy' \
  -H 'X-API-Key: YOUR_LOCAL_OWNER_KEY' \
  -H 'Content-Type: application/json' \
  -d '{"enabled":false}'
```

The contact's phone number alone does not provide authenticated permission to use these owner API routes.

## Migration and deployment

Migration `0005` adds memory lifecycle fields, an opt-out flag, conflict records and improvement proposals. It does not delete or transform legacy memories. Previous records default to `origin=owner`, `strength=1`, and memory enabled for existing registered contacts; **review this default with your privacy requirements** before exposing the system to external callers.

Back up the database before deployment. Run from the extracted repository directory:

```bash
python -m alembic upgrade head
python -m pytest -q
```

Render's single-instance Docker entrypoint already applies Alembic migrations before serving. Deploy to **a staging Render service first**, enable `DEMO_MODE=true`, test the owner console, and perform real-provider checks on a controlled number only after staging passes. No real provider connection was validated during this build.

## Verification

- 61 offline pytest tests passed, including v3 regression tests and v4 opt-out, ranking, correction, conflict, reviewer safety and API tests.
- Upgrade from a seeded SQLite revision `0004` to `0005` preserved an old contact and memory.
- Python compilation and browser JavaScript syntax checks passed.
- PostgreSQL/pgvector CI workflow is provided but was **not run against a live PostgreSQL service in this build**.
- Twilio, GPT-Live, OpenAI embeddings, Google OAuth and Render end-to-end acceptance remain required.

## Further work

Not yet fully implemented: deep temporal entity resolution, verified caller OTP for sensitive memories, human voice takeover, comprehensive turn-end/silence experiments, true multi-step durable workflow graphs, production-grade scheduler isolation, Google Calendar writes, automatic knowledge-source refresh, autonomous policy improvements, and complete provider cost reconciliation.
