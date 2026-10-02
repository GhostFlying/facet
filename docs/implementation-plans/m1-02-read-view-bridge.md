# M1-02 guarded read-view bridge: aligned implementation plan r3

Date: 2026-10-02. Engineering base is
`422ba9b8a845db60a587bda9e1946fd77269674f`, carrying reviewed main
`ff77e63a823dc8bcb130836243746c067778b94f` by normal merge. The implementation
owner is `phase1_plan_author`; independent review remains a different agent.

This is a file-level plan, not source dispatch or a new permission. The no-create
design r4 is independently approved at SHA256
`4f12b845e8fdd6662079a5df84a4da83e64a338f6f38143a615119f8b480a780`
(589 lines), with the r2/r3 prefixes unchanged. This revision consumes that exact
bridge inventory and the two-stage bootstrap correction. This implementation
plan's independent review and root source dispatch are still required. Neither
new bridge, factory, SQLite mode nor test adapter is implemented by this document.

## Purpose and preserved contracts

Replace the unguarded supplied-connection read attachment with the approved
permit boundary, retaining finite typed/materialized private repository reads.
`query_only` protects SQL operations but cannot prove absence of filesystem
creation. Ordinary read-only WAL connections can create sidecars or modify a
shared writable SHM node. Unknown provenance must fail before schema SQL.

Preserve the original M1-02 plan's 503-line prefix, storage r3/r4, insert-result
and mapping supplements. There is no schema migration, new output profile,
public capability, path opener or generic SQL/IPC API in this work. Correct
target facts, existing jobs and stopped generations are unchanged. This library
unit cannot certify M1-03 production launch/lock ownership or complete G1.

## Owned file scope

| File | Intended change after all design gates |
| --- | --- |
| `src/facet/db/read_views.py` | The r4 private mode/identity/runtime values, opaque permit/lease/seal identities, three factories and exact binding/consumption lifecycle; production compiled registries stay empty |
| `src/facet/db/connection.py` | Require permit before any read PRAGMA/schema query; retain it through the ReadSession lifetime; check before/after each bounded read and close SQLite before releasing lease |
| `tests/unit/test_db_read_views.py` | Real-file paired RV controls for the bridge; explicit production-unavailable and forged/missing/stale admission negatives |
| `tests/unit/db_view_adapter.py` | Test-owned fixed producer's six lifecycle and two audit methods, real locks/peer/inventory and bounded predetermined cases; imported only after the probe, outside the distributed package |
| `tests/unit/db_view_bootstrap.py` | Standalone fresh `-I -S` test entry: one initial latch/audit guard, one closed memory probe, fixed imports and final claim; no facet/SQLite import before latch installation |
| Existing `tests/unit/test_db_*.py` read consumers | Only necessary explicit test-adapter updates, preserving existing assertions and actual typed query/fault coverage |
| This plan and approved no-create supplement | Exact reviewed design integration and execution appendix; no retrospective rewrite of earlier evidence |

The M1-03 launcher, root traversal, provider implementation, socket/peer/pidfd,
bootstrap audit guard, runtime qualification registration and owner/view lock
operations remain their respective owner's reviewed source scope. Do not add
them implicitly to M1-02 or modify CLI/config/auth/status/public DTOs here.

## Required closed inputs before source

1. Independent review must approve this aligned implementation plan, followed
   by root source dispatch. The approved r4 sequence is the only design input;
   earlier prefix approval alone did not approve the appended construction.
2. Follow the r4 latch/probe/claim sequence below, not a preload check after the
   authorized probe. Do not infer freshness from `sys.modules` or issue a
   production seal in the pytest writer process.
3. Existing test consumers must use the r4 split below without weakening actual
   live, same-inode, lifecycle or fault assertions. No fabricated permit makes
   their current same-process writer plus ordinary reader eligible.
4. Real runtime identity/paired controls must determine live qualification.
   Unknown runtime/URI/VFS/process origin refuses; no version-only allowlist,
   ignored flag, test-only permit or local diagnostic becomes production proof.

Production registration starts empty. Missing actual registered M1-03 producer
means controlled owner-unavailable before schema access. There is no environment,
config or public registration option, and no bare-attachment compatibility route.

## Exact r4 inventory and ownership

