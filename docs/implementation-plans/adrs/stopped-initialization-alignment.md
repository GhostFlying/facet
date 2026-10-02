# Stopped initialization: explicit interface and staging alignment

Date: 2026-10-03. Revision: proposed r3, PLAN ONLY, NOT APPROVED.

This is the required written alignment companion to
[the finite implementation plan](../m1-03-stopped-initialization.md). It does not
rewrite any original writer/read/core/schema/CLI document. Its author is
`phase1_os_acceptance_sol` (Sol xhigh); another independent agent must review both
exact hashes. No source, registry change, publication or source release is
authorized by writing or approving this proposal.

## Frozen inputs and precedence

The complete writer plan438 SHA3934f2a4..., extension876 SHA3b9dc3e6..., read229
SHA9d28e18c..., schema1228 SHA3d902151..., core614 SHA795f80ab..., command475
SHA5f0e5af9..., and CLI309 SHA6215d726... were read personally. Complete hashes
are in the companion plan. They remain exact immutable reference artifacts.
The actual candidate base is qualified unmerged `a9c4e36de6ad70294002a83e678a2a7cf1b012d6`.
Current migration/no-state implementation is not independently accepted input.
Original historical HOLD/FAIL findings retain their attribution and scope.

User product/privacy/authority contracts take precedence; neither old runtime
design nor accidental implementation authorizes a changed product promise.
The following are proposed engineering/staging alignments within those contracts.
If independent review identifies a material conflict, root must obtain direction,
not let either author silently choose new semantics.

## Alignment decisions and unchanged boundaries

| Subject | Actual conflict/gap | Proposed finite disposition |
| --- | --- | --- |
| Filename | Writer/read prose says metadata.db; installed PrivatePaths.db says facet.db | Canonical managed database is `facet.db`; no alias/discovery/rename/adoption. Older design names are logical references only |
| Module | Earlier inventory says runtime.py; accepted runtime is a package | Add only allocated `runtime/bootstrap_files.py` and `runtime/stopped_initialization.py`; no replacing package initializer/import graph |
| v1/v2 | Current `_inspect` accepts exact v1 only; frozen extension proposes v2 | Jointly allocate fresh v2 initializer, exact v1/v2 manifests and inspector before any v2 producer. Preserve immutable v1 and its behavior |
| Receipt bootstrap | v1 metadata has no durable command row | Fresh first init must commit schema2 and original-key operation together; never manufacture a v1 receipt or initialize v1 then upgrade |
| Owner publication | Current attach requires stored previous run; no fresh-run entry exists | Add only the frozen private fresh-owner v2 CAS, requiring actual holder at caller. Do not borrow stored run as authority |
| Reconciliation | Frozen ordinary getters need UoW/ReadSession before new-owner attach | Add a bounded private supplied-connection bootstrap inspection seam; no read provider, arbitrary query or attach bypass |
| Consumer versions | Existing snapshot reports v1; read and migration consumers are not qualified for v2 | Explicit exact-v1 consumer barriers before backup/destination mutation or read admission; retain v1 positives and defer jointly qualified v2 consumer support |
| Scaffold | Real root/locks prove ownership, not initialized state | A separate opaque actual issuer continuously checks real resources and exact journal/config/DB facts; no dataclass or FD-tuple capability |
| Staging | Original full writer and read designs require many genuine participants | Independently accept storage A, then private stopped issuer B. Keep all shipping read/provider/executor registrations and full CLI unavailable |
| Empty/unbound | Strict Config requires both distinct declared identities | Pending verification is unbound. Empty ruleset0 is allowed; missing account identifiers are not a new mode; nonempty rules wait M1-06 |
| Closure | Earlier initialization prose can suggest release before SQLite close | Confirm actual connection close while owner/view remain held, then retire descriptors/leases; uncertainty retains live ownership until process death |

No wire version, digest version, journal/receipt JSON fields, bootstrap phase,
confirmation/disclosure semantics, raw storage policy, credential scope or new
product command is changed. Source unit B remains private/internal; a future CLI
adapter needs its own finite allocation and acceptance. An installed subprocess
calling a real private issuer is not an implemented public command.

