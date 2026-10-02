# M1-03 bounded OS root and lock foundation plan r1

Status: proposed for independent review; no source dispatch or runtime capability.
Authoring HEAD: `1b7cd58b4846aab86edcbb781a999abb968d047c`.
Read-only integrated input: main `ff77e63a823dc8bcb130836243746c067778b94f`.
This file is the sole current writable scope. Other owned proposals remain frozen.

## Inputs, dependencies and deliverable

Preserve approved writer plan SHA256
`3934f2a4d6bc1cf0e0ebf4748cd1ed8be426cc7a04f785ca5d1641ed5beaa64c`,
writer extension
`3b9dc3e637ba727589768f0055c746193809f7e0fcd07bc94839dd565a0110c8`
and read-runtime integration
`9d28e18cee3dbaed00c939838686a6b715cefb569c268a4f3e73a0d1cc6c660e`.
They allocate the ownership behavior; this plan closes only the low-level callable
and file allocation. It does not change canonical M1-02/M1-03 dependencies or G1.

Actual M1-01 core/config, P1-02 foundations and M1-05 safe errors/logging are in
the integrated input; M1-04 there is pure values/codec, not an OAuth participant.
SQL `eb7dde4ff33c349b3a5e7270c5ac480a292f425b` is an inspected bridge input,
not the final DB21 acceptance candidate. Its production provider registry is empty.
Moving isolated-reader helpers and test producers do not establish runtime trust.

Before SOURCE: this plan must pass independent review; root must identify an
independently qualified exact DB21 library candidate and its CI, assign a distinct
worker/file owner, record actual implementation base/input SHAs and dispatch the
bounded slice. Root/integration decides base carry, not this document. Parallel
low-level work must not claim the remaining actions/migration/restore repositories,
whole M1-02 or canonical M1-03 integrated. Material input drift returns to review.

Deliver only real private directory descriptors and stable OS advisory locks.
No SQLite import/open, schema, SQL transaction, read seal/permit, DB21 registration,
CLI route, socket/actor, command codec/journal, bootstrap receipt, owner-run
publication, credential access, backup, migration or restore is implemented here.
No Gmail/network operation, dependency/CI change, private-state inspection or
deployment. Empty scaffolding is NOT initialized Facet state or accepted work.

## Exact future file scope and mapping

| File | Allocation |
| --- | --- |
| `src/facet/runtime/__init__.py` | Empty package marker only; needed to implement the already allocated runtime package, no re-exports or import effects |
| `src/facet/runtime/private_root.py` | LockFailure, opaque HeldPrivateRoot, existing traversal, explicit scaffold creation, descriptor/creator checks and local lifecycle bookkeeping |
| `src/facet/runtime/locks.py` | LockMode, opaque LockLease, the fixed owner/view/key acquisition/check/release functions below |
| `tests/unit/test_runtime_lock_values.py` | Exact input/closed-error/opaque identity and import-side-effect controls |
| `tests/integration/test_runtime_os_locks.py` | Actual process contention, descriptor/path/lifecycle/fork and zero-write tests |
| `tests/integration/runtime_lock_child.py` | Fixed synthetic child test cases only, no arbitrary operation/path execution endpoint in the product |
| This plan | Actual input alignment and evidence appendix without altering accepted prefix |

The old proposed `src/facet/db/lock.py` and `ownership.py` responsibilities map
solely to these two runtime modules. Do not create those old modules, a parallel
`runtime.py`, a second root opener or compatibility re-exports. Existing
`src/facet/private_paths.py` remains unchanged: its structural inspection cannot
mint HeldPrivateRoot. Future actor module filenames remain for that separate plan.
The empty initializer is the only mechanical file beyond the two assigned modules;
independent review includes it before any implementation. No shared conftest,
core enum, source in another package, status/README/AGENTS or lockfile edits.

## Finite types and signatures

All names here are private package contracts, not CLI/public DTO exports. No
caller-selected function, arbitrary filename, callback, flags map or FD argument.

In private_root.py:

```text
open_existing_root(path: str) -> HeldPrivateRoot
create_lock_root(path: str) -> HeldPrivateRoot
check_root(root: HeldPrivateRoot) -> None
close_root(root: HeldPrivateRoot) -> None
```

