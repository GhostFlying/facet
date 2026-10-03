# M2 Automated Discovery, Backfill, History and Projection Core

Status: plan for independent review. This document authorizes no code, Gmail
operation, deployment, image publication or merge by itself.

This is the first implementation unit intended to produce a usable Facet
product capability. It is deliberately one product path rather than a set of
one-shot copy, storage-only, or provider-only demonstrations:

```text
verified bindings -> preview -> explicit backfill start
  -> fixed six-month discovery -> durable jobs
  -> normal History polling -> rule/action processing
  -> complete thread projection -> mapping and target verification
  -> restart / retry / unknown-insert recovery
```

The user does not select individual threads. A preview and one explicit
`backfill start` confirm the disclosure scope; discovery, admission, backfill,
History consumption and projection are then automatic. There is no latency
SLA, polling interval gate, queue-age gate or throughput target in this unit.

## 1. Baseline, ownership and contract

- Package: M2 automated projection core, combining the normal path of the
  existing M2-01..05, M3-01..04, M4-01, M5-01 and M5-03 work-package IDs.
  Those IDs remain useful for issue tracking, but this unit is accepted as one
  product candidate, not as a sequence of disconnected library deliveries.
- Plan base: the current approved-plan candidate `170cfb9e8b85370fcd793f2a9af24c321b9139c4`.
  The implementation worker must rebase or carry this plan onto the actual
  main SHA selected by the coordinator and record the exact candidate SHA.
- Plan owner: delegated M2 integration/documentation owner. The owner may
  coordinate the workers but must not self-approve the plan or implementation.
- Implementation owners: separate workers for adapter/binding consumption,
  admission/discovery, History/actions, projection/fidelity/recovery, and the
  final integration candidate. The coordinator assigns actual agents, branches,
  base SHAs and reviewers in the package handoff.
- Independent plan reviewer: a Sol high/xhigh reviewer who did not author this
  plan. Independent implementation/acceptance review must inspect the exact
  candidate SHA and its evidence; a green CI run on another SHA is not evidence.
- Product references: `docs/product-contract.md`, `docs/project-plan.md`,
  `docs/gmail-projection-spec.md`, `docs/cli-spec.md`,
  `docs/phase-1-execution-plan.md`, `docs/dashboard-spec.md` and the ordered
  repository instructions. These documents remain authoritative if a local
  implementation convenience conflicts with them.

The unit must preserve these product facts:

1. One user, one projection and two different Gmail accounts. Source is the
   sole source of truth; target is an inspectable disclosure view.
2. Source defaults to `gmail.readonly`; target uses `gmail.insert` and
   `gmail.readonly`. Facet never sends/forwards, deletes, purges or adopts
   unmanaged target mail.
3. A newly admitted message authorizes the complete available non-draft
   source thread, including earlier history, attachments, other participants
   and own replies. A tracked thread continues when later senders change.
4. Raw MIME exists only in bounded process memory. DB, WAL/journal, logs,
   reports, CLI output and public status contain metadata, digests, IDs and
   controlled states only; they never contain body, HTML, snippet, attachment
   bytes/names or complete headers.
5. Gmail and SQLite are not one transaction. Intent is durable before insert;
   an uncertain insert is recovery/attention, never a blind insert retry.
6. A user action label is a source-side rule signal. Readonly mode observes it
   and does not mutate source labels. Removing a rule does not revive stopped
   or already tracked work.

## 2. What this unit delivers

### 2.1 Verified source/target path

Consume the M1 binding and credential manager instead of inventing another one.
At startup and before eligible work, verify:

- source and target profiles are the two persisted, different accounts;
- the source binding has the approved readonly scope (or an explicitly
  selected convenience mode) and the target has insert plus read scope;
- the binding role, projection ID, credential revision and provider identity
  match the private state; mismatches leave work pending and refuse Gmail I/O;
- no spike token, cursor, mapping, target ID or `.facet-spike` state is read.

The M2 adapter is a narrow Gmail-shaped production interface. Source operations
are profile, discovery page, history page, message/thread metadata and raw
message retrieval. Target operations are profile, insert, message/thread read,
bounded candidate search and target visibility/readback. There is no send,
forward, delete, label cleanup or arbitrary provider JSON method. The adapter
maps provider failures to the closed error catalogue and never persists a raw
provider response.

