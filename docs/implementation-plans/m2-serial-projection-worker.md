# M2 Serial Projection Worker

Status: plan for independent review. This is a bounded implementation unit
inside the approved M2 product plan; it does not reorder or close M2 gates.
This plan authorizes no Gmail operation, deployment, image publication or
merge by itself.

## Goal

Make the already-integrated M2 producers executable as one bounded product
path in the supported foreground process. A single `ProjectionWorker` will
claim and finish durable `expand_thread` and `project_message` jobs using the
existing SQLite repositories and the typed Gmail source/target adapters:

```text
tracked expand_thread -> metadata snapshot -> project_message jobs
  -> in-memory raw fetch -> durable insert intent -> target insert
  -> target readback -> mapping verified
```

This is the next independently verifiable capability after PR #41. It does
not claim the complete Phase 1 or the final M2 gate: CLI/run construction,
credential-file loading, normal History poll scheduling, recovery audit and
Dashboard/Compose remain separate work where they are not already provided by
the current main tree.

## Contract and boundaries

- Base is exact `origin/main` SHA `d0777b3d4c2fe0e44f18e978b1e2ecef8e4b4dfc`.
- One owner session and one serial worker; no daemon, IPC, scheduler,
  cross-thread concurrency or runtime/native compatibility layer.
- Source and target are injected typed adapters. Tests use the existing fake
  Google-shaped transport only at that boundary. No live Gmail call is made.
- Raw MIME is held only in local memory during one message attempt, then
  released. DB rows, audit, exceptions and return values contain IDs, digests,
  typed states and closed error codes only.
- Gmail and SQLite are not one transaction. Intent is persisted before
  `messages.insert`; a lost/ambiguous response becomes `pending_recovery` and
  is never retried as a new insert by this worker.
- No send, forward, delete, source-label mutation, target-label mutation or
  automatic repair is introduced.

## Files and implementation

1. Add `src/facet/projection/fidelity.py` with a small stdlib MIME fact
   extractor. It computes versioned raw/semantic digests, extracts only the
   RFC Message-ID and Date policy required by the existing intent schema, and
   never returns body, subject, address or attachment data.
2. Extend `src/facet/gmail/target.py` with a typed, read-only inserted-message
   readback sufficient to compare semantic digest/version, thread ID and
   visibility. Raw digest is a source-integrity fact, not target equality.
   Keep the adapter closed to send/delete/modify operations.
3. Add `src/facet/projection/worker.py`:
   - claim one eligible job with the existing owner-run claim protocol;
   - expand a source thread from metadata, sorting by `internalDate` then
     message ID, excluding drafts, preserving Spam/Trash for an already
     tracked thread, carrying the first confirmed target thread as the anchor,
     joining existing mappings and enqueueing stable project jobs through
     `expansion` repositories;
   - for a project job, fetch one raw message, prepare an `InsertAttemptRow`,
     persist the dispatch marker, perform one insert for that attempt, record a
     definite or unknown result, read back a definite insert, and call
     `verify_mapping`; a replayed dispatch marker is never permission for a
     second insert;
   - honor current generation and existing mapping/unknown-insert blockers;
     classify source loss, auth/rate-limit/storage and malformed data as
     typed non-insert outcomes; leave network/response-loss uncertainty in
     recovery state;
   - process only one job per call or until the bounded selection is empty, with a
     redacted aggregate receipt useful to tests and future CLI/status wiring.
4. Add focused unit/integration tests using a real temporary SQLite owner and
   the existing fake Gmail controller. Cover complete non-draft thread
   expansion, deterministic order/anchor reuse, successful
   insert/readback/mapping, replay after restart, raw/privacy absence,
   definite target failure, generation cancellation before dispatch, an
   in-flight stop, and response loss. Do not add raw fixtures to tracked files.
5. Update `docs/development-status.md` with exact candidate and evidence; do
   not mark M2, G2 or Phase 1 complete.

## Acceptance

The candidate passes when a clean synthetic state can:

1. start with an admitted tracked thread and one `expand_thread` job;
2. create stable child project jobs for every available non-draft source
   message, including an older message, in deterministic order, without
   copying raw data to SQLite; draft-only history creates no project job;
3. perform one persisted dispatch per successful attempt, read back and
   verify the target semantic MIME/thread facts, and persist one mapping per
   source message. The evidence must not claim Gmail+SQLite exactly-once;
   an uncertain response remains recovery and is not retried by this worker;
4. close all successful jobs and leave no claim rows after the worker drains;
5. reopen the SQLite state after a completed mapping and replay the worker
   without another target insert;
6. leave an ambiguous insert in `pending_recovery` with a recovery job and no
   blind second insert; response-loss, source/target auth/rate-limit/network,
   and source-missing cases retain a typed non-success explanation. A definite
   failure removes its claim and leaves the durable job in retry_wait,
   needs_attention or source_missing rather than orphaned claimed state; and
7. show synthetic sensitive sentinels absent from DB, WAL/journal, runtime
   files, audit, logs and worker receipts. In-memory fake provider state may
   contain sentinels; exported transport traces and exceptions may not.

The worker enforces a fixed single-message raw limit (`max_raw_bytes`, default
35,000,000 bytes, matching the supported Gmail fixture limit). An oversized
message is released before any target call and left in a typed attention state
(`invalid_input`); no spool or raw diagnostic is written. Every provider call
occurs outside SQLite transactions. A stop-generation fault before dispatch
records `cancelled_before_dispatch` with no target call; a stop during an
in-flight insert records the provider result and preserves the target mapping
facts or leaves the attempt in attention. A provider response-loss fault
leaves `pending_recovery` and the worker never invokes insert again.

The semantic digest is versioned and computed from the parsed MIME tree,
decoded part bytes, attachment metadata and non-transport headers. It must
ignore provider-added transport headers while preserving Date policy, RFC
Message-ID and actual target thread ID. Synthetic coverage includes plain,
HTML, inline, attachment, non-ASCII and reply-header messages, valid and
invalid/missing Date, and a provider-added transport header. A threading
mismatch is recorded as attention; no broad 400 fallback or automatic
duplicate repair is implemented here.

Required checks for the candidate are the focused worker/privacy integration
tests, the full offline pytest suite, Ruff check/format, wheel import smoke,
repository safety and Python 3.12/3.13 candidate CI. A separate independent
implementation/acceptance review must bind its result to the exact candidate
SHA before merge.

## Explicitly deferred

This unit does not add CLI `facet run`, credential OAuth/file loading,
automatic History polling/backfill scheduling, H1 gap recovery, target
candidate attribution/audit/repair, stale-claim takeover after SIGKILL,
Dashboard, Compose, Actions or real Gmail evidence. The worker accepts a
bounded `max_jobs` run selector and handles only expansion/project jobs; it
does not claim to schedule or recover `recover_insert` work. Those remain
visible follow-up gates; this worker is useful when invoked by the existing
typed producer/owner seams and stops safely at those boundaries.
