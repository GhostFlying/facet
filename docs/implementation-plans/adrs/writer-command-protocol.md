# ADR: private commands and single-writer ownership v1

Date: 2026-10-02. Package: P1-01. Revision: `p1-writer-v1`.
Status: selected design, pending independent candidate review and integration.
Implementation base: `2618eafad817aee4e491aa87ebede0f44f27a20b`.

This implements the reviewed [P1-01 plan](../p1-01-core-contracts.md) together with
[core-state-contracts](core-state-contracts.md). CLI semantics and existing exit
codes remain in the [CLI specification](../../cli-spec.md). G0 approval is a
development decision, never a runtime configuration flag.

## Selected architecture

A running daemon is the only process allowed to write projection SQLite state,
config or credentials. Inside it, one writer actor serializes repository mutations;
network workers return typed results to that actor. Running CLI mutations use a
private filesystem Unix-domain stream socket in the shared state volume. This is
not a Web endpoint, not exposed by Nginx and not a general remote API.

Stopped local commands execute in a one-shot owner using the same validators,
handlers and repositories after acquiring the exact same ownership lock. They
do not start the scheduler, bind a second socket or run Gmail jobs inline. Remote
preview/audit/recovery commands require the daemon; their durable receipt lets
work wait for authorization/network recovery. Offline diagnostics and required
backup/restore/migration remain usable without it. Auth/reauth requires the daemon
stopped and holds ownership for the interactive flow; live daemon refresh is
performed only by its per-role credential manager. This intentionally avoids
transferring OAuth secrets over command IPC.

Rejected alternatives:

- Direct CLI SQL while the daemon runs would make independent writers responsible
  for transaction/refresh/generation decisions; SQLite's one-write-transaction
  limit does not itself establish Facet ownership.
- A durable file inbox would require another directory protocol for atomic rename,
  receipts, conflict/replay, permissions and cleanup; it is unnecessary alongside
  SQLite command storage. The client journal below stores no command payload.
- A public/loopback HTTP write interface would blur the read-only Dashboard
  contract and create an extra access-control boundary.
- Stopping the daemon for every command would prevent the required running CLI
  control path. Stopped execution is retained only for the categories below.

## Stable files and ownership locks

Paths are relative to the configured private state root; examples are not actual
host paths. Initialization creates the root and stable lock directory with mode
0700, files with 0600, correct service UID and no traversed symlink components.
Resolve/canonicalize the root before opening files, verify directory identity, and
use directory-relative operations/no-follow checks where supported. Different
aliases to the same state directory must use the same lock inodes. Root relocation
and arbitrary replacing the lock directory are unsupported while anything runs.

| Object | Role / lifecycle |
| --- | --- |
| `locks/owner.lock` | Stable OS advisory exclusive lock for every DB/config/credential writer; open descriptor held for owner lifetime; never replaced/unlinked |
| `locks/view.lock` | Shared lock for offline readers; exclusive during multi-file replacement/migration and bundle backup; also stable |
| `run/control.sock` | Daemon-only private command endpoint, 0600; stale cleanup only after owner lock acquisition and type/owner checks |
| `facet.db` with WAL/SHM | Projection metadata/commands/jobs; only owner changes state, readers use SQLite read-only connections |
| `config.yaml`, `credentials/` | Private configuration and per-role tokens; no client direct replacement while owner exists |
| `requests/` | Owner-only typed client journal; key/digest/status only, separate from DB writer authority |
| `maintenance/` | Private staged bundle, typed operation journal and completion manifest; no mail raw |

OS lock primitive is `fcntl.flock` on supported local Unix filesystems. The target
deployment is Linux/Compose; unsupported locking or credential/peer checks fails
with a controlled ownership error, not a weaker fallback. M1-03 tests actual
process exclusion; M6 validates the mounted local filesystem and container UID.
Do not infer reliable lock behavior from a PID file, endpoint liveness or NFS/SMB
path appearance. PID/run metadata is diagnostic only and contains no authority.

