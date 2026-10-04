# M2 foreground sync and CLI vertical path

Status: implementation plan for independent review. This is a bounded revision
of the approved M2 product path; it does not change Phase 1 scope or acceptance
gates.

## Goal

Deliver the first runnable, restartable production-shaped path in the supported
Docker process model:

```text
initialized owner -> explicit backfill preview/start -> fixed-window discovery
-> durable expansion/message jobs -> serial projection worker
-> normal History poll -> action-label effect -> subsequent projection jobs
```

The path uses the already integrated typed owner, repositories, backfill/history
producers, action consumer, and serial projection worker. It does not add a
daemon, IPC broker, native/read-bootstrap gate, scheduler framework, or spool.
One foreground process owns the SQLite writer and performs one job at a time.

## Files and boundaries

- Add a small `facet.sync` runner that owns one cycle and a bounded foreground
  loop. It must reopen existing state through `StateOwner`, consume pending
  backfill discovery, consume one complete History poll, resolve action events,
  and drain projection jobs until idle or an explicit cycle bound is reached.
- Extend `facet.gmail.source`/`target` only with the narrow typed calls needed by
  the runner (label lookup, typed action facts, and provider error mapping).
  Raw MIME remains in memory and is never passed to persistence/status output.
- Extend `facet.cli.bootstrap` with real `run --once` and aggregate `status`
  dispatch. `init`, OAuth authorization and backfill command journaling remain
  explicit prerequisite commands until their owner/config-file integration is
  implemented; this unit must not claim them complete from an in-memory test
  harness. The runner API itself accepts an already initialized and verified
  `StateOwner` and the approved typed adapters.
- Add synthetic end-to-end tests using the existing fake Gmail transport and a
  file-backed owner. The test must prove discovery, complete non-draft thread
  expansion, target insert/readback, mapping persistence, History/action event
  handling, and restart continuation without a duplicate target insert.
- Update `docs/development-status.md` and `docs/phase-1-progress.md` once with
  actual candidate evidence and explicit remaining gates; do not add per-test
  self-referential SHA history.

## Required corrections while wiring

- Backfill candidates must be fetched and authenticated outside SQLite
  transactions. The production default uses the existing typed candidate seam;
  unknown or unavailable source-path evidence returns a typed attention
  decision. The existing `epoch_partitions.state=needs_attention` is the
  durable aggregate review marker; no candidate identity or provider payload is
  added to the schema. Synthetic tests may inject a reviewed typed evidence
  provider and must verify the marker survives reopen.
- Backfill must not revive an inactive/stopped tracked thread merely because a
  later scan sees it; stopped generations remain stopped.
- Source network calls (candidate metadata/auth and Gmail pages) must happen
  outside SQLite transactions. Transactions contain only typed, redacted facts.
- History startup must create the initial catch-up poll from the persisted H0
  fence before any normal checkpoint poll; an active poll is resumed rather
  than duplicated. History `messagesAdded` events must create/continue projection work only for
  an active tracked thread and must preserve the event's originating epoch.
  Action-label resolution remains readonly and durable.
- The initial epoch remains in durable `DRAINING` after discovery and H0
  catch-up. It is the single live authorization epoch for subsequent
  checkpoint History action effects, so the existing action consumer can
  enqueue a complete selected thread without inventing a new scheduler or
  epoch type. The runner passes this active epoch to action effects; it never
  reuses a terminal epoch or silently completes the live authorization epoch.
- On reopen, pre-dispatch claimed jobs may be re-queued only through an
  explicit typed recovery transition; a dispatch-started or pending-recovery
  insert is never auto-retried. An unknown insert remains a recovery/attention
  state until a later explicit recovery path.
- If the real source-path authenticity provider is still unavailable, automatic
  admission remains `review`/attention. The implementation must expose that
  typed state and report it as an open live-admission gate rather than silently
  admitting or claiming a complete Gmail sync.

## Acceptance

1. The runner refuses an uninitialized, paused, or unverified owner before Gmail
   work. Aggregate `status` contains no mail content or per-message addresses;
   owner-private binding/rule configuration is not treated as public telemetry.
2. The producer/API `backfill preview` has zero target writes; the producer/API
   `backfill start` persists H0 and discovery state before source paging. The
   `run --once` composition can resume after process close and drains a
   synthetic admitted thread to verified mapping. CLI journaling for these
   commands remains the separate prerequisite explicitly called out above.
3. A synthetic History page is persisted before its cursor advances; duplicate
   pages/events do not duplicate action effects or inserts. A label-added action
   updates a rule and enqueues the selected thread through the existing consumer,
   both during initial catch-up and after a restart on the normal checkpoint,
   using the retained DRAINING authorization epoch.
4. Unknown insert outcomes stay pending recovery and are not retried by the
   foreground runner. Raw/body/subject/per-message recipients or senders/full
   headers/attachments sentinels are absent from DB, logs, CLI JSON and status
   DTOs; private binding/rule configuration may remain in the owner-only state.
5. Focused tests, the complete offline suite, Ruff, wheel/import smoke, and
   repository safety pass on the exact candidate. No real Gmail write or
   deployment is performed by this unit.

## Stop gates

- Stop and report if wiring would require a new OAuth scope, real mailbox
  mutation, target deletion, or a product/privacy decision.
- Keep the candidate incomplete for live automatic admission until a reviewed
  source-Gmail-path authenticity provider is available. This is an explicit
  evidence gate, not a reason to block the synthetic vertical path.

## Revision 1: review-driven convergence fixes

The implementation review found three convergence gaps in the first candidate.
This revision keeps the repair inside the existing foreground unit:

1. Preflight projection, both role bindings, pause state, and restore state
   before any source-provider call. A non-ready owner fails with a typed
   maintenance/binding error and performs no discovery or History read.
2. Provide an explicit source-candidate/admission bridge. Provider metadata and
   source-path evidence are fetched outside SQLite transactions and then passed
   to the pure admission policy. The ID-only synthetic seam remains available
   for fake adapters, but production construction cannot accidentally pass
   `DiscoveryItem` to the typed candidate evaluator.
3. Persist unsupported/non-retryable History work as durable
   `needs_attention` event/job state. Temporarily unavailable provider work
   uses durable `retry_wait` with a future next-attempt time. Neither remains
   immediately queued and counted repeatedly on every foreground cycle; retry
   work is eligible only when due, while review work waits for a later
   reviewed recovery/decision path.

Acceptance for this revision is focused: the exact candidate must prove these
three convergence properties, including both durable attention and due-only
retry behavior, with synthetic adapters; preserve the existing unknown-insert
recovery behavior; and pass the complete offline checks. It does not claim
CLI/OAuth, live Gmail, Dashboard, Compose, or final Phase 1 completion.