The implementation must exercise this same adapter and actor with an injected
`tests.fakes.gmail.Controller/Service` in offline tests. The fake is a provider
transport, not a second business engine and is never imported by production
code. The existing Google client dependencies remain the provider dependency;
do not add a generic provider/capability framework.

The following are hard consumer gates, not optional test fixtures:

- **M1-04 actual credential/profile/binding manager:** the adapter must load the
  owner-only credential files through the shipping manager, refresh through its
  serialized account path, verify both live profiles and expose a verified
  role/scope/binding revision. Closed credential value models, a fake profile,
  or test-constructed binding rows do not satisfy this gate.
- **M1-03 actual initialized writer/state owner:** `facet run`, backfill
  mutations and the one-off command path must acquire the shipping writer/root
  ownership and use the initialized state directory. The low-level lock/value
  tests or a direct SQLite connection are not an M2 owner.
- **M1-02 shipping migration and repositories:** the candidate must open a
  database through the released migration/initializer and use the typed
  repositories, command journal and transaction boundaries. Unit tests that
  hand-construct rows, an unregistered schema snapshot, or a read-bootstrap
  memory probe cannot create M2 producer evidence.
- **M1-06 admission consumer:** the trusted-authentication policy and its
  unknown/review result must be the actual admission consumer. A parser-only
  or synthetic `dkim=pass` fixture does not enable automatic admission.

If any of these consumer gates is not integrated on the implementation base,
workers may continue bounded pure adapter/fault-test preparation, but the M2
candidate is blocked from integration. The integration test must reopen the
shipping DB, invoke the shipping writer and credential/profile manager, and
prove that no rows were produced by a test-only shortcut.

### 2.2 Fixed six-month automatic discovery and backfill

`backfill preview` performs no Gmail insert. It reports only aggregate scope,
the fixed UTC calendar-month cutoff, rule revision, tracked-thread disclosure
semantics and the fact that older thread history/attachments/participants may
be included. `backfill start` is the one explicit scope confirmation. It does
not accept a normal per-thread selector and it does not imply all-mailbox
disclosure beyond the configured rules and window.

On start:

1. Persist an initialization epoch, cutoff and H0 before discovery reads.
2. Page the source search within the fixed six-month window; page tokens are
   progress hints, not durable truth.
3. Re-evaluate every candidate locally using blacklist, exact sender/domain
   boundaries, `effective_at`, source mailbox state and the trusted
   authentication policy. A candidate with unknown authenticity goes to
   review/attention rather than disclosure.
4. For an admitted message, persist thread authorization and durable
   expansion/message jobs. The worker copies the complete available non-draft
   thread, including messages older than the cutoff.
5. A failed page or restart can rescan the same fixed epoch; stable keys and
   mapping constraints suppress duplicate business effects. H0 persistence
   failure prevents scanning. `resultSizeEstimate` is never treated as a
   complete total.
6. Initial completion requires discovery and the H0-origin History catch-up to
   reach a durable boundary and the resulting jobs to be explained as complete,
   queued, retrying, review, cancelled or a concrete failure.

The cutoff is not continuously moved during an epoch. A later historical
expansion is a separate, explicit epoch and is outside this unit's automatic
initial window.

The preview/start boundary is a shared persistence concern, not a CLI-only
check. The shipping DB owner must persist the preview operation's purpose,
projection/binding revision, ruleset revision, six-month cutoff, H0/cutoff
scope digest and expiry/invalidating revision. `backfill start` must atomically
validate that typed preview operation and its stable request key before
publishing the `backfill_start` epoch decision, H0 fence and initial scan
state. Reusing a preview for another projection, changed binding/ruleset,
changed cutoff or a different operation purpose is a typed `preview_invalid`
or `request_conflict`; it cannot be repaired by constructing an epoch row in a
test. The epoch, decision, command operation and checkpoint writes use the
existing writer transaction and migration-owned repositories.

### 2.3 Normal History polling is first-milestone functionality

Normal `history.list` polling is in this unit, not a later optimization. The
poller consumes all pages from the persisted opaque string cursor and uses the
same durable jobs/mappings as discovery:

1. Begin a poll from the reliable checkpoint (or H0 initialization origin).
2. For each page, normalize only typed `messagesAdded`, label changes needed
   for action labels, and required deletion facts. Persist the page's typed
   events and resulting jobs before advancing the cursor.