Lock order is fixed:

```text
owner.lock EX (writers only)
  → view.lock EX (only maintenance/bundle switch)
    → credential mutex source
      → credential mutex target
        → short writer-actor SQLite transaction
```

Normal daemon operations already hold `owner.lock` and skip the view lock; a
single-role refresh takes only its role mutex and performs network work without
a DB transaction. Credentials are never locked in target-then-source order.
The credential manager releases its mutex before awaiting writer-actor metadata
updates; updates carry the credential revision and reject stale revisions. The
writer actor does not wait for a credential lock/network call while a DB
transaction is open. No worker holds a DB connection transaction across callback
or network waits. Multi-role setup/maintenance follows source then target order.

Offline readers take only `view.lock SH`, never `owner.lock`, and close the DB
read transaction/connection before releasing it. They perform no auth refresh,
schema migration, write-mode PRAGMA or hidden initialization. An uninitialized
root reports uninitialized without creating paths. They release their view lock
before requesting any mutation or remote check; no SH→EX lock upgrade.

The daemon takes the owner lock before opening a write connection or reading
tokens for refresh. It does not expose command acceptance before schema and local
state integrity checks complete. New Gmail writes additionally await fresh profile
verification. Daemon shutdown drains accepted local effects, records known
in-flight results within its bound, closes writer/credential workers and endpoint,
then releases the owner descriptor last. OS process exit releases locks; a client
must actually acquire the lock before becoming a stopped owner. No force-unlock.

## First initialization and staged engineering delivery

M1-03 owns the bootstrap writer as well as the running protocol. M1-01 first
delivers real offline config validation/show, schema/template values, core types
and CLI parsing/output. Until M1-03/M1-06 connect the write handlers, config init
and facet init return controlled `owner_unavailable`, never a success/help-only
substitute. Their eventual implementation and G1 tests remain mandatory. This
coordinator-confirmed delivery sequence creates no durable-command exemption.

When no initialized namespace exists, an explicit init/config-init invocation
creates only the private root/lock/journal infrastructure first: mkdir with 0700,
open stable lock files with create/no-truncate/no-follow and 0600, verify ownership,
then acquire owner EX and view EX. Concurrent creators converge on the same lock
inodes; none replaces an existing path. Unknown pre-existing content or unsafe
ownership is a conflict, not something to chmod, erase or adopt automatically.
Pure offline queries never perform these creation steps.

The first caller's full request ID supplies the bootstrap namespace; TTY may
generate it and nonce before writing its client journal, non-TTY supplies both.
Under the locks, persist `bootstrap.json` with version, namespace, command kind,
request key/digest, artifact checksums, phase
`accepted|config_created|db_created|completed` and controlled result. It is a typed
owner receipt, separate from the client journal; no complete
command payload or credential. Replay compares digest and validates created
artifact checksum; different key/payload cannot overwrite unfinished bootstrap.
Request acceptance is durable before exclusive config creation. Resume may verify
already created exact artifacts; mismatch is attention, never guessed success.

Config init ends after exclusive creation of its validated private config and
completed bootstrap receipt, without DB, bindings, rules or Gmail. Facet init with
a separate stable key accepts only that config/new empty DB path, creates schema
and pending binding, imports its initial rules once, and copies bootstrap receipt
metadata into the operations repository. It marks DB-created/completed phases
after the respective durable boundary. A crash is recoverable using the original
key and preserved receipt; it does not recreate an existing DB. A combined facet
init may perform both phases under the same request. DB/config namespaces must
match the bootstrap record. Completed bootstrap receipt remains available for
lookup; it is never a second writer for an initialized DB. Later config changes
use normal commands. M1-03/M1-06 test every creation/receipt crash boundary.

## Command effect and stopped-owner policy

Command registry is closed and versioned. Each name maps to its typed payload,
effect class, guard, executor and stopped policy. Wire requests cannot select a
Python function, SQL, file to execute or arbitrary handler payload. Mutations that
aren't registered fail `invalid_input`; newly implemented variants require the
owning feature's reviewed contract extension before enabling the command.

