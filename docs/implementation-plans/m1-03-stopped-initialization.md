# M1-03 stopped first-initialization and owner-provenance plan

Date: 2026-10-03. Revision: proposed r3. Status: PLAN ONLY, NOT APPROVED.

## Dispatch, base and authority

This is a finite preparatory slice of M1-03, not a replacement for its complete
writer/runtime design, M1-02 acceptance, or G1. The root explicitly dispatched
this plan and its alignment ADR to `phase1_os_acceptance_sol` (Sol xhigh).
That author must not independently approve either this design or its source.
Only these two new documents are allocated in this dispatch. There is no coding,
staging, commit, push, PR, provider registration, Gmail/OAuth, or external action.
Shared status/progress/contracts, frozen input documents, and other worktrees
remain untouched.

The owned branch is `p/luchengxuan/m1-03-initialization-plan`; its exact base is
`a9c4e36de6ad70294002a83e678a2a7cf1b012d6`. This combined SQL/OS/harness candidate
has independent finite acceptance and dual-Python CI 37038807962, but is unmerged
at this dispatch. Its parents are accepted SQL `c0bb4b0` and main harness `befe278`.
That qualification does not approve any new schema, runtime producer or CLI.
Later accepted inputs require explicit normal carry and a newly frozen source
candidate; this plan does not guess their future commit SHAs.

The companion [alignment amendment](adrs/stopped-initialization-alignment.md)
contains necessary interface/version/staging changes. Both complete exact hashes
must receive independent non-author review before root can release any source.
Approval is not an automatic release, provider allowlist entry, or milestone gate.

## Required input artifacts and actual interfaces

The author read the complete ordered repository instructions and the following
complete references personally. Original bytes remain unchanged. Writer and read
artifacts currently live in their separately owned planning trees; naming them
here does not assert they are installed or tracked on this base.

| Frozen artifact | Lines | SHA-256 |
| --- | ---: | --- |
| `m1-03-writer-runtime.md` | 438 | `3934f2a4d6bc1cf0e0ebf4748cd1ed8be426cc7a04f785ca5d1641ed5beaa64c` |
| `writer-runtime-extension-v1.md` | 876 | `3b9dc3e637ba727589768f0055c746193809f7e0fcd07bc94839dd565a0110c8` |
| `read-view-runtime-integration.md` | 229 | `9d28e18cee3dbaed00c939838686a6b715cefb569c268a4f3e73a0d1cc6c660e` |
| `adrs/persistence-schema-v1.md` | 1228 | `3d9021511cb148dfa8b9543ac880d27d83c4f01940659da5fe373e802d74f433` |
| `adrs/core-state-contracts.md` | 614 | `795f80ab672ed4e0130eafc330bc0403981360f2e70bf935579973065c64f2f6` |
| `adrs/writer-command-protocol.md` | 475 | `5f0e5af9cc238f7967a88590fb53acc91c4697ffa27d19773cc66cf5ccc41368` |
| `docs/cli-spec.md` | 309 | `6215d7264403c4ce5fee722d57e74215f910f0298b3673bf67988a9513f022f3` |

Current concrete symbols, rather than hypothetical replacement APIs:

- `PrivatePaths.db` and `select_paths` select `facet.db`, not `metadata.db`.
  `facet.runtime` is an existing package, not a proposed `runtime.py` module.
- `Config`, `load_config`, and `initial_template(source_email, target_email, ...)`
  require two declared, distinct addresses. They do not verify Gmail accounts.
  `config_warnings` retains verification/state/rule warnings. No accountless
  template, alias inference, or source-mode/scope change is proposed.
- `open_existing_root`, `create_lock_root`, `check_root`, `close_root`, and the
  five lock operations retain actual opaque enrolled OS resources. A scaffold
  has no initialized-state authority. Its existing creation whitelist stays
  unchanged; use existing-root opening once bootstrap artifacts exist.
- `_initialize_database` currently installs exact v1 on a supplied pristine
  connection; `_attach_writer` requires the stored owner triple to match.
  `BootstrapInitContext` and `OwnerSessionInfo` are constructible metadata,
  not actual ownership or permission to open/create a DB.
- `_inspect` currently recognizes only the exact trusted v1 catalogue/ledger.
  `WriterSession._check_creator` retains PID and the strong Thread object;
  `UnitOfWork` checks creator/currentness before all lifecycle changes. The
  accepted R1/R2/R3 action and suppressed-error rollback fences remain required.
- `_PROVIDER_TYPES`, read runtime qualifications and maintenance providers are
  empty shipping authority, not slots for this plan to fill. The no-state read
  foundation is implementing, not accepted; it issues no read seal/lease/permit.
- `facet.cli.bootstrap.main` currently refuses init mutations. This finite
  producer does not enable those commands or implement operations CLI routes.

## Two separately gated source units

Source A is storage-local v2 creation/inspection and fresh-run publication.
It may be implemented only after both documents are independently approved,
the current migration-entry implementation is independently accepted, its exact
source/input CI is qualified, and root serially reallocates overlapping DB files.
The approved migration plan is not an accepted source prerequisite by itself.
Neither author edits the other's moving schema/connection/registry files.

Source B is the genuine private stopped filesystem bootstrap issuer consuming
accepted A plus accepted OS. It requires independent exact A source acceptance,
accepted migration carry, a frozen B base/plan, and a separate root dispatch.
Before any read foundation reuse, its actual source must likewise be independently
accepted with exact CI and normal carry; this plan does not accept that source.
B is a private library with installed subprocess acceptance, not shipping read
provider registration, daemon start, status/doctor availability, or complete CLI.
Public CLI activation needs a separate adapter plan and actual CLI gate.

Both source units receive independent plan/implementation/CI gates, atomic user
identity commits and later integration only through the root-owned workflow.
No implementation authority is conferred by the proposed file lists below.

