# Live dashboard composition

Date: 2026-10-05. Status: implementation candidate; independent plan approval
received, implementation review pending.
Base: `ae400ae3c0eac405ab71c08c0df16321f766402e`. Root owns this branch;
`cli_sync_review` independently approved the original plan before implementation.

## User-observable delivery

The Compose image's supported foreground process can publish a read-only,
aggregate Dashboard snapshot after each completed sync cycle. The Dashboard
shows sync phase/health, discovery progress, confirmed mapping count, mutually
exclusive job counts, and categorized error counts. Before the first usable
snapshot it remains explicitly `unknown`/`unavailable`.

## Scope

- Add one in-memory snapshot provider owned by the foreground process.
- Derive only allowlisted aggregates from the existing private SQLite state and
  the cycle receipt; HTTP handlers never open SQLite or call Gmail.
- Run the existing foreground cycle and HTTP server in one supported process
  with a bounded polling interval; no daemon, IPC, request broker, worker pool,
  raw spool, or second database writer.
- Keep the current `web` command as a safe read-only boundary. Compose will use
  the combined foreground command only after its offline fake/runtime tests
  pass; no live Gmail or deployment is performed by this unit.
- Sync and SQLite remain on the main thread, HTTP on one cache-only thread.
  Validate config/selectors before binding HTTP; retain one owner until exit.
  Do not call Gmail while awaiting bindings or explicit backfill start. Handle
  SIGINT/SIGTERM and failed listener startup with deterministic lock cleanup.
- Snapshots age by monotonic time; stale snapshots cannot remain healthy or
  ready. Collector failures invalidate readiness rather than serving fresh
  cached success. Unknown metrics remain null, and partition attention must
  be visible even when no job/error-event row exists.
- Progress confirmed messages and queue categories use lifetime projection
  counts; epoch summary is separate. Current-epoch discovered/completed thread
  counts come only from durable `expand_thread` jobs. A scanned-thread count is
  left unknown because the privacy-preserving DB does not retain rejected
  candidate thread IDs; do not substitute message candidates or invent a
  percentage/ETA.
- Before each provider cycle, a DB-only gate requires verified source/target
  bindings and a non-terminal, explicitly-started epoch. Pending bindings or
  pre-start state publishes an aggregate blocked/unknown snapshot and waits;
  it never constructs or calls a Gmail service.

## Files and acceptance

- `src/facet/runtime/dashboard.py`: aggregate snapshot construction and
  thread-safe in-memory publication; reject/private fields never cross the
  status models.
- `src/facet/web/server.py`: accept the provider without changing fixed routes
  or output allowlists.
- `src/facet/cli/bootstrap.py`, `docker-compose.yml`, `Dockerfile`: compose the
  one-process sync/dashboard entrypoint while preserving explicit `run --once`
  and `web` behavior.
- tests: fake owner/runtime cycle publishes status/progress/issues; HTTP reads
  remain Gmail/DB-free and privacy sentinels do not appear; restart starts from
  durable state; a failed/unknown source-auth cycle is shown as blocked or
  degraded rather than healthy.

## Stop gates

- Do not claim live Gmail sync, automatic admission, or deployment.
- Do not add an attestation shortcut, public private metadata, or content
  caching. Source-path attestation remains a separate unresolved gate.
- If the existing runtime cannot safely provide a single-process composition
  without changing the approved Docker execution model, stop and report the
  smallest decision instead of adding a daemon/IPC layer.