| Category / commands | Running daemon | Stopped CLI |
| --- | --- | --- |
| O: status, config validate/show, auth-status, operations, queue/review/audit list/show, maintenance inspect, migration/restore plan | Local read-only view; no IPC needed | Same offline path |
| C local: config apply, rules changes, stop, daemon pause/resume, backfill pause/resume, safe queue reschedule, review reject | Socket to writer | One-shot owner may commit eligible local effects; remote work remains durable and unexecuted |
| C requiring existing scoped preview: track, admission approve, backfill start, bounded repair start, approved gap or allowed recovery retry, mode selection | Socket; commit jobs/epoch only, worker later executes | One-shot may durably accept only already valid previews and guards; never performs remote work inline |
| R with durable work: thread/review/backfill/repair/recovery/gap preview, doctor live, audit/reconcile, recovery check | Socket; durable read jobs, account manager/transport coordination | Refuse `owner_unavailable`; do not hide a background daemon in a one-shot command |
| W: insert or convenience label mutation | Only scheduler/worker under intent/generation/mode guards | No direct execution |
| A: auth/reauth | Controlled refusal requiring stopped daemon | One-shot owner + role credential manager; exact approved scopes/role and validated replacement |
| M: backup, restore apply, migrate apply | Controlled refusal requiring stopped daemon | One-shot owner + exclusive view + credential ownership; offline supported |
| Daemon shutdown | Socket durable request, bounded safe shutdown | Report already stopped; no process creation |
| Init/config init | Refuse existing state/config; no overwrite | One-shot initialization protocol; no Gmail |

Local `mode set` cannot synthesize scopes or authorize a pending OAuth operation;
it applies only with actual compatible credentials or leaves an explicit blocked
state. Rules changes do not require Gmail to commit, but their later admission
still needs trusted policy evidence. Stopped acceptance never clears restored
binding/revalidation flags. Querying a preview or receipt is not executing it.

## Wire format and registry payloads

Socket request/response uses a 4-byte unsigned big-endian length followed by that
many UTF-8 bytes of one JSON object. Maximum frame size is 262144 bytes; arrays
are capped at 1000 elements and identifiers have their core type bounds. Reject
invalid UTF-8, duplicate JSON keys, non-finite/floating numbers where integer is
required, unknown fields, excess depth (16), unsupported versions and trailing
objects. Request processing timeout defaults to 10 seconds; accepted jobs outlive
that client connection. The client `--timeout` changes its wait, not server guards.
No progress frames or unfiltered exceptions are returned.

Daemon checks the connecting peer UID equals its own service UID using the
supported Unix peer-credential facility, as well as parent/socket owner/mode.
Container one-off commands must run with that same UID/shared mount; root bypass
is not an alternate protocol. Overlong Unix socket paths or unsupported platform
peer checks are controlled configuration errors. The socket is filesystem-named,
not abstract, and never published on TCP. Rate/backpressure limits refuse before
acceptance or return an accepted receipt; no response falsely claims completion.

Request envelope:

```text
wire_version: 1
rpc: submit
request_id: rq1_<namespace32hex>_<nonce32hex>
projection_id: ProjectionId
command: closed CommandKind
payload_version: 1
payload: that CommandKind's exact typed fields
confirmation: {yes: bool, duplicate_risk_acknowledged: bool}
expected: {binding_revision: int, config_revision: int, preview_id: LocalId|null}
```

The other closed RPC is `lookup`: exact fields are wire version, `rpc=lookup`,
projection ID and request ID. It performs serialized receipt lookup only, without
submitting a new command or requiring another request key. A connection carries
one request/response and then closes; clients may reconnect to wait/poll. Read-only
local operations listing remains a DB/journal query and is not a mutation RPC.