HeldPrivateRoot is exact, opaque and identity-enrolled, not a caller-constructible
dataclass. It retains the canonical lexical absolute path privately, creator PID,
strong `threading.current_thread()` object, every traversed ancestor FD plus root,
locks/, requests/, requests/locks/ FDs and original device/inode/UID/mode facts,
owned descriptor inventory, live leases, and state open/invalid/closed. Strong
identity registration plus live OS checks is necessary; construction alone grants
nothing. No property exports an FD, path or mutable inventory. Safe fixed repr.
`with root as held` checks and returns itself; exit calls close_root and never
suppresses a body exception. Exit with outstanding leases refuses owner_busy
without releasing their resources: callers must nest lease contexts inside root.

In locks.py:

```text
LockMode = shared | exclusive  # exact local StrEnum, not a core expansion
acquire_owner(root: HeldPrivateRoot) -> LockLease
acquire_view(root: HeldPrivateRoot, mode: LockMode,
             *, owner: LockLease | None = None) -> LockLease
acquire_key(root: HeldPrivateRoot, namespace: LocalId, nonce: LocalId,
            *, view: LockLease, create: bool = False) -> LockLease
check_lock(lease: LockLease) -> None
release_lock(lease: LockLease) -> None
```

Every acquisition is one nonblocking attempt, never an internal retry/sleep or
deadline policy. View EX requires the exact live same-root owner lease. View SH
may omit owner; when supplied it must be the actual same-root owner lease.
Key always EX; its exact name is `rq1_<namespace>_<nonce>.lock`, with both actual
LocalId UUID4 validators, not a new RequestId implementation/export. `create` is
exact bool. False opens existing only; True permits exclusive creation of that
single stable lock while the supplied view SH/EX is held, for later explicit
mutation callers only. It does not authorize a request or create a journal.

LockLease retains exact root, creator PID/strong Thread, kind owner/view/key,
mode, optional key pair, one privately owned FD/identity, parent owner/view lease
where required, enrolled identity, and held/invalid/released state. No exposed FD,
subclass, serialization or caller constructor. `with lease as held` checks/returns
itself; exit releases and does not suppress. Re-entering a live context refuses.
No lease duplication, transfer, lock conversion or reentrancy. A process-local
inventory rejects overlapping acquisitions of the same lock inode from this
library, including another root object/thread; readers use distinct processes
for simultaneous SH. This restriction avoids self-deadlock and does not constrain
cross-process SH sharing. Future in-process sharing needs a separate design.

LockFailure has exactly a valid fixed ErrorCode and constant safe args/str/repr;
no rejected value, path, errno text, original exception or copied traceback is
stored in its fields/args; native Python traceback is never formatted/exported.
No context/cause is retained. Error mapping: malformed exact input -> invalid_input;
unsafe type/UID/mode/link/path -> scope_required; absent existing infrastructure
or unavailable Linux primitives -> owner_unavailable; lock contention/outstanding
dependent lease -> owner_busy; replaced identity/foreign creator/invalid lifecycle
-> owner_unavailable; actual creation/fsync/close IO failure -> persistence_failure.
No raw OSError formatting. Construct/raise outside caught-exception context; test
both __context__ and __cause__. Existing M105 presentation consumes only the code.

## Existing traversal versus explicit creation

Inputs are exact strings, absolute lexical paths, nonempty/no NUL, bounded to
4096 UTF-8 bytes, at most 256 components, each at most 255 bytes. Reject `.`/`..`,
empty repeated components, trailing slash, root `/`, symlinks and `.facet-spike`
components; no tilde/environment expansion, realpath fallback or caller Path hooks.
Identity comparisons, not string equality, handle any remaining same-inode aliases.

Walk from `/` using retained O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC descriptors and
dirfd-relative operations; reject non-directory components before further work.
Traversal ancestors must be owned by root or effective UID and have no group/world
write bits (and no special permission bits). They need NOT be user-owned 0700.
Thus normal root-owned 0755 ancestors are legal; root-owned sticky writable /tmp
is not a trusted ancestor under this finite policy. Private root and the three
managed directories must be effective-UID owned, exactly 0700 with no special bits.
Do not chmod/chown permissive entries. Supporting a different traversal policy
requires explicit reviewed alignment, not a test-only exception in production.

Existing mode opens only already present directories and owner/view lock files.
Stable lock files are regular effective-UID-owned 0600, nlink=1, size=0; no FIFO,
socket, device, directory or lock-file contents. Use O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK,
never CREATE/TRUNCATE; verify fstat and named no-follow identity. Use read-only
FDs for existing locks on the supported Linux flock path. Keep them for the root
inventory inspection only if needed; acquisition must use a separately owned FD,
never duplicate/reuse a root inspection FD as the lease's open-file description.
Do not read config, credentials, DB, receipts or directory entries unrelated to
the allocated lock infrastructure. No root/lock creation, fsync, marker repair,
content/mtime change or permission adjustment on existing/read paths.