### Proposed exclusive file allocation: A

| Path | Finite responsibility |
| --- | --- |
| `src/facet/db/command_records.py` (new) | Closed storage-local enums/records, RequestId, bootstrap seeds and bounded inspection result; core/stdlib only |
| `src/facet/db/command_store.py` (new) | Fixed bootstrap receipt decoding/reconciliation and initializer insert helpers; no general command executor |
| `src/facet/db/migrations/v0002.py` (new) | Fixed trusted command schema from the frozen extension; immutable compiled statements/checksum |
| `src/facet/db/migrations/__init__.py` | Exact version-specific fresh manifests for v1 and v2; no activation of existing-state migration steps |
| `src/facet/db/schema.py` | Exact version-dispatched inspection plus exact-v1 consumer barrier; no permissive catalogue/version acceptance |
| `src/facet/db/connection.py` | Separate v2 initializer/fresh owner/bounded inspection; exact-v1 barrier at `_attach_view`; retain ReadSession class, v1 and R3 guards |
| `src/facet/db/migration_backup.py` | Only exact-v1 source/destination barrier before native backup/destination mutation; keep truthful existing SchemaVersion1 result and all ownership checks |
| `tests/test_command_records.py` (new) | Exact type/tag/nullness/overflow/privacy controls |
| `tests/test_command_schema_v2.py` (new) | Exact manifests, trigger/DDL/FK tamper and old-v1 controls |
| `tests/test_command_bootstrap_storage.py` (new) | Atomic initializer and persisted-key reconciliation on real WAL files |
| `tests/test_command_owner_session.py` (new) | Real fresh-run CAS, lineage preservation, ambiguous commit and creator lifecycle |

No source A changes to core records, v0001, repositories/actions, transactions,
ReadSession/read_views, OS production bytes, migration execution/provider code,
models, dependencies, CI, CLI or shared docs. If accepted migration carry changes
these exact interfaces or A needs another file, amend/review allocation first.

### Proposed exclusive file allocation: B

| Path | Finite responsibility |
| --- | --- |
| `src/facet/commands/__init__.py` (new) | Empty passive package, no registration/import effects |
| `src/facet/commands/bootstrap_codec.py` (new) | Strict fixed journal/receipt codecs and canonical config/request digests |
| `src/facet/runtime/bootstrap_files.py` (new) | Fixed fd-relative private artifacts and controlled writer connection; actual resource enrollment/check/cleanup |
| `src/facet/runtime/stopped_initialization.py` (new) | Sole private stopped issuer, state machine, exact-key submit/lookup, closure ordering |
| `tests/test_bootstrap_codec.py` (new) | Closed codec/digest vectors and detecting privacy negatives |
| `tests/test_bootstrap_files.py` (new) | Actual filesystem/inode/open/durability/fault controls |
| `tests/test_stopped_initialization.py` (new) | Genuine owner/key/replay/config/DB/process scenarios |
| `tests/integration/test_installed_stopped_initialization.py` (new) | Noneditable-wheel child protocol, deadline/output/privacy/cleanup oracles |
| `tests/integration/stopped_initialization_child.py` (new) | Test-only bounded child fault driver, excluded from wheel |

B retains OS files and their public APIs byte-for-byte. The private file adapter
may inspect the accepted internal enrolled root/lease state under its existing
inventory mutex, after actual creator checks; it cannot enroll a forged handle,
export/duplicate FDs, add callbacks to OS APIs, or weaken physical-root ordering.
New nonempty artifact nodes have their own explicit policy, not the zero-length
stable-lock policy. Any need to change the OS foundation requires a prior finite
amendment and non-author review, not an improvised descriptor-export API.

## Source A: exact versioned storage seam

Keep `v0001.py` byte-for-byte SHA-256
`c4531c7fa27634aadcec1c00cb8b42fa6ba921e4e35febc2a643049934c25477`.
Keep the existing v1 initializer/signature/positive and rejecting tests. Compile
two exact immutable catalogue/ledger/registry-digest manifests, selected only by
actual application_id/user_version. Exact v1 remains v1; exact v2 includes v1
plus fixed v0002. Future, partial, mixed, extra/missing/altered SQL objects refuse.
Generic trusted inspection can recognize v2, but consumer support is explicit.
Add private `_inspect_v1` with an exact-v1 version barrier plus unchanged full v1
inspection; `_attach_view` and snapshot_database use that barrier, not generic
v2 recognition. ReadSession's class/lifetime and read_views remain unchanged.
Snapshot's source rejects v2 BEFORE native backup or any destination configuration/
mutation; destination remains exactv1 and its existing SchemaVersion1 receipt
stays truthful. v2 read/snapshot support requires another jointly allocated and
qualified consumer plan, not optimistic reuse of a now broader inspector.
Keep REGISTRY/CHECKSUMS/REGISTRY_DIGEST and migration's current v1 manifest unchanged;
use separately named fixed fresh-v2 registry/checksums/digest/manifests. Otherwise
the existing v1 initializer would accidentally write a mixed v1/v2 ledger.

v2 contains the five frozen tables `command_runtime`, `operations`,
`operation_controls`, `operation_bootstrap`, `operation_auth`, their fixed indexes
and binding-guard trigger. Exact fields/nullness/uniqueness/constraints come from
the 876-line extension, not user SQL/JSON/callbacks. Passive auth/control kinds
do not register their missing executors. The future genuine CredentialChange FK
and participant remain a jointly reviewed credential extension; no fake UUID,
dummy credential table or authentication capability is introduced now.