Use only `ViewMode` (stopped_clean/live_wal), `FileIdentity` (nonnegative exact
device/inode/uid/mode) and the newly allocated `ReadRuntimeIdentity`. The latter
contains the exact Python/SQLite version triples, bounded safe ASCII source ID,
sorted compile-options SHA256, Linux architecture/platform and unix VFS. Probe
and compare actual values; a caller-created matching value is not provenance.

The opaque objects have precisely the r3 retained slots and safe fixed repr, no dictionary,
serialization or public constructors. Enroll their actual object identities in
private registries; copied slots or `object.__new__` never establish admission.
Only these three private factories are added:

```text
_issue_read_seal(provider: object, runtime: ReadRuntimeIdentity) -> ReadProcessSeal
_issue_read_lease(seal: ReadProcessSeal, mode: ViewMode) -> ReadViewLease
_bind_read_view(connection: sqlite3.Connection, expected_instance: LocalId,
                lease: ReadViewLease, seal: ReadProcessSeal) -> ReadViewPermit
```

Production `_PROVIDER_TYPES=()` and `_QUALIFIED_RUNTIMES=()` remain empty. Reject
before touching an unknown provider's attributes or SQLite. A later reviewed
M1-03 implementation, not this unit, supplies the exact compiled class and
runtime inventory. Invoke only the registered class's six fixed lifecycle
methods: `_check_bootstrap`, `_acquire_lease`, `_check_lease`, `_claim_connection`,
`_closed_connection`, `_release_lease`. Do not use instance-assigned callables,
duck typing, subclass acceptance, config import strings or an extension loader.

Acquisition validates the exact tuple of mode-appropriate file identities before
enrolling an active lease. Binding verifies enrolled identity/creator/lifecycle,
then claims only the producer's fresh inventory connection. Attachment consumes
bound to attached once before SQL. ReadSession owns that attached permit through
close. Failed acquisition unwinds provider-owned partial resources; rejection
of a foreign unclaimed connection never adopts it. Close SQLite first, confirm
inventory retirement, then release the lease; uncertain close invalidates the
entire seal instead of asserting that a writable SHM node disappeared.

## Exact isolated test-bootstrap sequence

The test-only standalone entry follows r4's two stages. It is not an additional
production module or generic bootstrap framework; M1-03 owns that real entry.

1. A fresh `-I -S` exec with `close_fds=True` calls the test-private
   `_begin_read_bootstrap` before importing SQLite, facet or the provider. It
   enrolls one latch in its fixed audit-hook closure, with exactly r4's finite
   fields/phases, rejecting preloads and duplicate initiation at this point.
2. Its fixed `probe_runtime` admits one `:memory:` connection on the creator
   thread, runs only `SELECT sqlite_source_id()` and `PRAGMA compile_options`,
   collects actual version/architecture facts and confirms close before probed.
   No state path, extra memory connection, caller facts or retry is admitted.
3. Only now add the fixed reviewed test package locations and import read_views
   and the fixed test provider. The audit guard still refuses import-time opens.
   Build the exact runtime value, including r3's compile-options digest encoding,
   and use only the test qualification established by actual paired controls.
4. Call the unchanged `_issue_read_seal`. Its fixed provider bootstrap check
   consumes `latch.claim(provider, runtime)` once, checking enrolled identity,
   creator and retained actual facts. Do not reject the permitted SQLite import
   again. Failed allocation after claim terminates/invalidate; no reissue.
5. The claimed hook routes only the two SQLite audit events to the fixed class
   methods `_audit_connect` and `_audit_handle`. No state open until the provider
   owns its enrolled final seal and live lease with exact opening inventory.

The M1-02 bridge never implements the production latch/audit driver, consumes a
config boolean as freshness, or imports a fabricated working M1-03 provider.
Test-stage failures retain fixed errors and permanently invalidate that child;
no clearing modules, registry resets or inherited handles can recover provenance.

## Implementation order after dispatch

First implement the closed opaque bridge and refusal-before-SQL controls. Then
integrate permit consumption and ReadSession invalidation/resource order. Only
then update explicit test consumers and run the real stopped/live paired matrix.
Freeze a coherent source slice for independent review before adding other work.

