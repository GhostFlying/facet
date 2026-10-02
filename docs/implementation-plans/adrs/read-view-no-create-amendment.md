# M1-02 / M1-03 read-view no-create amendment r2

Status: proposed design only, pending non-author independent review. No source,
provider registration, production inspection or SQLite configuration change is
authorized by this draft. Date: 2026-10-02. Owned design HEAD remains
`1b7cd58b4846aab86edcbb781a999abb968d047c`; actual main observed during drafting is
`ff77e63a823dc8bcb130836243746c067778b94f`.

Keep storage r3, result amendment `2bf222b1819d80ddbed48387c8afd8fda5678db4b6425d1e89f396ea2687b427`,
mapping amendment `81b21b0f1c30d0799ea636acb59fdfc90d9920567e25e3abb5484347c38ec2d6`
and writer extension r3 `3b9dc3e637ba727589768f0055c746193809f7e0fcd07bc94839dd565a0110c8`
unchanged. This file is their narrow DB-21/M1-03 read-view compatibility supplement,
not a schema migration or a new general filesystem/SQL API.

Revision r1 (273 lines), SHA256
`9a162cf2c48b75b3906ebf8c47eb597771ce002248a02831c5693ed3ec98445e`,
received independent CHANGES_REQUESTED for R1: forbidding only write-capable DB
connections misses an ordinary mode=ro connection's writable process-global SHM
node. This revision closes process provenance/lifetime and RV-08/09 controls;
the two view modes, tables and authority boundaries are unchanged.

## Evidence and boundary

Storage r3 requires clean stopped reads, active readable WAL reads and refusal
before sidecar creation or persistent recovery. Its supplied-connection adapter
did not define how the producer guarantees that precondition. query_only is a
connection defense, not a filesystem no-write promise. SQLite delays WAL/SHM
opening until a schema/read query, so even successful sqlite3.connect(mode=ro)
does not establish this condition.

Primary references checked on 2026-10-02:

- [SQLite WAL read-only databases](https://www.sqlite.org/wal.html#read_only_databases)
  distinguishes existing readable sidecars, permission to create them, and
  immutable databases. WAL remains part of the database's committed state.
- [SQLite URI parameters](https://www.sqlite.org/uri.html#uriimmutable)
  says immutable disables locking/change detection; changing that file can give
  incorrect results. Facet must establish stable stopped ownership for its full
  connection lifetime, not label a live file immutable.
- [SQLite 3.53.1 unix VFS source](https://raw.githubusercontent.com/sqlite/sqlite/version-3.53.1/src/os_unix.c)
  shows readonly_shm opening shared memory read-only. This is a version/VFS
  implementation detail, not a portable URI guarantee.
- [SQLite 3.53.1 WAL source](https://raw.githubusercontent.com/sqlite/sqlite/version-3.53.1/src/wal.c)
  opens the WAL with CREATE even on this path; readonly_shm alone cannot prohibit
  a missing WAL from being created. Its internal heap WAL-index fallback also
  must not be confused with a Facet-approved post-crash inspection lifecycle.
- [SQLite file lifecycles](https://www.sqlite.org/walformat.html#file_lifecycles)
  explains normal last-connection cleanup versus sidecars retained after crash.
  [SQLite descriptor caution](https://www.sqlite.org/howtocorrupt.html#posix_advisory_locks_canceled_by_a_separate_thread_doing_close_)
  warns that closing unrelated descriptors for the same DB inode can cancel
  process-wide POSIX locks. Provider identity checks must not casually open/close
  extra ordinary DB/WAL/SHM descriptors while SQLite uses them.

Actual temporary synthetic-file diagnostic (not product/provider acceptance):
CPython 3.12.13, SQLite 3.53.1, source ID
`2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.
Tests used the task runtime, the existing real schema initializer and independent
reader processes. All temporary directories were removed; no private state was
opened. Snapshots compared directory names, file sizes and byte digests.

| State / connection | Actual inspection result | File delta |
| --- | --- | --- |
| Clean stopped, mode=ro | Schema/read succeeded | Created WAL and SHM: failing control |
| Clean stopped, mode=ro + readonly_shm=1 | Controlled unavailable | Still created WAL: failing control |
| Clean stopped, mode=ro + immutable=1 | Schema/read succeeded | No creation or byte change |
| Active writer, existing sidecars, ordinary mode=ro | Schema/read succeeded | Existing SHM bytes changed |
| Active writer, existing sidecars, mode=ro + readonly_shm=1 | Schema/read succeeded | No creation or byte change in quiescent control |
| Active writer, immutable=1 | Schema inspection refused | No delta, but omitted committed WAL schema: invalid strategy |

A second real-process probe held owner EX in a writer and view SH in a reader:
graceful writer close could not acquire view EX; readonly_shm read returned the
committed synthetic row without file delta. Killing the exact writer made its
pidfd readable; a pre-inspection lifecycle check could refuse without touching
SQLite. This probes primitives only, not the future registered runtime adapter.

R1 was independently reproduced during revision on the same exact runtime: a
fresh reader child kept an ordinary mode=ro connection open, the separate writer
committed another row, and a second readonly_shm connection in that child read
both rows but changed SHM bytes. Repeating with both child connections using the
qualified readonly_shm parameters returned both rows with no SHM byte change.
Thus DB read-only flags do not prove the process's shared-memory node is read-only.

## Ownership and finite allocation

M1-03 remains sole production owner of root traversal, locks, connection opening
and view lifetime. M1-02 neither discovers a path nor opens a second connection.
The raw `_attach_view(connection, expected_instance)` shape is insufficient and
must not remain an alternate unguarded entry point. Proposed exact replacement:

```text
_attach_view(connection: sqlite3.Connection, expected_instance: LocalId,
             *, permit: ReadViewPermit) -> ReadSession
```

M1-02 owns the private bridge types in `facet.db.read_views` (not core exports):

- `ViewMode`: exactly stopped_clean or live_wal.
- `FileIdentity`: exact nonnegative device/inode/uid/mode integers, fixed safe
  repr; no path, content or network fields. It is metadata, never permission.
- `ReadViewPermit`: opaque, nonserializable, non-dataclass with no public
  constructor. Bound to one exact unused sqlite3.Connection, expected instance,
  creating PID/thread, one provider lease, one ReadProcessSeal, mode and qualified runtime identity;
  single attach, active/closed lifecycle, no caller flags or replaceable callback.
- `ReadViewLease`: opaque, private constructor; concrete lifecycle implementation
  belongs to the statically registered M1-03 provider, not a user plug-in. It
  retains actual root/lock descriptors and file identities, active PID/thread,
  mode, and the live peer pidfd/socket identity only in live mode. It exposes only
  `check()` and `close()` to the bridge. check performs the exact nonblocking OS
  identity/lifetime checks below; no SQL, network wait, mutable user callback or
  configurable behavior. close follows the fixed lifetime order below.
- `ReadProcessSeal`: opaque process-lifetime object created only by the actual
  isolated reader bootstrap below, not a constructor, command flag, PID assertion
  or "registry empty" claim. It owns the process-wide connection-opening mutex,
  registered connection/lease inventory and irreversible invalidated state.

The bridge has one private producer entry:

```text
_bind_read_view(connection: sqlite3.Connection, expected_instance: LocalId,
                lease: ReadViewLease, seal: ReadProcessSeal) -> ReadViewPermit
```

Only the fixed registered production view provider may bind its just-opened,
never-queried connection after the defined preflight/open sequence. The registry
is compiled module/class identity plus live lease ownership, not an import path
from config/DB or a settable "trusted" boolean. The permit registry binds object
identity; object.__new__, copied fields, another connection, stale PID/thread,
closed/released lease or caller-created FileIdentity cannot establish entry.
Binding also checks the same seal that admitted the actual connection open and
its full-lifetime inventory record; binding an already open unregistered object
is forbidden, even when its URI/DB is described as read-only.
Python internals are not a hostile same-process sandbox; actual provider code and
OS-lifecycle tests establish the guarantee, not a record's class name.

Production provider methods are exactly
`open_stopped_view(root: HeldPrivateRoot, expected_instance: LocalId)` and
`open_live_view(root: HeldPrivateRoot, expected_instance: LocalId)`, each yielding
one ReadSession context. HeldPrivateRoot is the already reviewed M1-03 root
capability, not a new string path factory. Implementation location is the owned
M1-03 runtime read-view adapter; it must consume this exact supplement before
source dispatch. No public/open-any-path method or connection option dictionary.
Return controlled StorageFailure on unavailability; no automatically selected
weaker mode and no permanent capability escapes the context.

M1-02 tests may use an explicitly test-owned registered adapter only within the
test process, exercising real temporary directories, locks and SQLite processes.
That registration is absent from the production build/registry and cannot be
enabled by environment/config. Its success verifies bridge/database behavior,
not actual M1-03 ownership. With no actual registered producer, managed reads
remain owner_unavailable before any schema query. This is a hard runtime/G1 gate.

## Common preflight, URI and runtime rules

Use existing verified root and initialized owner/view lock inodes only. No mkdir,
create-lock, chmod, unlink, symlink following, cursor write or marker repair.
Retain directory descriptors; inspect fixed `metadata.db`, `metadata.db-wal`,
`metadata.db-shm`, `metadata.db-journal` entries with no-follow relative metadata
checks. Apply the reviewed trusted ancestor/private boundary policy, expected UID,
regular-file type, single link and exact private file permissions. Root/lock/DB
or present sidecar replacement, unsafe permissions or a maintenance/bootstrap/
restore-in-progress marker refuses before opening SQLite. A restore recovery
fence inside a structurally valid DB may be displayed; reading cannot clear it.

Use the fixed canonical DB location under the retained root, URI-escape the path
and add only the mode-specific literal parameters below. No client-supplied URI,
vfs, nolock, cache, ATTACH or query parameters. Check root/entry identities again
after connect and immediately before first SQL. No extra ordinary DB descriptor
may be closed while any same-process SQLite connection uses that inode. File
identity inspection uses directory-relative stat; stopped header reads, if needed,
finish and close before the SQLite connection opens. Cooperative Facet actors
obey the locks below; arbitrary privileged/same-UID filesystem sabotage is not
claimed to be prevented. Detected replacement always refuses, never adopts it.

Connections are fresh exact sqlite3.Connection, autocommit=True,
check_same_thread=True, detect_types=0, uri=True, timeout=5, default row_factory;
no registered converters, trace callbacks, loadable extensions or prior query.
The private producer, not a boolean in ReadViewPermit, establishes this origin.
M1-02 validates/consumes the permit and lease BEFORE any PRAGMA/schema SQL.
It may then set connection-local query_only/trusted_schema/foreign_keys defenses,
inspect the trusted schema/instance and return the bounded ReadSession. It never
runs journal_mode assignment, checkpoint, migration, WAL repair or creation.

Runtime qualification is mandatory for the exact Python/SQLite source ID,
compile-options fingerprint, Linux architecture and forced unix VFS. No version
number alone proves readonly_shm behavior. Build/CI executes the paired RV tests
and installs a code-owned qualified-runtime entry; unknown builds refuse live
views with unsupported_version before state opening. This initial proposal's
diagnostic qualifies only the observed runtime as a design input, not a future
image or every Python 3.12/3.13. Adding a supported runtime requires actual paired
tests and reviewed entry. Runtime status/doctor must not run qualification by
creating probe DBs in a user's state or silently download/recompile SQLite.

## stopped_clean: truly excluded writers, not immutable live fallback

Acquire existing owner EX first, then view SH, without upgrading a held view lock.
If owner is busy, this path returns owner_busy; it must release what it owns and
let the caller explicitly attempt the live path. Missing locks are unavailable,
not initialized by a read. Hold both locks until the connection has closed.
No writer/startup/maintenance/credential participant may replace DB state under
that owner. Other ordinary stopped readers must serialize behind owner EX.

Require DB present/safe and WAL, SHM and rollback journal all absent, even zero
length. Require no unfinished bootstrap/maintenance publication or evidence of
crash recovery required by the existing lifecycle markers. Mere missing sidecars
cannot legitimize a manually copied/imported/unrecognized state. The original
validated initialization/restore lineage and current schema/instance are still
mandatory. Absence of WAL under genuine stopped ownership permits this strategy;
the provider must never delete/checkpoint a WAL to manufacture the precondition.

Open with literal `mode=ro&immutable=1&cache=private&vfs=unix`. This immutable
promise lasts exactly while owner EX excludes every legitimate writer, view SH
blocks replacement, the same DB inode remains and the connection is alive. It
is not a stored "immutable DB" setting. Before and after attach/read, recheck
same root/lock/DB identities and continued sidecar absence. Any new sidecar or
changed lifecycle refuses and invalidates the read; never return partial rows.
Close SQLite before releasing view SH then owner EX. Unknown/leftover sidecars
stay untouched and produce maintenance_required; actual recovery is a separately
authorized writer task, not read-only inspection.

## live_wal: no initialization or crash-recovery adoption

Acquire view SH on the existing verified inode. Require the actual selected live
daemon's private ready socket, peer UID/PID identity and retained pidfd; root's
existing socket/owner readiness contract binds that peer to the current owner.
Verify it is alive and owner is held. Any nonblocking owner-lock probe must release
immediately if it unexpectedly succeeds, release view and return owner_unavailable;
never upgrade/wait for owner EX while holding view SH. Bind the lifetime to that
exact peer pidfd, not PID text or "some owner now holds the lock". No Gmail call
or new wire command is used merely to obtain SO_PEERCRED/pidfd evidence.

Require DB plus both WAL and SHM already present, safe and readable, and no
rollback/unfinished lifecycle marker. All three file identities must remain
stable; byte contents may change only from the legitimate writer. An existing
SHM file alone is not proof of initialized/live ownership. Open only with
`mode=ro&readonly_shm=1&cache=private&vfs=unix` on a qualified runtime. Never add
immutable. Before schema SQL check identities/liveness again; after a read check
again before returning any result. Owner death, changed entry or SQLite refusal
invalidates the context and returns a fixed unavailable/maintenance category;
do not retry with writable SHM, rebuild sidecars or reinterpret dead-owner WAL
as clean stopped. The connection does not adopt SQLite's heap-WAL recovery
success as authoritative Facet post-crash readiness.

M1-03 must acquire view EX around any normal close/reopen of its final writer
connection, sidecar-removing lifecycle operation and state replacement; no such
close may race an active view SH. Its owner EX remains held while waiting for
view EX; no view reader blocks on owner while holding SH. Normal commits can
continue with SQLite concurrency and do not acquire view EX. A crash bypasses
graceful close but leaves sidecars; pidfd death makes readers refuse results, and
new startup cannot repair/remove them until it obtains view EX. Before/after
checks plus these actual producer invariants close the preflight/open race for
cooperating actors. Root's stop/maintenance draining must honor this lifecycle.

### Whole reader-process connection provenance

SQLite's unix VFS may reuse an existing process-global SHM node for the same DB
inode before interpreting a later readonly_shm flag. Ordinary mode=ro is also
disallowed: its DB cannot be written, but it can have established a writable SHM
node. Exact identity is device/inode, not path spelling. Unknown connection
origin, prior ordinary-ro/RW handles, another binding/native SQLite entry point,
uncontrolled concurrent open, inherited process state or uncertain close makes
this process ineligible. An empty application registry alone proves none of this.

M1-03 must provide a genuine isolated read-command bootstrap before enabling
these openers. It launches the selected existing bounded CLI read command in a
fresh interpreter with `-I -S`, close_fds=True, no inherited SQLite handles and
no user/PYTHONPATH/sitecustomize imports. It uses a fixed installed application
bootstrap file, not code/path from the CLI/config/DB. That minimal standalone
entry runs before importing facet/SQLite/third-party modules; it installs the
connection audit admission guard, establishes the seal, then adds only its fixed
reviewed installed-package locations and imports the read command. Absence of
this real entry path is owner_unavailable, not an invitation to mark an already
running arbitrary interpreter sealed. A normal flag/environment variable cannot
select or emulate a valid seal. A reused daemon interpreter is not eligible.

The bootstrap's private `_seal_read_process() -> ReadProcessSeal` is single-use
and rejects preloaded sqlite3/_sqlite3 or an existing/invalidated seal. Its claim
of fresh execution is justified by the reviewed launcher/isolated entry and
actual subprocess tests, not just sys.modules inspection. Native SQLite access
outside CPython sqlite3 is excluded from this fixed process's reviewed import
graph; an audit hook is not advertised as a sandbox against malicious native or
same-process code. Uncontrolled launchers/import graphs cannot register a seal.

Every CPython sqlite3 open in that process is admitted by the fixed producer
under the seal's process-wide mutex BEFORE connect: exact inode, active lease,
mode/URI and creator thread are recorded as opening, then the one returned exact
connection is bound. The CPython connect/handle audit events must agree with that
single in-progress opening; direct/ordinary-ro/RW/unregistered opens refuse
before SQLite open and invalidate the seal. The only non-file exception is one
fixed in-memory runtime-identity probe during bootstrap, closed before state
opening. No caller-supplied path/URI or library may request that exception.

For one DB inode, concurrent leases are allowed only when every opening/open
connection has this seal and the same qualified strategy: live_wal with the
readonly_shm URI, or stopped_clean sharing the same genuinely held stopped
owner/view lease and immutable URI. Mixing modes or an unknown handle refuses.
Serialize open/bind/close transitions through the mutex; do not remove inventory
entries until sqlite3.close completed. Uncertain close or bypass evidence
irreversibly invalidates the seal and all reads; do not clear a registry and
claim a writable node disappeared. After all known handles close normally, a
later opening repeats full filesystem/owner preflight. Forked contexts cannot
reuse the seal; only a fresh exec of the same controlled entry qualifies.

These requirements are actual M1-03 producer/launcher work, not a new long-lived
worker or ASGI process. Rendering and existing CLI output validation happen in
the isolated read-command context; raw ReadSession/rows do not cross a new generic
IPC API. The coordinating CLI retains no DB connection and forwards only that
existing command's permitted output/exit. The daemon actor uses its existing
bounded read mechanisms to materialize cached aggregate snapshots and never
invokes this external opener. HTTP stays cached-only. Test-only factory/seal
registration cannot stand in for the production launcher and import graph.

ReadSession retains its permit/lease until close and invokes the fixed lease
checks before/after each materialized read. Fork, another thread, lost lease or
use-after-close refuses before SQL. On failure, discard results and close the
owned SQLite connection first, then release provider resources/locks. Raw
unregistered caller connections are rejected before SQL without adopting their
cleanup obligations. No callback/network wait runs inside a DB transaction.

## Paired acceptance and integration stops

| ID | Required actual positive/negative control |
| --- | --- |
| RV-01 | Reproduce ordinary ro creation and readonly_shm-only missing-WAL creation in test-owned directories; oracle catches both, not merely SQL transaction changes |
| RV-02 | Real stopped initialized schema, owner EX/view SH, all sidecars absent: immutable supplied connection + permit reads correct rows and leaves names/inodes/sizes/digests unchanged through close |
| RV-03 | Separate real live writer with committed WAL-only data, existing safe sidecars: qualified readonly_shm view reads actual committed value, never a stale main-only value; quiescent bytes unchanged |
| RV-04 | Absent DB/lock/WAL/SHM, unsafe permission, symlink and parent/root/sidecar replacement refuse before schema SQL/open repair; no create/chmod/unlink/empty DB |
| RV-05 | Writer graceful close waits on view EX while reader holds SH, then proceeds after reader connection closes; owner/view ordering has no upgrade cycle |
| RV-06 | Kill exact live owner before open, between connect/check/inspection, during read and before return; no success after observed death, no persistent recovery or file creation, no admission of a replacement PID/owner |
| RV-07 | Crashed leftover WAL/SHM, zero sidecars and unfinished maintenance markers reject stopped mode unchanged; no immutable fallback or WAL deletion; restore fence remains visible/uncleared on valid structural reads |
| RV-08 | Wrong/missing/forged/reused permit or process seal, writable/prior-used/unregistered connection, wrong instance/PID/thread and expired lease refuse before SQL. Test ordinary-ro retained connection plus separate-writer commit then readonly_shm in the same child as a detecting SHM-byte-change negative control; genuine sealed bootstrap rejects that first unauthorized open, including concurrent or alternative-path same-inode attempts |
| RV-09 | Qualified readonly_shm-only multi-reader child reads committed updates without reader SHM byte change; close/reopen, fork, concurrent admission and uncertain-close cases exercise full inventory lifetime. Ignored/unsupported URI/VFS or unqualified process rejects before state access, never falls back to ordinary ro. Run isolated-entry positive and sitecustomize/preloaded/forged-seal negatives; test-only factories are not production readiness |
| RV-10 | Each fixed repository read remains bounded/materialized; read errors/caught exceptions/close do not leak raw SQL/path/rows, do not leave transaction/lease active, and do not write state |
| RV-11 | Actual M1-03 private socket/peer/pidfd, owner startup/close/restore and static provider registration tests replace test-only leases before managed CLI/G1 runtime gate can close |

Snapshot names/inodes/sizes/byte hashes and syscall probes against synthetic files
are complementary; timestamps/atime alone are not a no-write oracle. In concurrent
positive controls distinguish writer-originated DB/WAL changes from reader
actions; do not assert frozen bytes while intentionally committing new writes.
Never weaken no-create because an unsuccessful read happened to leave a file.

M1-02 can implement and independently test its permit/attach/session integration
with real test-owned producers after approval. M1-03's real producer and the
stated close/read lifecycle extension require explicit aligned source scope and
independent review; absent production provider keeps managed reads unavailable.
DB-21 library evidence and actual runtime/G1 evidence must be reported separately.
This proposal does not close full M1-02, backup/restore, OAuth, Gmail or Compose.

## Proposed r3: finite private bridge construction and test-consumer allocation

This appendix requires a new independent review before source. Preserve the first
346 lines, accepted r2 SHA256
`0f282903bae9a311cffe6c3609125cf6382eda30b0c0f653ac33dae2298be602`.
It specifies the previously unnamed construction/registration seam, not a weaker
permit, production provider or exception to isolated-process provenance.

All definitions below are private to `facet.db.read_views`; no root package
re-exports or public registration method. Its production constants initially are
`_PROVIDER_TYPES=()` and `_QUALIFIED_RUNTIMES=()`. M1-02 does not import a missing
M1-03 module or invent a working producer. Enabling a real provider later is a
reviewed source change to these compiled exact class/runtime inventories, with
the actual M1-03 entry/lifecycle evidence. Config, environment, setuptools entry
points, import strings and arbitrary callbacks cannot populate them.

Allocate one additional storage-private immutable value, `ReadRuntimeIdentity`,
with all required fields: `python_version:tuple[int,int,int]`,
`sqlite_version:tuple[int,int,int]`, `sqlite_source_id:str`,
`compile_options_digest:Sha256Hex`, `architecture:Literal['x86_64','aarch64']`,
`platform:Literal['linux']`, `vfs:Literal['unix']`. Version elements are exact
nonnegative ints, bool rejected; source ID is nonempty ASCII, at most 256 bytes,
without controls. Compile digest hashes UTF-8 sorted compile-option strings
joined with newline and one final newline (empty list encodes empty bytes).
This is a qualification key, not permission or a public DTO. Its values must
equal actual runtime probes AND a qualified compiled entry before state access;
constructing a matching object alone does not prove bootstrap provenance.

Opaque constructors raise fixed invalid_input; only the following private
factories allocate and enroll exact objects in bridge-owned identity registries.
Every registered object has a fixed safe repr; no `__dict__`, serialization or
public mutation. The slots are finite:

| Object | Exact private retained fields |
| --- | --- |
| ReadProcessSeal | provider, runtime, creator_pid, creator_thread, invalidated, leases, permits |
| ReadViewLease | seal, mode, db_identity, wal_identity, shm_identity, creator_pid, creator_thread, active |
| ReadViewPermit | connection, expected_instance, lease, seal, creator_pid, creator_thread, phase |

Here leases/permits are internal identity sets, never caller-supplied collections.
phase is the private literal bound/attached/closed; these are not persisted core
enums. Stopped leases have null WAL/SHM identities; live leases have both. The
provider retains actual OS descriptors, connection-opening inventory/mutex and
peer resources keyed by the exact enrolled lease. That state is not a new SQL
record and is not supplied to the bridge as an arbitrary dictionary.

```text
_issue_read_seal(provider: object, runtime: ReadRuntimeIdentity) -> ReadProcessSeal
_issue_read_lease(seal: ReadProcessSeal, mode: ViewMode) -> ReadViewLease
_bind_read_view(connection: sqlite3.Connection, expected_instance: LocalId,
                lease: ReadViewLease, seal: ReadProcessSeal) -> ReadViewPermit
```

For `_issue_read_seal`, require type(provider) exactly one compiled provider class
(no subclass/duck typing), validated runtime, current PID/thread, no prior seal
for this provider/process and its successful fixed bootstrap check. The provider
is bound to the selected genuine HeldPrivateRoot by M1-03; these factories take
no string path or new root. Missing production inventory returns owner_unavailable
before touching provider attributes or SQLite. A registered class/runtime mismatch
is controlled unavailable/unsupported_version, not permission to skip checks.

The registered class implements exactly these bridge-facing lifecycle methods;
invoke its fixed class method with the provider instance, not an instance-assigned
callable. They either complete/return the listed value or raise StorageFailure:

| Fixed method | Exact allocation / responsibility |
| --- | --- |
| `_check_bootstrap(runtime:ReadRuntimeIdentity) -> None` | Genuine isolated entry, audit guard and empty pre-state provenance from r2; no "fresh" boolean input |
| `_acquire_lease(lease:ReadViewLease, mode:ViewMode) -> tuple[FileIdentity,FileIdentity\|None,FileIdentity\|None]` | Acquire actual mode-specific OS lifecycle, retain resources under that exact lease; return DB/WAL/SHM identities only after preflight |
| `_check_lease(lease:ReadViewLease) -> None` | Nonblocking actual identity/lock/peer/process checks from r2, before/after each read |
| `_claim_connection(connection:sqlite3.Connection, lease:ReadViewLease) -> None` | Claim exactly one fresh connection already opened by this producer under the seal's audit/mutex inventory; reject foreign/prior-used/already-claimed objects |
| `_closed_connection(connection:sqlite3.Connection, lease:ReadViewLease) -> None` | Only after SQLite close succeeds, retire its inventory entry; failure invalidates seal, never asserts clean shared-memory state |
| `_release_lease(lease:ReadViewLease) -> None` | Release retained resources only after all its connections closed; fixed SQLite-before-view-before-owner order |

The provider's connection opener remains its r2 mode-specific method, not a new
generic callback to M1-02. It calls `_issue_read_lease`, admits/opens the literal
URI under its real process inventory, then `_bind_read_view` and `_attach_view`.
`_issue_read_lease` first validates enrolled noninvalidated seal/PID/thread and
exact mode, allocates an inactive provisional lease, then calls `_acquire_lease`.
Validate its exact tuple/identity types and mode-specific nullability, fill the
identities, mark active and enroll only after success. The provider owns and
unwinds any partially acquired resources on its acquisition failure; a provisional
lease never authorizes connect, bind or reads. Neither caller supplies identities
as proof nor can an inactive lease be attached.
Binding checks enrolled seal/lease identity, equal PID/thread and active lifecycle,
calls fixed `_check_lease` and `_claim_connection`, then enrolls a bound permit.
Attachment consumes bound→attached exactly once, before any PRAGMA/schema SQL.
ReadSession retains that same permit; checks validate identity-set membership,
active lease/seal and the fixed provider checks, not merely populated slots.
Copy/object.__new__/unregistered constructors never enroll identity. There is no
arbitrary callable field or method to change the provider of a live object.

Failures during acquisition/bind/attach clean up only actually acquired owned
resources. Failures after owned connection acceptance close SQLite first and
retire inventory only after confirmed close, then release the lease. A close
failure invalidates the entire seal and prevents all future SQL; it cannot be
treated as successful deregistration. Foreign unclaimed connection ownership is
not adopted on rejection. Preserve fixed errors without original SQL/path context.

### M1-02 test producer, not a hidden production provider

Only tests may temporarily monkeypatch the two private compiled constants to
the exact test-defined provider class and an actually qualified test runtime.
The class/helpers and replacement are under tests, excluded from wheel/runtime;
there is no shipped test provider, fixture import, environment switch or generic
registration function. Test helper methods must hold real OS resources and
exercise the same finite calls/actual audit admission, not simply return None
for OS/provenance checks. Runtime entries are justified by actual RV paired
behavior on that binary; do not derive an "approved" entry solely by echoing its
version fields. An unpatched ordinary production import keeps both tuples empty.

Broad existing repository tests must NOT replace a naked same-process RW+ro
reader with a fabricated permit. Use two explicitly different test arrangements:

1. Pure repository materialization/closed-row semantics may use a stopped
   synthetic metadata snapshot created by the real SQLite backup API after the
   tested commit. A fresh isolated test reader process exercises the genuine
   stopped lease/permit/read path and the same fixed case assertions. Snapshot
   initialization, file ownership and absence of sidecars are independently
   checked; no main-file-only copy. This proves contents at that snapshot, not
   live visibility or real production bootstrap readiness.
2. Any case asserting active WAL visibility, concurrent writes, view locking,
   current instance/lifecycle or sidecar behavior uses separate real writer and
   sealed reader processes on the SAME DB inode. Keep RV-01..11 and the original
   assertions; do not turn a concurrency/live test into a snapshot test.

Test-only child case runners may exchange bounded synthetic inputs/results and
execute predetermined test assertions; they are not a product generic SQL/row
IPC and are not packaged. The child begins through the isolated test bootstrap
before SQLite import, installs its actual admission guard, then registers the
fixed test provider and creates the seal. The parent pytest process's old SQLite
handles cannot establish child capability or leak through exec/close_fds.

Additional paired checks: empty shipped registry refuses before SQL; forged exact
opaque objects lack enrollment; a second bind/attach refuses; direct constructor,
ordinary-ro and unregistered concurrent opens are rejected before open; real
same-strategy multiple leases close in order; poison/uncertain close prevents
reuse; packaging inspection finds no test provider. All earlier real M1-03
bootstrap/import-graph/provider and runtime/G1 gates remain pending, even if
M1-02 bridge and synthetic isolated-test consumers pass.

## Proposed r4: two-stage isolated bootstrap handoff

Independent review requested this one ordering correction to r3: a final typed
ReadProcessSeal needs actual SQLite runtime facts and the provider class, so it
cannot exist before importing those modules. Preserve the first 487 lines and
r3 SHA256 `df3041e81ff351f25a24d360d0fb39f5b3b0482b35758824e59430f7e76db943`.
This appendix replaces only the contradictory pre-import-final-seal wording in
r2 and its repetition in the r3 test-runner paragraph. The r3 bridge factories,
empty production registration and actual M1-03 integration gates remain intact.

### Stage A: pre-import guard/latch, not a final seal

The fixed standalone M1-03 `read_bootstrap.py` entry, invoked by the reviewed
fresh `-I -S` launcher with close_fds, first calls private
`_begin_read_bootstrap() -> ReadBootstrapLatch`. This is the replacement for the
previous pre-import `_seal_read_process()` wording. It imports only the reviewed
minimal standard-library bootstrap dependencies and rejects already loaded
sqlite3/_sqlite3, application/provider modules, an existing bootstrap latch or
wrong PID/thread. Checks of preloaded SQLite happen HERE, exactly once, before
the guard is installed, not again after the authorized probe imports SQLite.
Failure terminates this read-command context; no clearing sys.modules, resetting
the registry or creating another latch makes a contaminated interpreter trusted.

ReadBootstrapLatch is M1-03-private, not a DB/core export, serialized token or
public constructor. The real entry creates one exact object retained by its
installed audit-hook closure; only that enrolled identity is valid. Its finite
fields are creator_pid, creator_thread, phase, probe_connection, runtime_facts
and provider. phase is installed/probing/probed/claimed/invalidated; nullable
fields are populated only by the transitions below. A plain bool, copied object,
manually populated fields or caller-selected bootstrap filename is not accepted.
The real isolated launch/import graph is still necessary evidence: module absence
alone does not certify a fresh process.

The guard is installed before importing SQLite. In installed/probed phase it
rejects every SQLite connect/handle event. In probing phase it admits only the
one exact `:memory:` open made by the latch's fixed probe method on the creating
thread, followed by its matching exact returned connection handle. Unexpected
events invalidate the latch before state-file opening. No provider/config/env
value can enable an additional open or choose the probe database.

### Stage B: one memory probe, then final registered seal

The only pre-seal probe is private `latch.probe_runtime()`, returning the exact
tuple `(python_version:tuple[int,int,int], sqlite_version:tuple[int,int,int],
sqlite_source_id:str, compile_options:tuple[str,...],
architecture:Literal['x86_64','aarch64'], platform:Literal['linux'],
vfs:Literal['unix'])`. It is callable once from installed; the forced VFS literal
must match the runtime qualification entry, not a user selection. It switches to
probing, imports the actual CPython sqlite3,
opens one `:memory:` connection with autocommit=True and runs only the fixed
`SELECT sqlite_source_id()` and `PRAGMA compile_options` queries. Together with
the actual Python/SQLite version and Linux architecture, these form the primitive
runtime facts needed by r3. It closes that connection successfully before changing
to probed, clears probe_connection and retains the exact observed facts. Query,
audit or close failure permanently invalidates the latch; no fallback probe,
state path, alternate SQLite binding or caller-supplied facts are allowed.

Only after probed may the entry add its fixed installed package locations and
import `facet.db.read_views` and the statically selected M1-03 provider module.
Those imports cannot open SQLite connections; the audit guard still denies them.
Construct ReadRuntimeIdentity from the retained facts using r3's exact digest
encoding and validate against the compiled qualified-runtime inventory. The
provider is constructed with this genuine latch and the genuine selected root;
neither constructor creates a final seal or touches state SQLite.

Call the unchanged `_issue_read_seal(provider, runtime)`. Its r3 type/runtime/
PID/thread checks run first. The fixed provider `_check_bootstrap(runtime)` then
consumes the latch through private `latch.claim(provider, runtime) -> None`:
require the enrolled latch identity, probed phase, same PID/thread and exact
equality to its retained runtime facts. Bind this exact provider identity and
transition once to claimed. Reuse, substitution or changed runtime invalidates;
there is no repeat rejection merely because the permitted SQLite import is now
present. The bridge factory now creates/enrolls the final ReadProcessSeal. If
that allocation fails after claim, terminate/invalidate rather than reissue.

After claimed, the installed guard routes only the two fixed CPython audit
events to the claimed compiled provider's fixed class methods
`_audit_connect(database: str) -> None` and
`_audit_handle(connection: sqlite3.Connection) -> None`. They enforce r2's exact
in-progress opening/mutex/URI/connection inventory; neither is supplied as a
callback argument nor configurable. No opening is admitted until that provider
owns its enrolled final seal and a live issued lease. Other SQLite opens remain
forbidden, including additional memory probes. Errors retain only fixed codes.
These two methods are M1-03 bootstrap-driver methods, in addition to r3's six
bridge-facing lifecycle methods; M1-02 does not implement a fake driver for them.

The actual production entry, latch/audit driver and qualified provider are still
M1-03 work. M1-02 test fixtures implement the same two stages in their isolated
test-only launcher before loading the fixed test provider and monkeypatching the
two empty compiled inventories. They may not import the ordinary test suite or
SQLite first and then fabricate a latch. There is no import-time production
bootstrap side effect and no new generic bootstrap framework.

Required order controls augment RV-08/09: genuine fresh child demonstrates guard
installed → one memory probe closed → provider imported → final seal → state
connection; direct connect or Connection before admission rejects; preloaded
SQLite, duplicate probe, file-path probe, altered runtime facts, forged/reused
latch, provider import that opens SQLite and post-probe extra memory open all
refuse. The positive sequence must not fail its initial-only preload check after
the legitimate probe. Isolated import and inventory tests do not substitute for
actual production entry/OS lease implementation or open the M1-03/G1 gate.