3. Use typed event keys to deduplicate replayed pages and duplicate entries.
   `messagesAdded` creates or joins a projection job; a label-added event is
   consumed by action semantics. Generic `messages` data must not cause a
   second business effect.
4. Consume every page, then commit the final history ID and covered time in a
   separate durable transaction. A crash or persistence failure leaves the
   previous cursor so replay is safe.
5. Record a successful empty poll's coverage fact. The loop may poll slowly;
   timestamps are diagnostics only and are not SLA fields.

This unit covers normal polling, pagination, cursor durability, event/job
deduplication and initialization interleaving. A History 404/expired cursor is
recorded as an explicit unknown-gap/attention state and stops unsafe admission;
it must not silently reset the cursor or scan all history. Full H1 gap recovery
for every active thread and the whole trustworthy downtime window belongs to
the later continuous-recovery milestone. M2 evidence must say this plainly and
must not claim the M3 gap gate.

### 2.4 Readonly action-label rules

The History event path handles `AI/AddSender`, `AI/AddDomain` and
`AI/BlackList` through the existing action repository contracts. The label ID
mapping is configured/private and resolved by the producer; current label
snapshots do not replace History events. A `(projection, history record, label,
source thread)` activation is executed once; remove/re-add produces a new
history key.

The producer is a concrete, closed M2 actor rather than an arbitrary callback
or plugin registry. Its private inputs/outputs are:

```text
PrivateActionLabelMap {
  add_sender_label_id: ProviderId
  add_domain_label_id: ProviderId
  blacklist_label_id: ProviderId
}

ActionSourceReader.get_thread_facts(source_thread_id)
  -> tuple[ActionMessageFact, ...]

ActionLabelProducer.consume(event: SourceEventKeyLabelChanged,
                            labels: PrivateActionLabelMap,
                            source: ActionSourceReader,
                            own_addresses: tuple[PrivateAddress, ...])
  -> ActionActivation | ActionAttention
```

`ActionMessageFact` is a closed metadata value containing only source
message/thread `ProviderId`s, a normalized `PrivateAddress`, source ordering
timestamp/ID and the own-address classification needed to select the latest
external sender. It does not carry raw, body, subject, attachment or arbitrary
provider JSON. `SourceEventKeyLabelChanged` must have `change=added`; a removed
label is an observation with no new action command.
`PrivateActionLabelMap` is loaded from the verified projection configuration
and binding; label names are never inferred from a current snapshot. The
shipping actor is the only registered producer type. Its registration/witness
extension is owned by `src/facet/projection/actions.py` and the existing typed
`db/repositories/actions.py` contract; a test producer may be installed only
inside a test and never into the production registry or wheel.

Domain normalization uses a pinned, offline resolver owned by the admission
worker: `tldextract==5.3.2` with its bundled Public Suffix List and
`idna==3.20`, both recorded in `pyproject.toml` and `uv.lock`. Runtime PSL
fetch/update is disabled. The resolver converts domains to one IDNA A-label
form before exact sender/domain and dot-boundary checks, rejects public
suffixes, and records the resolver/PSL policy version in rule metadata. A
dependency/version change requires the policy owner and a new plan review.