`_initialize_database_v2` has exactly the frozen extension signature. It requires
a supplied actual connection with autocommit=True, no open transaction, pristine
appid/version/catalogue, exact bootstrap/core rows and exact
`FreshCommandBootstrap`. All input/type/initial lineage checks precede schema
writes. Configure WAL/FULL/FK/trusted_schema/busy policy, then use ONE explicit
BEGIN IMMEDIATE transaction: install v1+v2, initial paused/pending projection and
two pending bindings, empty sealed ruleset0/null checkpoint, command_runtime
guard1/control0/current run/idle, current completed facet-init operation and
optional prior completed config-init import, both ledger checksums and version2.
There is no intermediate v1 commit or post-commit operation insertion. Commit,
fully validate, then attach the same connection. Any uncertain commit/attach
failure invalidates it and yields no success; the runtime owns confirmed closure.

Current operation ID and instance ID are durably planned by the original accepted
filesystem receipt BEFORE DB creation. An optional prior config operation ID is
allocated once before initialization, outside a transaction; its first durable
publication is the same commit. Original config archive retains its NULL SQL ID.
Lost acknowledgement inspects the original keys to recover committed identities;
it never allocates a replacement operation because the response was missing.
A genuinely pristine rollback permits only the same original journal's retry;
partial, unrelated, inconsistent or ambiguous state is refusal, never a reset.

The bounded `_inspect_bootstrap_v2` addition is specified in the alignment ADR.
It validates exact schema/settings/one projection and materializes at most two
original-key operation/payload pairs and current lineage in a short read snapshot.
It is not a new ReadSession, read provider, raw row getter or authority issuer.
It exists to reconcile committed initialization before attaching a fresh writer.

`_begin_owner_session_v2` has exactly the frozen signature. Full schema/settings,
instance/namespace and projection/runtime previous-run equality precede BEGIN.
The real holder supplies a fresh different run; one CAS transaction updates
ONLY projection.last_owner_run_id and command_runtime.owner_run_id. Then ordinary
same-connection attachment validates that lineage. Claims, operation receipts,
shutdown provenance, pause, stop generations, binding/restore/unknown fences and
namespace remain unchanged. Failure/ambiguous acknowledgement closes/invalidate;
no retry, old-run borrowing, or dataclass-based production caller is allowed.
This source does not implement daemon recovery/dispatch or clear old shutdowns.

## Source B: genuine stopped issuer and stable-key protocol

Only its fixed factory can allocate an opaque `StoppedBootstrapOwner`; direct
construction/subclass/copy/pickle fails. It is strongly enrolled while live with
actual PID, retained Thread object, root and ownerEX/viewEX leases, fixed artifact
FD identities, connection identity, current key and exact lifecycle phase.
Metadata returned to callers is not that authority. All methods check creator
before SQL, poison, cleanup or any inventory mutation, including after invalidation.
Integer thread IDs, booleans, arbitrary providers, externally supplied connections,
FD tuples, subclasses and root/scaffold existence cannot enroll it.

Private entry names are `submit_stopped_bootstrap` and `lookup_stopped_bootstrap`.
They receive only the closed request/explicit selectors defined in the ADR; caller
callbacks, factories, supplied sessions/leases and arbitrary paths beyond the
explicit validated selectors are forbidden. They allocate/use/retire one owner
locally and return typed bootstrap data, not a lease/session/native FD. No public
factory registry, read seal, issuer allowlist or handler registration is added.

Require original stable rq1 key and explicit confirmation before filesystem
changes; non-TTY mutation must already supply both. Never generate a new key on
timeout/unknown response. Canonical digest v1 includes the closed typed Config,
command/projection/expected0 guards/yes=true/duplicate-risk=false. It excludes
nonce/times/output flags. Store digests/typed phases, not configuration values or
credentials in journals/receipts/SQL payloads. Config content has only its approved
private config file and in-memory request home. Nonempty rule lists refuse before
artifacts until actual M1-06 normalizer input is independently integrated.

Existing complete roots use `open_existing_root`; new explicit creation uses only
`create_lock_root`. Unexpected preexisting config/DB/bootstrap content cannot be
adopted through scaffold creation. Acquire owner EX nonblocking, then view EX,
then the exact key EX under that same root/view. No SH-to-EX upgrade, recursive
SH, hidden wait or second writer. Key failure releases dependent resources in
order before returning; no IPC or owner wait while client holds key/view SH.
The whole bootstrap is finite stopped ownership, never a background daemon.

Before new acceptance, validate current active and matching completed archives.
Write/fsync client journal, then durable accepted BootstrapReceipt with fixed
instance/current operation identities for facet-init. A different unresolved
key conflicts. Same key/digest resumes or returns its original receipt; different
payload conflicts. A prior completed config-init may precede a separate facet-init
only with the same namespace/projection/config semantic+artifact digests.

New config uses exact serialized bytes, exclusive0600 staging, file fsync,
no-overwrite atomic final publication and directory fsync. Never truncate/chmod
or replace existing config. Explicit selected owner-only external config is a
facet-init input, not discovery/adoption; hold/check its FD identity through the
read and compare exact artifact+semantic digests before creating DB. Config-init
refuses existing config without its own matching original receipt. DB-init never
normalizes or rewrites the selected existing config bytes.

Before SQLite, validate no-follow private root/name/type/UID0600/single-link and
exclusive new `facet.db` ownership; no arbitrary SQLite URI/options, empty-state
fallback or memory DB. The fixed writer opener must bind the actual newly opened
connection/files to the retained root/expected DB inode BEFORE configuration or
initialization SQL, then revalidate at critical boundaries. Real path/inode/FD
replacement tests must detect the attempted violation before SQL effects escape
the owned tree. Mere before/after path strings or `PRAGMA database_list` are not
physical resource proof. If the selected SQLite/VFS cannot establish that seam
without a new native VFS, descriptor-proxy filename or audit/provenance strategy,
STOP for a prior finite opener amendment; do not invent a fallback. Qualification
is actual local tested runtime/filesystem only, not all Linux mounts or SQLite
builds. The proposed opener's proof is writer-local, not read-runtime sealing.

