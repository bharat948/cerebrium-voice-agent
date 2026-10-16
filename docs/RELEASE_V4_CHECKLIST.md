# Release gates: Voice Foundry v4.0 alpha

- [x] New data structures are additive and have an Alembic migration.
- [x] Previous 50 offline regressions pass.
- [x] 11 new regression tests pass, total 61.
- [x] Voice policy remains pinned to published releases for live calls.
- [x] Memory opt-out prevents new collection and personalized retrieval.
- [x] Contradictions require manual review rather than autonomous rewriting.
- [x] Proposed prompt changes cannot publish automatically.
- [x] Legacy SQLite data survives an 0004 -> 0005 migration smoke test.
- [ ] Run migration on staging managed PostgreSQL + pgvector.
- [ ] Measure 100+ real Hindi/Hinglish turns and interruption false-positive rate.
- [ ] Verify GPT-Live function calls, media playback and all tool approval paths on real providers.
- [ ] Verify Google sign-in/Contacts/Calendar in the deployed owner's Google project.
- [ ] Threat-model account/session security, data retention, caller consent, and provider-side transcripts.
- [ ] Load-test budget and concurrency controls; verify process restarts during active calls.
- [ ] Complete backup restoration and migration rollback rehearsal.
- [ ] Obtain code review and approval before production merge.

**Do not run unattended external calling based only on these offline results.**