Explicit create_lock_root is solely the later bootstrap's scaffold primitive.
Its parent must already pass trusted traversal. Create only the final root,
locks/, requests/, requests/locks/ with mode0700 and owner/view files with0600;
no recursive arbitrary parent creation. It may converge on an empty/pre-existing
exact partial scaffold: root entries subset {locks,requests}, locks entries subset
{owner.lock,view.lock}, requests entries subset {locks}, requests/locks empty.
Unknown entries, existing config/DB/receipt, unsafe/truncated/nonempty lock files
refuse; never adopt existing initialized state through this creation path.
Check before any creation; revalidate at each publication. Concurrent creators
use mkdir/EEXIST and O_CREAT|O_EXCL, then validate the winner's actual inode, never
truncate or replace it. No broad cleanup: a partial failure leaves its empty
safe scaffold for inspection/retry; it does not delete another creator's entries.
fsync each newly created regular file and containing directory in publication
order. Mode must be exact after creation; an incompatible restrictive umask
causes fixed refusal, not chmod. Do not change global umask.

Scaffold success does not acquire owner or mark initialization accepted. A future
bootstrap must acquire owner EX then view EX and execute the reviewed key/receipt
protocol before any config/DB effects. That consumer is explicitly outside this
slice. HeldPrivateRoot here proves path/lock resources only; actual initialized,
maintenance and restore receipt checks remain mandatory in the future managed
provider before its separate ReadViewLease/ReadViewPermit can be minted.

## Lock checks, ordering and failure cleanup

Before every operation, check exact enrolled class, original PID and strong Thread
by `is`, then local phase, then descriptor/entry identities; foreign/forked callers
refuse before syscall, mutation, poisoning or cleanup of the genuine owner.
Rewalk the retained ancestor chain from `/` and compare every named child with
its retained FD, UID/mode/device/inode. Recheck before and after lock acquisition,
creation and every explicit check; reject root/parent/lock-directory relocation.
This is trusted-runtime advisory coordination, not a sandbox against root or
same-UID arbitrary native/file writes between checks. No DB effects exist here.

Order: owner EX before optional view; view before key. The local inventory rejects
owner acquisition while that root has a held view/key, view SH->EX conversion,
recursive view acquisition and a second key while one is held on that root.
Parent release with live child leases returns owner_busy and leaves it held.
Normal release is key -> view -> owner; close root last. Check key also checks
its actual view and that view's supplied owner, not just saved inode tuples.

Acquire uses LOCK_NB. On EAGAIN/EWOULDBLOCK: close only the new unacquired FD,
return owner_busy, and create no held lease. On other failure or post-lock identity
drift: close the newly owned FD, invalidate the affected root for new operations
where identity is uncertain, and return the fixed error. No lock-file deletion.
**A key failure does not release a caller-owned view automatically.** The actual
client/actor must put view in a finally/context and release it before retry or IPC;
this exact pattern is tested. Actor failures release temporary key/view only,
not its long-lived owner. Maintenance already holding EX never recursively takes SH.

Release uses close of the uniquely owned FD (not LOCK_UN), then marks released;
same-creator repeat release is zero-effect, not reuse authority. Invalidated own
leases/root can still be closed using their original descriptor identity, without
requiring the renamed pathname to recover. Before closing verify FD still belongs
to the recorded device/inode; never close a reused unrelated descriptor. Close
failure is uncertain: invalidate, remove that integer from all future automatic
cleanup inventories, report persistence_failure, and do not retry close on it.
No finalizer/atexit silently unlocks live application resources.
Consumers must stop protected work on check/close failure; production recovery
and process shutdown policy are not implemented by these helpers.

## Fork, descriptor inheritance and process qualification

All opened descriptors are non-inheritable/CLOEXEC; no fileno/dup/pass_fds escape.
Factories lazily install a fixed os.register_at_fork guard BEFORE their first FD;
import alone installs no hooks, opens files or changes logging. A private mutex
serializes only short inventory/open/close/acquire operations. Before-fork takes
it, parent releases it, and child closes every recorded inherited descriptor
without LOCK_UN, marks copied resources unusable and releases/resets its local
bookkeeping. Never close another process's descriptors or re-enroll copied objects.
Factories in a fork-copy interpreter refuse; fresh exec/spawn is required.
No lock is held across user code, sleeps or IPC by the bookkeeping mutex.