Use A's v2 initializer only on this actual pristine owned file under the matching
accepted journal. Existing v1 returns maintenance_required; unrelated existing v2,
partial DB, wrong instance/key/digest or unexpected artifacts refuse unchanged.
After committed original-key inspection, reconciliation may attach a genuine
fresh owner through A's CAS, never reuse stored previous run as lock authority.
It performs no dispatch, claim cleanup, recovery authorization or provider work.

Phases are accepted -> config_created -> db_created -> completed for facet-init;
config-init omits db_created. Record each only after actual preceding durability.
After SQL commit, verify exact schema2/instance and committed current/prior keys.
Confirm connection/session close while owner/view remain held BEFORE publishing
completed archive/active completion or returning success. WAL-dependent state is
not a main-file-only receipt: inspect the committed real DB, synchronize the owned
artifact set/directory as applicable, retain any required sidecars, never delete
them or claim a physical power-loss guarantee from SIGKILL/fsync tests.

Archive completed receipt exclusively and durably before active-pointer reuse.
Recover only the frozen permitted same-key active/archive phase/time pairs; exact
immutable fields and code=None must agree. Never overwrite malformed archives.
A kill after config fsync/SQL commit but before phase update requires original-key
reconciliation of exact known artifacts, not re-execution or a new namespace.
Foreign-root, partial/truncated/changed receipt or uncertain close/fsync results
produce a fixed refusal/attention and no completed success.

Close order is creator-check -> finish/rollback owned SQL -> confirmed connection
close -> owned artifact descriptors -> key -> view -> owner -> root. Connection
close that cannot be confirmed MUST NOT release view/owner or free live enrollment;
invalidate, report fixed failure, retain strong resources until confirmed closure
or actual process death. Do not retry an uncertain raw descriptor integer. Explicit
terminal-only retirement may use weak tombstones without value-to-key retention;
no GC/finalizer/atexit unlock. Old/stale handles cannot retire a current owner.
Fork child closes only its own verified copied descriptor inventory, without
LOCK_UN or inherited SQLite API calls, marks local enrollment unusable and keeps
inherited native connection quarantined against destructor-driven reuse. B does
not qualify a continuing forked writer/worker; tests exit their own child promptly.
If complete actual SQLite descriptor closure cannot be established, this is a
source stop gate, not permission to weaken the approved no-inheritance contract.

## Exact lookup and deliberate unavailable surfaces

Lookup never creates a missing root/requests directory, lock or receipt. It takes
genuine stopped ownerEX/viewEX and existing key lock where journal inspection
requires it; busy is unknown, not proof of no effect. Before DB creation it may
return the actual typed active/archived BootstrapReceiptData. After initialization
SQL and retained receipt facts must agree. A missing SQL row alone is not absence.
Authoritative absence requires current namespace, complete healthy exact journals
and known stopped artifacts; unsupported/uncertain state returns unavailable.
Any response-loss replay retains key/payload and returns original identities.

No general operations listing CLI, daemon control/auth/UDS/actor/pidfd/lifetime,
worker capability, raw session/SQL access, credentials, backup/migration/restore
provider, managed read registration, status/doctor healthy or Gmail action consumer
is delivered. Full operations lookup/listing and CLI wiring remain future exact
plans. Installed private submit/lookup tests are evidence of this issuer only.

## Finite acceptance: actual resources and detecting controls

All rows are proposed, NOT executed evidence. Each negative is paired with a
legitimate positive and must detect its named cause, not merely a generic error.

| Case | Actual evidence and mandatory counterexample |
| --- | --- |
| SI01 | Exact original hashes/old test ASTs and base manifests; all retained a9c 1625 tests, accepted migration/no-state carries measured separately; v1 normal attach/inspect succeeds, altered/extra/future/mixed v1/v2 rejects without permissive inspector |
| SI02 | Real local WAL v2 initialization: one commit includes v1/v2 ledger, paused/pending roles, empty ruleset/checkpoint and original-key receipts; faults at every SQL/COMMIT/attach boundary, suppressed error/ROLLBACK and reopen distinguish pristine/committed/partial with no replacement or false completion; genuine v1 WAL snapshots retain correct version/rows, while v2 rejects before native backup/destination settings/files change; exact-v1 read attach remains positive and v2 admission refuses with correct owned cleanup |
| SI03 | Actual CAS under two real processes and kernel owner locks, including crash-after-publication; fresh different run updates both rows once, stale/equal/mixed previous run refuses; preserve byte/value facts for claims, intents, shutdown provenance, stop/pause/restore/namespace and all receipts |
| SI04 | Strict full-field digests/codecs/seed validation and field-by-field privacy; duplicate/unknown JSON keys, malformed rq1 IDs, bool-as-count, wrong guards/tag/nullness/overflow/surplus/content inputs refuse before effects; same digest vector including defaults succeeds |
| SI05 | Real ownerEX->viewEX->keyEX with competing processes/physical-root aliases and creator lifecycle; forged/dataclass/copied/foreignThread/recycled-ident/fork handles refuse before poison/SQL/cleanup; real holder remains BUSY until owned close/process exit; stale cleanup cannot retire current owner |
| SI06 | Genuine no-follow root/ancestor/config/DB/WAL/receipt identities; symlink/hardlink/FIFO/wrong UID/mode/root/path/lock/FD replacement and EEXIST races with paired expected artifact; invalid cases leave other inode/tree untouched; no chmod/truncate/unlink lock or destructive reset |
| SI07 | Original-key response loss before/after accepted, config fsync, SQL commit, db_created and completed/archive publication; reopen exact identities, recover prior-config SQL ID, archive promotion obeys allowed pairs, changed key/digest/namespace/receipt refuses; no operation or business-effect duplication |
| SI08 | Named bounded own-child SIGKILL/fork phases and actual close/fsync/rename/open/allocation failures, including uncertain connection close; parent proves kernel/FD holder retention and eventual process-death release; no finalizer/foreign cleanup, untracked child, indefinite pipe/thread wait, or claimed power-loss proof |
| SI09 | Empty-rule pending-binding first init/config-only with both distinct declared addresses; explicit config bytes preserved; invalid/missing/same addresses and nonempty unqualified rules refuse before DB/artifact creation; no OAuth/profile inference, credential/read provider activation, H0/backfill/network/target mutations |
| SI10 | Fresh noneditable wheel installed in isolated child with exact source byte manifest/static assets and no test helpers; fixed private submit/lookup/import zero-effect controls, bounded deadline/output, all old CLI/help/safety/ruff checks and exact dual-Python CI checkout/tree provenance; no whole M1/G1 or usable CLI claim |

