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
| Admission/rules | `src/facet/projection/rules.py`, `authenticity.py`, `admission.py` | policy worker | M1-06 auth ADR, closed rule/action types |
| Discovery/backfill | `src/facet/projection/backfill.py`; epoch/checkpoint repositories/tests | discovery worker | verified adapter, M1-02 repositories |
| History | `src/facet/projection/history.py`; event/checkpoint integration/tests | History worker | event/epoch/job repositories |
| Actions | `src/facet/projection/actions.py`; action/replay tests | action worker | History typed events, action persistence contract |
| Fidelity | `src/facet/projection/fidelity.py`; synthetic MIME tests | MIME worker | adapter raw bytes and MIME fixture contract |
| Worker/recovery | `src/facet/projection/worker.py`, `recovery.py`; fault tests | projection worker | jobs/intents/mappings, runtime writer lock |
| CLI/run integration | `src/facet/cli/backfill.py`, `status.py`, `run.py`, focused integration tests | integration worker | all above; M1 command/lock protocol |
| Shared DB | existing `src/facet/db/repositories/` only where a typed consumer is missing | persistence owner | no schema/API rewrite without owner review |

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

1. Freeze the typed contracts and inspect the actual M1 binding, writer,
   repositories and fake APIs. Record any missing consumer method before code.
2. Implement the narrow adapter with injected fake transport and provider error
   mapping. Its tests must prove no send/delete/forward path exists.
3. Implement rules/admission and the fixed backfill epoch/H0 path. Establish
   durable source-thread/message job keys before worker integration.
4. Implement normal History pagination/cursor and action-label command
   consumers. Run discovery and History against the same fake mailbox before
   adding target assertions.
5. Implement fidelity, serial worker, intent/mapping and recovery. Wire restart
   and response-loss cases before any broad CLI polish.
6. Add the real CLI run/preview/start/status path and the complete synthetic
   subprocess E2E. Do not wait for Dashboard/Compose to exercise the product.
7. Integrate one candidate, run the full required checks and submit it for
   independent implementation/acceptance review. A later live Gmail test is a
   separate evidence record and does not silently alter the candidate.

If a dependency is not yet integrated on main, workers may implement a pure
adapter or test fixture against an explicitly recorded interface, but the
integrated candidate must use the actual M1/M1-02 repository/provider inputs.
Tests that construct rows directly are not producer evidence.

## 7. Acceptance evidence

### 7.1 Offline fake-Gmail end-to-end

Use a clean temporary state directory and the production CLI/adapter/actor with
the fake service injected at the provider boundary. Seed synthetic source data
with multiple threads and:

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
config/auth binding -> preview (zero insert)
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

- the actual M1 binding/writer/repository types cannot support the path without
  changing the product contract or adding an unreviewed generic framework;
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

Open engineering inputs are the exact M1 binding/credential consumer, the
reviewed insert-attribution evidence mechanism, and the concrete adapter method
names after inspecting the integrated repositories. These are not user product
decisions unless they require scope, disclosure, deletion, latency or recovery
semantics to change. The following are deliberately later milestone decisions:
full History 404 gap window, daily/weekly reconcile/audit, Dashboard schema/UI,
backup/restore bundle, Compose/image publication and real host/dogfood.

## 10. Review and handoff

Before implementation, the independent plan reviewer checks this exact file
against the current main/base and records:

- source/target role and scope assumptions;
- H0/cutoff/History transaction boundaries;
- action-label effective time/generation semantics;
- mapping/fidelity/unknown-recovery safety;
- privacy and no-send/delete evidence;
- the explicit later-milestone boundary for 404 gap/reconcile and delivery;
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
