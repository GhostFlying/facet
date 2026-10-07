# Provider request timeout plan (Rev10)

## Rev10 change: OAuth token-refresh transport

The existing 30-second `httplib2.Http` bound covers Gmail API discovery and
requests, but `google-auth`'s token exchange uses a separate
`google.auth.transport.requests.Request`; its default call has no timeout.
Rev10 bounds that exchange without changing OAuth scope, refresh ownership, or
recovery semantics:

- Reuse the existing fixed `PROVIDER_REQUEST_TIMEOUT_SECONDS = 30` value; do
  not add configuration or a second timeout policy.
- Wrap the constructed `google.auth.transport.requests.Request` at its call
  boundary so every token endpoint invocation receives
  `timeout=PROVIDER_REQUEST_TIMEOUT_SECONDS`. The wrapper must override a
  caller-supplied timeout rather than relying on a constructor argument
  (`Request` has no timeout constructor parameter).
- Add the in-memory `ProviderStage.TOKEN_REFRESH` stage. Transport timeout,
  `google.auth` transport failures, and provider `RefreshError` mappings retain
  the existing closed error-code semantics while carrying this private stage,
  fixed timeout, attempt one, and observed timestamp. No URL, account, token,
  response body, exception text, or provider payload may cross the boundary.
- Keep malformed/expired successful results as the existing typed
  `invalid_input`/role-auth failures, and keep `invalid_grant`, scope,
  auth/rate-limit, and retryable backend mappings unchanged. A bounded
  timeout/network transport failure is `network_unavailable`.
- Preserve the current `CredentialManager.refresh` cleanup and single-flight
  behavior: a token-refresh failure after `credential_changes` enters
  `requesting` is abandoned/held through the existing writer path, old
  credential/binding revisions remain published, and concurrent waiters see
  the same closed error code. No durable schema or public DTO changes.

### Rev10 files and acceptance additions

- `src/facet/gmail/refresh_exchange.py`: add the fixed-timeout request wrapper,
  construct it for `Credentials.refresh`, and map transport/provider failures
  to the typed private `TOKEN_REFRESH` stage without retaining raw data.
- `src/facet/gmail/retry.py`: add `ProviderStage.TOKEN_REFRESH` and retain its
  existing additive/private serialization rules.
- `tests/unit/test_refresh_exchange.py`: assert the actual request call gets
  `timeout=30`, including overriding an injected timeout; cover timeout,
  `TransportError`/network, `invalid_grant`, scope/auth/rate-limit and backend
  fixtures with the expected closed code/stage and no payload leakage. Cover
  malformed/expired results separately as existing invalid-input/auth failures.
- `tests/unit/test_credential_manager.py` (or the existing refresh fault
  fixture): prove a token-refresh timeout after `begin_change` closes the
  requesting row through the existing abandon/attention path, publishes no
  revision, and propagates the same typed code to same-flight waiters.
- Keep `service_factory.py`, Gmail API request timeout behavior, error-event
  schema, public/default CLI output, preview/status/doctor, OAuth scopes,
  refresh-token ownership, and insert/recovery behavior unchanged.

### Rev10 stop gates and external actions

- Stop before implementation if the timeout requires a new provider client,
  retry policy, OAuth scope, persistence/public schema, or implicit token
  writes outside `CredentialManager`.
- Offline/synthetic tests only; do not invoke live OAuth, Gmail, the current
  prepared state volume, Docker deployment, or image publication in this unit.
- Independent plan review is required for this changed timeout boundary before
  coding; implementation review and the normal offline/Ruff/format/safety
  gates remain required afterward.

## Scope

- Bound every production Gmail API request issued through the existing
  `GoogleGmailServiceFactory`/`retry.execute` seam, including profile probes,
  discovery, history, labels, reads, and target inserts.
- Use one fixed **30-second** transport timeout with no new user configuration,
  no retry-policy expansion, and no change to insert/recovery/privacy semantics.
  Pass a timeout-configured `httplib2.Http` into `googleapiclient.discovery.build`
  so both discovery and generated Gmail requests inherit the bound; retain
  `num_retries=0` on the existing request executor.