## Exact storage contract

Keep existing `_initialize_database` and the v1 initializer tests unchanged.
Freeze v0001 source SHA-256
`c4531c7fa27634aadcec1c00cb8b42fa6ba921e4e35febc2a643049934c25477`.
Exact v1 manifests/ledger/digest must remain the accepted ones, even after v2 is
compiled. A global `version <= current`, wildcard catalogue, database-authored
manifest, altered v1 checksum, or accepting v2 through the v1 path is forbidden.

Fresh v2 installation is the fixed v1+v0002 statement sequence in ONE explicit
transaction. v0002 is the exact command extension (five tables, fixed constraints/
indexes and binding-guard trigger), not arbitrary JSON command storage. Metadata
and ordered ledger record both compiled checksums and exact schema version2.
Existing migration execution may still have an empty shipping successor/provider
registry; compiling a fresh manifest cannot activate an existing-v1 upgrade.
The current migration source must be accepted and its overlapping files serially
released before this later change; compatibility needs a new exact combined gate.

### Complete actual consumer/version audit and proposed policy

The author searched every actual `_inspect`, REGISTRY/digest, user_version and
SchemaVersion consumer in accepted a9c DB/CLI/runtime/private_paths. Recognition
cannot silently become support by callers whose local metadata still means v1.
Add only private `_inspect_v1(connection)`: exact version1 required, then the
unchanged complete trusted-v1 inspection. No skip/current-version parameter.
v2 receives fixed UNSUPPORTED_VERSION at this barrier, never a falsely labelled
result. Existing zero/partial/foreign/future/v1-tamper refusals remain fail-closed.

| Actual consumer | Explicit version policy and allocation |
| --- | --- |
| `_initialize_database` in connection.py | Remains pristine->v1, exact current REGISTRY/CHECKSUMS/REGISTRY_DIGEST unchanged; no new ledger/checksum imported into it |
| `_attach_writer` | Jointly allocated generic exact1/2 inspection and ordinary matching lineage; no adoption/previous-run permission |
| `_attach_view` | Jointly allocated call to `_inspect_v1` before configuration/admission SQL; `_consume_permit`/creator and owned-failure cleanup remain, ReadSession class/read_views unchanged |
| `snapshot_database` source and copied destination | Joint narrow allocation to use `_inspect_v1`; reject v2 source before backup or destination settings/files change, then preserve all v1 checks and literal truthful SchemaVersion1 |
| `_pristine` | Unchanged: appid0/version0/no objects/no transaction, never existing v1/v2 recovery or migration |
| `get_schema_metadata`/SchemaMetadataRow | Actual typed decoding through a valid ReadSession; current read consumer remains v1-only, no coercion of returned version |
| SchemaMigrationRow/DatabaseSnapshotInfo/MigrationBackupReceipt | Exact existing shapes and SchemaVersion codec; constructibility gives no support/authority. Snapshot result remains v1-only; no fake-v2/9001 receipt |
| REGISTRY/CHECKSUMS/REGISTRY_DIGEST/TRUSTED_CATALOGUE | All current v1 constants preserved exactly; add separately named fixed fresh-v2 constants/manifests rather than broadening old globals |
| Currently implementing migration entry | After its independent acceptance, preserve its exact current-v1 target/predecessor/provider policy; v2 is unsupported, no BEGIN/backup/step. Any conflicting accepted interface requires plan amendment before A |
| CLI `_emit` schema_version1 | This is output-envelope version, not DB version or healthy-state evidence; no change, init remains unavailable |
| New `_initialize_database_v2`/`_begin_owner_session_v2`/`_inspect_bootstrap_v2` | Jointly allocated exact-v2 writer/inspection only; no v1 receipt shortcut or new read consumer |

`snapshot_database` remains a current qualified storage primitive, not complete
backup. Broader generic inspection would otherwise mislabel v2 as its literal v1.
Its allocated change is a conservative exact-v1 barrier, not new v2 snapshot
support. Source version check must precede native backup and every destination
PRAGMA/configuration/mutation. Actual source WriterSession/creator/currentness/
lineage/relational checks, pristine destination and BUSY/fault/close/privacy
guards stay; copied destination must still be exactv1 before receipt construction.
Future actual v2 backup requires its own jointly reviewed snapshot/provider plan.
No fake predecessor WriterSession, complete-bundle capability or M6 activation.

