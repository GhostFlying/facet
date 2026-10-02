# M1-03 isolated read-view production integration plan r1

Design alignment only. Base is `1b7cd58b4846aab86edcbb781a999abb968d047c`;
actual integration main reported for this phase is `ff77e63a823dc8bcb130836243746c067778b94f`.
Do not treat this older owned branch as current source. Before implementation,
normally integrate the actual reviewed SQL branch and recheck concrete symbols.
No source or production provider registration is authorized by this plan alone.

Frozen inputs: writer plan `3934f2a4d6bc1cf0e0ebf4748cd1ed8be426cc7a04f785ca5d1641ed5beaa64c`,
writer extension `3b9dc3e637ba727589768f0055c746193809f7e0fcd07bc94839dd565a0110c8`,
DB21 r4 `4f12b845e8fdd6662079a5df84a4da83e64a338f6f38143a615119f8b480a780`
and the SQL bridge file plan `17dfde9535d3fa4c9925eaa8970386bf928c04140cfa49de682bedf4d2cc6094`.
Those documents remain unmodified. The bridge was being implemented during this
alignment; its source/acceptance is a dependency, not inferred from its plan.

## Boundary and file allocation

This supplies the real producer for the existing three bridge factories, six
lifecycle methods and two audit-driver methods. It does not reimplement the
M103 command actor, M6 backup, credential manager, general plugin system, SQL
RPC or full CLI data adapters. Existing read commands do not gain mutation.

| Future owned file | Finite responsibility |
| --- | --- |
| `src/facet/runtime/read_bootstrap.py` | Standalone pre-import latch/audit and fixed two-stage child entry from DB21 r4 |
| `src/facet/runtime/read_launcher.py` | Fixed installed child exec, validated bounded existing read-command routing, exit/output handling |
| `src/facet/runtime/read_views.py` | Exact production provider, held-root/lease resources, literal connection opens and bridge calls |
| `src/facet/runtime/read_qualification.py` | Reviewed immutable runtime/import-graph qualification entries, never self-generated trust |
| `src/facet/runtime/private_root.py` and `locks.py` | Existing M103 root/owner/view ownership allocation; only needed read-lifecycle participation, not a second opener |
| M103 owner/server lifecycle module selected in its implementation plan | Startup/final SQLite close/reopen view EX; private socket lifetime bound to that owner |
| `src/facet/db/read_views.py` | One reviewed compiled exact provider/runtime registration change after this real producer passes acceptance |
| Existing `src/facet/cli/bootstrap.py` and finite read handlers | Route only eligible managed reads; no permissive fallback or write handler change |
| `tests/integration/test_read_view_runtime.py`, fixed test subprocess helpers | Actual installed bootstrap/root/locks/socket/pidfd and all paired RV evidence |

If the actual M103 implementation chooses different filenames for already owned
root/actor modules, record that finite mapping before source; do not duplicate
ownership. No other source/shared docs are implicitly assigned by this plan.

## Closed runtime-facing operations

Retain only the approved provider methods
`open_stopped_view(root:HeldPrivateRoot, expected_instance:LocalId)` and
`open_live_view(root:HeldPrivateRoot, expected_instance:LocalId)`, each a context
yielding the exact accepted ReadSession. No URI/path/options/callback dictionary
is accepted by either. The provider is exact registered class identity and holds
the actual root and r4 latch; methods cannot be used from an ordinary parent CLI,
the daemon writer interpreter, a fork copy or a different thread.

Creator-thread checks retain the exact threading.current_thread() object and
compare with `is`, not recyclable get_ident/native_id numbers. Check actual PID
as well. Foreign/forked contexts refuse before touching SQL or releasing/poisoning
the genuine owner's resource; a copied object cannot enroll in bridge/provider
identity inventories.

HeldPrivateRoot is minted only by the actual M103 existing-root traversal owner.
It retains real root/parent/lock directory descriptors, creator PID/thread and
verified device/inode/UID/mode facts. No caller tuple/path is a substitute. It
uses fixed root filenames and no-follow dirfd operations; trusted system traversal
ancestors are distinct from the owner-0700 private root, per accepted filesystem
contracts. Missing root/initialized locks or unsafe/moved inodes refuse; read-only
code never creates, chmods, deletes, repairs markers or takes over a stale socket.
Its existing initialized/bootstrap/maintenance receipt inspection is mandatory;
an empty directory or absent sidecars alone is not initialization provenance.

The read-handler selection is a private finite tag: `status`, `doctor_local`,
`config_show`. A strict parsed selector contains that tag, the existing private
root selection, output mode (existing text/json and explicit public/private
profile), and no provider query or arbitrary function name. Public/private
rendering still uses the canonical CLI/M105 boundary; config_show cannot disclose
secrets. No OAuth URL, network check, operations mutation or --live doctor path
is routed through this isolated DB reader. Other future read families require
their actual owner adapter before adding a tag; no generic row export is enabled.

