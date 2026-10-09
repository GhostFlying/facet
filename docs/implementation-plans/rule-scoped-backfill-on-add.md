# Rule-scoped historical backfill on rule addition

Date: 2026-10-09. Product decision confirmed by the user in this turn.

## Goal

When a new enabled sender/domain allow rule is added, Facet must automatically
schedule a bounded historical backfill for that rule. The scan starts at the
project's fixed historical anchor, the initial backfill `window_start`, and ends
at the rule-processing snapshot. Rules present before the initial epoch are
covered by that initial scope; the automatic rule-scoped path waits until the
initial History checkpoint exists. It must not rescan the entire mailbox or
re-run unrelated rules.

The rule-add command remains DB/offline-capable. The next foreground sync fences
the source History ID, publishes the durable expansion epoch, and runs the same
discovery, admission, thread expansion, insert, readback, mapping, and restart
deduplication path as an explicit historical expansion.

## Reuse and scope

- Reuse the existing operation journal, `BackfillProducer`, historical expansion
  epoch/checkpoint guards, `SourceCandidateAdmission`, thread worker, intent and
  mapping recovery. Do not add a second projection path or a new provider layer.
- Reuse the existing sealed ruleset for policy validation, but scope the
  provider query and evaluator to the newly added allow rule. Current
  blacklists remain applied at scan time.
- Persist the rule scope as a deterministic metadata digest in the existing
  backfill payload. The digest/key covers projection ID, normalized rule kind and
  value, rule revision, effective time, policy version, fixed anchor, end fence,
  and discovery cutoff. This makes a remove/re-add a new scope and makes replay
  independent of a lost first response. No mail content is stored and no schema
  migration is needed; existing v3 row/union codecs must be exercised unchanged.
- The canonical bytes are prefixed with `facet-rule-backfill-v1` and encoded as
  length-delimited UTF-8 metadata. They are combined with independent
  domain-separation labels `preview-request`, `preview-operation`,
  `start-request`, `start-operation`, and `epoch`; each result is SHA-256
  truncated to 128 bits with UUID-v4/variant bit normalization. The five IDs
  must be distinct. The existing unique
  operation key and `_existing_backfill_epoch` lookup are the CAS/replay guard;
  a concurrent loser reloads the committed row rather than allocating a second
  effect.
- A rule-scoped digest is the typed marker for the existing `scope_digest`
  field. The owner recognizes it only by recomputing the digest for the sealed
  rule revision and payload window; ordinary CLI scope digests do not match.
  Therefore old v3 readers continue to see a normal `Sha256Hex` payload and no
  SQL/union shape changes are required.
- Add Gmail domain candidate queries as a provider-side superset, followed by
  the existing exact sender/domain admission check.

## Files and behavior

- `src/facet/projection/backfill.py` (or a small adjacent helper): canonical
  rule-scope digest and fixed-anchor calculation.
- `src/facet/projection/admission.py` and
  `src/facet/runtime/foreground_runtime.py`: load a scoped evaluator for a
  rule-scoped epoch while retaining current blacklist checks. Historical
  rule-scoped candidates use processing-time eligibility so messages older than
  the rule's `effective_at` are included; the provider window remains fixed.
- `src/facet/sync.py`: before discovery, create and start any durable
  rule-scoped expansion not already represented by an operation/epoch. Use a
  stable derived request/operation/epoch key and the existing typed preview/start
  operation journal; a response loss is recovered by the same request lookup,
  never by a second start. Fence H0 before publishing the epoch and do not start
  before the initial History checkpoint is established. Rules whose current
  revision was effective no later than the initial epoch creation are treated as
  covered by that initial scope even if a stale/incomplete ruleset membership
  lookup would otherwise suggest expansion.
- `src/facet/db/command_records.py` and `src/facet/db/command_store.py`:
  permit a fixed anchor older than the rolling six-month boundary only when the
  typed rule-scope digest matches the current normalized rule/payload; ordinary
  CLI previews still require the exact `_six_calendar_month_start` window. The
  fixed anchor is `initial_epoch.window_start`; rules present before that epoch
  are already included in its sealed scope. `window_end` is the scheduler's UTC snapshot;
  `discovery_cutoff` is that snapshot's UTC first-of-month boundary. All three
  are persisted in `operation_backfill` before the H0-fenced start and survive
  crashes/replay. The discovery cutoff is the current UTC first-of-month
  boundary when that is strictly before the end fence; at an exact UTC month
  start it uses the preceding month boundary to satisfy the existing strict
  `window_start < cutoff < window_end` invariant.
- `src/facet/cli/bootstrap.py`: keep `rules add` an offline rule mutation; its
  next sync automatically schedules the backfill. Preserve idempotent replay.