Required paired tests: existing real v1 initializer/attach/read/WAL snapshot and
all original fault tests remain; genuine new v2 writer/session/receipt succeeds
only in allocated writer seams; synthetic qualified-view controls refuse v2
before `_attach_view` configuration and preserve owned connection-close-before-
lease order; v2 snapshot attempts leave destination bytes/catalogue/settings and
source rows unchanged with zero native backup. Include future/partial/tampered/
foreign/invalidated/close-fault privacy negatives. Verify no old v1 ledger/digest
becomes the combined fresh-v2 one. Empty shipping registries remain empty.

Passive storage enums/records live in `db/command_records.py` and depend only on
accepted contracts/stdlib. Base DB code cannot import runtime/CLI/commands to get
authority. All seven frozen command kinds may be structurally represented, but
only completed bootstrap facts are inserted in this finite source. There is no
accept_control/accept_auth/update_auth_operation executor, daemon shutdown handler,
credential revision publication or generic operation setter. `operation_auth`
does not create a dummy CredentialChange reference/issuer. Its future real FK and
participant retain the frozen requirement for joint credential-extension review.

`BootstrapOperationSeed` and `FreshCommandBootstrap` keep the exact frozen fields
and invariants: current facet_init, optional prior config_init, expected binding/
config revisions0, confirmation true, duplicate-risk false, complete exact config
digests/times, same namespace/config lineage and distinct nonce/operation IDs.
They contain no Config/path/credential. Caller construction supplies data only.

The new initializer is exactly:

```text
_initialize_database_v2(connection: sqlite3.Connection, *,
    bootstrap: BootstrapInitContext,
    initial_projection: ProjectionRow,
    source_binding: BindingRow, target_binding: BindingRow,
    initial_ruleset: RulesetRow,
    commands: FreshCommandBootstrap) -> WriterSession
```

Pristine connection, exact types, initial lineage/paused/pending/empty-rule facts,
current seed key and prior seed checks precede writes. Configure approved writer
settings; install both schemas and all initial state/command facts in one commit;
then full same-connection attachment. No intermediate v1 commit, receipt gap or
unvalidated second connection. Current facet operation/instance IDs come from the
durable accepted filesystem receipt. Prior config SQL ID is allocated once before
the call and first published with this commit; a lost response recovers it by its
original key. Do not modify the old config archive's NULL operation ID.

The new owner entry is exactly:

```text
_begin_owner_session_v2(connection: sqlite3.Connection, *,
    owner: OwnerSessionInfo,
    expected_previous_run: LocalId | None,
    now: Timestamp) -> WriterSession
```

It accepts only exact v2, no open transaction, correct settings, expected instance/
namespace and equal previous projection/runtime run. The actual newly held owner
supplies a fresh different run; BEGIN IMMEDIATE CAS changes only those two run
columns. Full same-connection attach follows commit. No claim/intent/receipt/pause/
stop/shutdown/restore/binding/namespace edits or enabled dispatch are implied.
Ambiguous commit/attach cannot retry or return a session from the old run.
Normal `begin_owner_run` intent-aware startup/shutdown retirement remains future
full-runtime scope; it is not smuggled into this CAS.

### Narrow pre-attachment reconciliation addition

The sole extra storage inspection entry is:

```text
_inspect_bootstrap_v2(connection: sqlite3.Connection, *,
    projection_id: ProjectionId,
    namespace: LocalId, nonce: LocalId,
    prior_config_nonce: LocalId | None) -> BootstrapInspection
```

`BootstrapInspection` has only `schema_version:SchemaVersion`,
`owner:OwnerSessionInfo`, `current_operation:OperationRow | None`,
`current_payload:BootstrapPayloadRow | None`,
`prior_operation:OperationRow | None`, `prior_payload:BootstrapPayloadRow | None`.
No config/path/raw SQL/cursor/connection/permission escapes. Current namespace is
the inspected instance namespace; nullable pairs agree. Optional prior nonce must
differ, be in the same namespace and decode as completed config_init. Each present
operation/payload pair is decoded against exact trusted constraints and immutable
request key/digest/command; no child alone is accepted. Missing pairs are facts,
not authority to create another operation. Caller compares its retained journals.