The private local namespace is available in minimal local status/init output;
it is not in public status. TTY generation reads that namespace and generates
the nonce, while non-TTY supplies the complete request ID explicitly. A caller
must not obtain a new namespace/nonce automatically when retrying an uncertain
old request. Malformed keys are rejected; keys and payloads are not logged.

CommandKind variants and v1 payload families:

| Variants | Typed payload fields |
| --- | --- |
| `config_apply` | validated mutable-config changes; per-field closed variant, no binding/state-path/rule-import change |
| `rule_add_sender`, `rule_add_domain`, `rule_remove`, `rule_blacklist` | normalized sender/domain or rule ID; blacklist also source thread ID; applicable rule revision |
| `thread_preview`, `thread_track`, `thread_stop` | source thread ID; track requires expected preview; stop includes expected generation |
| `backfill_preview`, `backfill_start`, `backfill_pause`, `backfill_resume` | typed initial-six-month or explicitly approved historical range selection; start references preview; pause/resume epoch ID |
| `review_preview`, `review_approve`, `review_reject` | review item ID/revision; approve references matching preview |
| `queue_retry` | job ID/revision and generation; no target ID or retry override |
| `recovery_check`, `recovery_preview`, `recovery_retry` | job/attempt ID and revision; retry requires preview, permitted policy branch and explicit risk acknowledgment |
| `gap_preview`, `gap_approve` | gap ID/revision, bounded UTC start/end; approve references exact range preview |
| `source_reconcile`, `target_reconcile`, `target_audit` | defined role/task and bounded existing epoch continuation or new epoch flag; no repair by default |
| `repair_preview`, `repair_start` | audit ID/revision plus bounded selected source IDs or stored selection reference; start references preview |
| `daemon_pause`, `daemon_resume`, `daemon_shutdown`, `doctor_live` | empty payload; confirmation required for controls, not doctor |
| `mode_set`, `labels_setup` | desired source mode and approved label-setup selection; actual scope guards required |

M-only commands use the same request identity/digest/receipt semantics within the
one-shot owner, not socket execution; their typed payload is the reviewed backup
destination or backup selection, expected bundle/schema and explicit maintenance
preview reference. A operations are owner-controlled credential workflows, not
durable commands containing OAuth responses. Persist only operation kind/role,
request key and controlled result; credentials never enter payload/journal/receipt.
The exact mutable config field registry belongs to M1-01's reviewed config plan;
until a field is registered `config_apply` rejects it. No placeholder arbitrary map
is enabled in the interim.

Response is the CLI's versioned result envelope: schema version, command, status
(`completed|accepted|blocked|needs_attention`), controlled code, allowlisted data
and warnings. Local data may contain opaque receipt/request/preview selectors and
state; private mail metadata still requires CLI opt-in. Rejected operation maps to
an appropriate guard/input blocked result and nonzero exit, not success. A response
never includes the input payload/digest by default or raw provider data. Public
DTOs are a separate path and cannot wrap arbitrary command data.

## Request keys, journal and replay

The durable server identity is `(projection, request_namespace, nonce)`; full
request ID is reconstructible. Canonical payload digest v1 covers wire/payload
versions, command, projection, namespace, normalized typed payload, semantic
confirmation and expected guards. It excludes nonce, output profile, wait timeout
and transport framing. Canonical JSON is UTF-8, sorted keys, compact separators,
no insignificant whitespace, integer numbers, no duplicate keys or NaN; strings
are used exactly after each field's explicit normalization, not generic Unicode
or email alias rewriting. SHA-256 includes a fixed `facet-command-v1` domain prefix.
Server validates and recomputes the digest; it never trusts a caller's hash.

TTY-generated key must be durably journaled before submission. Each journal entry
contains only request ID, fixed command kind, digest/version, created time, local
send state and optional receipt/state. One entry is atomically replaced in a
private per-request file with fsync of file and containing directory; no raw
payload, arbitrary parameters, mail headers, credentials or provider errors.
Non-TTY already holds its explicit key; the same minimal journal may track it.
Pre-send journal failure means no submission. A failure to update the journal
after accepted response does not undo the server record; lookup remains possible.