- Domain discovery uses the bounded Gmail superset clause `from:(@<IDNA-domain>)`
  (sender uses the existing escaped `from:"<normalized-sender>"` clause), then
  exact local metadata admission enforces dot-boundary domain matching and
  Spam/Trash/draft exclusion. This clause is enabled only when the provider
  adapter advertises the exact capability token `gmail-from-domain-v1`, with
  versioned, auditable domain-recall evidence proven by a controlled recall
  fixture; absent capability or failed recall is a typed
  `maintenance_required` hold, never a fallback to an unfiltered mailbox query.
  Query rendering keeps the 4096-byte limit; invalid or overlong clauses fail
  closed with the same typed path.
- `src/facet/db/repositories/epochs.py` and the discovery adapter guards accept
  an old sealed ruleset revision for a marked rule scope after unrelated rule
  revisions advance the projection. They recompute the scope digest from the
  operation payload and its rule snapshot; only current blacklists and
  stop-generation checks remain dynamic. In addition, each candidate uses a
  current allow-rule enabled/revision guard before durable admission: removal
  stops new admission without changing the sealed provider query or reviving a
  stopped thread. The guard runs again inside the durable discovery transaction
  after provider pages are read, closing the remove-between-read-and-commit
  race. This preserves a sealed query while allowing unrelated rule changes
  without a false conflict.
- `docs/product-contract.md`, `docs/gmail-projection-spec.md`,
  `docs/project-plan.md`, `docs/cli-spec.md`, and `docs/development-status.md`:
  replace every old “new rules do not backfill” passage, explicitly record this
  approved contract delta, and document the fixed anchor and rule-scoped behavior.
- Focused tests cover sender/domain queries, fixed-anchor scheduling, one scope
  per new rule, no duplicate operation after restart, exact admission,
  blacklist/stopped-generation guards, and end-to-end synthetic projection.
- The durable page transaction also rechecks the current blacklist against each
  candidate after provider metadata is read; a blacklist written during the
  read phase therefore cannot bypass a stale evaluator snapshot.

## Acceptance

1. Start from a synthetic state whose initial epoch contains no later rule.
2. Add a sender rule and a domain rule through the real CLI command path.
3. The next `run --once --fake` persists a preview/start operation for each
   rule, proves source profile/H0 precedes epoch publication and discovery, and
   creates one historical expansion per rule from the exact fixed anchor. The
   provider query is the escaped sender/domain superset only when the fake
   transport explicitly advertises `gmail-from-domain-v1`; otherwise the domain
   scope is held
   with `maintenance_required` and no unfiltered request is issued. Where
   enabled, local metadata admission proves exact domain boundaries and excludes
   Spam/Trash/drafts.
   The test drives this through the real CLI rule mutation and sync commands and
   asserts the resulting operation, epoch, discovery, insert, and mapping; it
   does not seed readiness, rules, or epochs directly in the database.
4. A crash/response-loss replay finds the same operation by its stable key; a
   committed start/epoch wins over an older preview, including after preview
   expiry. The five domain-separated derived IDs are distinct and stable, it
   publishes at most one epoch, and never creates another insert attempt for an
   already mapped source message. Replaying an explicit complete-sync request
   preserves its saved scope while a separately added rule may create its own
   automatic scope. Existing v3 schema inspection and row codecs
   pass without migration. An exact UTC month-start end fence still produces a
   valid strictly earlier discovery cutoff.
5. A rule added while the process is stopped is discovered after restart. A
   removal or blacklist during a scan blocks new admission, does not revive a
   stopped thread, and does not widen a sealed scope. Re-adding the rule creates
   a new revision/scope; it does not reuse the old operation.
6. Rules present before the initial epoch are covered by that initial scope; no
   pre-initial rule-scoped epoch is created. Later unrelated rule additions do
   not change the sealed query/evaluator for an in-flight scope; the old scoped
   query remains valid while current allow enabled/revision, blacklist and stop
   generation guards apply. Removal stops new admission without reviving a
   stopped thread. Preview remains
   zero-write, raw mail remains memory-only, and all existing unknown-insert,
   H0/cursor, account/scope, writer-lock, and privacy tests stay passing.

## External boundary and stop gates

This unit does not authorize a real Gmail backfill, target writes, target
cleanup, new scopes, deployment, or release. After offline/synthetic acceptance,
the current Hyatt rule requires a separate explicit live-backfill authorization.
Stop for any schema/contract conflict, unknown insert, provider account/scope
mismatch, unresolved History gap, or a rule-scope ambiguity; do not widen the
scan to all current rules as a fallback.