Exact connection/PID/thread/instance/provider identity, one-use attach, lease
activity and process provenance are required checks, not caller assertions.
Reject fabricated, copied, reused, closed, foreign-thread or inherited objects
without reading custom properties/repr. A failure discards materialized results
and closes resources it owns; an unregistered caller connection is not adopted.
Use only connection-local defenses after admission. Never set journal mode,
checkpoint, repair, mkdir, create locks, remove sidecars or retry in a weaker mode.

## Explicit test-consumer migration

The test-only provider and bootstrap are not shipped, imported by production or
selected by environment/config. Only the isolated test process temporarily
replaces the two private compiled constants with its fixed class and a runtime
justified by real paired behavior. Its methods hold actual OS resources/audit
inventory; they are not `None`-returning capability mocks.

Classify each existing read test before adapting it. Pure closed-row/query
materialization assertions can use a synthetic metadata snapshot made by the
real SQLite backup API after the tested commit. The fresh isolated child checks
its ownership, schema and absence of sidecars, executes the actual stopped
permit/read path and predetermined assertions. It proves that snapshot's facts,
not source live visibility. Never copy only the main DB or change a test that
relies on observing concurrent/current source changes into this arrangement.

Live-WAL visibility, concurrent writers, instance/lifecycle, locking and sidecar
assertions use separate real writer and sealed reader processes on the same
inode. Preserve original paired controls and bounds; child inputs/results are
bounded synthetic test data, not a new product SQL/row IPC. Wrong context/type/
closed/foreign-thread and caught-read-fault tests still execute the actual read
method in its genuine context. Do not satisfy them by only testing a proxy.

Record which assertions remain snapshot-only and which are live-process evidence.
If an existing assertion cannot be preserved with this finite arrangement,
report it before changing the assertion or adding a different test protocol.

## Verification and honest closure

RV-01 through RV-10 remain the supplement's acceptance IDs; no reduced substitute
matrix is introduced. Test directory names/inodes/sizes/bytes and actual SQLite
results together. Include the ordinary-ro and same-process writable-SHM detecting
controls, real stopped ownership with immutable only for its held lifetime,
separate live writer with committed WAL data, missing/unsafe/replaced entries,
owner death and ordered close, forged permit/seal and full inventory lifetime.
Fault tests must prove refusal before first SQL and no false/partial result.
Add r4's real order controls: the legitimate one-probe sequence succeeds; direct
connect/Connection before admission, preloaded SQLite/provider, duplicate or
file-path probe, altered facts, forged/reused latch, import-time open and extra
post-probe memory connection refuse. No test disables the actual admission hook
to make a previously used connection pass. Inspect the built wheel for absence
of the test entry/provider and confirm ordinary shipped imports leave both
compiled inventories empty without bootstrap side effects.

Current finite getters, list limits/keyset ordering, close/thread restrictions,
privacy fixed errors and caught-failure rollback tests remain mandatory. Real
DB/WAL/journal/file sentinels complement logical rows. No private source state,
provider responses, credentials, external network or Gmail fixtures are used.

Run the exact candidate's full regression, both CLI help entries, locked lint/
format, whitespace and staged safety checks on the task CPython 3.12.13 runtime;
require actual 3.12/3.13 CI lanes. Preserve user author and committer noreply and
atomic `type: action summary` subjects. Normal branch pushes/Draft PR15 are the
only publication in scope; merge still needs root's qualified dispatch.

Report separately: bridge implemented/test-producer verified; actual registered
M1-03 provider absent; managed reads unavailable; RV-11/runtime/G1 pending. A
synthetic permit or isolated test producer cannot close the latter gates. Full
M1-02 still needs its original DB-01..28 matrix and remaining action/migration/
restore work, not merely a green bridge slice.

## Stop conditions

Stop source work for unallocated factory/registration/connection ownership,
test-consumer semantic drift, new provider/IPC/API requirements, missing runtime
qualification, or a no-create counterexample. Submit the finite evidence and
missing interface to root/design review. Never fix a failing filesystem gate by
weakening its assertion, masking sidecar changes or using immutable on a live DB.

## Finite consumer execution appendix r4 (review required before adaptation)

This appendix preserves the approved 215-line r3 prefix. Base is
`eb7dde4ff33c349b3a5e7270c5ac480a292f425b`: the first real isolated producer tests
are committed, but their independent acceptance is separate from this proposed
consumer adaptation. No production API, schema or registration changes here.