Server operation record: operation ID, request identity, command and payload version,
validated typed payload, digest/version, state, accepted/updated/completed times,
effect marker?, controlled result reference?, dependency/error code?. Database
payload variants are typed columns/child rows or schema-validated closed records;
they cannot become free-form JSON. No request/receipt garbage collection in Phase 1.
Retaining metadata is necessary for replay safety; this is not mail-content retention.

Acceptance and execution:

1. Validate frame, command and exact binding/namespace. For a durable duplicate,
   compare canonical digest before rechecking time-sensitive execution guards.
   Same identity+digest returns the existing state/result without rerunning it;
   same identity+different digest returns `request_conflict` with no mutation.
2. For a new request, validate confirmation/scope/preview and current revisions.
   In one short transaction write operation+typed command+accepted receipt and
   any immediate local effect. Structural invalidity is not acceptance; a valid
   request rejected by business guards can persist a rejected receipt and reason.
3. Only committed accepted receipts are acknowledged. Deferred execution claims
   that operation and rechecks relevant guards at effect time. Local effect marker,
   effect rows/audit and completion commit together. A deferred Gmail action only
   creates/updates durable work; insert is never a command handler shortcut.
4. Connection loss/timeouts do not cancel accepted work. `--wait` observes, does
   not resubmit. Its bounded timeout returns accepted/pending receipt and exit 4.
5. `operations show --request-id` works without the receipt; operations list can
   union validated client-journal keys with server operations, marking journal-only
   entries unknown. These local selectors are absent from public diagnostics.

Lookup results are precise:

| Observation | Safe client action |
| --- | --- |
| Same-lineage durable receipt exists | Return that state/result; no new effect, even if original preview has since expired |
| No row, current namespace, healthy authoritative DB lookup serialized after prior acceptance attempts | `request_not_received`; caller may explicitly resend same key and payload, retaining all ordinary guards |
| Lock unavailable, persistence uncertain, DB unreadable, owner switching | `request_outcome_unknown`; retry lookup, not business effect |
| Old namespace absent after restore | `request_lineage_mismatch`; no automatic re-key or resubmission |
| Old namespace receipt restored from backup | Historical receipt is queryable; submission cannot resume old external effects through a new namespace; job restore fence applies |

A read-only SQL snapshot taken while an earlier request is still in flight is not
the authoritative negative lookup above. Running negative lookup is serialized
through the command endpoint after acceptance processing; offline negative lookup
must acquire stopped ownership for a definitive not-received check, or report
unknown from the ordinary read-only view. `operations show` remains available
read-only but clearly distinguishes missing-in-snapshot from proven-not-received.
A concurrent send that has not yet reached the owner can still arrive later;
same-key replay is safe because the owner uniqueness transaction arbitrates both.

## Shutdown, cancellation and stale claims

Stopping a thread, accepting daemon pause and invoking a Gmail mutation are ordered
by the writer's dispatch gate. The core ADR defines invocation entry as the local
start point. Claims/intent preparation and queued executor tasks remain unstarted.
Stopped generation invalidates those tasks; a returned known in-flight result is
recorded even after stop. Global daemon pause uses the same dispatch admission
barrier for all mutation lanes, while per-thread stop only gates its lane.

Shutdown receipt means shutdown is durably requested, not that the owner lock is
free. Stop accepting new mutation work; allow known result recording for a bounded
grace period (default 30 seconds), then exit with dispatched unknown intents
recoverable. A hung transport cannot grant a second process ownership before exit.
Restart marks stale dispatches pending recovery; stale pre-send claims can be
released only after inspecting intent certainty. No wall-clock claim stealing.

Worker-result messages include owner run, claim ID, job revision, generation and
attempt ID. The writer verifies all before changing scheduling state. An old-run
late result cannot revive a job or overwrite a newer attempt. Known target facts
that cannot be applied consistently produce attention/consistency failure rather
than being silently dropped or trusted as a new insert command.

