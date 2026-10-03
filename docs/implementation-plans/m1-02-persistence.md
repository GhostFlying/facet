# M1-02 metadata persistence, migrations, and repositories

Date: 2026-10-02. Revision: r1, plan-only candidate.

Status: drafted for independent review. No SQL, production source or test
implementation is authorized by this draft. This is not a schema freeze.
M1-01 executable types and completed P1-02, including its mandatory CT tests,
are still implementation prerequisites. A suitable local Python/SQLite runtime
is also unresolved. G0 and the P1-01 design freeze do not satisfy these gates.

## Assignment, evidence and readiness

- Package: M1-02; [Issue #9](https://github.com/GhostFlying/facet/issues/9),
  parent [Epic #1](https://github.com/GhostFlying/facet/issues/1).
- Planning author: delegated `phase1_plan_review`, temporarily acting as author,
  not reviewer. A different independent Astra high reviewer must review this
  plan, its schema extension and later implementation. The coordinator assigns
  the implementation owner; this author cannot independently approve that unit.
- Owned worktree: sibling `../facet-worktrees/m1-02-persistence`; branch
  `docs/m1-02-persistence-plan`. Current writable scope is this file only.
- Exact starting HEAD, local origin/main and fresh remote main:
  `09031e723af1ef6590dc6746744ee52894501e38`. The worktree was created by normal
  `git worktree add` after confirming the target did not exist. No ignored state
  was copied and no other worktree was edited.
- Correct existing Git identity was verified: user account and its authorized
  GitHub noreply email. No configuration change, commit, push or PR in this step.
- P1-01 `p1-core-v1` and `p1-writer-v1` are independently approved and integrated
  at this base. Core hash:
  `795f80ab672ed4e0130eafc330bc0403981360f2e70bf935579973065c64f2f6`;
  writer hash:
  `5f0e5af9cc238f7967a88590fb53acc91c4697ffa27d19773cc66cf5ccc41368`.
- M1-01 approved plan r3 hash:
  `feeabe53d454c931da343964aa7d0a923508d86d3710a03e7c69dc413d534101`.
  P1-02 approved plan r3 hash:
  `000e7c079108edceaa50b902d421e06b2e99cf333dd4b86d3f36bab5827512e9`.
  These are plans, not merged executable dependencies or passing CT evidence.

Repository instructions and ordered product/project/Gmail/Dashboard/CLI/execution/
workflow documents, the package card, progress ledger and both frozen ADRs were
read. The two current owned prerequisite plans were inspected at those hashes.
Some tracked status prose is an earlier handoff snapshot; actual dependency SHAs
and reviews determine readiness. Existing tracked code has only `facet_spike`,
not production SQLite repositories. No ignored runtime files or Gmail were read.

| Gate | Current state | Required release evidence |
| --- | --- | --- |
| Plan preparation | Authorized | This file and bounded Issue tracking only |
| P1-01 design input | Integrated | Exact versions/hashes above; further drift reviewed |
| M1-01 types/package | Implementation pending | Independently reviewed merged commit, accepted exports/constructors and Python floor |
| P1-02 test foundations | Implementation pending | Reviewed merged foundation plus CT-01..04 actually passing against that M1-01 commit; provider-only partial output is insufficient |
| Local DB test runtime | Unresolved | Python >=3.12 with working sqlite3, selected SQLite compatibility/security evidence and real file-backed tests |
| Storage extension | Not authored/frozen | After independent plan approval, exact field/SQL/repository extension written and independently reviewed before SQL/source coding |
| M1-02 implementation | Not ready | All above inputs aligned on actual base, renewed plan review if material drift, explicit coordinator dispatch |
| Production ownership/CLI | Later M1-03/M1-06 | Real process/view locks, bootstrap receipts and CLI integration; no bypass in M1-02 |

## Deliverable and scope

Deliver metadata-only schema v1, a deliberate initialization/migration library,
bounded read repositories and typed transactional writes for the core persistence
invariants. Real disk-backed SQLite tests must establish rollback, replay and
privacy at named boundaries. M1-02 does not implement Gmail calls, admission policy,
worker scheduling, HTTP, command transport, OAuth or full backup/restore CLI.

The plan first commissions the M1-02-owned storage extension. Its proposed file is
`docs/implementation-plans/adrs/persistence-schema-v1.md`; this file does not exist
yet and is not authorized for editing in the current plan-only dispatch. The
extension must close every SQL field/type/nullability/key/check/FK/index and every
enabled repository operation before its source is implemented. P1-01's deferred
storage layouts are requirements, not permission to guess executable records.

| Future owned file family | Responsibility / exclusion |
| --- | --- |
| This plan and proposed storage ADR | Reviewed scope, exact schema/API extension, fault/owner matrix and handoff |
| `src/facet/db/__init__.py`, `connection.py`, `transactions.py` | Private connection/session and short transaction library, explicit mode/version checks; not process locks or a standalone daemon |
| `src/facet/db/schema.py`, `migrations/__init__.py`, `migrations/v0001.py` | Exact DDL manifest, schema inspection, ordered migration registry and initialization; no generic execute-user-SQL API |
| `src/facet/db/models.py`, `codecs.py`, `keys.py` | Storage-only immutable records, closed field codecs and versioned stable-key encoding, importing M1-01 values |
| `src/facet/db/repositories/` | Projection/binding metadata, rules/tracking, events/checkpoints/epochs, jobs/claims, intents/mappings and typed audit repositories |
| `src/facet/db/migration_backup.py` | Internal SQLite backup primitive and prerequisite receipt interface; not full credential bundle ownership or M6 backup CLI |
| `tests/unit/test_db_*.py`, `tests/integration/test_db_offline_*.py` | Real temporary SQLite, faults, process restart, metadata privacy and compatibility tests; offline only |

No changes to shared AGENTS/README/status/ledger, frozen P1-01 ADRs, M1-01/P1-02
plans, `tests/fakes/`, root conftest, existing spike tests, CI or dependencies are
currently assigned. Use P1-02's published helpers through imports and request
helper additions from its owner. Shared documentation changes are handed to the
integration/docs owner. A runtime/dependency or scope change requires a reviewed
plan amendment before editing outside this inventory.

## Storage extension: required concrete design output

Select standard-library `sqlite3`, no ORM, no alternative business-state model.
The extension owns SQL serialization, not new public `facet.contracts` exports.
It consumes the exact M1-01 primitives/enums/closed values, including required
nullable fields and tags. All proposed table families below must have an explicit
enabled-now versus reserved-for-reviewed-extension classification; empty generic
payload columns are not an acceptable way to defer a design.

For every enabled table, the ADR supplies an exact column matrix: SQL type,
Python value/codec, required/nullability/default, bounded length/range, PK/FK,
unique and CHECK constraints, immutable versus mutable fields, privacy class,
producer/consumer, and transaction methods. Every nullable composite FK must be
all-null or all-present; SQLite null semantics must not silently defeat uniqueness
or reference validation. Polymorphic references use discriminator-specific columns
and constraints or normalized child tables, never an unvalidated JSON blob.

### Proposed table families and necessary relationships

| Family | Required stored facts and key/relationship design to close |
| --- | --- |
| Schema identity and migration ledger | Facet application identifier, schema version, exact migration checksum/version, completion time; reject unrelated SQLite and ledger/schema disagreements |
| Projections | One Phase-1 projection; projection ID, state-instance ID, request namespace, config revision, binding/restore state, durable daemon pause, last owner run; namespaces never silently reused after restore |
| Bindings and scope metadata | Composite projection+role key; declared/verified account identity, binding/credential revisions, expected mode and typed scope entries, last verified time; source differs from target, no tokens or OAuth responses |
| Rules and immutable revisions | Rule ID, projection, closed kind, private normalized value, enabled, effective_at, origin, policy version and revision; current identity uniqueness plus immutable historical revision rows |
| Rule-set snapshots | Projection+snapshot revision and explicit member rule ID+revision references; retained disabled/deleted revisions preserve historical epoch/admission meaning, not destructive current-list replacement |
| Tracked threads and admissions | Projection+source-thread key; active flag, generation, admitted/stopped timestamps and closed reason; exact AdmissionRef variant columns with rule/epoch/preview/action provenance |
| Epochs, decisions and partitions | Epoch ID+projection; closed kind/state; fixed UTC start/end/cutoff, EpochDecisionRef, durable H0/H1 and catch-up boundary, discovery_complete, nullable known total, operational counts; child PartitionProgress keyed by immutable PartitionRef |
| Source events and processing | Stable SourceEventKey columns, observed time, nullable thread context, consumed/resolution state; immutable identity, idempotent context enrichment and explicit contradiction outcome |
| History checkpoint and poll progress | Projection cursor as TEXT, reliable coverage timestamp, poll ID/start cursor/revision, next page hint and page progress; page completion is not final cursor completion |
| Jobs and claims | Job ID+projection, JobKind+exact JobSubject, versioned stable identity, priority/state/revision/counts/times/error, optional epoch/command refs; claims carry exact owner-run/job-revision/generation/phase |
| Insert attempts and factual results | Attempt ID, source IDs, binding revision, generation, job/claim, prepare/dispatch/result times, digest+version/date policy, optional RFC ID/anchor, independent state/certainty/verification facts, controlled result/error and recovery schedule |
| Mappings, mapping history and target ownership | One current verified mapping per projection+source-message; explicit immutable verified-history rows and attempt references, target message/thread ownership, visibility and last existence audit; repair preserves former verified facts |
| Thread target set | Projection+source-thread+target-thread key, anchor flag and creation provenance; at most one chosen anchor, actual fallback target threads retained |
| Action commands | Projection+History-record+label+source-thread unique activation, action ID/kind, business execution marker and independent cleanup state; original event links, no learned per-message header copies |
| Audit events and controlled errors | Local ID, projection, time, closed action/object/reason, typed state/revision before/after, command/job refs and normalized ErrorCode/Class/role/count/times; no exception/message/general diff dictionary |
| Aggregate metric buckets | Projection, metric enum/window/unit, bucket timestamps, count/sample count/sums or explicitly versioned histogram representation; no raw message times or private object references in public outputs |

Bindings/scopes are metadata only. M1-04 owns live profile/scope verification and
credential representation; SQL recording cannot turn a declared value into a
verified credential. The extension must define supported scope codes with M1-04
before enabling scope writes, rather than accepting arbitrary provider strings.

The storage extension may reserve no table at all for an unfrozen feature instead
of installing speculative columns. Feature-owner changes then use reviewed,
versioned migrations. This cannot remove required Phase-1 persistence: the ADR
must name the exact deferred owner/release gate and preserve an end-to-end route
for every family above. Core events/jobs/epochs/rules/tracking/intents/mappings
and their required audit/metadata constraints cannot be deferred merely to make
M1-02 small. Table aliases to canonical names in the Gmail spec must be explicit.

### Command/preview and policy ownership boundary

M1-03 owns the full command/payload/preview/wire registry and canonical payload
digest. M1-02 must not create `payload TEXT` and claim that later validation will
make it safe. The storage ADR defines transaction composition and typed receipt
metadata insertion requirements; M1-03 later supplies its reviewed closed storage
extension and enables payload tables. Until then no production command acceptance
or request replay interface is advertised by M1-02.

Where core rows reference a not-yet-enabled operation/preview, define the required
same-projection invariant and reject production creation until the target registry
is integrated; do not treat an arbitrary UUID as an authorization capability.
Synthetic storage tests can seed exactly typed provenance fixtures in their own
temporary DB. Fixture reachability is not permission for production handlers to
skip scope, auth, rule or generation guards.

Similarly M1-06/M3 own rule normalization/auth evidence; M2-02 owns fidelity
digest semantics; M2-04 owns recovered attribution/risk policy; M4 owns History
and scan control; M5 owns learning. Repositories store validated decisions and
enforce structural/transaction preconditions, not invent these algorithms.
Before those extensions exist, unsupported evidence variants are refused, unknown
auth/attribution stays review/attention, and missing policy never becomes pass.

## Stable keys, indexes and replay

The schema ADR must give exact column predicates and versioned length-prefixed
encoding vectors for these keys. Store source components and validate equality;
a hash is not the only evidence. Use bound parameters and allowlisted query
shapes. No key contains raw mail, a provider page token, an exception or a guessed
numeric History sequence. Repeated keys with incompatible immutable facts are
conflicts, not `INSERT OR REPLACE` or silent `ON CONFLICT DO NOTHING` success.

| Job/event | Stable identity and required replay behavior |
| --- | --- |
| Source event | Full tagged SourceEventKey; label/change distinguish activations; duplicate generic provider messages are not additional typed events |
| project_message | projection, kind, source message, generation; current verified mapping or unresolved dispatched attempt blocks a new ordinary insert |
| repair_message | projection, kind, repair operation, source message, generation; authorized repair is distinct from retry and retains mapping history |
| expand_thread | projection, kind, source thread, epoch, generation |
| resolve_event | projection, kind, exact SourceEventKey; one enrichment job, original activation identity survives |
| operation_read | projection, kind, operation ID; immutable read-kind must agree, first-response loss reuses operation and job |
| recover_insert | projection, kind, original attempt ID; all concurrent checks join one job and one claim, no new insert attempt |
| scan_discovery/scan_gap/reconcile_source/audit_target | projection, kind, epoch, exact PartitionRef; page/count progress never changes identity |
| cleanup_action | projection, kind, action-command ID; replay cannot repeat rule/admission effects |

Every child relation uses projection-aware FKs, including IDs that are globally
generated. Index runnable jobs by projection/state/next-time/priority with stable
ID tie-breaking; index pending attempts by source message and thread; index event
processing and epoch partitions without sorting History IDs numerically. Define
bounded keyset pagination, not full-table private row exports. Work fairness and
queue priority policy remain M2-03 rather than SQL ordering becoming a scheduler.

At most one unresolved dispatched attempt per projection+source-message has a
partial unique constraint whose exact state/certainty predicate is independently
reviewed. Two prepared claims must also be prevented from dispatching the same
message. Cross-message thread serialization is the runtime lane's responsibility,
with DB claim/revision/generation CAS guards as the final metadata check.

## Connection, filesystem and ownership design

Write-side SQLite configuration is explicit and verified on each connection:
WAL, foreign_keys ON, synchronous FULL, bounded busy timeout, and a supported
SQLite version. Prefer STRICT tables plus explicit semantic CHECKs; STRICT alone
does not reject every coercion or validate a tagged union. Python constructors
validate before SQL; SQL independently protects nullability, enums, relationships,
uniqueness and numeric bounds. Only metadata enters bound parameters.

Use explicit short BEGIN IMMEDIATE/COMMIT/ROLLBACK transaction control, selected
and tested against Python >=3.12 sqlite3 autocommit semantics. Set connection
options deliberately, not version-dependent defaults. Transaction composition is
owned by a unit-of-work boundary; repositories do not secretly commit. Nested
transactions either use reviewed savepoints or are refused, never commit a caller's
partial operation. No executescript implicit-commit surprise in migrations.

M1-03 owns process/view/credential locks and production connection opening under
those locks. M1-02 is a library over explicitly supplied sessions, with no CLI,
automatic state-directory discovery, daemon startup or public unlocked open/create
shortcut. Its schema ADR must specify the checked owner-session integration
interface with M1-03 before coding. Missing production ownership provider refuses
before touching DB/config/WAL, not a boolean skip-lock fallback. Tests use an
explicitly test-owned connection to a new private temporary database and exercise
library operations; they do not constitute an alternate production owner protocol.

A writer session is thread-affine and bound to owner-run/session lifecycle; workers
cannot acquire independent writes. Connection teardown invalidates sessions. An
internal Python session object is not proof of an OS lock: M1-03 integration and
subprocess competition tests establish that separately. No production adapter is
enabled until that provider exists; this avoids a M1-02/M1-03 dependency cycle
without exempting runtime writes from the reviewed ownership requirement.

Read sessions consume the M1-03 view provider. They never create state, perform
write PRAGMAs, migrate, checkpoint, repair permissions or refresh tokens. SQLite
WAL read-only opens may require existing readable sidecars; the extension must
prove the chosen open path has no hidden file creation/checkpoint or refuse with
a controlled diagnostic. Never use `immutable=1` on a live-changing DB just to
bypass WAL coordination. Stopped crash recovery remains a lock-owning operation.
For multi-file config/credential/DB inspection, revision consistency belongs to
the common provider; do not infer coherence from a SQLite snapshot alone.

File creation by the future owner path is exclusive, no-follow, owner-only, with
stable directory identity checks. DB/WAL/SHM/journal/backup paths must remain within
the selected private local filesystem. Existing unsafe/unrelated files are refused,
not chmodded, overwritten or treated as empty. SQLite cannot safely replace the
writer ADR's lock anchor. Never unlink sidecars manually or change journal mode
to bypass readers. No filesystem evidence is inferred from a pathname alone.

The writer connection alone performs automatic/passive checkpoints; do not add a
second background checkpoint connection. Bound read transaction lifetime and DB
batches so readers do not cause unbounded WAL growth. BUSY is a bounded outcome,
not an unbounded sleep or permission to replay a remote effect. Capacity/backpressure
retains durable jobs and forbids cursor advance on failed persistence.

## Atomic repository boundaries and forbidden continuations

These are planned library methods/transactions, not a production authorization API.
The exact signatures and closed input/output records belong in the storage ADR.
Do not accept arbitrary callbacks that perform network work inside a transaction;
fault hooks are explicit test injection points and never production plugin hooks.

| Boundary | Facts committed together | Failure/replay rule |
| --- | --- | --- |
| Initialize new DB | Identity/version, one projection, pending bindings, immutable initial rules snapshot and initialization marker | Only explicit M1-03 bootstrap owner/key; existing DB never silently recreated/imported from spike |
| Record rule mutation | New immutable revision, current pointer/ruleset revision, effective_at, audit and command effect marker when its registry exists | Replay preserves chosen effective time; removing allow/blacklist does not implicitly stop/re-track |
| Admit or explicitly re-track | AdmissionRef, active generation, provenance, selected jobs and audit under valid caller scope | Existing active admission dedupes; re-track increments generation, cannot recopy already mapped messages |
| Stop/blacklist selected thread | Exact sender rule when requested, inactive flag, incremented generation, cancellation of unstarted work, audit/effect marker | Same operation cannot increment twice; dispatched attempts remain factual work, other threads/domain untouched |
| Ingest History page | Typed events, deduped resolution/derived jobs or durable unresolved-event work, processing/page marker | Failure retains old cursor; no selected event silently marked consumed |
| Finish History poll | Final-page durable work plus final cursor/coverage and poll completion | Requires matching start-cursor/poll revision, successful complete page chain; empty successful poll still updates coverage |
| Start fixed epoch | Explicit decision/window/ruleset, durable H0 or H1, initial partition state | No scan before commit; unknown gap lacks allowed decision until reviewed range approval exists |
| Advance scan | Discovered work and partition progress/counts | Lost/expired page hint may rescan same fixed epoch; dedupe, not new cutoff or authorization |
| Claim job | Eligible state/time, expected revision/generation, owner-run/claim fields | CAS loser has no work; elapsed lease time never steals a live owner or authorizes insert |
| Prepare intent | Valid claim/current generation, immutable attempt facts, prepared certainty/state | No raw; preparing is not dispatch or proof of remote effect |
| Mark dispatch entry | Rechecked claim/binding/pause/generation plus durable dispatch-start marker | Called at writer actor's actual invocation-entry gate; failed commit forbids provider call; no network in transaction |
| Record remote result | Known target facts or unknown/definite-not-inserted state, attempt/error, required recovery scheduling | Result remains recordable after stop; unknown cannot become ordinary queued insert |
| Verify mapping | Reviewed evidence/fidelity result, target ownership, mapping/history/thread set, job completion and unique-success basis | Known inserted but unverified is not success; failed readback never re-inserts; conflict stays attention |
| Execute action | Activation dedupe, business marker, applicable rule/tracking/jobs/audit | Cleanup independent and after durable business effect; legacy snapshots cannot fabricate activation |
| Commit audit finding | Typed target-missing/visibility/ambiguity metadata and audit progress | No automatic repair/delete/adopt; repair selection/evidence is a later owner contract |

Rule effective times, fixed epoch boundaries and generation/revision compare-and-set
are tested together. Wall-clock rollback must not move an accepted rule's stored
effective_at or a prior epoch window on replay; temporal admission logic stays with
M3. Source raw unavailable and no recoverable target becomes source_missing only
after any unknown attempted effect has been retained for recovery/attention.

The transaction API separates attempt-result recording from scheduling permissions.
An in-flight insert result arriving after stop cannot revive its generation, but
cannot be silently dropped. Stale owner-run/claim/attempt mismatches produce a
controlled consistency/attention result with durable known facts where safely
attributable. A prepared-but-unsent job loses the stop race and stays cancelled.
The runtime proves gate ordering; the repository proves each transaction's guards.

A command-local effect must be composed with M1-03's typed receipt/effect marker
in the same unit of work once registered. Do not implement a generic SQL command
inbox in advance. Receipt absence after restore is not not-received proof: store
state instance/namespace/restore fence, preserve historical receipt references,
and refuse a new projection/repair release on restored uncertainty until M2-04's
reviewed policy supplies the applicable decision. Binding verification alone
never clears restore revalidation.

## Initialization, migration, backup and rollback

Initialization is a separate exclusive API, not fallback from failed open. Only
the future M1-03 bootstrap owner creates the path/namespace and calls it with a
stable request. M1-02 handles transactional DB creation/version metadata and
repeat inspection of the exact initialized instance. Restart at partial bootstrap
requires its original receipt/checksums, not replacement of the existing file.
No config, token or existing spike cursor/mapping is imported implicitly.

The storage ADR selects an application ID and ordered checksummed migration
registry; it must distinguish not-initialized, unrelated database, current,
supported-old, unsupported-new, corrupt and interrupted-migration states. A
known schema version with divergent catalog/checksum is not a healthy current DB.
Opening for read inspection must not repair or run migrations. Parameterized data
queries never accept user SQL; trusted migration statements are fixed source code.

Before modifying an existing schema, require a verified backup receipt from the
coordinated owner: DB snapshot via SQLite backup API and coherent config/binding/
credentials, schema/instance/namespace/revision metadata, completed manifest and
private permissions. M1-02 supplies only the DB snapshot primitive and hook
contract. Until a full bundle provider is integrated, existing-state migration
returns maintenance_required; no callback returning True or DB-only copy can
pretend to satisfy the production bundle gate. Test-only backup hooks use synthetic
private bundles and must have explicit failure controls. Full M6 CLI stays later.

Create backup destinations exclusively, refuse overwrite, use SQLite's supported
backup API rather than copying only facet.db, close/check integrity and foreign
keys, flush completed metadata before reporting success. The source is unchanged
when backup fails. Never checkpoint or delete WAL merely to make a naive copy work.
The future provider owns credential locking and all manifest/atomic publication
semantics; the snapshot helper receives no token bytes and does not log paths.

Apply supported DDL/data/version/ledger changes in one explicit transaction where
SQLite supports that boundary. A deliberate failure before commit leaves the
old catalog/data/version; failure with uncertain commit is inspected on reopen,
not blindly rerun. Do not place VACUUM, file replacement or external configuration
changes inside a claimed atomic SQL transaction. Such migrations require the
writer ADR's staged-bundle journal and M6 reviewed maintenance path.

No arbitrary legacy v0 schema is accepted as production input just to test a
migration. Tests may define a clearly test-only predecessor and exercise the
migration engine; production registry accepts only explicitly supported Facet
versions/checksums. Unknown higher versions refuse downgrade. Rollback uses old
image plus complete compatible backup when no reverse migration is implemented;
neither an empty DB nor a blind schema-version decrement is recovery.

On restore integration, rotate request namespace/owner-run, preserve bindings,
paused/stopped generations, pending jobs and unknown attempts, mark binding pending
and restore revalidation. Post-backup remote effects may have no row at all; no
repository list/search absence grants duplicate insert or implicit full rebuild.
M6 owns actual multi-file install/restart rollback; M1-02 tests the DB fence/state
transitions and hook requirements, not a completed restore product.

## Privacy and storage validation

All persistent inputs use closed typed records and fixed codecs. Reject unregistered
fields/variants before executing any statement; validation exceptions never print
values, SQL parameters, provider messages or paths. Bounded text has a semantic
type (ID, private rule/account, version, code), not a generic error/detail/notes
column. Full headers, per-message addresses/subject, raw/MIME/body/attachments,
credentials and arbitrary provider JSON cannot enter any row, journal, log or
runtime cache through error/audit/event payloads.

Parameter binding prevents SQL injection, not content leakage: field-source review
and P1-02 sentinels are both required. Do not enable sqlite trace callbacks or
dump rows on failing assertions. Exception mapping uses numeric/controlled SQLite
classification internally, not str(exception) in production logs. Rejected
content is not first written and then deleted; WAL/journal bytes are inspected
while active and after failure/checkpoint/close. No raw .eml fixture is written.

Allow necessary account/rule values/IDs in their explicit private metadata tables;
test that allowed data survives. The same values are forbidden in public DTOs,
but public serialization belongs to M1-05/M4, not a raw-row export here. DB
snapshots/backups are owner-only test artifacts, never uploaded as CI artifacts.
Aggregate query outputs use a separate typed internal result shape; they are not
automatically public-safe. Count unique confirmed source mappings, not attempts
or target mailbox size; retain null/unknown totals and sample counts.

## Required acceptance matrix

All cases use P1-02 helpers plus real temporary SQLite files where durability or
constraints are claimed. Test-only fixtures do not stand in for production locks,
AUTH/attribution or full CLI operation. No skipped missing dependency counts as
pass. The storage ADR maps each case to exact tables/methods/hook labels.

| ID | Counterexample / actual required assertion |
| --- | --- |
| DB-01 | Python >=3.12 imports sqlite3; record runtime version/compile options; required features and selected compatibility policy actually work |
| DB-02 | Exact DDL/catalog/ledger identity, all tables/columns/keys/FKs/CHECKs match reviewed manifest; arbitrary unknown DB/schema refused |
| DB-03 | Initialize twice/reopen; wrong projection/role/same-account/spike DB refuses; interrupted bootstrap never replaces an existing database |
| DB-04 | Every closed row codec rejects wrong enum/tag/type, extra fields, invalid nullability/bounds and forbidden payload; safe fixed error output |
| DB-05 | FK cross-projection and nullable-composite misuse fail; rule revision/snapshot and immutable reference integrity survives current-rule changes |
| DB-06 | All 11 JobKinds key vectors; repeated event/operation/attempt/epoch identities dedupe, incompatible thread/read-kind conflicts, distinct repairs remain possible |
| DB-07 | Repeated activation and first-response replay compose one local effect/audit; no generic untyped command payload accepted before M1-03 extension |
| DB-08 | Allow removal leaves tracking; exact blacklist stops only selected thread; stop/re-track generations increment once per effect and never overflow/reuse |
| DB-09 | Two competing claims/CAS updates produce one winner; stale revision/run/generation refused; lease expiry cannot authorize another insert |
| DB-10 | Stop before dispatch cancels unsent work; dispatch marker before stop retains eventual result but cannot re-enable scheduling; actor integration explicitly pending |
| DB-11 | Crash before/after intent/dispatch/result commit; one unresolved attempt constraint, unknown remains recovery; known inserted readback failure does not queue reinsert |
| DB-12 | Mapping/target ownership/verified count commit together; repair retains history; different sources cannot silently share target ownership; Spam/Trash remains distinct |
| DB-13 | History page one commits then page two fails/restarts; old cursor retained, stable events/jobs replay, no duplicate business work; empty final poll records coverage |
| DB-14 | H0/H1 commit fails: no scan permission; successful fence retains fixed window/ruleset; rescan tokens cannot change epoch identity |
| DB-15 | Unknown gap lacks approved range; restore/reconcile/new rule cannot widen historical admission or revive stopped generation through repository APIs |
| DB-16 | Required rule effective_at and immutable revision persist over replay/clock rollback; no rule reload or snapshot rewrite changes accepted scope |
| DB-17 | Inject statement/commit/disk-full/BUSY/rollback failure; no successful receipt/cursor promise, ambiguous persistence closes session for inspection, jobs remain explainable |
| DB-18 | Kill child process at actual SQLite transaction boundaries and reopen independent connection; durable committed rows persist and uncommitted rows do not become success; not merely raised exceptions |
| DB-19 | Backup API includes committed WAL state; source preserved on failure; incomplete/wrong-instance/unsupported backup receipt blocks migration |
| DB-20 | Migration statement/version failures roll back; rerun is idempotent, future/damaged schema refuses, no fallback empty DB or invented production v0 |
| DB-21 | Read-only inspection never creates state/sidecars/checkpoints/migrates; unavailable unsafe WAL-read setup reports controlled failure, not immutable-live fallback |
| DB-22 | Wrong-thread/closed/missing-owner session and absent M1-03 provider refuse production opening; no skip-lock flag or parallel checkpoint writer |
| DB-23 | Restore older metadata preserves paused/stopped/jobs and rotates namespace/fences; absent post-backup receipt/attempt cannot be false non-effect proof |
| DB-24 | Classified content sentinels absent from logical rows, live DB/WAL/journal/temp files/logs/errors/backup; allowed IDs/rules/bindings survive; negative controls actually detect leaks |
| DB-25 | Unique success/job-state/epoch counts exclude attempts/duplicates, remain mutually exclusive, distinguish unknown total/zero samples/partial failures |
| DB-26 | Fault callback at simulated network boundary observes no open DB transaction; future M2/CLI owners repeat with real subject-under-test transport hooks |
| DB-27 | Bounded page/batch/read lifetimes and query-plan checks; BUSY/checkpoint starvation controlled without lost work or unbounded raw/private result allocation |
| DB-28 | Exact-candidate full offline regression, both CLI help entries if available, locked dependency/format/lint/safety and required CI lanes; no Gmail credentials or network fixtures |

Process-kill tests use test-owned child PIDs and private temporary roots only,
with bounded timeouts and cleanup; never signal other worktrees/daemons. Real
power-loss/fsync guarantees remain filesystem/deployment evidence, not claimed
from SIGKILL alone. Ordinary low-level SQL tests may verify constraints directly;
repository behavior tests must call the actual typed repositories.

## Environment prerequisite and upstream checks

Read-only checks on 2026-10-02 found the installed Python 3.13.5 interpreter lacks
`_sqlite3`: importing sqlite3 raises ModuleNotFoundError. System Python 3.11.2 has
SQLite 3.40.1, but is below the production Python floor. The installed-runtime
listing also showed PyPy 3.9 but no usable Python 3.12 alternative. No interpreter,
library or system package was installed or rebuilt, and no DB test has been run
for this plan.

Before implementation, the coordinator must obtain a verified compatible
engineering environment. During this plan handoff the coordinator separately
dispatched the QA owner to prepare an official managed CPython 3.12 in a private
sibling task-tools directory; actual download/import/SQLite results remain pending
and this plan author performs no installation. The selected approach is a build
downloaded by the delegated engineering owner with uv into an explicitly selected
private task-tools directory, without changing system Python, global Git settings
or a production host. This ordinary tool preparation does not require a new user
product decision; the coordinator dispatches it separately. A runtime/dependency
amendment is needed if the remedy changes tracked build or delivery files. Record
real imports, linked SQLite version/compile options and file-backed WAL checks:
downloading Python alone does not prove its bundled SQLite is patched.
Do not silently use 3.11, fake sqlite3, delete WAL tests or claim
CI covers local checks that never ran. CI can provide separate actual evidence,
but pending CI is neither pass nor failure.

Current SQLite documentation reports a WAL-reset race affecting versions 3.7.0
through 3.51.2, fixed in 3.51.3+ and named backports 3.44.6/3.50.7. It concerns
multiple connections racing writes/checkpoints on the same WAL database; being
one process is not itself sufficient protection. The readiness review must record
the actual linked library and select a verified patched runtime for production
delivery, or explicitly review a documented engineering mitigation/version path;
do not silently add a binary sqlite dependency or infer the fix from Python's
version. The single writer/checkpoint connection is an invariant, not a claim that
every shipped SQLite build is patched. Upstream details must be rechecked when
choosing the implementation/image environment.

Primary references checked read-only, not Facet test evidence:

- [SQLite WAL](https://www.sqlite.org/wal.html): local filesystem, sidecar/read-only
  conditions, checkpoint ownership and current WAL-reset advisory.
- [SQLite PRAGMAs](https://www.sqlite.org/pragma.html): verify connection settings
  and durability rather than assuming defaults.
- [SQLite STRICT tables](https://www.sqlite.org/stricttables.html) and
  [foreign keys](https://www.sqlite.org/foreignkeys.html): structural checks need
  semantic validation and deliberate connection configuration.
- [SQLite backup API](https://www.sqlite.org/backup.html): DB snapshot primitive,
  not atomic credential/config bundle backup.
- [Python 3.12 sqlite3](https://docs.python.org/3.12/library/sqlite3.html): explicit
  transaction control, backup and version interfaces; prove behavior on the
  selected interpreter and linked library.

## Sequence, authority and stop gates

1. Save this plan and exact hash/base; independent reviewer is not this author.
   Current Issue remains plan_drafting/plan_review, not ready or implementing.
2. On separate dispatch after plan approval, author only the full storage ADR
   with exact field/SQL/repository signatures and DB-01..28 mapping. Obtain
   independent design review; do not implement an unreviewed SQL layout.
3. Wait for actual merged M1-01 and completed merged P1-02+CT, resolve runtime
   prerequisite, carry base only on coordinator dispatch, align exact exports/
   helper APIs and record final input SHAs. Material changes require plan review.
4. Only after these gates and implementation dispatch, build coherent atomic
   units: schema/codecs/constraints; migration/backup prerequisites; typed
   repositories and transaction tests; fault/privacy/restart evidence. Each
   change includes its tests, not one large unchecked schema/feature commit.
5. Run locked supported-Python install, Ruff lint/format, targeted DB tests,
   complete pytest, available production/spike help and repository safety.
   Record exact interpreter/SQLite versions, commands, counts and limitations.
6. Before authorized commit/push, review only owned staged paths, whitespace,
   safety and both author/committer noreply. Use atomic English subjects such as
   `feat: impl metadata schema constraints` or `test: verify cursor rollback`.
7. Independent implementation/acceptance review and exact-candidate CI precede
   integration. Hand actual schema/API/evidence revisions and remaining runtime
   integration gates to the delegated docs owner, M1-03/04/05 and later owners.

Stop for dependency/interface drift, concurrent ownership changes, an unclosed
SQL/payload variant, incompatible SQLite/runtime, unsafe filesystem/read-only
side effects, missing backup/owner provider, or any need to persist prohibited
content. Compatible design issues go to independent engineering review. Product,
privacy, authorization or scope changes go through root to the user; never weaken
unknown insert, cursor, generation, metadata or backup promises to release a gate.

This dispatch permits the owned plan, worktree and bounded Issue #9 only. No
commit/push/PR, SQL/source/test implementation, schema freeze, live Gmail/OAuth,
mailbox mutation, new scope, host deployment, image publication, release/license,
third-party contact or automation is included. No G1-G6 capability is claimed.

## Execution appendix: separately dispatched storage design

On 2026-10-02 the coordinator confirmed independent Astra review approval of the
original 503-line plan above (SHA-256
`abc9f87b813cb510205deab5e350c04ab5fa4a24498cceb43f44349125979e4f`)
and separately dispatched documentation-only storage ADR authorship. This appendix
does not alter that approved prefix or grant implementation authority.

The owned storage-proposal-r3 is
[`adrs/persistence-schema-v1.md`](adrs/persistence-schema-v1.md). Its author remains
ineligible to self-review. The coordinator's scope includes this appendix and the
ADR only; no source/SQL/test/CI/dependency/shared-file changes, commit, push or PR.
Actual M1-01 integration at b1e passed main CI 36980646059. Complete P1-02 CT
at `1b7cd58b4846aab86edcbb781a999abb968d047c` passed independent review, exact CI,
actual PR #12 integration and main CI 36982879970. Root verified these receipts
and authorized a normal fast-forward of this owned branch to 1b7, preserving the
two untracked documents. The original plan base is historical, not rewritten.
The task runtime owner supplied Python 3.12.13 / SQLite 3.53.1 with import and
memory query; actual database, WAL and storage acceptance tests are still planned.

Independent plan-review handoff refinements are carried into the draft: DB-07
separates M1-02 typed transactional replay from M1-03 receipt/IPC replay, without
invented receipt types or a circular prerequisite; DB-21 must prove read-only
no-sidecar creation and safe refusal when recovery is needed, not an immutable
live-database shortcut. This is a design handoff, not evidence those tests ran.

The proposed extension now has 32 exact table/row inventories, SQL scalar/branch/
foreign-key/index constraints, a versioned stable-key codec, finite repository
operations, transaction/intent transitions, migration/backup/restore boundaries
and DB-01..28 counterexamples. Command/credential/fidelity/public registries remain
explicit owner-reviewed extensions, not ghost payload columns. No product or
authority change is requested. Another independent reviewer must accept the exact
proposal before schema freeze or source implementation; root dispatch is still
required. This appendix records preparation, not storage acceptance or G1 closure.

R1 proposal received independent changes_requested. R2 adds closed initial-H0 /
ordinary / recovery-H1 poll origins, fixed persisted known-gap safety overlap,
generation-bound expansion runs/items and the unique owner-supplied pristine
initialization lifecycle. It coordinates retained bundle instance identity with
M1-04 while rotating request namespace/owner and preserving restore-effect fences.
The exact original 503-line approved plan remains unchanged. These changes and
their DB counterexamples require new independent design review before SQL coding.

## Execution appendix: approved r3 engineering dispatch

On 2026-10-02 independent reviewer `phase1_architecture_plan` approved storage
proposal r3, ADR SHA-256
`da2cfcd0081eaca8b102436186c9f5d034947fbf71ca2f0b95a14ee25840cfa0`
and this plan's pre-dispatch full SHA-256
`7c4dd9e0725f8832c0c691e0370067fd38cfef6aaf9b503e89727dc3aa32d552`.
The original 503-line approved prefix above remains unchanged. R3 closes the
initial-poll unresolved-gap guard and makes the epoch catch-up boundary derived
only from its actual completed History poll, never a caller-selected cursor.

The coordinator formally dispatched implementation to `phase1_plan_author` at
actual base `1b7cd58b4846aab86edcbb781a999abb968d047c`. The M1-01 foundation and
complete P1-02 compatibility dependencies are independently reviewed and merged;
that base passed the real 379-test offline suite and supported-Python CI. The
owned branch may become `feat/m1-02-persistence` without rewriting history. This
dispatch supersedes the historical plan-only authority statements above, not
their product, privacy, ownership or acceptance requirements.

Authorized changes are the scoped DB source and tests, these owned design files,
and the current-state/progress documents under this worker's sole shared-docs
ownership at a coherent engineering handoff. First preserve this reviewed design
in an atomic documentation commit; subsequent atomic code/test commits share one
focused Draft PR. Use the task-managed Python 3.12.13 / SQLite 3.53.1 in an
independent locked environment. Normal public dependency retrieval is permitted;
tests remain offline with respect to Gmail. No Gmail, credentials, deployment,
image publication, system changes or unrelated worktree writes are authorized.

Implementation is not storage acceptance. DB-01..28, whole-candidate independent
implementation/acceptance review and exact-head CI remain required before root
can delegate integration. Actual M1-03 ownership/view/receipt and M1-04 credential
providers remain deferred; typed library sessions do not prove production locks,
authorize mailbox effects or complete G1. Any material interface/approach drift
returns to independent design review before implementation of that change.

The first schema/session slice keeps ordinary `_attach_writer` lineage matching
strict. A fresh daemon's new owner-run publication is not allocated by storage
v1's finite API; the M1-03 design owner confirmed it as a subsequent reviewed
storage/session extension. Current tests use the same supplied test-owned lineage
and do not borrow a prior daemon identity or prove restart-owner publication.
This explicit consumer seam does not add an unreviewed setter/skip flag, block the
remaining storage-library implementation, or constitute production runtime proof.

The next library slice implements finite policy/job/audit operations and bounded
private reads, with closed row codecs. Synthetic test-only binding/origin fixtures
do not enable production OAuth, previews or command registries. Manual admission,
operation reads and repair enqueueing remain controlled-unavailable until their
owning reviewed providers exist. Source loss remains a failure category rather
than completed success; recovery-job retries are checks, not new insert attempts.
History page/epoch transitions, expansion proof, insert/mapping transactions,
backup/restore/migration and real process-crash gates remain pending in this
partial slice. No empty event consumption or caller-provided catch-up ID is enabled.

## Independently approved insert-result recording extension

The coordinator dispatched the independently approved result-recording amendment
on 2026-10-02: [exact finite supplement](adrs/insert-result-recording-amendment.md),
SHA-256 `2bf222b1819d80ddbed48387c8afd8fda5678db4b6425d1e89f396ea2687b427`.
Its design author was `phase1_plan_review`; independent design reviewer was
`phase1_architecture_plan`. The frozen storage r3 prefix and History r4 amendment
remain unchanged. This execution append does not rewrite their historical scope.

Implement only that supplement's result signature, full-row CAS/replay, explicit
observation time, original-job/claim disposition and finite recovery membership
rules. Actual IR-01..10 tests add to DB-10/11, not replace DB-01..28. Counters,
deadlines, same-state error patches, attribution evidence and scheduling policy
remain outside this supplement. Design approval is not source acceptance; a new
exact implementation candidate, independent acceptance review and CI are required.

## Independently approved first-map verification extension

The coordinator dispatched the independently approved finite
[mapping supplement](adrs/mapping-verification-amendment.md) on 2026-10-02,
SHA-256 `81b21b0f1c30d0799ea636acb59fdfc90d9920567e25e3abb5484347c38ec2d6`.
Design author `phase1_plan_review` and independent design reviewer
`phase1_architecture_plan` closed the direct-response normal/inserted-attention
completion, four-row provenance, two bounded private reads, visibility, time and
exact-replay seams. Original storage/result/History documents and the approved
503-line plan prefix remain unchanged.

Implement only its project-message first-map transaction and MV-01..12 real-file
tests. Unknown attribution, repair, missing fidelity facts, actual M2 readback
authority and runtime attention scheduling remain separate gates. Independent
exact-source acceptance plus CI is required; this document dispatch is not source,
Gmail, process-owner or whole M1-02 evidence. DB-21 no-create closure stays held.

## Independently approved guarded read-view library extension

The coordinator dispatched the finite DB-21 bridge on 2026-10-02 after
independent `phase1_architecture_plan` approval of the
[589-line design r4](adrs/read-view-no-create-amendment.md), SHA-256
`4f12b845e8fdd6662079a5df84a4da83e64a338f6f38143a615119f8b480a780`,
and [215-line implementation plan](m1-02-read-view-bridge.md), SHA-256
`17dfde9535d3fa4c9925eaa8970386bf928c04140cfa49de682bedf4d2cc6094`.
The source owner is `phase1_plan_author`; exact base is
`422ba9b8a845db60a587bda9e1946fd77269674f`. Preserve earlier frozen prefixes.

Implement only the private opaque bridge, guarded ReadSession and real isolated
test consumers/paired RV-01..10 controls. Production provider and qualified
runtime inventories remain empty; actual M1-03 bootstrap/OS lifecycle, RV-11,
managed CLI reads and G1 remain unavailable/pending. This library dispatch does
not certify source acceptance or complete M1-02; independent exact-source review
and both CI lanes remain required. No action/migration/restore policy is added.