Use fresh owned test roots under a verified safe local ancestor; `/tmp` sticky or
wrong-owner `/data00` is not a positive anchor. Record actual Python/SQLite/source
ID/compile options/mount and actual process phases. The known development runner
is CPython3.12.13/SQLite3.53.1 with locked uv0.12.2; future CI runtimes are measured,
not assumed qualified from this note. Original three real SQL R3 counterexamples
and OS physical-root/thread/kernel harness pairs remain regression requirements.

Installed child launcher uses fixed entry/arguments and sanitized environment,
no PYTHONPATH/CWD helper imports, installed provenance verification, capped output
and common deadlines. Default maximum is 15 seconds per fault child and 60 seconds
per whole controlled scenario including cleanup; parent owns exact children,
terminates/kills only them and finally reaps all started children. Bounds may be
revised only by written detecting evidence, not rerun-until-green/skip/fake IDs.

Sentinel scans cover actual config-designated content versus prohibited DB/WAL/
rollback/temp/journal/archive/log/exception/stdout/stderr and wheel artifacts.
Synthetic config-address values are permitted only in config/binding storage;
raw/mail/body/subject/header/credential/provider/path sentinels must never enter
receipt/error/public output. Include deliberate leaking scanners' positive
controls, including exception context/cause and caller-already-except cases.
Use sealed fixed error codes/constant repr, never native exception text/trace.

## Stop gates and handoff

Stop before source on failed independent plan review, missing actual prerequisite
acceptance/CI/base, file overlap, unresolved SQLite opener/fork closure, or any
necessary new API/format/schema strategy. Amend first, review independently, then
root may release a finite source unit. Existing-v1 upgrade requires the genuine
complete coordinated backup/credential provider and maintenance journal; empty
registries/dataclasses cannot satisfy it. Do not add v2 to an existing-state
migration execution registry solely because fresh initialization supports it.

Stop and ask root for user direction on material product/privacy/authority changes,
including content storage, accountless configuration, nonempty unqualified rules,
scope expansion or destructive recovery. No empty-DB reset, force binding, spike
adoption, namespace refresh to escape uncertainty, or implicit upgrade exists.

Handoff each future source candidate with exact plan/ADR/base/HEAD/parents/file
scope, measured retained/new tests and faults, full/lint/format/CLI/wheel/privacy/
safety outputs, fresh CI checkout/tree identity, user+noreply author AND committer,
independent non-author verdict and unresolved gates. No private runtime files are
published. The source author cannot self-approve, merge or activate another unit.
Real initialized provenance would unblock planning of qualified stopped reads;
it would not by itself satisfy RI/RV, LIVE, credentials/full bundle, migration/
restore/daemon/complete CLI/Compose/Gmail or any milestone gate.

R3 author correction supersedes the unapproved r1 c83280a5.../90dce735... and r2
3abe6f46.../ebcf56b7... freezes. Every actual inspector/version consumer has an
explicit policy in the ADR: v1 registries stay unchanged, only jointly allocated
writer seams accept v2, and unqualified read/snapshot/migration consumers refuse.
No code/original artifact changed; the snapshot barrier and attachment allocation
need non-author review/root release like every other source A change.

## Factual Source A implementation release

Date: 2026-10-03 PRC. The original 390-line plan above remains unchanged at
SHA-256 `7f3086e3622907288297912c3e50e3ebca98d0c8ae8b065e0692c53f69e57c1a`.
The unchanged 372-line alignment ADR remains at
`cb18c2e0f350ffd1d0e512ebe3c0a7bfb09ea54c1ac3b7785ed1e06a7f841faf`.
Their independent nonauthor PLAN approval is the 151-line report SHA-256
`84cb2a086d4ce381884e4e901efd77ef74035981884ab7be702f1d644cac4cd5`.

Root explicitly released ONLY Source A to `m103_os_source` (Sol xhigh), after
personally reading those exact artifacts and the qualified combined input:
`d6888df7f16abb63e400675a8accfd8ba4a96bd5`,
tree `8f653c421241cf075b49ace91b49a2eee4a6c234`.
The new sole-owned branch is `p/luchengxuan/m1-03-bootstrap-storage`, based
exactly on that immutable input. Its independent 172-line combined SOURCE report
is `04ced096cd2713af89f64930063bb4ae341cd689d95239bd32538e055cbb7c46`;
both CI 37065104441 lanes succeeded on actual checkout
`cdeb2682167b13c5d3245e60ad1f767f0e9ee7bb`, whose tree equals that input.
The measured retained baseline is 1810, not the earlier 1625 or 1739 counts.

This factual receipt changes no approved API, strategy, table, or allocation:
only the seven DB files, four NEW test files, this plan and its exact ADR copy.
No concurrent restore/DB owner is allocated. The v1 migration target/registries,
read_views and literal no-state bootstrap graph stay byte-identical; fresh
installed nine-helper graph controls are retained regression requirements.
Source B/native file/fork authority, production providers, existing-state v1-to-v2
migration, public init/CLI/daemon, credentials/bundles/restore, whole milestones,
G1 and all live/deployment/release authority remain closed or pending.
Independent exact SOURCE acceptance, fresh dual-Python CI and root qualification
are still required; this pre-code release is not candidate acceptance or merge.

