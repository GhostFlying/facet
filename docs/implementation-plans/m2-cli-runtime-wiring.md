# M2 runtime composition (CLI handoff boundary)

Date: 2026-10-04. Status: revised scope independently approved; candidate under review.

## Goal

Connect the already integrated `StateOwner`, `CredentialManager`, Gmail source/
target adapters, admission policy, and `ForegroundSync` into one small runtime
composition seam. The first proof is a synthetic/fake end-to-end `run_once`;
the same seam must be able to construct Google Gmail services from verified
credential snapshots without adding a daemon, IPC protocol, scheduler, raw
spool, or a second writer. This unit intentionally stops at the library
boundary: it is not an executable production CLI sync command.

## Scope

- Add one service-factory protocol and a Google implementation. Its initial
  profile probe accepts the manager-owned in-memory `ProviderSecret`, performs
  only `users.getProfile`, and returns the account fact; the runtime supplies
  the policy's already-recorded grant scopes to the typed `ProfileEvidence`.
  Only after both profiles pass account/scope/expiry checks and pending bindings
  are published does the runtime request `AccessSnapshot` values and create
  one Gmail API service per role. The existing typed adapters/error classifier
  remain the only business boundary. It does not send, delete, change labels,
  or retry provider requests.
- Add one runtime composition function that, under the existing owner, runs
  the exact `profile probe -> expiry/account/scope verification -> publish ->
  snapshot -> adapter -> ForegroundSync` sequence. The factory/profile seam is
  injectable so fake tests traverse this composition rather than constructing
  adapters directly.
- Add fake-service integration tests using synthetic credentials and content;
  assert discovery, History, projection, target insert/readback and durable
  mapping all occur through the production composition seam, with raw content
  absent from DB/output.
- Keep CLI output aggregate-only. `facet run --once` remains preflight-only in
  this unit because production OAuth authorization and persisted-rule admission
  are not yet available. A later unit must add the CLI dispatch and subprocess
  boundary tests; this plan does not claim that handoff is complete.

## Non-goals and stop gates

- No OAuth browser flow, client-secret import, refresh protocol, CLI auth
  command, live Gmail call, live/real-account target write, or real-account
  operation in this unit. Fake target insert/readback is allowed only in
  offline synthetic tests.
- No alternate lock/session, background daemon, IPC/request receipt, generic
  capability framework, or provider abstraction beyond the one factory needed
  by the composition seam.
- Stop and report if the existing credential envelope cannot safely provide an
  access snapshot, or if wiring would require storing raw mail or provider
  responses.

## Files and ownership

- `src/facet/gmail/service_factory.py`: narrow service factory and Google
  implementation; no credential persistence.
- `src/facet/gmail/credentials.py`: reject expired credential envelopes before
  profile calls or binding publication; preserve the existing typed auth code.
- `src/facet/runtime/foreground_runtime.py`: composition and aggregate receipt.
- `src/facet/cli/bootstrap.py`: explicitly out of scope for this unit; no CLI
  dispatch is added while OAuth and rule admission are absent.
- `tests/integration/test_foreground_runtime.py` and focused unit tests.
- `docs/development-status.md`: one handoff after acceptance.

## Acceptance

1. A fake source/target service factory plus synthetic credential envelopes can
   be opened through the real `StateOwner` and `CredentialManager`, then
   execute `ForegroundSync.run_once` through the new composition function;
   the test records the profile-probe and service-construction order.
2. The receipt contains only aggregate counts; DB rows contain IDs, digests,
   mappings and typed state, never synthetic body/subject/header sentinels.
3. A missing, expired, swapped, or mismatched credential returns the existing
   source/target auth or binding error before profile publication, Gmail
   discovery, or target insert; expired credentials leave bindings pending.
4. Google factory construction is lazy, creates separate role services, uses
   the existing no-retry adapter boundary, and never logs/serializes token or
   provider payloads.
5. The fake composition uses the injectable factory/profile seam rather than
   directly constructing adapters. Focused tests, complete offline suite,
   Ruff, wheel/import smoke and safety
   pass on the exact candidate; no live Gmail or deployment action occurs.
6. Invalid factory inputs and malformed provider profile payloads return typed
   `StorageFailure` values. Direct tests prove failed profile verification does
   not expose or retain a provider service.
7. Runtime tests cover expired/missing/swapped credential failures before
   profile publication and service construction. The deferred CLI boundary is
   documented rather than implied by this unit's name.

## Review and integration gates

- Independent plan review binds this file revision before implementation.
- Implementation review binds the exact candidate SHA after focused/full
  checks and CI. Merge only after both Python CI lanes pass.