Exact supplied connection/type/autocommit/no-open-transaction/settings/schema are
checked; one bounded short read snapshot materializes at most two original-key
pairs plus lineage. COMMIT/ROLLBACK/close faults yield fixed failure, not partial
observations. This storage-local seam deliberately does not attach a ReadSession,
set journal mode, checkpoint, publish an owner, migrate/create schema or require
a fictitious provider. Production authority comes only from B's real continuously
held owner/view and controlled connection. Test supplied connections prove its
storage behavior, not production authority. A caller cannot use this result to
register a read producer or borrow a prior owner run.

## Genuine issuer and file provenance

The only real issuer is the private fixed factory in stopped_initialization, not
Config, PrivatePaths, BootstrapReceipt, BootstrapInitContext, OwnerSessionInfo,
`FileIdentity` or `ReadRuntimeIdentity`. Its opaque live handle is identity-enrolled
with retained actual PID and strong Thread object plus actual root/owner/view/key
resources and a controlled connection. No public caller-supplied enrollment or
boolean validation callback exists. Foreign/fork/stale callers fail before native
access, poisoning, retirement or closing, even after actual connection failure.

The file adapter checks accepted OS inventory under its mutex after creator-first
checks. Only fixed internal operations may consume directory FD numbers; they
never return numbers/duplications to callers or add generic fd/callback APIs.
No private inventory manipulation may fabricate membership, bypass dependency
ordering or close another owner. Stable locks remain single-link zero-length0600
and are never replaced/unlinked; artifacts are owner0600 single-link regular files
with their separately valid nonzero sizes. Directories remain0700, ancestors
trusted root/eUID and not sticky world-writable. Existing-root opening is zero-write.

Only explicit first-init may create the accepted empty lock scaffold. A preexisting
scaffold may continue only with complete valid matching bootstrap facts; unknown
DB/config/artifacts are not adoption authority. Existing initialized state uses
the existing-root path. Before filesystem changes check request ID, confirmation,
strict Config, projection selector/paths, pending distinct roles and empty rules.
No automatic account discovery/profile check/credential read/network occurs.

The request key syntax and canonical digest remain frozen rq1/version1. Add only
the in-process `BootstrapSubmitRequest` with the exact frozen submit field set:
wire_version1, rpc='submit', request_id:RequestId, projection_id:ProjectionId,
command:BootstrapCommand, payload_version1, payload:ConfigInitPayload or
FacetInitPayload, confirmation:Confirmation and expected:ExpectedGuards. Payload
type must exactly match command; both contain only the actual validated Config.
These Config-bearing values live in commands/bootstrap_codec, not storage-local
command_records, preserving the latter's core/stdlib dependency restriction.
No socket variant or new JSON payload is enabled. The private exact entries are:

```text
submit_stopped_bootstrap(request: BootstrapSubmitRequest, *,
    state_dir: str, config_path: str | None) -> BootstrapReceiptData | ReceiptData
lookup_stopped_bootstrap(request: LookupRequest, *,
    state_dir: str, config_path: str | None) -> BootstrapReceiptData | LookupData
```

Selectors are metadata, not ownership: normalize/validate them against actual
PrivatePaths and real resources; no alternate db filename or caller-chosen VFS.
Submit always requires an already established full key and yes=true, regardless
of TTY. Future CLI handles TTY key generation/confirmation before this entry;
this library never trusts a caller's is_tty/validated boolean. It cannot accept an
arbitrary request kind/payload, factory/session/lock or SQL connection. Lookup
takes the exact frozen LookupRequest without effect payload. Before SQL exists,
return the actual BootstrapReceiptData; after SQL receipt reconciliation use the
actual ReceiptData/LookupData with fixed frozen ReceiptView, not a fabricated SQL
ID or a new result shape. No
automatic key renewal or inferred resend is added. Public DTOs expose only fixed
bootstrap phase/code data; operation IDs/keys have only the existing explicit
local private-metadata allowance, never Web/public aggregate output.