## Proposed A1: exact passive storage-value dependencies

Date: 2026-10-03 PRC. PLAN AMENDMENT ONLY; independent approval and a root
corrective source release are pending. Source has not started. The original
390-line plan and 372-line ADR remain exact; the factual pre-code release at
ff349bf840f7b83b88b92a0ad2d14e5a4681dddc remains historical authority only
within its allocation. The preceding 421-line plan is unchanged.

### Concrete trigger and finite resolution

The A allocation says command_records depends on core/stdlib only, while the
exact approved six-field BootstrapInspection requires the already accepted
storage-local SchemaVersion and OwnerSessionInfo classes. Constructor failures
must likewise use the existing sealed StorageFailure, not a shadow error type.
The actual immutable input supplies SchemaVersion/StorageFailure in db.codecs
and OwnerSessionInfo in db.models. Both are passive value modules, but importing
them would violate that literal dependency sentence. This is a dependency-text
conflict, not an observed source failure or accepted implementation.

Replace ONLY that dependency interpretation for command_records: it may import
accepted contracts and stdlib, plus the existing exact db.codecs.SchemaVersion
and StorageFailure and db.models.OwnerSessionInfo. These are finite passive
value dependencies, not an opener, session, schema inspector or authority.
No imported class is duplicated, coercively substituted, or validated by its
module/name string. No caller flag, factory, provider registration or callback
is added. The existing codec/model files and their dependencies stay unchanged.
Command records must not import connection, schema, migrations, transactions,
repositories, runtime, CLI, config, Google SDKs or the future bootstrap issuer.
Its constructors retain exact-class/full-field validation and constant repr;
fixed failures never retain private exception cause/context.

### Unchanged signatures, scope and detecting acceptance

BootstrapInspection still has precisely schema_version, owner,
current_operation/current_payload and prior_operation/prior_payload, with the
existing exact SchemaVersion/OwnerSessionInfo and matching nullable pairs.
All other fields/signatures/tables, seven DB/four test/two document paths,
atomic initialization/CAS/inspection strategy and v1 consumer barriers remain.
No new public symbol, field, SQL statement family or production capability is
authorized by this clarification. In particular the literal accepted read
Stage B graph still does not import command_records or any allocated writer
module; read_views and all three no-state foundation files remain byte-identical.

SI04 extends its existing record controls with genuine codec/model values as
positive inputs, and malformed/wrong-class/subclass/foreign-metadata/surplus/
bool/null-pair cases as detecting negatives, rather than forged type names.
SI10 retains fresh noneditable installed import-effect/byte-manifest controls
for the complete A modules and the nine actual retained Stage B helper cases.
These verify no SQL/open/network/Thread/hook/log/write effect or new registration
from this passive dependency, not that constructing a result grants ownership.
All original 1810 tests, native WAL/fault/creator/privacy checks, independent
exact source acceptance and both fresh CI lanes remain mandatory. Source B,
existing-state migration/provider, full CLI/package and external gates remain
pending. This appendix must be independently approved and root-released BEFORE
the clarified dependency is implemented; it does not self-approve its author.

## Factual A1 independent approval and continuation release

Date: 2026-10-03 PRC. The preceding 477-line exact A1 plan remains unchanged
at SHA-256 2f9342e00c3549bdea8784ce0ae43d322752627e1d5bf42a8d43b97776b51d92.
The independent nonauthor reviewer approved ONLY this finite dependency amendment
in the complete 149-line report SHA-256
876f370d9feb62b4e9a10144ba327dcc3e75f78b558825be281cc8db8dfddb29.
Root personally read and verified that report and all 477/421/390 prefixes plus
the unchanged 372-line ADR, then separately released Source A continuation.
The sole author records this plan-only receipt BEFORE any implementation.

Only the existing exact SchemaVersion/StorageFailure from db.codecs and
OwnerSessionInfo from db.models are permitted extra command-record dependencies;
no existing invalid/sqlite_failure helper or other storage/runtime import is
added there. Existing codecs/models/contracts and literal read graph stay exact.
All original seven DB/four NEW test paths and exact approved APIs/37-table/v1
barrier/CAS/stable-key/native-fault/privacy/full1810/wheel/nine-helper/CI gates
remain. This is not source acceptance, Source B authority, provider registration,
existing-state upgrade, complete CLI/G1 or merge permission.

## Prospective ordinary correction: all owned exit classes

Date: 2026-10-03 PRC. The preceding 497-line plan remains exact at SHA-256
8dc96118f80dc4439b3a2bd2cff356a377e6015316e56b24a13982b970e58b6c;
all approved 477/421/390 prefixes and the unchanged 372-line ADR are retained.
No Source A candidate has been committed, frozen, pushed or independently
accepted. The final pre-correction author runs (2235 full, 425 focused and
425 fresh-installed tests) remain historical passing evidence, not acceptance.

An additional read-only synthetic native probe raised KeyboardInterrupt at the
exact connection.execute BEGIN IMMEDIATE c_return after SQLite succeeded. It
observed one hit, in_transaction=True and a fresh real mode=rw contender BUSY.
The Exception-only handler missed that exit class. The probe explicitly rolled
back and closed only its own fixture afterwards; no production file was opened.

Root released this as an ordinary implementation correction to the already
reviewed all-exit owned-cleanup contract, not a changed strategy or authority.
Record and commit this prospective note BEFORE the correction. Only the new
v2 execution/rollback/close fences and already allocated writer-attachment
cleanup fence may catch BaseException instead of Exception. The existing typed
neutral-error/no-cause/no-context contract remains; no interruption result,
success, retry, replacement handle or false completion is introduced.