## Credentials, backup, restore and migration

All credential reads capable of refreshing/replacing token files go through the
owning process's per-role manager. Offline auth-status only inspects safe metadata;
it does not invoke library auto-refresh. Token files use a private manager-owned v1
envelope containing role, credential revision and the provider credential object;
these replace atomically together. Replacement writes a private temporary file, fsyncs it,
atomically replaces, fsyncs the directory and publishes the new revision/cache.
The manager exposes immutable in-memory snapshots to per-worker transports;
workers cannot autonomously persist refresh results or share an httplib2 transport.
Wrong profile/scope leaves old accepted binding and token available, not partially
rebound state. No response/receipt ever contains the serialized token.

Stopped auth holds owner ownership throughout browser/network waits but no SQLite
transaction. This prevents backup or restore from crossing the interactive token
replacement. Doctor live requires the daemon and uses its manager; its credential
effects cannot bypass ownership just because its mailbox operation is read-only.

Backup/migration/restore take owner EX, then view EX, then both role mutexes. Since
no daemon can run, no external writer/refresh can race the bundle. View EX waits
boundedly for offline readers to close; timeout returns controlled ownership error.
The lock files and client journal directory are not replaced during restore.
No maintenance operation force-kills a process or unlinks its lock.

Backup uses the SQLite backup API into a new private destination, plus config,
binding metadata and credentials; a manifest records schema, instance, namespace,
credential/config revisions, checksums and operation ID. It publishes a completed
manifest only after all files are durable and verified. Partial backups stay
explicitly incomplete; verify/restore refuses them. Files/checksums/paths remain
private. Raw mail is absent. Backup may not overwrite an arbitrary existing tree.

Restore/migration use a typed journal outside the replaced DB, with phases
`prepared | installing | validating | committed | rollback_required` and stable
operation key, old/staged bundle references, schema/revision expectations and
per-file completion bits. It contains no mail, secrets or provider text. Stage and
verify a complete new bundle and preserve a recoverable old bundle before replace.
Durably mark installing before the first replacement; while marker exists, normal
startup/read views refuse the bundle and maintenance inspect reports its phase.
All replacements occur under view EX. After reopening and validating the installed
bundle, commit DB namespace/verification flags, fsync the completed manifest, then
clear the maintenance marker durably. Failure at any boundary either retains the
old state or leaves explicit recoverable maintenance; never silently initializes
an empty DB. M6-02 implements phase-specific restart/rollback from this journal.

Offline restore checks bundle integrity, supported schema and stored identity,
but cannot certify live profiles. It generates a new request namespace and owner
run, keeps source/target binding and paused/stopped generations, and sets binding
verification pending plus restore revalidation. It preserves command receipts
present in the backup and the destination client journal's old keys as historical.
Keys whose receipts were accepted after the backup cannot become fresh commands
merely because the restored DB lacks them. No automatic namespace rebasing.

The restore fence also covers post-backup Gmail effects missing from the restored
intent/mapping tables. Candidate rediscovery, queue retry, successful reauth or
daemon resume cannot prove those effects absent. Recovery can verify mappings and
read candidates; it leaves uncertain projection/repair work attention until the
separate M2-04 attribution/explicit-risk policy permits a scoped release. Absent
proof is not a reason to reset the cursor or blindly reinsert. This respects the
documented limitation of DB loss; no algorithm here claims full target rebuild.

Ordinary safe startup migration runs under owner/view/credential ownership before
exposing the daemon, after a valid backup hook. A schema that requires the reviewed
maintenance path returns `maintenance_required`,
not an empty database or implicit downgrade. Rollback uses the old image plus a
complete compatible bundle when no backward schema migration exists.

## Error handling, privacy and bounds

