# Honor the configured polling interval

2026-10-09. Base: `78f8450634baa7bcda01ce72455f3444c01d7092`.
Root implements; an independent Sol reviewer checks plan and actual candidate.

## One delivery

Continuous `run` and `sync` use `sync.poll_interval_seconds` unless an explicit
`--interval` overrides it. Missing configuration/new init defaults to 60 seconds.
The interval is idle time AFTER a cycle, not a fixed start cadence or latency SLA.
`--once` never waits. Validate explicit invalid values before any owner/network
mutation; validate the resolved configuration interval before acquiring an owner.
Preserve all existing account/scope/config-artifact and single-writer checks.

Files: `config.py`, `cli/bootstrap.py`, `cli/sync_entry.py`, focused config/CLI/
runtime tests, CLI/operations documentation and one current-status handoff.
Reuse the existing production runtime, config loader and snapshot collector.
No schema, config-mutation command, scheduling framework or shared timer thread.

The 30-second Dashboard freshness budget must still detect a stalled owner.
While deliberately idle, the owner can refresh LOCAL aggregate snapshots every
at most ten seconds, preserving the last cycle's failure/verification state.
This does not poll Gmail, advance checkpoints, or update last successful poll/
insert timestamps. Failed collection invalidates snapshots. Monotonic deadlines
and interruptible waits preserve the requested total idle duration and SIGTERM.
Never keep re-publishing after shutdown or during a stalled network operation.

Operational timestamps remain UTC in persistence. Public Dashboard/CLI formatting
must use the sync server's local timezone (not the browser timezone); the chosen
zone/offset is presentation metadata only and must not change ordering or stored
instants. The user explicitly approved a private Dashboard rules view during
this unit. It adds one read-only `rules` snapshot family with current
sender/domain values, enabled state, and configured action-label text. It does
not expose binding addresses, message IDs/content, credentials, or rule values
through other public DTOs, logs, or exports.

## Acceptance and bounds

- Missing/configured/explicit interval precedence for both entrypoints; invalid
  NaN/infinite/non-positive/over-24-hour explicit values remain rejected before
  writes, including `sync --once`. New init persists 60; legacy explicit values
  remain unchanged. Synthetic subprocesses use ordinary setup/binding/scope.
- Virtual-time owner-loop tests prove a 60-second idle, local-only heartbeat,
  retained last-poll time/error state, failure invalidation and prompt stop.
  Existing cached GET/privacy and full CLI/restart tests must keep passing.
- Targeted checks during development; qualified candidate full offline baseline,
  independent implementation/acceptance review and required exact-head CI before
  merge. Non-root candidate image proof precedes deployment.
- Current test deployment only: stopped/locked SQLite/config/credential backup,
  immutable-image/source verification, same accounts/rules/window/volume. Its
  managed config already explicitly says 30 and has an immutable artifact guard:
  do NOT silently rewrite it or its DB digest. Use the existing CLI override 60
  in a private Compose command override, documenting that distinction. Prove
  config precedence in synthetic production-path tests, not by this override.
  Observe real cycle timing and fresh local snapshots through the idle period.
  No new historical start, deletion, sending, scopes, repair or Release.

## Label investigation (read-only)

The current writer consumed three recent label notifications and recorded three
successful current AddSender activations, each with a tracked thread and confirmed
mapping. Local and Tailnet cached APIs agree. The prior Dashboard lacked
rule/action fields; displayed thread discovery counts belong to the old backfill
scope. The new rules view is a read-only current configuration snapshot, not a
historical scan or a sync-success signal.