Within the existing four test files, extend genuine native fault controls with
KeyboardInterrupt and SystemExit at BEGIN/COMMIT/attach/ROLLBACK/close call or
return boundaries. Pair owned cleanup with an unguarded native BEGIN contender
negative, original-key/37-table reopen truth, single-close/unknown-close facts
and retained OS holders. Preserve precondition/foreign/external transaction
ownership and creator/fork barriers, old v1 helper bodies and successful v1
behavior. Committed unknown outcomes retain the existing close-only disposition.
No API, file, manifest, consumer, provider, cleanup authority or product change
is authorized. Remeasure expanded stable focused/full/installed/native/CLI and
retained controls before one source freeze. Independent exact SOURCE review
must explicitly assess this defect and correction, with fresh dual-Python CI;
Source B and all full-package/external/integration gates remain pending.

## Source A factual author handoff

Date: 2026-10-03 PRC. AUTHOR EVIDENCE ONLY, not independent SOURCE approval,
root qualification or integration. The preceding 533-line prospective plan is
unchanged at SHA-256
895758c9a1c82c3be3177383ef738696c2acdefee049aa3949336c567c248e25.
Its ordinary correction was recorded before code in plan-only commit
8e69a3d08fa5a39f1bc63210f0e510b0263676c1. Original 497/477/421/390
prefixes and the 372-line ADR remain exact.

The implementation changes only seven allocated DB paths and adds exactly four
allocated tests. Closed passive records keep the exact six-field inspection and
A1 dependencies. Separate fresh-only v2 manifests install 37 tables/receipts in
one transaction; existing v1 registry/checksums/migration targets remain unchanged.
Bounded original-key lookup and fresh-run CAS implement the reviewed storage
surface. CAS changes only the two owner-run columns and preserves nonempty claims,
unknown insert intent, stopped/paused/restore/namespace and shutdown facts.
Supplied native handles and passive values are not an opener or issuer.

BEGIN/COMMIT attempt fences are set before native calls. Actual native
MemoryError/KeyboardInterrupt/SystemExit exits use owned rollback/one-close or
committed-unknown close-only disposition, without retry, result or false success.
The all-exit correction changes only new v2 execution/rollback/close and the
allocated writer-attachment cleanup fences. Precondition/external/foreign
ownership is preserved. All six original v1 initializer/settings/session/insert
ASTs and old v1 inspector body (under its reviewed rename) remain exact.
V2 read/snapshot/migration consumers refuse before the reviewed forbidden effects;
no read graph, provider, existing-state upgrade or credential authority is added.

Final stable-byte author measurements on CPython 3.12.13/SQLite 3.53.1:

- Actual collection 2269: retained 1810 plus 459 new Source A cases.
- Full 2269 PASS in 444.80 seconds; focused 459 PASS in 10.91 seconds.
- Individual records/schema/bootstrap/owner files: 134/23/235/67 PASS.
- Native exit-class matrix 51 PASS in 2.75 seconds, including the actual unguarded
  BEGIN/real-contender BUSY detecting negative and original-key reopen controls.
- Retained R3 73 PASS/16.86 seconds; OS 150 PASS/88.76 seconds;
  read foundation 71 PASS/13.79 seconds; migration 114 PASS/51.88 seconds.
- Fresh noneditable installed Source A 459 PASS/11.00 seconds;
  installed real WAL lifecycle probes 8 PASS/1.50 seconds and all nine fixed
  accepted read-foundation child scenarios PASS.
- CLI subprocess 40 PASS/4.71 seconds; both source/installed help and JSON
  version PASS. Locked offline dev sync, Ruff and format (184 files) PASS.
- Fresh wheel SHA-256
  645296132f3850f73cefed2ff7d9fa8efa4cd1f37bf1c237f934d70e4bcaabc3:
  69 source/archive/installed file-byte proofs and 54 fresh guarded library
  imports PASS, with no SQL/network/process/write/hook/thread/log effects.
- All 125 unallocated retained source/test blobs, including all 63 old tests,
  remain d688-exact. Original migration prefix/58 ASTs, v0001, literal read graph,
  empty production action/read/migration/predecessor registries remain exact.

Every 179 compiled DDL boundary and 17 initial row/ledger/binding/receipt/version
cuts use actual native fault/reopen controls. Native COMMIT denial, rollback/close
uncertainty, caller-already-except privacy, actual two-process CAS/SIGKILL,
foreign-thread/UoW/fork refusal and v1-positive/v2-before-effects consumer tests
are included. These qualify synthetic local storage tests only, not power-loss,
arbitrary filesystem, native provenance or production capability.

Earlier diagnostic failures and full 2204/2235/wheel passes remain historical.
The concrete prefreeze KeyboardInterrupt acknowledgement-loss finding above was
not waived by them; the final correction is still subject to independent exact
SOURCE review and fresh dual-Python CI checkout/tree qualification. No candidate
is self-approved. Source B, native file/fork issuer, config/artifact publication,
complete credential/bundle/restore providers, existing-state upgrade, public init,
daemon/full CLI, whole M1-02/M1-03/RV11/G1-G6 and live/deployment/release gates
remain pending. Frozen inputs/main/shared current-state documents are untouched.

## Prospective ordinary K1 correction: exact keyword-name boundary

Date: 2026-10-03 PRC. The preceding 600-line plan remains exact at SHA-256
e97cf02383fade849154ea86264462c5965c62adee81ed4e842fc9a3e8b5b4ca;
all original 533/497/477/421/390 prefixes and the unchanged 372-line ADR
cb18c2e0f350ffd1d0e512ebe3c0a7bfb09ea54c1ac3b7785ed1e06a7f841faf
remain retained. Exact source 74d9eb0b36a41ff62342320de7921dda54e61fdf,
tree 44d114ad2de2eb30ab4d050e75f06f358e5c5c51, is SOURCE HOLD, not accepted.