Malformed frames, permission errors, timeouts and unexpected exceptions map to
fixed registered codes, never `str(exception)` or provider text. Log records contain
fixed command category, aggregate counts, duration and controlled reason only;
request IDs, digests, addresses, IDs, payload, auth URL, socket/root paths and peers
are not public logs. DEBUG does not change the rule. Minimal journal persistence
is not a general request spool. Content/credential/provider sentinel tests cover
parse, validation, acceptance, response, timeout and cleanup failures.

Transport limits protect memory but cannot silently truncate a selected scope.
Too-large requests return input error before acceptance with fixed guidance to
use a bounded stored selection. Backpressure never advances History without
durable events/jobs. File permission or durability failures stop related writes;
network/auth failure retains accepted jobs and offline diagnostic access.

## Required implementation tests and freeze

The P1-01 plan's 14 cases have concrete obligations:

| Cases | Required injected boundary and assertion |
| --- | --- |
| CC-01 | Duplicate event/command and repair key collision; one local business effect, distinct authorized repair, no extra ordinary insert |
| CC-02/03 | Before journal fsync, before/after acceptance commit, before/after effect commit, lost first response; key-only lookup and same-payload replay work, changed payload fails |
| CC-04/05 | Two daemons, one-off owner, shutdown takeover, offline view under token/network failure; actual subprocess locks and no reader Gmail/refresh/write-lock call |
| CC-06 | Pause before claim, intent, gate entry, invocation entry and result recording; winning stop prevents call, winning invocation retains result without reactivating |
| CC-07/08 | Cursor/page/intent/map durability loss, target ambiguity; old cursor and unknown outcome retained, no guessed target binding or resend |
| CC-09 | Refresh/reauth versus owner/view/credential maintenance locks; no mixed revisions, late cache overwrite or lock-order deadlock |
| CC-10 | Crash each maintenance-journal phase and each file replacement; readable coherent old/new state or explicit incomplete state, never half-bundle success |
| CC-11 | Accept/insert after backup, restore old bundle, retry old key and rediscover old unmapped message; lineage/fence refuses duplicate effects and still permits offline inspection |
| CC-12/13 | Content and metadata sentinels through all private/public outputs; blocked/unknown/stale/partial counts truthful |
| CC-14 | Hook asserts no SQLite transaction during network callback; stale socket/PID, replaced symlink/lock path and aliased state cannot create a second writer |

M1-03 supplies OS-process/IPC tests; P1-02 supplies injection points, not the
business outcome engine; M1-04 and M6 supply credential/bundle/container evidence.
The writer must expose test-only synchronization hooks at the named boundaries
through dependency injection, not public debug routes or production content logs.

Version acceptance is exact wire/payload v1 for initial release. A new incompatible
revision is rejected until a reviewed migration/compatibility implementation exists;
adding arbitrary payload fields is not forward compatibility. Storage, command,
public DTO, fingerprint and trust/attribution versions remain independent.
Independent candidate review plus integration freezes `p1-writer-v1` and
`p1-core-v1` at the actual commit recorded in Issue/PR. This ADR has no runtime,
Gmail, Compose or milestone acceptance evidence yet.

## Primary references

- [SQLite transactions](https://www.sqlite.org/lang_transaction.html): write
  transactions and failure handling; application ownership is a separate layer.
- [SQLite WAL](https://www.sqlite.org/wal.html): local-filesystem and reader/writer
  constraints; do not treat copying only the main DB as a coherent backup.
- [SQLite backup API](https://www.sqlite.org/backup.html): supported snapshot
  primitive; additional config/credential bundle coordination is Facet's job.
- [Python fcntl](https://docs.python.org/3.12/library/fcntl.html): Unix locking
  primitive; actual process/container exclusion remains an implementation test.
- [Linux Unix-domain sockets](https://man7.org/linux/man-pages/man7/unix.7.html):
  filesystem sockets and peer credentials; Linux uses `SO_PEERCRED` here.
- [Linux flock](https://man7.org/linux/man-pages/man2/flock.2.html): open-file
  description lock lifetime; unrelated workers must not inherit owner descriptors.