- Convert a request timeout to the existing typed `network_unavailable` result
  at the provider boundary; do not retain or expose exception text, URLs, or
  response payloads.
- Add a fixed provider-stage enum to the in-memory typed failure boundary:
  `profile_probe`, `service_discovery`, `history_list`, `message_list`,
  `message_get`, `label_list`, and `target_insert`. Every production request
  site supplies one stage. `message_get` covers source thread metadata/raw
  fetches and target RFC Message-ID search/readback; `label_list` covers the
  source label listing. Failures carry only role, stage, error code, fixed
  `timeout_seconds=30`, `attempt=1`, and a UTC observed timestamp.
- Stage fields are additive: legacy `ProviderFailure.status` and
  `retry_after_seconds` remain intact, and all rewrapped failures preserve
  those fields plus stage metadata. Legacy constructors default stage metadata
  to `None` so existing typed callers remain valid.
- Rewrapping must use one preserving helper (or equivalent complete field
  copy), never a fresh positional `ProviderFailure` that drops metadata. In
  particular, `projection/history.py`'s stale-cursor 404 conversion and both
  `projection/worker.py` 404-to-`source_missing` conversions must retain
  `status`, `retry_after_seconds`, `provider_stage`, `timeout_seconds`,
  `attempt`, and `observed_at` while changing only the intended code/role.
- Credential/profile verification must preserve a typed `ProviderFailure` from
  `profile_account`/`ProfileReader.get_profile` through `CredentialManager`
  verification and the non-fake CLI preflight. Existing error-code semantics
  remain unchanged (HTTP 401 maps to the role auth code; transport timeout
  maps to `network_unavailable`); only the private stage/status/retry metadata
  is retained for explicit diagnostics. No durable error-event or credential
  schema gains these fields.
- Refresh/profile `ProviderFailure` raised after a durable credential change
  enters `requesting` must use the existing `_abandon`/`_attention` cleanup
  with its closed `ErrorCode` before re-raising. The refresh single-flight
  owner and waiters must retain that same typed code (for example
  `network_unavailable` or role auth), never convert it to generic
  `persistence_failure`; no credential revision or binding publication occurs.
- Add a writer-owned startup reconciliation for an interrupted refresh change:
  only a `credential_changes` row with `kind=refresh`, `phase=requesting`, no
  matching pending candidate envelope, and a coherent owner-readable final
  envelope at the recorded old revision may transition atomically to
  `abandoned` with the role auth-required error. The old credential file,
  binding revision, and credential revision remain unchanged. Any pending
  candidate, digest mismatch, unexpected file, owner/lock uncertainty, or
  non-refresh/requesting shape stays `maintenance_required`/attention; never
  force-reset, initialize an empty DB, or edit state outside the existing
  writer protocol.
- The coherent-old-envelope predicate must include the role, owner
  `state_instance_id`, declared-account match, expected scope policy and
  scope-policy revision, binding revision, and old credential revision; the
  change row's state-instance and policy lineage must match the owner/config.
  A swapped-role, wrong-account, wrong-policy/revision, or wrong-state fixture
  therefore fails closed and remains unresolved.
- Keep the existing `error_events` schema and public `Issues`/`Diagnostics`
  DTOs unchanged: they have no stage field, and adding one would require a
  schema/public-version migration. Stage details remain private typed failure
  metadata (and optional private CLI diagnostic data); persisted/public output
  remains aggregate error code/count/timestamp only. If emitted by a CLI
  command, the allowlist is exactly `provider_stage`, `role`, `error_code`,
  `timeout_seconds`, `attempt`, `observed_at`, `status`, and
  `retry_after_seconds`, and it is emitted only with explicit
  `--private-metadata`; public/default output omits it. No provider URL,
  account, message ID, raw exception/response, token, or request payload is
  carried.
- Keep synthetic providers and preview/status/doctor offline paths unchanged.

## Files

- `src/facet/gmail/service_factory.py`: construct the Google client with a
  30-second `httplib2.Http(timeout=30)` transport while preserving
  access-token-only credentials and separate role services.
