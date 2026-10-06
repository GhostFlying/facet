# Provider request timeout plan (Rev5)

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
- Focused provider/runtime tests: fake a hanging request/transport at each
  representative stage and assert bounded invocation, typed stage metadata,
  no raw leakage, and no durable H0/epoch mutation.
- Focused projection tests: assert stale-cursor 404 and both worker
  source-missing conversions preserve stage metadata, HTTP status, and
  retry-after values; legacy `ProviderFailure` construction remains valid.
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
