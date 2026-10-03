# M1-02/M2 operation journal and backfill decision extension

Date: 2026-10-03 (PRC). Revision: r1, PLAN ONLY.

This document is a bounded implementation plan. Writing, reviewing, or
committing this plan does not authorize source, migration, CLI, provider, or
Gmail work. An independent non-author plan review and an explicit coordinator
release are required before implementation.

## Base, ownership, and evidence

The implementation base is the merged main commit
`5175fb2f552da40c0e165301cdc2c4bab5d76737` (tree
`0e67b5c6f431f350b42a91680a5ddf558411cc08`). The owned branch is
`p/luchengxuan/m2-foundation`. The current worktree contains unrelated
untracked foundation work (`runtime/state_owner.py`, `gmail/credentials.py`,
`db/repositories/bindings.py`, and
`docs/implementation-plans/m2-foundation-consumer-seam.md`); those files are
not part of this plan and must remain untouched and unstaged.

The plan is bound to these reviewed contracts at the base:

| Input | SHA-256 | Relevance |
| --- | --- | --- |
| `docs/implementation-plans/m2-automated-projection-core.md` | `ca60e62064595dcc6522cda5397d51ab038bd626b4c2f5c72336d0dd1ade215c` | Fixed six-month preview/start, H0, command journal, and M2 stop gates |
| `docs/cli-spec.md` | `045b73faddfb6586e7c51aa76be2c2f9a191513a6dbba9dcc3d75fa63ea9b0fc` | Stable request keys, preview freshness, confirmation, and privacy |
| `docs/phase-1-execution-plan.md` | `877fac0a9f6b1521e58287a5521adf8b0b037e1e95e9cd2319231d3c199e451b` | Shared DB-owner and CLI work-package ownership |
| `docs/implementation-plans/m1-02-persistence.md` | `6e4d35aa74925403006010b27e1b20c2b79b64eb8b9a033f665536f770c7649e` | Fixed migration, rollback, backup, and metadata-only rules |
| `docs/implementation-plans/adrs/persistence-schema-v1.md` | `3d9021511cb148dfa8b9543ac880d27d83c4f01940659da5fe373e802d74f433` | Trusted manifests, closed records, and no generic SQL |
| `docs/implementation-plans/adrs/writer-command-protocol.md` | `5f0e5af9cc238f7967a88590fb53acc91c4697ffa27d19773cc66cf5ccc41368` | Local owner transaction, request identity/digest, and replay semantics |

Read-only inspection of the base found the following finite blocker. The
closed `LocalCommandKind` and fresh `v0002._COMMANDS` contain only daemon,
bootstrap, and auth kinds. `OperationRow` requires a null preview reference,
and `command_store.py` only inserts/looks up bootstrap payloads. The existing
typed `EpochDecisionRefBackfillStart` and v1 `epochs` columns are present, but
`repositories/epochs.py::_decision` rejects every decision other than the
reconcile/audit families with `owner_unavailable`. A UUID-shaped operation or
preview in a test therefore is not authority. The extension below supplies
the missing shipping journal and guard without inventing a second operation
format.

## Goal and non-goals

The goal is the smallest shipping DB-owner capability required by M2:

1. persist a typed `backfill_preview` operation and its aggregate fixed-window
   scope;
2. persist a typed `backfill_start` operation keyed to that preview;
3. make the same local request key plus the same canonical payload digest
   replay the existing result, while a changed payload returns
   `request_conflict` without mutation;
4. atomically validate the preview, publish a `backfill_start` epoch decision,
   persist its H0 fence/cutoff and initial scan state, and make a lost first
   response recoverable by request-key lookup; and
5. preserve the existing writer-owned transaction and repository boundaries.

This is local metadata and epoch fencing only. It does not run discovery,
call Gmail, insert target mail, admit threads, create jobs from provider data,
or expose a public command endpoint.

Explicitly out of scope are Unix/HTTP IPC, a receipt broker, a file inbox,
client-side receipt files, a daemon or second writer, raw MIME/body/provider
payloads, arbitrary JSON columns, a generic command registry, schema reflection
or user SQL, credential/OAuth work, action-label producers, History polling,
projection workers, pause/resume, recovery/repair, provider registries,
backups/restores, CLI handlers, Dashboard output, and any M3-M6 behavior.