This is necessary because Linux flock follows the open-file description, and
fork/dup copies can otherwise keep the parent's lock alive or explicitly unlock
it. Tests exercise actual fork while the parent still owns EX. Native fork paths
that bypass Python hooks, arbitrary dup/FD export and unreviewed native import
graphs are unsupported, not magically blocked. The future actual runtime must
prove its fixed launch/import graph satisfies this rule before ownership use.
Thread-ID recycling is irrelevant: retain and compare the Thread object itself.
PID/thread validation alone is NOT proof of a kernel lock; actual flock and live
descriptor identity remain required. A PID file is never used.

## Paired acceptance, all planned

Tests create synthetic roots in a private temporary directory under a verified
non-writable-ancestor test workspace; do not weaken traversal for pytest's /tmp.
Only freshly spawned test child PIDs may be signalled; bounded coordination pipes,
timeouts and finally cleanup are mandatory. Children independently forbid external
network. No copied production state, credential fixtures or test helpers in wheels.

| ID | Real positive and detecting negative controls |
| --- | --- |
| OL01 | Existing safe root/0755 trusted ancestors open/check/close with identical tree/content/modes/mtime; missing root/lock/requests path refuses with zero creation |
| OL02 | Explicit fresh scaffold and two concurrent creators converge on identical stable inodes; partial exact scaffold retry works; unknown config/entry, unsafe existing modes and restrictive umask refuse without repair/overwrite |
| OL03 | Two real processes owner EX contention; owner context exit/SIGKILL allows another actual flock, not PID-based takeover; no deletion/replacement of stable lock |
| OL04 | Two process view SH coexist; owner+view EX refuses while SH exists and later succeeds; same-process recursive acquisition/upgrade/reverse-order refused without releasing original |
| OL05 | Same-key clients contend; failed try-key caller finally releases SH so owner can acquire EX; success releases key/SH before simulated IPC barrier; cross-key identities cannot select another path |
| OL06 | Root/ancestor/locks/requests/key-dir or file inode replacement, symlink, hardlink, FIFO, nonzero lock content, wrong UID/mode and writable ancestor refuse; original FD cleanup never closes replacement/unrelated FD |
| OL07 | Foreign live thread, exited creator with recycled integer ID, and fork-copy operations refuse without unlocking genuine owner; same-thread controls work |
| OL08 | Actual fork child remains alive after parent releases/exits: inherited copies were closed and contender succeeds; while parent holds EX contender remains busy; exec child inherits no owned FDs; detecting no-hook duplicate control demonstrates lifetime hazard |
| OL09 | Inject open/fstat/flock/fsync/close failures at allocated boundaries, including caught errors; verify no leaked acquired FD, no false lease, fixed error without cause/context/private sentinels, no cleanup unlink |
| OL10 | Root close with live lease and owner/view close with child lease refuse; reverse nested contexts close cleanly; own invalidated handle cleanup and repeated release cannot affect a later FD/lease |
| OL11 | Hostile/subclass path/enum/LocalId objects, malformed request IDs, boolean flags and exact scalar bounds are checked before hooks; safe repr/import stdout/stderr/log sentinel and no SQLite/network tests |
| OL12 | Noneditable wheel imports only empty package and finite modules without effects; full offline regressions/Ruff/format/safety and Python3.12/3.13 CI at exact candidate |

OL01–12 are OS-foundation evidence only, not complete WR-01/02/03/04/C01, DB21 RV11,
read-runtime RI01–07, second real daemon refusal, actual backup or G1 acceptance.
Existing WAL/process and private-output tests remain mandatory in their packages.
No skip/xfail/fake participant may replace the missing actual consumers.

## Sequence, risks and stop gates

1. Independent review of this exact file, then root records qualified exact DB21
   input/CI and actual base before assigning source. No source in this task.
2. Implement finite validation/resource foundation, real multiprocess locks and
   fork cleanup in atomic reviewed scope; add tests with the implementation, not
   a permissive initial API awaiting future hardening.
3. Run focused OL matrix, full locked offline suite, Ruff/format, CLI/spike help,
   repository safety and noneditable-wheel controls. Record exact test filesystem,
   Python/kernel facts; they do not qualify arbitrary Compose/NFS/SMB mounts.
4. Independent source/acceptance review and exact new CI before any merge decision.
   Shared docs updates remain the delegated integration owner's work.

Missing platform primitives, unqualified mount behavior, unsafe path, descriptor
uncertainty or a need for a new callable/owner consumer stops this slice at a fixed
error or review gate. Never broaden permissions or fall back to PID locks. The
future managed read provider must still validate actual receipts, qualified
runtime/isolated bootstrap and owner peer/pidfd; actual SQLite/actor/v2/Auth/M6
composition remains separately designed, reviewed and dispatched. No standalone
OS-lock success is evidence that the projection is initialized or safe to resume.

