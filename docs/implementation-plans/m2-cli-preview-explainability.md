# Explainable backfill preview

Status: bounded CLI product unit on top of `origin/main` `7e6ab6d`.
It improves the existing preview response without changing admission, source
trust, or the explicit-start boundary.

## User-observable delivery

`facet backfill preview --json` returns a redacted aggregate scope summary:
the fixed six-calendar-month window, discovery cutoff, active ruleset revision,
explicit-start requirement, thread-wide disclosure semantics, and
`target_writes: 0`. Replaying the same request returns the same preview scope.
The output contains no message, sender, subject, rule value, provider payload,
credential, or target identifier.

## Scope and reuse

- Extend the existing `_backfill_preview` response using the already persisted
  operation/payload and projection facts; do not create a second preview store.
- Add subprocess coverage that checks the aggregate fields, request replay,
  zero target writes/mappings, and privacy sentinels.
- Do not add Gmail calls, target calls, schema changes, admission changes,
  source-path attestation, or implicit backfill start.

## Acceptance and stop gates

Focused CLI/preview tests, affected backfill tests, the full offline suite,
Ruff/format, wheel smoke, repository safety, independent implementation review,
and supported-Python CI must pass. Any need to persist mail content, alter
preview guards, or change disclosure semantics stops this unit for a revised
plan.