The fixed artifact set is root `config.yaml`, `facet.db` and valid associated WAL/
SHM as required by actual SQLite, `bootstrap.json`, `bootstrap-receipts` and
`requests` journal/key-lock entries. External `--config` is an explicit selected
owner-only file, not an alternate managed DB/root. It is never overwritten.
Staging basenames are manager-generated local IDs, not user-controlled path text;
they remain known same-journal artifacts and are never blindly deleted on failure.
Create/open/fsync/rename/close must revalidate actual inode/UID/mode/link/entry facts.

The controlled writer opener is a hard provenance gate. A plain lexical path and
post-open name comparison are not proof that SQLite bound the expected file.
Its implementation must establish actual connection/file enrollment causally
before settings/initialization SQL and retain root/DB identity at critical use.
No arbitrary URI/VFS override, `immutable=1`, read-provider/audit seal, raw FD tuple,
fallback opener or memory DB can satisfy it. A new native/VFS/descriptor-proxy
strategy requires a prior written finite opener amendment and review, not an
implementation improvisation. Missing platform proof blocks B source acceptance;
it cannot be papered over by schema/receipt success. There is no adversarial
sandbox promise against arbitrary native descriptor/SQL misuse by trusted code.

## Durable journal, restart and first-response-loss protocol

Use exact frozen ClientJournal and BootstrapReceipt formats: bounded16384 bytes,
depth8, strict duplicate/unknown keys/exact scalar types. No Config/raw/credential/
exception/filename/provider data in these formats. Per-key journal creation and
updates use the stable key lease; client viewSH/keyEX must be released before any
IPC/owner wait. A stopped bootstrap already holding viewEX uses that exclusive
lease as key parent without another SH acquisition. Every request keeps its key.

Hold ownerEX->viewEX->keyEX before inspecting acceptance. Persist accepted receipt
before artifact creation; for facet_init its instance/current operation IDs are
already immutable. Config-init has NULL instance/schema/SQL operation throughout.
New config is exclusively staged, fsynced, no-overwrite published, dir-fsynced,
then config_created is recorded with exact artifact digest. Existing explicit
config is validated and its digest recorded without rewriting it. Fresh DB then
commits exact v2 state/current+optional prior receipt in one transaction. Only
verified committed schema2/instance/key/digest permits db_created.

After SQL commit/inspection, confirm actual connection close with owner/view held,
complete owned artifact durability, exclusively archive completed receipt and
sync archive directory, then atomically/fsynchronously set active completed.
Archive publication precedes reuse of active bootstrap.json. No completed success
may escape if commit/close/fsync/archive/active update is uncertain. Retain strong
ownership if closure is unconfirmed; actual process death releases OS copies.

Restart under a newly acquired real owner handles only original keys and known
artifacts. Precommit pristine rollback is distinguishable from partial/corrupt
state; it alone may resume original initialization. Postcommit lookup recovers
the original operation/instance and optional imported config operation ID; never
allocate new identities to fill a missing response. Config bytes cannot be
rewritten, completed SQL effects cannot repeat, namespace cannot refresh to escape
conflict, and foreign/missing receipt state cannot initialize an empty DB.

Archive/active reconciliation uses the extension's exact immutable-field checks
and permitted phase/time pairs; code must be None. Same-key completed timestamps
match, config_created/completed or db_created/completed promotion changes only
active pointer, and different older keys remain historical. Truncated/divergent
archive is refusal, never overwrite or silent omission. Once initialized, SQL and
matching retained receipt facts must agree; neither independently blesses the
other. A missing row/file or absent owner response is not proof of no effect.

Lookup is read-only with respect to artifacts and never creates missing key/root
paths. True locally authoritative absence requires actual stopped resources,
matching current namespace and complete healthy typed inspection. Otherwise fixed
unavailable/lineage/conflict means unknown. Before SQL exists return the actual
BootstrapReceiptData, not an invented SQL receipt. Full operations listing and
CLI adapter behavior are deliberately deferred, not falsely declared complete.

