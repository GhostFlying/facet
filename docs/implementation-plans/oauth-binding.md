# Production OAuth binding command

Date: 2026-10-04. Status: plan for independent review. Base: `f7cbe8f`.

## Goal

Replace the current non-fake `source_auth_required` CLI stop with a bounded
production OAuth binding path. The command will use the existing owner,
credential-change, profile-verification, and single-writer protocols. It will
accept a private Google installed-app client configuration, perform one
explicit loopback OAuth exchange for the explicitly selected Gmail role, probe
that role's profile through the existing Gmail service factory, and call a
single-role credential-manager path so account, scope, revision, and
persistence checks remain authoritative. Initial setup therefore requires two
explicit invocations, one for `source` and one for `target`; readiness is not
published until both have independently completed. The existing `--fake`
closure command remains a test-only compatibility path.

This unit does not run OAuth against a real account, select a live mailbox, add
scopes, write target mail, or claim source-path authenticity. Live use remains
blocked behind the existing explicit account/scope/test authorization boundary.

## Files and behavior

- Add a small private `facet.gmail.oauth` adapter around
  `google-auth-oauthlib` with typed `ProviderSecret` output. It must use the
  fixed Gmail scope policy, loopback-only redirect handling, no refresh in the
  Google client object after exchange, and sanitized errors.
- Extend `facet.cli.bootstrap auth authorize` with required `--role
  {source,target}` and explicit `--oauth-client` path. Each invocation reads
  the owner-only client JSON, obtains consent for only that role's fixed scope,
  and reuses the existing durable operation/recovery behavior. `--fake` remains
  test-only and mutually exclusive with this flag; the old fake closure may
  continue to authorize both roles for offline setup.
- OAuth URLs and callback details are shown only during an explicit interactive
  flow on the controlling TTY, never in `--json` stdout, `--private-metadata`,
  logs, DB rows, diagnostics, or public output. Client secrets, tokens,
  authorization codes, and raw provider responses are never emitted or stored.
- Add focused fake OAuth-flow tests that exercise the same command/manager seam
  without network access, including account mismatch, scope mismatch, callback
  failure, first-response-loss recovery, and owner-only client-file checks.
- Update the short status/plan evidence only once after the candidate is
  accepted. Do not change the source-auth contract: Gmail headers alone remain
  unknown and automatic admission remains unverified.

## Acceptance and stop gates

1. Existing synthetic CLI closure remains green and the non-fake command now
   reaches a typed OAuth transport boundary instead of silently using fake
   credentials.
2. A fake OAuth transport can complete both role exchanges through the real
   `CredentialManager.authorize` path; no test seeds bindings, credentials,
   rules, or readiness directly in SQLite.
3. Client JSON and credential files are owner-only, no-follow, bounded, and
   never appear in Git, logs, public output, or database content.
4. Provider/profile/scope/account failures return the existing closed error
   codes and preserve pending/recovery state; no blind retry or duplicate
   authorization is introduced.
5. Run affected tests, the complete offline suite, Ruff, and repository safety
   on the exact candidate. No live OAuth or Gmail call is made by CI.

Stop and report if the installed-app library cannot provide a loopback flow
without retaining refresh material, if its callback behavior requires a new
external service, or if source-path attestation would need to be inferred from
message headers. Those are separate decisions, not reasons to weaken the
binding/privacy contract.