- `src/facet/gmail/retry.py`: preserve the typed failure boundary for
  `TimeoutError`/`OSError` transport exceptions; add stage metadata and keep
  `num_retries=0`/attempt one while retaining status/retry-after fields.
- `src/facet/gmail/source.py`, `target.py`, and `service_factory.py`: annotate
  each existing provider call with the fixed stage enum, including discovery
  construction failures. Catch build-time `TimeoutError`/`OSError` from
  service discovery and map them to typed `network_unavailable` with
  `service_discovery` stage before any Gmail operation.
- `src/facet/projection/history.py` and `src/facet/projection/worker.py`:
  replace stale-cursor and source-missing error rewraps with the preserving
  helper, keeping the existing 404/source-missing semantics and all additive
  stage/status metadata.
- `src/facet/gmail/credentials.py` and `src/facet/cli/bootstrap.py`: preserve
  typed profile `ProviderFailure` through verify/profile preflight and expose
  its fixed private diagnostic allowlist when `--private-metadata` is explicit;
  public/default output continues to expose only the closed error code.
- `src/facet/gmail/credentials.py`/`src/facet/runtime/state_owner.py` (or the
  existing writer-owned startup seam): reconcile only the bounded interrupted
  refresh shape above before normal provider work; offline status remains
  read-only and does not reconcile.
- Focused provider/runtime tests: fake a hanging request/transport at each
  representative stage and assert bounded invocation, typed stage metadata,
  no raw leakage, and no durable H0/epoch mutation.
- Focused projection tests: assert stale-cursor 404 and both worker
  source-missing conversions preserve stage metadata, HTTP status, and
  retry-after values; legacy `ProviderFailure` construction remains valid.
- Focused credential/CLI regression: a synthetic profile timeout retains the
  `profile_probe` stage, status/retry fields, and `network_unavailable` code
  through verification; private JSON emits only the allowlist while public
  JSON omits stage metadata. A synthetic 401 still produces the existing role
  auth code.
- Focused refresh fault regressions: inject a profile/transport
  `ProviderFailure` after `credential_changes` begins and assert the row is
  `abandoned`/attention-coded, no new credential revision is published, and
  concurrent same-flight callers receive the original typed error code rather
  than `persistence_failure`.
- Focused startup-recovery fixtures: safe no-candidate requesting refresh is
  abandoned idempotently with the old revision retained; candidate-file,
  digest/old-envelope mismatch, swapped role/account, scope-policy/revision or
  state-lineage mismatch, and uncertain-owner cases remain held for
  attention/maintenance without destructive or public/raw output.
- No live state, OAuth, Gmail writes, Compose, image, or deployment changes.

## Acceptance

1. A synthetic request that never returns is interrupted at the 30-second
   transport bound and yields `network_unavailable`, without an unbounded
   `run --once` wait; unit tests use a fake transport to avoid waiting 30s.
2. Existing provider HTTP/auth/rate-limit mappings remain unchanged and raw
   provider data is absent from errors/output.
3. A timeout before discovery leaves existing epoch/H0/checkpoint state
   unchanged; no blind retry or insert/recovery behavior is introduced.
4. Existing focused tests, full offline pytest, Ruff, and repository safety
   pass. The local image may be used only for offline/container wiring checks;
   the immutable main image remains the deployment artifact and is not
   substituted with a mutable tag.
5. A timeout diagnostic identifies the fixed stage while the exact private CLI
   allowlist is tested; public serialization proves stage data is not exposed
   and no error-event schema migration is introduced. Build-time discovery
   timeout has a dedicated typed regression.
6. Synthetic stale-cursor and worker 404 fixtures demonstrate that changing an
   error code/role does not erase stage metadata or existing retry scheduling
   fields, and no unrelated projection behavior changes.

## Stop gates

- Stop before implementation if bounding the request requires a new provider
  abstraction, retry behavior, OAuth scope, state schema, or public output.
- Do not start live OAuth, Gmail reads/writes, or deployment as part of this
  unit. A queued GHCR publication remains an external release gate.