## Exact implementation allocation (future release only)

The following is the complete proposed source/test allocation. A path change,
new public symbol, or new storage strategy requires a written amendment and a
new independent review before coding.

### Production

| Path | Bounded responsibility |
| --- | --- |
| `src/facet/db/command_records.py` | Add closed backfill command/payload records and command-specific validation. Reuse `RequestId`, `OperationRow`, `Sha256Hex`, `Revision`, `Timestamp`, `PreviewPurpose`, and existing error codes; do not add an open mapping or provider fields. |
| `src/facet/db/command_store.py` | Add private owner-transaction insert, typed preview validation, and request-key lookup/replay helpers. The request identity remains `(projection_id, request_namespace, request_nonce)`; no second journal. |
| `src/facet/db/migrations/v0002.py` | Extend the separately named pristine fresh-v2 command catalogue with exactly `backfill_preview` and `backfill_start`, one fixed `operation_backfill` child table, indexes, foreign keys, payload-kind trigger, and immutable-row triggers. The DDL is fixed source, not a schema builder. |
| `src/facet/db/migrations/__init__.py` | Recompute only the named fresh-v2 registry/checksum/digest/manifest for that reviewed v0002 extension. Preserve `REGISTRY`, `CHECKSUMS`, `REGISTRY_DIGEST`, `_CURRENT_MANIFEST`, and `_EXISTING_STEPS` byte-for-byte; there is no v1-to-v2 production migration in this unit. |
| `src/facet/db/repositories/epochs.py` | Replace the bare `backfill_start` refusal with a fixed lookup of the journal and child payload. Validate operation kind/state, exact preview lineage, projection/binding/ruleset revisions, six-month window/cutoff/scope digest, expiry/invalidation, H0 fence, and current sealed ruleset before `start_epoch` writes. Existing reconcile/audit/gap guards remain unchanged. |

`connection.py`, `schema.py`, `transactions.py`, `repositories/base.py`,
`repositories/serialization.py`, `models.py`, contracts, runtime owner, and
CLI files are not allocated. The existing fresh-v2 initializer already runs a
trusted manifest in one transaction; it must not gain a second opener or a
special M2 bootstrap shortcut. If an implementation needs one of these paths,
stop and return an amendment rather than widening the allocation.

### Fixed storage shape

The new `operation_backfill` row is a closed child of `operations`, keyed by
`(projection_id, operation_id)`. It contains only typed metadata:

* `projection_id:P` and `operation_id:L` (the composite primary/FK);
* `purpose:PreviewPurpose` fixed to `start_backfill`;
* `preview_operation_id:L?`, null only for `backfill_preview` and required for
  `backfill_start`;
* `ruleset_revision:R`, `window_start:T`, `window_end:T`, and
  `discovery_cutoff:T`;
* `scope_digest:H` (SHA-256 over aggregate typed scope facts);
* `expires_at:T` and `invalidating_revision:R`.

The parent operation's existing `expected_binding_revision` and
`expected_config_revision` are the binding/config guard. Its existing request
namespace/nonce, command, digest/version, operation state, timestamps and
controlled error code remain the journal identity/state. There is no address,
sender, thread/message ID, subject, body, attachment, header, credential,
provider response, SQL text, path, or arbitrary payload column. A fixed SQL
trigger requires a start child to reference an existing preview operation of
the same projection, command family, digest/scope lineage, and current
revision; a preview child cannot reference another operation.

This is an intentional fresh-v2 manifest amendment, not a generic schema
rewrite. All original v1 tables and the existing 37 v2 table definitions and
their data columns remain unchanged; the extension only amends the closed
command/check/trigger literals and adds the named child table with its fixed
constraints/indexes. The historical pre-extension fresh-v2 manifest is not
silently upgraded or downgraded. If an already-created v2 database must be
upgraded, the complete backup/credential/config bundle and a separately
reviewed existing-state migration are required; that migration is a stop gate
and is not part of this plan.

## Typed operation and transaction protocol

### Preview

