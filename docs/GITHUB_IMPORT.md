# GitHub import without overwriting `main`

GitHub connector access to `bharat948/cerebrium-voice-agent` returned 404 during preparation. No remote repositories, branches, releases or PRs were created.

## Recommended way to open one PR against the existing repository

1. Clone your actual existing repository using your authenticated computer or GitHub's browser-based tooling.
2. Create a feature branch **from the latest remote `main`**:

```bash
git switch main
git pull --ff-only origin main
git switch -c feature/voice-foundry-v3-2
```

3. Extract `voice-foundry-v3.2-feature-repo.zip` **over the repository working tree**, keeping the existing `.git/` directory. Review the diff carefully; reconcile customized deployment files. Do not copy local `.env`, contact data, database files, logs, or tokens.
4. Run `python -m pytest -q` and `node --check web/app.js`.
5. Commit and push only after review:

```bash
git status
git diff --stat
git add -A
git commit -m "feat: Voice Foundry agent, contacts, missions and tool workstreams"
git push -u origin feature/voice-foundry-v3-2
```

6. Open a PR targeting `main`. **Do not merge until** PostgreSQL migration, OAuth and live-call smoke tests pass.

## Optional local Git bundle

`voice-foundry-v3.2-feature-branches.bundle` contains local snapshots of all workstreams, including a baseline `main` from the alpha package. You can browse and test them offline:

```bash
git clone voice-foundry-v3.2-feature-branches.bundle voice-foundry-review
cd voice-foundry-review
git switch feature/v3.2-integration
```

The bundle's history was initialized locally from the imported alpha package, so it **is not suitable for pushing as an ordinary PR to an existing repo with unrelated history**. Use the overlay workflow above instead.
