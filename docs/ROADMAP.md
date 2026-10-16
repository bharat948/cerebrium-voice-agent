# Product Roadmap and Deferred Decisions

The original /grill-me session yielded 64 confirmed product choices; Q55 was skipped, Q65 remains unanswered. This is a staged roadmap, not a claim all items are built.

## Now: v3.1 foundations

- [x] Preserve v2 voice calling and the existing dashboard workflow.
- [x] Establish PostgreSQL/pgvector schema and SQLite migration utility.
- [x] Four agent templates, compiled prompts, draft/publish APIs.
- [x] Contacts, CSV import, explicit consent flags, scoped memories.
- [x] Basic fixed news/search/task tools and a persisted research job worker.
- [x] Hosted Google OIDC route and Render deployment configuration.
- [ ] Run live database, OAuth, email, and provider smoke tests.
- [ ] Finish full Agent Studio configuration editor and browser WebRTC playground.

## Next: v3.2 quality and data

- [ ] End-to-end inbound AI receptionist and agent routing.
- [ ] Google Contacts and Calendar integrations with verification and consent.
- [ ] Automatic post-call memory extraction, temporal consolidation, corrections, deletion workflow.
- [ ] Strict identity verification before sensitive memories/tasks.
- [ ] Typed tool gateway for in-call GPT-Live backend delegation.
- [ ] NSE/BSE compliant licensed market data adapters.
- [ ] Worker source verification against full articles and primary documents.

## Later: v3.3 advanced autonomy

- [ ] Mission DAGs, replay-safe scheduling, approvals and human escalation.
- [ ] Knowledge ingestion and RAG over PDFs and owner documents.
- [ ] Live call owner intervention, optional human transfer, browser push notifications.
- [ ] Budget routing and provider-cost reconciliation.
- [ ] Manual-evaluation voice lab and configurable personality editor.
- [ ] Shared verified knowledge library and controlled agent evolution.
- [ ] Durable worker extraction and container clustering (after benchmark-driven need).