## Cleanup, fork and uncertainty boundaries

Creator identity remains available independently of connection validity. Owned
cleanup may finish a broken session, but foreign creator refusal cannot change
owner state. Stale cleanup checks current enrolled owner before retiring it.
Confirm native connection closure before retiring artifact FDs/key/view/owner/root.
Unconfirmed close retains ownership and blocks all admission; cleanup may not retry
an uncertain raw FD integer or claim it is closed from lack of exception alone.
Retire only explicit terminal resources; live strong retention remains and weak
terminal tombstones must not strongly retain keys. No GC/finalizer unlock exists.

New artifact/SQLite descriptor inventory must participate in before-fork capture
under the real inventory mutex. Child closes verified copied descriptors only,
never LOCK_UN or inherited SQLite SQL/close calls, invalidates enrollment locally
and prevents native connection destructor reuse. Parent kernel ownership is
unchanged. Real tests fork and exit only their own child with bounded cleanup;
continued forked runtime/actor inheritance is not qualified. If complete actual
SQLite descriptor closure/quarantine is not achievable with the approved finite
strategy, stop for an amendment rather than weakening no-inheritance promises.
No atfork hook or FD appears at import; any required hook is installed only at the
explicit real factory, inventoried and covered by zero-effect import tests.

Errors have fixed typed codes, constant repr, no native error strings/trace or
sensitive exception context/cause, including when caller is already excepting.
Inputs and temporary values do not survive in receipt/result/log structures.
Positive typed metadata/config storage is distinguished from prohibited content
by actual scans of active WAL/journal/temp files and deliberate leaking controls.
No debug/provenance diagnostic exports full path/SQL/private digest/account data.

## Prerequisite and future-gate matrix

| Gate | Required actual evidence | Not satisfied by |
| --- | --- | --- |
| Source A release | Both exact documents independently approved; accepted migration source+qualified CI; exact normal carry; root exclusive DB ownership allocation | Current migration plan approval/implementing tree; a9 qualification alone |
| Source A acceptance | Exact v1/v2 storage/full retained tests, real WAL/fault/CAS/reopen/creator controls, installed wheel, exact dual-Python CI and non-author source verdict | Seed/context dataclasses or unchanged old tests alone |
| Source B release | Accepted A+OS+actual dependencies, written opener/fork strategy resolved, frozen allocation/base and root dispatch | Scaffold, receipt schema, or no-state foundation plan |
| Source B acceptance | SI01–10 actual filesystem/connection/kernel/journal/restart/privacy controls, installed fixed private producer and exact CI/non-author review | Synthetic provider, FD tuple, green storage-only suite or same-author review |
| Existing v1 upgrade | Actual complete coordinated backup/config/binding/credential ownership provider and stopped migration journal/receipt, fixed registered successor | Fresh-v2 initializer, empty provider or constructed backup dataclass |
| Stopped read activation | Accepted initialized provenance plus genuine controlled read opener/runtime qualification/provider, explicit stopped-only staging amendment and actual RV controls | This initializer, memory probe, configuration bytes or FD metadata |
| LIVE/full M1-03 | Real actor/server/lifetime/socket/pidfd/noinherit, single writer/worker fences, intent-aware recovery and second-daemon refusal | Private one-shot owner or schema owner_run metadata |
| Full CLI/M1-04/M6 | Actual CLI adapter/end-to-end failures and exact credential/bundle/profile/backup/restore gates | Private installed function calls, pending declared bindings or local DB snapshot |

Both source units retain every applicable original writer/core/read/CLI gate;
unimplemented portions remain visibly pending, not removed from the DAG. No
shipping read runtime/provider, maintenance predecessor/provider, command handler
or credential participant is registered by these preparatory artifacts. Source
release/integration and later registration require their own actual gated dispatch.

The companion SI01–10 mapping supplies finite positive/detecting negative tests.
All acceptance is prospective; these documents execute no storage/process/Gmail
test and approve no candidate. Freeze both complete hashes, retain original input
hashes, and return them to root for independent non-author design review before
any implementation. Material contract changes return to the user through root.