The existing parent pytest process owns a writer and cannot be a qualified
reader. Its `view(state)` helper will capture only committed synthetic metadata
with the actual SQLite backup API from the explicitly supplied current writer
connection. Use a separate owner-only temporary root, private fixed lock files,
and a closed pristine destination with no sidecars. Never copy the main DB,
implicitly reopen a retired writer, or create a reader in the writer process.
Tests retaining an old state tuple after explicit reopen will pass the actual
reopened connection/session/info instead. A capture fails with an open source
transaction; it does not silently exclude a test's uncommitted assumptions.

`view(state)` now yields an explicitly test-only SnapshotProbe, NOT ReadSession
or a substitute accepted by production functions. Each named method launches a
fresh fixed `-I -S` child on that same captured snapshot. It executes one actual
production getter under a genuine stopped permit and ReadSession, checks the
actual connection has no writes/open transaction, closes SQLite/inventory/lease,
then returns a bounded synthetic materialization for parent assertions. Parent
object/type/closed checks do not count as production-context evidence. Calls
change explicitly to the test probe's methods; no monkeypatch of production
reads, weakened `_context`, fake `_connection`, or masquerading session exists.

### Closed case inventory and transport

The fixed entry/provider files and the existing `test_db_repositories.py` helper
contain the entire test transport. No additional product or test framework,
import loader, arbitrary SQL callback, arbitrary table/model selector, pickle,
dynamic `getattr` dispatch or configurable URI is introduced. Exactly these
case IDs map directly to the named existing production function:

| Case IDs / exact getter | Typed input after instance/projection | Exact permitted result |
| --- | --- | --- |
| `row_projection` / get_projection | none | ProjectionRow or None |
| `schema` / inspect_schema | none | SchemaMetadataRow and tuple of SchemaMigrationRow |
| `row_binding` / get_binding | Role | BindingRow or None |
| `row_binding_revision` / get_binding_revision | Role, Revision | BindingRevisionRow or None |
| `row_rule`, `row_epoch`, `row_event`, `row_job`, `row_attempt`, `row_action` / corresponding get_* | LocalId | RuleRow, EpochRow, SourceEventRow, SyncJobRow, InsertAttemptRow, ActionCommandRow respectively, or None |
| `row_thread`, `row_mapping` / get_thread, get_mapping | ProviderId | TrackedThreadRow, MessageMappingRow respectively, or None |
| `row_thread_target` / get_thread_target | source ProviderId, target ProviderId | ThreadTargetRow or None |
| `row_thread_anchor` / get_thread_anchor | source ProviderId | ThreadTargetRow or None |
| `row_checkpoint` / get_checkpoint | none | HistoryCheckpointRow or None |
| `row_history_poll` / get_history_poll | poll LocalId | HistoryPollRow or None |
| `row_history_page` / get_history_page | poll LocalId, Count ordinal | HistoryPageRow or None |
| `page_jobs`, `page_attempts`, `page_events`, `page_audit` / list_jobs, list_attempts, list_events, list_audit | PageLimit, bounded cursor bytes or None | ReadPage of its one registered row family |
| `counts` / counts | epoch LocalId or None | CountsSnapshot with closed JobStateCount tuple |

Transport has one exact case, expected-instance LocalId and projection plus only
that case's fixed scalar selector fields. Reject surplus fields, wrong primitive
types and unknown case before touching a provider. Request JSON is at most 32768
UTF-8 bytes: an 8192-byte cursor needs 16384 hex characters plus its envelope.
IDs retain their actual core bounds, ordinal/limit use real Count/PageLimit
guards and valid cursors are at most 8192 bytes. Response
is at most 2 MiB, page count at most 500, and schema ledger at most 500. Bounded
primitive cells use the existing registered `_encode_row`/`_decode_row` only for
the result family fixed by the case; a returned model/table name never selects a
codec. Bytes use bounded exact hex cells. Counts use explicit fixed fields and
all closed JobState values, not arbitrary dictionaries. Output is synthetic test
metadata only, never a product export/IPC or actual private account data.