Primary references checked for these finite mechanics:
[Linux flock](https://man7.org/linux/man-pages/man2/flock.2.html) and
[Python process hooks/descriptors](https://docs.python.org/3/library/os.html#os.register_at_fork).
These explain OS lifetime constraints; they do not substitute for OL tests or
the actual production launch/import graph qualification.

## Source dispatch and input alignment

Root released this exact approved 294-line plan (SHA-256
`840f8ed7c1381b3fdf6f438a57a6eb392cc0654fb68f6c8370fd7291c99e079a`) to
`m103_os_source` on source base `ff77e63a823dc8bcb130836243746c067778b94f`.
The distinct worker owns only the finite files allocated above. Independently
qualified DB21 library input is `16bcd0b99bf1118924b214bf9ded3976813f5e1a`;
its [exact CI](https://github.com/GhostFlying/facet/actions/runs/37014341329)
passed Python 3.12/3.13. This is a separate finite library dependency, not a
source import or whole M1-02/RV11/G1 acceptance.

After the policy handoff, the OS branch normally merged reviewed main
`a57dd77116ea79b44c177d03bb6b9815a5913795` through user-identity merge
`764efc8dbeb8dae796173c42ff0eceffaa047f0c`, preserving original plan commit and
saved source bytes. PR #19 actually merged at that exact main SHA; its independent
review and [candidate CI](https://github.com/GhostFlying/facet/actions/runs/37017774954)
passed. Prospective routing now uses only Sol high/xhigh or Luna, with an
independent Sol reviewer for this source. The original accepted plan prefix and
finite APIs/strategy are unchanged. Actual OS verification, source review and
exact candidate CI remain pending; no real runtime provider or daemon is claimed.

## Offline source verification checkpoint

The bounded implementation now has 113 focused OS controls (49 unit and 64
integration cases); the final focused run passed in 10.86 seconds. The full locked
offline suite passed 721 tests in 24.27 seconds, retaining all 608 input tests.
Locked offline dependency sync, Ruff, formatting (99 files), both CLI helps,
production JSON version, whitespace and staged repository-safety checks passed.
No dependency, workflow, shared conftest, contract or existing production source
was changed.

OL01–11 cover actual Linux file/descriptor/kernel/process behavior and detecting
negative controls: unchanged existing trees/bytes/modes/mtime, concurrent scaffold
publication, owner/view/key contention, SIGKILL release, strong Thread identity
including observed integer recycling, inherited fork-copy closure versus a
deliberate no-hook lifetime hazard, CLOEXEC, named inode/ancestor drift, reused FDs,
hierarchical release and injected open/fstat/flock/fsync/close failures. Native and
caller-handler synthetic private errors leave no context/cause or unsafe repr.
The fixed lock-file allocation is checked even when a root or ancestor itself is
named `owner.lock` or `view.lock`; no new API or path policy was introduced.

OL12 local wheel controls passed after an offline build and fresh noneditable
installation: archive/source/installed runtime bytes match, the initializer is
empty, only the three runtime files are packaged, and no tests/helper/docs are
included. Imports open no state, install no fork hook, change no logging, create
no network participant and import no SQLite/provider/CLI/spike modules. The build
tool's cross-filesystem hardlink warning fell back to ordinary copying; all
installation and exact-byte/import checks succeeded.

Local execution used CPython 3.12.13 on Linux 5.15.120.bsk.3-amd64, effective UID
1001, and a synthetic tmpfs fixture beneath verified root-owned 0755 ancestors
and an effective-UID-owned 0700 anchor. The actual foreign-UID workspace ancestor,
symlinked home alias and sticky writable temporary ancestor were not exempted.
These checks do not qualify arbitrary Compose mounts, NFS/SMB, native fork paths
bypassing Python hooks, descriptor duplication/export or an actual runtime launch
graph. Consumers must stop protected work on descriptor uncertainty; consumer
shutdown/recovery is outside this slice.

Independent exact-source acceptance review and new Python 3.12/3.13 candidate CI
remain pending. OS foundation success does not implement SQLite/read-provider
registration, initialization receipts, actor/UDS/CLI mutation, credentials,
backup/restore or a second real daemon refusal. Whole M1-02/RV11, canonical M1-03,
WR/RI acceptance, G1–G6 and live Gmail/deployment gates remain open.
