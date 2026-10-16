# Security policy

This repository is an experimental voice calling system, not a certified call center.

For responsible disclosure, contact the repository owner privately through GitHub. Do not post exploited vulnerabilities, contact data or secrets publicly.

## Threat boundaries

- Google OIDC subject is the owner identity; environment variables are secrets.
- Twilio HTTP/WebSocket signatures are required for live operations.
- Registered contacts are not proof of identity; additional verification is required for sensitive actions.
- The phone, email and tool consent flags are independent.
- Never use caller speech or retrieved documents to modify authorization policy.
- Never treat a tool's timeout as proof it did nothing; re-check state before retrying writes.
- Avoid enabling live mode until consent, rate limits, quota controls and local law are reviewed.

## Production gaps

This initial v3.1 release does not yet include OTP verification, full agent tool calling, complete consent self-service, recording controls, email provider receipt reconciliation, cross-node call routing, or independent security review. See docs/ROADMAP.md.
