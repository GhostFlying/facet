# Provider request timeout plan (Rev2)

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
- Keep synthetic providers and preview/status/doctor offline paths unchanged.

## Files

- `src/facet/gmail/service_factory.py`: construct the Google client with a
  30-second `httplib2.Http(timeout=30)` transport while preserving
  access-token-only credentials and separate role services.
- `src/facet/gmail/retry.py`: preserve the typed failure boundary for
  `TimeoutError`/`OSError` transport exceptions.
- Focused provider/runtime tests: fake a hanging request/transport and assert
  bounded invocation, typed failure, and no durable H0/epoch mutation.
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

## Stop gates

- Stop before implementation if bounding the request requires a new provider
  abstraction, retry behavior, OAuth scope, state schema, or public output.
- Do not start live OAuth, Gmail reads/writes, or deployment as part of this
  unit. A queued GHCR publication remains an external release gate.