Actual handler DTO/config adapters remain distinct dependencies. Missing status
aggregation/doctor/config integration returns controlled unavailable, never an
empty healthy DTO. Found operations receipts can still use the separately
reviewed actor lookup; ordinary view absence never becomes authoritative absence.
Daemon/HTTP reads stay on actual owner-serialized cached aggregate snapshots;
they do not create a read-only SQLite connection beside the daemon's RW handle.

## Genuine installed bootstrap and import graph

The ordinary CLI launches exactly its installed standalone read_bootstrap.py
using the same verified interpreter executable, `-I -S -B -X utf8`, close_fds=True,
and a finite sanitized environment. No PYTHONPATH/PYTHONHOME/sitecustomize/.pth,
LD_PRELOAD/LD_LIBRARY_PATH or caller-supplied script/module path survives. Standard
streams are the only inherited descriptors; no SQLite/root/lock handle is passed.
No shell, downloaded interpreter or source-tree fallback. The exact installed
bootstrap file and its package root are checked as trusted installed code, not
chosen by config/DB; the child derives its one package directory from that fixed
file location rather than an untrusted --install-root argument. `-B` avoids cache
writes; there is no temporary source, SQL or mail file.

Before importing SQLite, facet or provider, the child performs r4's genuine
fresh-process checks and installs its enrolled audit latch. Its unique fixed
memory probe closes successfully, yielding exact runtime facts. Only then add
the fixed installed package directory and load the fixed provider/bridge/safe
logging/read-handler graph. No implicit site initialization. The retained facts
must match a compiled qualified runtime before opening state; then claim once
and issue the final seal. No preload recheck rejects the authorized probe.