The owner validates the initialized projection, both binding/config revisions,
sealed ruleset revision, fixed UTC calendar-month six-month cutoff, aggregate
scope digest, and a bounded expiry. It computes the canonical digest from the
closed command/payload/version/guards (not from raw input), then inserts the
parent operation and `operation_backfill` child in the existing short writer
transaction. Preview has no H0 write, epoch row, discovery request, job,
provider call, or Gmail insert. A repeated same-key/same-digest request
returns the existing operation; a same-key/different-digest request returns
`request_conflict` without updating timestamps or state.

### Start

The owner receives a typed H0 history fence and a preview operation ID from
the already-qualified provider/worker boundary. Before any scan or effect it
opens the existing writer transaction and validates:

* the request key/digest is new or an exact replay;
* the preview operation is the same projection, purpose, binding/config and
  ruleset revision, scope digest, cutoff/window, and non-expired revision;
* the current binding and sealed ruleset still equal the preview guards;
* the typed epoch is `INITIAL_BACKFILL`, has `EpochDecisionRefBackfillStart`
  pointing at this start operation and preview, and has a non-empty H0 ID and
  recorded timestamp matching its cutoff/window constraints; and
* the initial source-window partition and checkpoint/H0 state are valid,
  unstarted, and owned by this writer.

The transaction then inserts the start operation/child, epoch decision,
initial partition(s), and H0/cutoff checkpoint fence together. No provider
network wait occurs while the transaction is open. H0 is a typed fence fact,
not a caller boolean or a fabricated UUID. A failure before commit rolls all
these rows back and prevents discovery/cursor advancement. An uncertain commit
invalidates the session and requires reopen inspection; it never retries
BEGIN/COMMIT or creates a second epoch.

### Request identity, digest, and first-response-loss lookup

The stable key is the existing lower-case UUID4 pair
`rq1_<request_namespace>_<request_nonce>`. A fixed domain-separated digest v1
uses the command/payload/version, projection, request namespace, confirmation,
expected binding/config/preview guards, and all typed child fields. It excludes
the nonce, wait timeout, transport framing, and output profile. Encoding uses
the writer ADR's reviewed canonical deterministic scalar sequence (implemented
as a private fixed helper if the current branch has not yet exposed it), never
arbitrary JSON; the owner recomputes it instead of trusting a caller hash.

Lookup runs through the same serialized owner DB boundary. A committed row
returns its existing accepted/completed/blocked/attention/rejected result and
never re-runs epoch/H0 work. A healthy authoritative absence returns
`request_not_received`; lock/persistence/commit uncertainty returns
`request_outcome_unknown`; a different namespace/lineage returns
`request_lineage_mismatch`. No result is represented by a fabricated success,
blind retry, or a second local journal.

## Compatibility and invariants

* v0001 source, its application ID, tables, checksums, current manifest, and
  existing migration registry remain exact. No production v1-to-v2 migration,
  downgrade, empty-DB fallback, or user SQL is introduced.
* Existing v2 bootstrap/auth/daemon operation rows, `BootstrapInspection`'s
  six-field shape, bootstrap seeds, auth payloads, immutable triggers, and
  request-key construction remain behaviorally unchanged. Their old command
  kinds retain their existing confirmation/preview/nullness constraints.
* New command-specific constraints are closed: preview has no required preview
  reference or target effect; start requires an exact preview reference and
  explicit confirmation; neither can set duplicate-risk acknowledgement.
* Existing epoch reconcile/audit/gap tests continue to reject wrong decisions.
  A bare `EpochDecisionRefBackfillStart` with no journal/preview remains
  `owner_unavailable` or `request_conflict`; constructing an epoch row in a
  test never grants authority.
* Reopen/duplicate migration checks compare the exact trusted fresh-v2
  manifest and checksum. A pre-extension v2 file is not modified in place; the
  owner reports the supported version/migration boundary instead of silently
  adding tables or dropping rows.

## Test and acceptance matrix

Only synthetic metadata and fake provider boundaries are used. The retained
tests stay; the implementation adds focused cases in these exact files:

