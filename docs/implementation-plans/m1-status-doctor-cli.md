# Offline status and doctor CLI

Status: implementation plan for one complete maintenance-CLI unit.  The base
is `origin/main` after PR #58.  This unit does not claim G1, complete CLI, live
Gmail health, or Phase 1 completion.

## User-observable delivery

From the same private state directory used by Compose, an operator can run:

```text
facet status --json
facet doctor --json
```

Both commands work while the foreground sync process is stopped or holding the
writer lock.  They open the local SQLite WAL read-only, do not construct a
Gmail client, refresh OAuth, acquire the sync writer lease, mutate the DB, or
print email details.  `status` returns aggregate phase/health, binding states,
epoch state, confirmed mapping count, mutually exclusive queue counts, and
typed issue counts.  `doctor` returns the same safe summary plus typed local
checks for config ownership/digest, schema readability, binding readiness,
restore/paused state, and unresolved work.  Unknown or stale facts remain
unknown; zero is never substituted for an unavailable check.

## Files and behavior

- `src/facet/cli/status.py`: add a narrow read-only state adapter.  Validate
  the managed config/state paths and private ownership, open the database with
  SQLite `mode=ro`, configure query-only/trusted-schema/foreign-key guards,
  inspect the compiled supported schema, and run only fixed aggregate SQL.
  Build an allowlisted CLI DTO with no addresses, rule values, Gmail IDs,
  paths, provider payloads, credentials, or raw errors.
- `src/facet/cli/bootstrap.py`: register and dispatch `status` and `doctor`.
  Keep global JSON/public/private flag rules and controlled error envelopes.
  `doctor --live` is not implemented by this unit; if presented, return the
  existing controlled unsupported/invalid result rather than silently doing a
  remote check.
- `tests/cli/test_status_doctor.py`: subprocess tests prove operation while a
  separate owner lock is held, no Gmail/provider imports or network access,
  schema/config failure classification, aggregate-only output, stale/unknown
  handling, and no file/database mutation.
- `docs/development-status.md`: record the exact candidate and evidence only
  after focused review, full offline checks, and CI pass.

## Reuse and non-goals

Reuse `select_paths`, managed-config validation, compiled schema inspection,
existing `ErrorCode`/status vocabulary, and the Dashboard's aggregate query
semantics where they can be reused without opening a writer session.  Do not
add a second state model, a public HTTP route, a Gmail live doctor, a daemon or
IPC protocol, queue mutation, recovery retry, backup/restore, or source-path
attestation.  This unit must not turn private CLI metadata into Dashboard or
public telemetry.

## Acceptance

1. Initialized synthetic state with auth/backfill/action data yields stable
   aggregate `status` and `doctor` JSON; no email-content sentinel, address,
   rule value, credential, ID, or private path appears in stdout/stderr.
2. The commands succeed read-only while another process owns the sync writer
   lock and leave the existing DB/config/WAL contents byte-for-byte unchanged.
   SQLite may create or refresh its ordinary `-wal`/`-shm` coordination
   sidecars while taking a read snapshot; those sidecars contain no Facet
   output or mail cache and are not business mutations.
3. Missing/invalid config, unsupported schema, and unreadable DB produce the
   documented typed envelope without echoing input or provider details.
4. Focused CLI tests, the complete offline suite, Ruff/format, wheel smoke,
   repository safety, and candidate Python 3.12/3.13 CI pass.

## Risks and stop gates

- SQLite read-only snapshots can be stale while a writer is active; report
  freshness/unknown explicitly and never claim a live Gmail health check.
- If the existing schema inspection cannot safely run against a WAL read-only
  connection, stop and revise this plan rather than falling back to a writer
  lock or an unvalidated raw query path.
- Any need to expose private metadata, refresh credentials, contact Gmail, or
  change the public output contract is outside this unit and requires a new
  reviewed plan/authority.

## External boundary

No OAuth, Gmail read/write, target mutation, deployment, image publication,
release, or host operation is performed.  This unit only reads the local
private state supplied by the operator.