The accepted graph includes the reviewed pure stdlib/Facet modules and CPython
extension modules actually needed by this runtime; the implementation must
record its exact transitive inventory and prove no alternate SQLite binding,
ctypes/cffi arbitrary native call path, extension loading, plugin discovery,
unpickling, eval or import-time state open. Do not import the broad Gmail SDK,
web server or credential manager into this child. This is fixed trusted
application composition, NOT an arbitrary-code sandbox. Python explicitly warns
that audit hooks are bypassable by malicious same-process code; isolated startup
and the reviewed import graph are therefore essential, not optional extra tests.
[Python audit-hook boundary](https://docs.python.org/3.12/library/sys.html#sys.addaudithook)

Before safe logging imports, failures use only fixed literal error output with
the existing CLI exit category; no traceback/exception string or repr. Afterward
actual M105 safe output/logging applies. Child output is the command's final
allowlisted result, not private rows for an unfiltered parent to forward. Real
subprocess privacy controls include hostile import/exception sentinels and normal
allowed output, not only silence assertions.

## OS leases, modes and peer lifetime

Stopped acquisition uses owner EX nonblocking, then view SH, with no upgrade.
Require safe metadata.db and total absence of WAL/SHM/journal, validated lifecycle
and same held inodes. Open only the r4 stopped literal immutable URI and hold
both locks through SQLite close. Owner busy may cause the command dispatcher to
release all stopped resources and explicitly try the independently qualified
live path; no weaker SQLite flags or uncertain-stopped interpretation. Other
stopped failures are not repaired or silently retried as live.

Live acquisition uses view SH, existing safe DB/WAL/SHM and no unfinished marker.
It requires the actual owner's private ready socket plus owner-lock contention.
A nonblocking owner probe which succeeds is released immediately and the read
refuses; never wait for owner while holding view SH. No source profile/network
call is needed for this local evidence.

The concrete initial peer strategy uses a retained connected private socket,
SO_PEERCRED UID/PID, and os.pidfd_open(peer_pid). Recheck socket entry identity,
peer credentials, pidfd non-death, and the connected socket's nonblocking
MSG_PEEK/EOF/HUP state before SQLite connect, before SQL, and after materialization
before returning anything. The only acceptable peek is “would block, no bytes”.
EOF, HUP, socket error, ANY queued response byte or timeout invalidates; queued
error bytes must not hide an EOF or count as readiness. The client sends no wire
frame/command; it occupies only a bounded ordinary server connection and closes
it on exit. Existing frame/read deadline expiry must cause refusal, not a
heartbeat or an unlimited lease. A slow query may fail without returning rows.

The PID-open race is not solved by PID text: if the original owner dies and a
new process reuses its number, the retained old peer socket must still become
closed. Thus the fixed daemon must never transfer, fork/exec-inherit, duplicate
into a successor or pass its accepted/listening socket FDs to another process.
Its actual source/FD lifecycle and real subprocess tests must establish that
property; no API lets a plugin retain the peer socket after owner death. A peer
worker subprocess, proxy endpoint or inherited socket makes this strategy
unsupported. New owner startup cannot reuse the old peer's socket connection.
If those conditions cannot be proved, LIVE is unsupported; do not substitute
“some PID alive” or “some process holds owner.lock”.

On Linux with SO_PEERPIDFD, a future explicitly reviewed refinement may obtain
the peer pidfd directly. It is NOT assumed here: this planning host reports
kernel 5.15.120.bsk.3-amd64. Linux v6.5 provides that option and obtains the pidfd
from the socket's retained peer identity; that source does not prove support on
this host. No raw numeric-option/native-binding fallback is silently enabled.
[Linux peer pidfd implementation](https://raw.githubusercontent.com/torvalds/linux/v6.5/net/core/sock.c)

With a qualified peer and runtime, open exactly the r4 live readonly_shm URI.
The six bridge lifecycle and two fixed audit methods use the real per-process
opening mutex, enrolled lease/inventory and exact connection handles; no custom
callback or caller-written FileIdentity. Only same-qualified-strategy handles
are admitted. Close SQLite successfully, retire inventory, then release view
and peer resources; uncertain close invalidates the entire seal. No fallback
to writable SHM, immutable live state or adoption of crash-recovery success.

## Writer coordination and precise activation gates

Startup must hold owner EX and obtain view EX BEFORE opening/recovering a writer
or changing sidecars. Only after actual schema/new-run/claim recovery and
required logging/credential participants are ready may it publish the private
ready socket. This does not waive Gmail account/restore/effect dispatch fences.
Normal commits do not require view EX. Final SQLite close, reopen, sidecar removal
and state replacement require view EX while owner remains held. Drain/disallow
new readers through existing bounded socket lifecycle; waiting for view EX must
not release owner or silently close the last SQLite handle first.

A reader holding view SH never blocks for owner EX, so owner→view ordering has
no reader-created upgrade cycle. Crash makes pidfd/peer checks invalidate reads;
new startup waits view EX before recovery. Reads that raced death discard their
materialized result. Retained historical data is not proof of healthy readiness.

Production registration is a reviewed source change AFTER actual bridge and
provider acceptance. Resolve module imports with fixed modules/classes and local
imports where necessary, not runtime monkeypatches or dynamic string registries.
Both exact class identity and actual qualified runtime entry are required. Test
constants or observed version strings cannot populate the shipping inventory.
Runtime qualification includes actual readonly_shm behavior/source ID/compile
digest, architecture and import graph; it is not doctor-on-demand self-certification.
Each eventual image runtime/architecture needs its own positive evidence.

## Acceptance and dependency stop gates

RI01: installed noneditable wheel launches the actual -I/-S entry; poisoned
PYTHONPATH/sitecustomize/LD variables, wrong bootstrap location, preloaded module,
extra memory/ordinary-ro/native-open attempts refuse without state access.
RI02: actual stopped existing root succeeds with no file/byte delta; unsafe
ancestors, symlink/hardlink/inode replacement, missing locks/DB and any sidecar
refuse without creation, repair, chmod or deletion.
RI03: actual writer and isolated reader on SAME inode show new committed WAL
rows; readonly_shm causes no reader-side file/SHM changes; ordinary-ro polluted
process negative control detects the prior failing behavior. Two genuine
qualified readers pass and release in the prescribed order.
RI04: actual writer close/reopen/startup blocks on view EX while reader exists;
reader never waits owner under SH. Kill exact owner, start replacement, race
PID acquisition, inject queued socket bytes/EOF/HUP/frame timeout and exercise
forbidden FD inheritance: old reader must refuse before publishing results.
RI05: root/socket/lock/DB/WAL/SHM replacement or peer UID mismatch rejects;
unknown runtime/VFS/compile identity and unsupported pidfd/peer lifecycle refuse
before SQL. No kernel-version-only positive or guessed platform fallback.
RI06: missing runtime managers/DTO adapters yields unavailable; cached daemon
status/HTTP reads never open another SQLite connection. Read commands cannot
invoke Gmail, enqueue jobs, clear fences or create authoritative absence.
RI07: actual RV01–11 from DB21, all six lifecycle/two audit hooks and empty-
registry/forged-capability negatives pass with the production provider, not only
test factories. Public/private stdout/stderr/file/DEBUG sentinel controls and
normal positive output pass under real subprocess exit/fault cleanup.

All are planned, not measured here. Source starts only after independent review
of this plan, actual accepted SQL bridge input/alignment, the actual M103 root/
owner/server primitives, selected command adapters and root dispatch. Full M103
also retains actual AUTH and complete-backup/migration input gates from its main
plan. This file changes neither the canonical DAG nor full CLI/G1/Gmail/M6 gates.