The independent nonauthor 290-line SOURCE HOLD report has SHA-256
dce768b5dbd0bbcdbdc33077bc812180b735ae4b6742ba398b4b59816838e526.
Its refined 91-line causal control has SHA-256
f27c0fed6aba63fc1b457337b83cb6390beb82815de35954edbd1d17b536a79f.
A genuine str-subclass keyword key survives Python's keyword binding and invokes
its equality hook in _RecordType.__call__ keyword membership. The hook raises an
unsealed private exception retaining caller context. Source and fresh installed
controls each measured one pass/one failure despite the historical 2269 full
and both successful CI 37075312893 lanes. Those passes do not waive K1.
An earlier diagnostic raised before Facet entry; it is not this causal finding.

Root personally read the complete report/control and released this ordinary
correction to the existing exact-input/fixed-error privacy contract, not a new
strategy, product, API, manifest or authority. Commit ONLY this prospective note
with the configured user/noreply identity before changing implementation/tests.
Then, within command_records.py, reject every non-exact-str keyword name using
the existing fixed INVALID_INPUT failure BEFORE membership/equality or record
construction. Do not invoke a foreign hook and then catch its exception.
Ordinary exact built-in names, exact fields/seed/six-field inspection, unknown/
missing/duplicate/surplus refusals and no-cause/no-context failures remain.

Only command_records.py, tests/test_command_records.py and this plan may change.
Add actual foreign-key controls that reach Facet, including a benign native cls
comparison, hook-detecting behavior and caller-already-except sensitive sentinels.
Pair them with built-in-key positives and retained constructor refusals. Measure
the detecting failure on unchanged source before fixing it, then corrected source
and a fresh noneditable installed wheel; distinguish pre-entry Python hooks from
the protected Facet boundary. Retain all existing 2269 tests/native fault/CAS/WAL/
SIGKILL/creator/literal graph/privacy/CLI controls and run the newly collected
full/focused/installed suites, locked lint/format/safety and fresh dual-Python CI.

Freeze one new atomic source plus factual handoff with exact tree/report hashes,
then normally push the existing Draft PR27 branch without retargeting/readiness.
Independent nonauthor SOURCE acceptance and root qualification remain mandatory.
Historical 74d9 HOLD and green tests/CI remain unchanged, not retrospective
acceptance. The main-integration plan remains paused; no main/shared-state edit,
Source B, provider/consumer/dependency activation, native issuer, whole M1-02/
M1-03/RV11/G1-G6 or external deployment/Gmail/release authority is added.

## K1 corrected-source factual author handoff

Date: 2026-10-03 PRC. AUTHOR EVIDENCE ONLY; independent corrected SOURCE
acceptance, fresh CI and root qualification remain pending. The preceding
648-line prospective note remains exact at SHA-256
96492c581658233b89edce85fef71540819e0f9146f788768d86ab1c1a8fafab.
It was committed before tests/code in
4489b6a42fe6ce4d63e57a7864b243c3d9e68781, parent historical HOLD74d9.
Original 600/533/497/477/421/390 prefixes and the unchanged 372-line ADR remain.

Production changes precisely two lines: exact keyword-name type refusal before
Facet membership/equality or super construction. All other 186 historical74d9
path/mode/blob and working-byte entries remain identical. Every original record
test function/class AST remains exact; two additive test functions contribute
nine built-in-key positives and 54 foreign-key behavior/context pairs across
all nine records. Native Python cls binding is explicitly benign and is not
attributed as a Facet violation. Before correction the actual raising/context
pair failed for every record: nine failures/0.22 seconds on unchanged production.
After correction all 63 new cases pass/0.18 seconds, with an actual Facet frame,
zero foreign hooks and exact fixed error/no-cause/no-context observations.

Final stable-byte local measurements: CPython3.12.13, SQLite3.53.1/eUID1001,
verified local TMPFS synthetic fixtures; no arbitrary mount/power-loss claim.
Actual whole collection2332; full2332 PASS/446.97 seconds. Four Source A files
522 PASS/10.89 seconds, records197 PASS/0.26 seconds. Genuine native exit-class
matrix51 PASS/2.77 seconds; expanded native/COMMIT-denial54 PASS/3.07 seconds.
Retained R3/OS/read/MG/CLI: 73/150/71/114/40 PASS respectively, measured
16.89/88.63/13.77/52.32/4.66 seconds. All original tests remain retained.

Fresh noneditable installed Source A522 PASS/10.92 seconds; exact independent
causal control f27c0fed passes both source2/0.08 seconds and installed2/0.12
seconds. Installed actual R3/WAL8 PASS/0.64 seconds and all nine unchanged
literal read-helper scenarios PASS. Fresh wheel SHA-256
909c070b74105161abcc60536216183b65b1261d06a0121079a340d240ce9845;
69 source/archive/installed byte proofs, 54 individually guarded inert imports,
combined FD/empty-registry inventory and actual connect detecting negative PASS.
All 125 retained base source/test blobs/63 old tests, six v1 ASTs, exact renamed
v1 inspector, old registries and original migration prefix/58 ASTs PASS.
Locked offline sync/Ruff/format184, source/installed helps and JSON version PASS.

A copied private installed-R3 probe initially retained the previous wheel's
absolute site assertion and failed collection. Only that sandbox-location check
was corrected; the subsequent eight real probes passed. This is a private
verification setup diagnostic, not a candidate-source failure or skipped gate.
No old report/finding/candidate/CI is rewritten: 74d9 remains SOURCE HOLD despite
its green2269/CI. The new candidate requires fresh exact nonauthor SOURCE review
and actual dual-CI checkout/tree qualification before any integration decision.
PR27 remains Draft against the unchanged qualified combined branch. Main plan,
main/shared-state/source inputs and Source B/provider/consumer/dependency/full
package/live/deployment/release gates remain untouched and pending as before.