None and fixed StorageFailure codes have distinct envelopes; no exception
traceback/SQL/path/provider payload is returned. A typed invalid-input result
must come from the actual child production call, not its parent facade. Page
keyset/cross-family tests retain their cursor values and production rejection.
Parent round-trip materialization equality is serialization evidence only;
independent child assertions below establish SQL/lifetime/guard evidence.

### Original assertion preservation and fixed physical cases

Pure committed-row equality, missing/foreign projection, unique counts, epoch/
job/attempt/event/mapping state and keyset ordering stay in their current tests,
with actual getters executed in the child. These are explicitly snapshot-content
assertions, not proof of live source visibility. Writer fault injection, rollback,
SIGKILL, History lost acknowledgments and reopen retain their original real
writer operations; only their later committed inspection uses this capture.

The following case IDs execute assertions IN the actual isolated child, not on
SnapshotProbe; parameters are limited to their fixed synthetic IDs/variants:

- `guard_history_types`: all existing Trap view/projection/poll/ordinal variants
  and Count(0), actual get_history_poll/page, foreign properties never evaluated.
- `guard_history_lifetime`: actual foreign Thread get_poll/page failures, same
  creator remains usable, then actual ReadSession close and both getters refuse.
  Existing wrong-UoW tests remain actual writer-context calls in the parent.
- `guard_thread_reads`: preserve mappings' actual get_thread_target calls with
  naked source/target strings, get_thread_anchor on a foreign Thread, creator's
  subsequent valid read and missing-projection None, then actual closed-view
  get_thread_target refusal. Preserve the original parent get_thread_anchor on
  a real UoW refusal with `_failed` still false; no SnapshotProbe pre-rejection
  counts as any of these named production guards.
- `guard_binding_role`: preserve repositories' get_binding(actual ReadSession,
  projection, naked "source") fixed INVALID_INPUT. The child passes that plain
  string directly, not Role("source"); afterward the same creator's typed Role
  read remains valid. Parent schema/count/equality assertions stay unchanged.
- `read_zero_write`: actual getter reads preserve total_changes and end each
  transaction; preserve history projection/missing/zero-write assertions.
- `keyset_501`: actual two pages (500+1), tuple ordering, cursors, no retained
  transaction/cursor, query_only=1; retain original expected-job equality.
- `guard_read_cursor`: actual production list functions reject the fixed empty,
  malformed/unregistered, wrong-family/projection and 8193-byte cases. Construct
  the latter in the child, not a facade rejection or oversized transport. Keep
  existing pure codec boundary tests unchanged; normal generated frames (four
  components, projection <=64 ASCII characters) are far smaller than 8192 bytes.
- `read_step_fault`: actual second/third SQLite row-step failure caught with
  rollback, fixed error and subsequent valid read; no proxy error substitution.
- `read_attach_failure`: actual accepted permit then schema/instance/SQL failure
  closes SQLite before retirement/release; foreign unaccepted handle untouched.
- `snapshot_reject_read_source`: actual ReadSession and its already admitted
  exact SQLite handle passed to snapshot_database. The exact-WriterSession source
  guard short-circuits before destination/alias/pristine checks; assert fixed
  INVALID_INPUT, zero SQL trace and original reader remains usable. No second
  SQLite open violates the audit inventory. Keep the old parent's pristine
  destination unchanged, but do not claim that as the child's guard proof.
- `live_schema_revision`: original schema read test moves to separate writer and
  sealed reader on the SAME inode; actual `_read` sees revision 0 then writer's
  committed 1, rejects UPDATE, no creation/reader file mutation, releases short
  snapshots. Reader assertions and controlled writer handshakes remain bounded.

Real live tests additionally retain all RV owner-death, final writer-close/view
EX exclusion, missing/replaced sidecars, dirty ordinary-ro provenance and paired
qualified readers. A stopped snapshot cannot replace any of these conditions.
Trace/index/fault checks needing real reader handles run fixed child assertions,
not parent-provided SQL. If another original live/connection assertion appears
during adaptation, stop and extend this explicit inventory before changing it.

Independent review of this appendix is required before consumer modification.
Final affected source review must compare the original assertions with their
actual child execution, full regression and exact 3.12/3.13 CI. RV-11/genuine
M1-03 provider and managed CLI remain unavailable; this arrangement certifies
only the finite library/test-producer boundary.