| Test path | Required evidence |
| --- | --- |
| `tests/test_command_records.py` | Exact closed fields, command-specific confirmation/preview invariants, canonical digest, foreign subclasses/keyword names, fixed errors with no cause/context/private text, and no raw payload fields |
| `tests/test_command_schema_v2.py` | Fresh manifest/ledger/catalogue has the original tables plus exactly `operation_backfill`; DDL checks, FKs, immutable rows, payload-kind triggers, old bootstrap/auth rows and historical v1 manifest remain intact |
| `tests/test_command_bootstrap_storage.py` | Existing facet/config bootstrap, reopen, duplicate, rollback, owner lineage, and bootstrap inspection remain green with the extended command catalogue |
| `tests/unit/test_db_command_operations.py` (new) | Preview insert/replay/conflict, start lineage and scope guards, operation-to-epoch link, metadata-only digest, and owner lookup outcomes |
| `tests/unit/test_db_epochs.py` | Valid journal-backed initial backfill with real H0/cutoff; no bare UUID authority; stale/expired/mismatched preview, binding/ruleset/config revision, wrong kind, missing H0, duplicate epoch, and invalid partition negatives |
| `tests/unit/test_db_history_epoch_work.py` | Initial History poll consumes the committed H0/cutoff epoch and cannot advance a checkpoint before its start transaction; replay remains one operation |
| `tests/unit/test_db_process_crash.py` | Child/process interruption before commit, after operation insert, after epoch/H0 writes, and after commit-before-response; reopen distinguishes committed replay from uncommitted rollback and never duplicates an epoch |
| `tests/unit/test_db_query_failures.py` | Execute/fetch/commit/rollback/BUSY and caller-already-excepting failures yield fixed typed errors, preserve owner failure fences, and do not expose provider/private exception text |

Required cases include:

1. clean fresh initialization and reopen with the exact manifest, WAL/FK/FULL
   settings, old bootstrap/auth rows, and no producer/provider registry;
2. preview zero-effect (no H0/epoch/checkpoint/job/provider call), valid start,
   repeated start, same-key payload conflict, stale/expired preview, changed
   binding/ruleset/config/cutoff/scope, and wrong-purpose preview;
3. exact two-owner/process contention where one request commits one operation
   and one epoch and the other replays or receives a fixed conflict;
4. faults at operation journal insert, child insert, preview lookup, epoch
   insert, partition/checkpoint/H0 write, commit, rollback and close; no
   partial accepted operation or cursor advance is reported;
5. first-response-loss lookup after a committed start, ambiguous commit
   lookup, lock-unavailable lookup, absent request, and namespace mismatch;
6. privacy sentinels in synthetic body/subject/attachment/provider exception,
   credentials and local paths stay absent from DB/WAL/SHM/journal, logs,
   stdout/stderr, and returned metadata; only approved IDs/digests/revisions
   appear; and
7. full locked offline tests, targeted DB suite, Ruff lint/format, both CLI
   help/version lanes, wheel import/privacy smoke and staged repository safety.

No test may construct an epoch row or operation child directly as producer
evidence, call Gmail, use a real mailbox, skip/xfail, weaken a guard, retry
until green, or fabricate a process/power-loss result. Provider and discovery
integration remain later M2 consumer gates.

## Risks, review, and stop gates

Independent review must inspect the exact base, manifest strategy, closed
records, transaction ordering, replay semantics, and privacy matrix before any
source release. Root/coordinator then provides a separate implementation
release; source author cannot self-approve or merge. A future candidate needs
fresh full tests, installed-wheel checks, and both Python CI lanes against its
immutable tree, followed by non-author source review.

Stop and return an amendment if any of these occurs:

* a fixed fresh-v2 extension cannot preserve the old v1/v2 compatibility
  boundary, or would require an unapproved existing-state migration;
* the operation payload needs generic JSON, raw content, provider response,
  credentials, arbitrary SQL, or a second journal/receipt protocol;
* an epoch/H0 guard needs a caller flag, test-only row, fake operation, or
  provider/network call inside the transaction;
* a new public CLI/wire API, daemon/IPC, command family, registry/provider,
  schema-version consumer, or unallocated source/test path is required;
* uncertain commit/close cannot be resolved by serialized lookup and reopen
  inspection without blind retry; or
* any privacy sentinel, old bootstrap/auth behavior, migration checksum,
  writer ownership, or retained failure control regresses.

This plan does not claim M2/G2, M1 completion, live Gmail, G1, backup/restore,
or any later milestone. The next action after this docs-only commit is an
independent plan review; no implementation or merge is released by this file.
