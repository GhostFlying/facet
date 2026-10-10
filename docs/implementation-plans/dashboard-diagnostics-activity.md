# Dashboard diagnostics and rule-match activity

2026-10-10. Base: current `rule-scoped-backfill` checkout. Root implements and
validates this bounded Dashboard unit.

## User-visible delivery

The read-only Dashboard will explain previously unreported diagnostics instead
of turning available local facts into `Unknown`, show the running image's
40-hex commit SHA when the deployment supplies it, and add a reverse
chronological activity section. Each activity row contains only the configured
sender/domain rule value, the number of newly verified mappings attributed to
that rule, and the server-local operational timestamp. It never exposes Gmail
message/thread/history IDs, subjects, addresses outside the already approved
rules view, content, digests, or provider errors.

## Implementation scope

- Extend the closed Diagnostics model/serializer and frontend with optional
  `commit_sha` and real local DB/scope/resource checks.
- Derive scope readiness from the already verified binding state; check the
  writer connection's read/write mode without a mutating probe.
- Classify memory from Linux `/proc/meminfo` when available and disk from the
  state filesystem's free-space ratio; unavailable platforms remain explicitly
  `Unknown`.
- Add a bounded `activity` public snapshot. Build it from durable mapping
  verification timestamps joined to the latest sender/domain admission rule;
  group by rule and server-time second, newest first, with a fixed row limit.
  Action-label/manual admissions without a sender/domain rule are omitted rather
  than guessed.
- Add `/api/v1/activity`, static rendering/tests, and update the Dashboard spec
  and development handoff.
- Read `FACET_COMMIT_SHA` first and fall back to the injected `FACET_IMAGE`
  commit tag. Invalid or digest-only values are shown as unavailable, never
  inferred from arbitrary process text.

## Acceptance and boundaries

- Existing five snapshots and privacy allowlist remain compatible; the sixth
  activity snapshot is independently validated and stale/unavailable-safe.
- Synthetic DB tests prove diagnostics states and activity aggregation; HTTP and
  browser tests prove no IDs/content appear and that newest activity sorts first.
- The container deployment must inject the immutable image reference (and thus
  its commit tag) for the SHA to be shown. Missing injection is an honest
  `Unknown`, not a release failure for non-container local runs.
- No Gmail calls, writes, schema migration, rule changes, or new external
  authorization are required. This unit does not claim final Phase 1 acceptance.