The pinned package references are [tldextract 5.3.2](https://pypi.org/project/tldextract/5.3.2/)
and [idna 3.20](https://pypi.org/project/idna/3.20/); the lockfile and bundled
suffix-data digest, rather than a mutable network cache, are the runtime source
of truth.

- `AddSender` learns the latest valid external sender in the selected source
  thread, excluding configured own addresses. It creates an exact sender rule.
- `AddDomain` learns the normalized registrable domain using the pinned PSL/
  IDNA policy, rejects public suffixes and does not learn the user's primary
  domain. It creates a domain rule with dot-boundary matching.
- `BlackList` creates an exact sender blacklist and stops that current thread
  by increasing its generation and cancelling only unstarted work. Other
  senders/threads are unaffected; dispatched or unknown inserts are recorded
  and target history is retained.
- The current action-labeled thread is the user's explicit label authorization
  and can be admitted as the action's selected thread. A learned sender/domain
  rule applies prospectively to later automatic discovery and still requires
  the trusted authentication policy. It does not silently backfill every old
  matching thread.
- Rule changes persist `effective_at`, origin, revision and policy version.
  Rule removal does not stop existing tracked threads; removing a blacklist
  does not resurrect a stopped generation.
- Readonly mode leaves source labels unchanged. Convenience cleanup and
  `gmail.modify` label operations are not part of this unit.

Action registration, rule publication, selected-thread admission/stop and
affected jobs must be one durable local business transaction using the reviewed
finite action repository semantics. No free-form label text, sender/domain
value, provider payload or email content is placed in an event/audit payload.

### 2.5 Projection, fidelity, mapping and recovery

The worker runs in the Docker-supported single process with one writer and a
single bounded worker/transport. It processes one source thread serially and
handles other jobs sequentially; it does not implement a worker pool or
cross-thread scheduler.

`SyncConfig.thread_concurrency` is already parsed by the shared config model
and remains accepted for forward compatibility, but M2 deliberately does not
consume it to create workers. The effective M2 worker count is one for every
positive configured value; values such as 1, 4 and 99 must produce the same
single-owner execution trace. A later scheduler owner may give that existing
field meaning only under a separate reviewed plan. `poll_interval_seconds` is
also a diagnostic/runtime input, not a latency promise.

Raw handling uses one simple typed disposition, not a scheduler framework:

```text
RawDisposition = in_memory | released_after_attempt | oversize_blocked
                 | released_target_blocked | source_missing
```

The worker obtains a `RawLease` with a fixed single-message byte bound. The
lease exposes only byte count, digest/version and the closed disposition; it
never exposes raw bytes to DB rows, logs, status or command results. Oversize,
target-blocked and source-missing paths release the lease and leave typed job
state; a successful/unknown attempt releases it after the network boundary.
The disposition is private transient metadata (a typed error/state may be
persisted), not a raw spool or free-form diagnostic string.

For each source message:

1. Claim a current-generation job and verify active tracking, binding and
   source/target readiness.
2. Fetch raw bytes into memory only. Compute source and versioned semantic/MIME
   digests from the raw bytes and metadata; persist only digests/versions.
3. Persist an insert intent before any target network call. Use `messages.insert`
   with the original raw bytes, anchor/thread information and valid Date policy.
4. On a definite response, record target message/thread IDs, visibility and
   mapping, then read back enough target metadata/content to verify fidelity.
   Preserve the actual target thread set if a confirmed threading mismatch
   requires a narrow fallback. Never fallback every HTTP 400.
5. On definite non-insert errors, keep the job in a typed retry/block state
   according to the error class. On timeout, connection loss, process exit or
   lost response, transition the intent to `pending_recovery`, enqueue a
   recovery check and pause that source thread's later inserts.
6. Recovery may bind only a candidate satisfying account, fingerprint,
   mapping and the separately reviewed insert-attribution evidence. A matching
   unmanaged/spike copy, multiple candidates, index delay or mismatch remains
   `needs_attention`; zero search results do not prove non-insertion. No
   automatic delete or duplicate cleanup is allowed.

Raw is released after the target attempt/readback or on prolonged target
failure. A single-message bound prevents an accidental oversized attachment
from exhausting the process; there is no cross-thread raw-budget scheduler.
Source deletion after a lost raw fetch becomes `source_missing`, with any
already-confirmed target mapping preserved.

## 3. Runtime and CLI shape

The supported runtime is one foreground process in the supplied Docker image:

```text
facet run
```

Docker/Compose will own lifecycle in a later unit. For this candidate, the same
process owns the sync loop, SQLite writer, provider transport and local status
facts. One-off supported commands use the existing writer lock and local stable
request key/command records; they do not require a daemon endpoint. The M2
minimum command path is real, not help-only:

```text
facet config validate
facet gmail auth-status
facet status
facet backfill preview
facet backfill start --preview <id> --request-id <id> --yes
facet backfill status
facet run
```

Action rules arrive through source History; no HTTP mutation or per-thread
selection command is introduced. Full queue/review/recovery/audit/repair,
Dashboard, backup/restore and complete maintenance CLI remain later consumers
of these durable facts, while the M2 integration must expose enough controlled
status to diagnose a failed fake run.

The foreground process is not a daemon protocol. This unit does not implement
Unix IPC, a command broker, an asynchronous receipt service, host service
installation, or a second runtime owner. Stable local request keys are retained
only to make a repeated preview/start command idempotent; they are not a
network/API receipt framework.

The minimum command persistence is nevertheless a real M1 consumer. Before
acknowledging `backfill start` (and before any long-running local effect), the
shipping `db/command_records.py`/`command_store.py` journal on the initialized
database records the request ID, command kind, canonical typed payload digest,
projection/scope guard, and operation state. The epoch decision and command
operation link are then committed through the writer-owned transaction. A
client that loses the first response looks up the same request ID and receives
the existing accepted/completed/blocked/attention outcome; the same key with a
different payload is rejected. It never resubmits a Gmail insert. This is the
small local idempotency/first-response-loss dependency of M2, not the discarded
v2 read-bootstrap, an IPC receipt service, or a mail-content journal. If the
shipping migration does not expose these command records on the integration
base, M2 is blocked rather than silently persisting a second ad hoc operation
format.

## 4. Explicit non-blockers and removed designs

The following are deliberately not implemented or required to close this unit:

- `runtime/native/read bootstrap`, installed import/native graph proofs,
  container-external runtime qualification, and similar sandbox mechanisms;
  Facet guarantees only the supplied Docker image/support contract later.
- An independent daemon, Unix/HTTP IPC, command broker or request-receipt
  protocol. Docker runs the foreground owner and a local writer lock protects
  one-off commands.
- Default cross-thread concurrency four, real-time priority, backfill fairness,
  rate-limit scheduler frameworks, per-worker transport pools or a complex
  cross-thread raw budget. Basic single-message in-memory bounds remain.
- Dashboard HTTP/UI and browser verification. M2 supplies aggregate producer
  facts but does not expose email details or claim the Dashboard gate.
- History 404 full gap recovery, source reconcile, target audit and bounded
  repair. The normal poller records an honest gap/attention state; later M3
  consumes it with H1/fence and recovery-window semantics.
- Backup/restore/migration bundle, Compose files, Nginx, Actions/GHCR and
  image provenance. Their absence does not make the fake end-to-end sync gate
  pass or fail; they are later delivery gates.

Removing or reintroducing any item above, changing the disclosure contract,
adding an OAuth scope, or changing the no-delete/no-send boundary is a material
plan change and returns to the coordinator/user review. It is not a routine
implementation choice.

## 5. File scope and ownership map

The worker must keep the implementation inside the existing package boundaries.
New generic frameworks, provider registries or runtime layers are out of scope.
The exact source files may be adjusted during implementation review, but a
material path/owner change requires a plan update.

| Area | Candidate files | Primary owner | Key dependency |
| --- | --- | --- | --- |
| Provider adapters | `src/facet/gmail/source.py`, `target.py`, `retry.py`; adapter tests | Gmail worker | M1-04 binding/credential contracts; fake provider |
| Admission/rules | `src/facet/projection/rules.py`, `authenticity.py`, `admission.py`; pinned `tldextract`/`idna` dependency and resolver tests | policy worker | M1-06 auth ADR, closed rule/action types, pinned PSL/IDNA |
| Discovery/backfill | `src/facet/projection/backfill.py`; epoch/checkpoint repositories and preview/start operation guards/tests | discovery worker + shared DB owner | verified adapter, M1-02 shipping migration/epochs/command journal |
| History | `src/facet/projection/history.py`; event/checkpoint integration/tests | History worker | event/epoch/job repositories |
| Actions | `src/facet/projection/actions.py`, `src/facet/gmail/labels.py`; typed producer/registration and action/replay tests | action worker + Gmail label owner | History typed events, action persistence contract, private label map/source reader |
| Fidelity | `src/facet/projection/fidelity.py`; synthetic MIME tests and typed raw lease/disposition | MIME worker | adapter raw bytes and MIME fixture contract |
| Worker/recovery | `src/facet/projection/worker.py`, `recovery.py`; fault tests | projection worker | jobs/intents/mappings, runtime writer lock, typed raw bound |
| CLI/run integration | `src/facet/cli/backfill.py`, `status.py`, `run.py`, focused integration tests | integration worker | actual M1 command journal/lock protocol |
| Shared DB | existing `src/facet/db/repositories/`, `src/facet/db/command_records.py`, `command_store.py`, `db/migrations/` only where a typed M2 consumer is missing | M1-02 persistence owner | shipping migration, preview/epoch/request guards; no schema/API rewrite without owner review |
| Shared dependency/config | `pyproject.toml`, `uv.lock`, `src/facet/config.py` only for pinned resolver and explicit `thread_concurrency` behavior | policy/config owners | dependency review; existing parsed config remains backward-compatible |

Existing `src/facet/db/repositories/jobs.py`, `intents.py`, `mappings.py`,
`events.py`, `epochs.py`, `history.py`, `actions.py`, `policy.py`, `reads.py`
and `audit.py` are the storage foundation. The worker must consume them rather
than recreate a second SQLite business engine. Any missing repository method
must use the frozen typed records, guards and transactions; no arbitrary JSON
or provider payload columns may be added.

`tests/fakes/gmail.py`, `tests/fakes/mime.py`, `faults.py`, `network.py`,
`transport.py` and `privacy.py` are reusable test infrastructure. Extend the
fake only for a provider behavior required by a concrete acceptance case; do
not add production imports or test-only shortcuts to make a business assertion.

## 6. Dependency ordering and integration strategy

The implementation is internally ordered, but it is integrated and reviewed as
one candidate product unit:

1. Freeze the typed contracts and inspect the actual M1-04 credential/profile/
   binding manager, M1-03 initialized writer/state owner, M1-02 shipping
   migration/repositories/command journal and fake APIs. Record any missing
   consumer method before code; do not hand-construct replacement rows.
2. Pin the offline `tldextract`/PSL and `idna` versions in the dependency owner,
   then implement the narrow adapter with injected fake transport and provider
   error mapping. Its tests must prove no send/delete/forward path exists.
3. Implement rules/admission and the fixed backfill epoch/H0 path, including
   shared-DB preview/start operation guards. Establish durable source-thread/
   message job keys before worker integration.
4. Implement normal History pagination/cursor and the typed action producer/
   label-map source interface. Run discovery and History against the same fake
   mailbox before adding target assertions.
5. Implement fidelity, typed raw lease/disposition, serial worker, intent/
   mapping and recovery. Wire restart and first-response-loss lookup cases
   before any broad CLI polish.
6. Add the real CLI run/preview/start/status path and the complete synthetic
   subprocess E2E. Do not wait for Dashboard/Compose to exercise the product.
7. Integrate one candidate, run the full required checks and submit it for
   independent implementation/acceptance review. A later live Gmail test is a
   separate evidence record and does not silently alter the candidate.

If a dependency is not yet integrated on main, workers may implement a pure
adapter or test fixture against an explicitly recorded interface, but the
integrated candidate must use the actual M1-02 migration/repositories/command
journal, M1-03 initialized writer/state owner and M1-04 credential/profile/
binding manager. Tests that construct rows directly, bypass the command journal
or assert against an uninitialized in-memory schema are not producer evidence.

## 7. Acceptance evidence

### 7.1 Offline fake-Gmail end-to-end

Use a clean temporary state directory, the shipping migrated DB and initialized
writer/command owner, and the production CLI/adapter/typed action actor with
the fake service injected only at the provider boundary. Bind source/target via
the actual credential/profile consumer (using synthetic credentials/profile
facts in the test harness) rather than constructing binding rows by hand. Seed
synthetic source data with multiple threads and:

- a message inside and outside the six-month boundary, where a matching recent
  message causes complete older thread history to be copied;
- HTML, inline content, attachments, non-ASCII headers, valid/invalid/missing
  Date and reply headers;
- a user reply and a later message whose sender differs from the first sender;
- action-label additions for all three commands, duplicate/replayed History
  entries and a remove/re-add sequence;
- History pages with tokens, empty polls, duplicate pages and a page failure;
- target insert success, definite rejection, response loss, timeout/index delay,
  pre-existing matching unmanaged copy and multiple candidates.

The observed command/evidence sequence is:

```text
shipping init + credential/profile/binding verification -> preview (zero insert)
  -> backfill start -> H0/cutoff persisted
  -> automatic discovery and full-thread jobs
  -> normal History pages and action commands
  -> target insert/readback/mapping
  -> process restart -> continued deduplicated work
  -> response loss -> pending_recovery/attention, never blind insert
```

Acceptance requires all discovered/admitted work to have a durable terminal or
pending explanation, unique confirmed source-message mapping counts, correct
target thread/date/MIME/attachment evidence, no duplicate business insert,
and a fake transport trace showing no send/forward/delete and no client-level
unconditional insert retry. The test must assert normal History is first-class
and that a 404 is reported as a bounded unresolved gap, not silently treated as
success.

### 7.2 Fault and crash boundaries

Inject and reopen the actual state after each of these boundaries:

| Boundary | Required result |
| --- | --- |
| H0/epoch write fails | No discovery request and no cursor advance |
| first `backfill start` response is lost | The shipping command journal resolves the same request ID and payload digest; retry is a replay/lookup, not a second epoch or Gmail effect |
| discovery/history page persistence fails | Old page/cursor remains replayable; no lost event |
| duplicate/replayed History page | Same typed event/job/action has one business effect |
| action/rule/job transaction fails after a sub-operation | Whole local transaction rolls back or becomes a typed attention state |
| crash after claim, before intent, after intent and before target call | Generation/intent state is explainable; stale unsent work is safe |
| insert succeeds before response/mapping | Unknown recovery, no blind insert; attribution gate required |
| target 401/403/429/5xx/timeout | Typed blocked/retry/unknown state; unrelated persisted jobs remain |
| target readback mismatch or multiple candidate | `fidelity_mismatch`/`needs_attention`, no duplicate insert/delete |
| BlackList races claim/dispatch | Unstarted work cancelled by generation; in-flight fact recorded |
| restart during backfill and normal History | Same epoch/cursor resumes without duplicate mapping |
| source message disappears before fetch | `source_missing` with existing confirmed target facts retained |

### 7.3 Privacy and side-effect sentinels

Inject synthetic body, subject, HTML, attachment name/bytes, sender/recipient,
RFC ID, token, provider URL/error and local path sentinels. Scan the DB, WAL,
SHM/journal, logs, stderr/stdout, temporary directories, CLI JSON and audit rows
after successful, failed, crash and response-loss runs. Assert:

- no raw/body/HTML/snippet/attachment/full-header sentinel is persisted or
  emitted;
- private IDs/rules/bindings remain only in owner-only state where the contract
  permits them; no public DTO is created by this unit;
- no credential, authorization URL or unfiltered provider exception appears;
- no `.eml`, disk spool or raw report is created;
- fake transport sees only profile/read/history/insert/readback operations in
  this unit; no send, delete, cleanup or scope expansion occurs.

The tests must include detecting negative controls so a column-name scan or an
ignored temporary file cannot masquerade as a privacy proof.

### 7.4 Verification commands and evidence classification

The implementation candidate runs the affected tests first, then the complete
repository checks required by the instructions: locked dependency sync,
Ruff check/format, full pytest, both CLI help probes, repository safety and
wheel/install smoke where applicable. Evidence is recorded as:

- `implemented`: source and tests exist at the candidate SHA;
- `offline_verified`: fake-Gmail E2E/fault/privacy evidence passes;
- `gmail_verified`: only after separately authorized source/target API/UI
  evidence; not implied by fake success;
- `deployment_verified`: only after the later Compose/image/host gate.

This unit may close its offline candidate and leave live Gmail, G2 live,
Dashboard, gap/reconcile, Compose and deployment evidence explicitly pending.

## 8. Live Gmail boundary

No live request is part of plan approval or CI. If the coordinator later obtains
the D3 scope packet, the live harness must name the source/target accounts,
approved rule/action labels, fixed six-month window, target write scope and
cleanup/stop policy before OAuth or insert. The harness must never send, delete,
purge, remove old target mail, broaden scopes, or import spike state. OAuth URLs,
tokens, addresses, Gmail IDs and raw evidence stay local and out of GitHub,
CI, images, docs, screenshots and reports. A real Gmail API/UI result is a
separate `gmail_verified` receipt; it cannot be inferred from this plan or
from the fake provider.

## 9. Stop gates and unresolved decisions

Stop implementation and return to the coordinator if any of the following is
observed:

- the actual M1-04 credential/profile/binding manager, M1-03 initialized
  writer/state owner, M1-02 shipping migration/repositories/command journal or
  M1-06 admission consumer cannot support the path without changing the
  product contract or adding an unreviewed generic framework;
- preview/start epoch guards or first-response-loss lookup would have to use
  test rows, the discarded read-bootstrap, or an unversioned local operation
  format instead of the shipping DB owner;
- the pinned PSL/IDNA dependency cannot be bundled offline, or its resolver
  would fetch mutable suffix data at runtime;
- a provider operation would require send, delete, broader OAuth, a second
  writer, a daemon/IPC layer or raw disk storage;
- insert attribution cannot distinguish an old unmanaged/spike candidate from
  a possible production insert; keep the job in attention rather than weaken
  recovery;
- History page events cannot be persisted before cursor advancement or action
  deduplication cannot be made durable;
- any privacy sentinel reaches DB/WAL/log/temp/CLI/public output, or tests
  would need to skip, xfail or delete a required failure;
- an implementation proposes to treat History 404 as normal success, to claim
  gap/reconcile/Dashboard/Compose delivery, or to introduce a latency promise;
- live work lacks a concrete D3 scope packet or an OAuth/scope/account mismatch
  is detected.

Open engineering inputs are the exact integrated M1 binding/credential,
writer/state, migration/command-journal consumer method names and the reviewed
insert-attribution evidence mechanism. The typed action actor, label map,
source-facts interface and pinned resolver versions are fixed scope for this
unit; they may receive ordinary implementation-level naming changes only after
the plan reviewer sees the actual inputs. These are not user product decisions
unless they require scope, disclosure, deletion, latency or recovery semantics
to change. The following are deliberately later milestone decisions:
full History 404 gap window, daily/weekly reconcile/audit, Dashboard schema/UI,
backup/restore bundle, Compose/image publication and real host/dogfood.

## 10. Authority-document cleanup handoff

The M2 plan is the implementation authority for this candidate, but the shared
project plan is also user-facing authority. The docs owner must make the
following exact edits before the M2 implementation candidate is called
integrated (this plan does not silently edit shared coordination documents):

- In `docs/project-plan.md`, the `### M2 自动 discovery、backfill、History 增量和投影核心`
  section must explicitly own the fixed six-month boundary, normal History
  polling, readonly `AI/AddSender`/`AI/AddDomain`/`AI/BlackList` semantics,
  `effective_at`/generation and automatic backfill scope. It must state that
  preview/start guards and the command journal are shared DB-owner behavior.
- In the `### M3 History gap、校对、Dashboard 和长期运行增强` section,
  remove any wording that makes normal History polling, six-month discovery,
  action-label rule processing, or initial backfill a M3 dependency. M3 owns
  only History 404/H1 gap recovery, reconcile/audit and Dashboard/long-running
  observability for this plan.
- In the `### M4 完整维护 CLI、审计/受限修复和 action-label 便利模式` section,
  retain only advanced maintenance, bounded repair, BlackList competition beyond
  the normal action actor, and `gmail.modify` convenience cleanup. Do not list
  readonly action-label learning or normal generation semantics as M4-only.
- In the `## 测试计划` table, move `六个月边界` and normal `BlackList 竞争` to
  M2; keep `Action labels` in M2; split `新规则和 reconcile` so
  effective_at/action-job behavior is M2 and reconcile behavior is M3. Keep
  `History 404` in M3 and retain its explicit gap boundary.

The docs owner should record the exact revised file SHA and consistency check in
the integration handoff. Until that handoff is complete, any stale M3/M4 row is
treated as a documentation blocker, not as permission to move implementation
work or weaken this unit's scope.

## 11. Review and handoff

Before implementation, the independent plan reviewer checks this exact file
against the current main/base and records:

- source/target role and scope assumptions;
- H0/cutoff/History transaction boundaries;
- action-label effective time/generation semantics;
- mapping/fidelity/unknown-recovery safety;
- privacy and no-send/delete evidence;
- the explicit later-milestone boundary for 404 gap/reconcile and delivery;
- actual M1-02/M1-03/M1-04 consumer gates and shipping command/epoch persistence;
- typed action producer/source interface, private label mapping and pinned
  PSL/IDNA resolver ownership/version;
- one-worker `thread_concurrency` behavior and typed raw lease/disposition;
- file ownership and the absence of runtime/IPC/high-throughput expansion.

After review approval, workers implement in owned branches with English atomic
subjects (`feat: impl ...`, `fix: fix ...`, or the repository's other explicit
action form). The integration candidate must include the exact plan revision,
base SHA, changed files, targeted/full check results, fake transport trace,
privacy sentinel scan and all known pending live/deployment gates. An independent
reviewer then reviews the exact candidate SHA; revisions that change state,
scope, privacy, recovery or dependencies require a new plan review.

The coordinator may mark the unit `ready_to_integrate` only after independent
implementation/acceptance review and CI. Integration does not close G2 live or
any later milestone. The handoff reports actual capability as implemented,
offline-verified, Gmail-verified or deployment-verified, never as a percentage
made from code/test/PR counts.
