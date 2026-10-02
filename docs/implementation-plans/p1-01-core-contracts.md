# P1-01 core contracts and single-writer design plan

Date: 2026-10-02

Status: plan drafted for independent review; no ADR is frozen and no production
implementation is authorized by this draft. The coordinator reports the user's
approval of overall plan commit `caba7c73895a303d329cf3eba1c89557530c38c5` and has
dispatched this bounded P1-01 planning step. Historical G0-pending statements in
that approved tree are being reconciled by the separate P1-00 owner.

## Assignment, baseline, and ownership

- Package: P1-01, core interfaces and single-writer design.
- Design owner: delegated architecture agent `phase1_architecture_plan`.
- Independent reviewer: assigned separately by the coordinator; not this author.
- Worktree: repository sibling `../facet-worktrees/p1-01-core-contracts`.
- Branch: `docs/p1-01-core-contracts`.
- Exact starting commit: `caba7c73895a303d329cf3eba1c89557530c38c5`.
- Observed main at assignment: `2f78fdf69cba786d2568689b0d0566d827d4285a`;
  the approved plan was still on its planning branch. This worktree deliberately
  uses the approved plan commit, not the older main tree.
- Before submitting this plan, local `origin/main` and a fresh read-only remote
  `refs/heads/main` query both verified the approved `caba7c7` full SHA above.
  The coordinator separately reported PR #2 merged and main CI successful.
- Implementation dependency: P1-00's integrated execution/authority/ownership
  baseline. Preparation can proceed in parallel; final contract freeze and
  integration wait for its exact merged main SHA and a reviewed base update.
- Current writable scope: this plan only. After independent plan approval and
  coordinator dispatch, the same owner may author the two ADR files below.

Read in order: repository AGENTS, development status, product contract, project
plan, Gmail specification, Dashboard specification, CLI specification, execution
plan and agent workflow. The Phase 0 results, repository-bootstrap plan and
phase-1-planning record were also inspected. No ignored state, credentials,
mailbox content or private spike evidence was read.

## Outcome and file scope

The deliverable is a reviewable, versioned contract foundation from which P1-02
can build falsifiable synthetic tests and M1 owners can implement compatible
modules. P1-01 closes a design gate, not G1 or any runtime verification gate.

| File | Planned content | Writer |
| --- | --- | --- |
| `docs/implementation-plans/p1-01-core-contracts.md` | Plan, review responses, execution and handoff evidence | P1-01 owner |
| `docs/implementation-plans/adrs/core-state-contracts.md` | Typed state/key/transition/transaction/privacy contracts and ownership/version registry | P1-01 owner after plan approval |
| `docs/implementation-plans/adrs/writer-command-protocol.md` | Selected local command protocol, receipt replay, process/credential ownership, maintenance and failure boundaries | P1-01 owner after plan approval |

No edits to shared AGENTS, status, workflow, execution plan, product/CLI/Gmail
specifications, package configuration, lockfile, source or tests. Required shared
clarifications go to their owner through the coordinator. No GitHub objects,
commit, push, PR or merge in this planning step. A later candidate/publication
step requires coordinator dispatch and the normal privacy/review checks.

## Existing implementation evidence and reuse limits

The package configuration installs only `facet_spike`, requires Python 3.11+, and
has only the `facet-spike` entrypoint. The existing CI tests Python 3.11/3.12. No
production schema, runtime lock, command journal or snapshot DTO exists in the
tracked source inspected here; Python 3.12+ production packaging belongs to M1-01.

`facet_spike/runtime.py` creates private runtime paths; `files.py` provides
owner-only atomic replacement and fsync of the temporary file. These are useful
inputs, not a verified production durability/locking protocol. P1-01 will specify
parent-directory durability, failure handling and symlink/path ownership questions
for the implementing owners rather than silently adopting the helpers.

`oauth.py` refreshes and saves credentials from a normal load path without a
production credential manager. `gmail.py` caches role services in one instance,
and profile reads can write JSON bindings. The spike CLI doctor performs live
Gmail calls; output includes masked addresses and some provider exception text.
Those behaviors do not satisfy the production offline/public-output boundary.
`experiments.py` stores exploratory JSON intent records, not typed transactional
repositories. Reuse requires a separate focused implementation review; no spike
runtime state or command path becomes a production interface by inheritance.

## Design work after this plan passes review

### 1. Core state contract inventory

Produce a field-level contract table for each type: purpose, owner, required and
optional fields, units, validation, stable identity, allowed transitions, storage
classification, version and consumers. Use closed tagged variants; no arbitrary
provider JSON, exception string or generic free-text audit payload. The ADR may
use typed pseudocode and synthetic examples but does not add executable types.

| Contract group | Questions the ADR must settle | Implementation consumers |
| --- | --- | --- |
| Projection/binding | Stable projection identity, immutable source/target roles, binding/config revision, actual scopes, verification time and pending/failed states | M1-01/02/04, restore/runtime |
| Rules/tracking | Rule effective time and provenance, active/stopped thread generation, explicit re-track generation, policy version and rule-revision guards | M1-02/06, M3/M5 |
| Typed source events | Stable typed event key, string History ID, event kind, necessary message/thread/label IDs, observed/coverage times; generic `messages` is not a second event stream | P1-02, M1-02, M4-01/M5-01 |
| Jobs/claims | Per-kind stable keys, thread versus message versus epoch tasks, exclusive scheduling states, priority, attempts, next eligible time, generation, claim owner/run identity | M1-02/03, M2-03, later schedulers |
| Insert intent/result | Durable pre-send intent, operation certainty, known target IDs, verification versus write completion, digest/version and opaque typed attribution-evidence extension | M2-01/02/03/04 |
| Checkpoints/epochs | H0/H1, fixed cutoff, page progress versus committed cursor, reliable coverage time, discovery/reconcile/audit epochs, unknown-gap decision reference | M3-02, M4-01/02/03 |
| CLI command/preview | Client request identity, canonical payload digest/version, durable receipt, effect class, scope/purpose/revision/generation guards and bounded result | M1-03 and all CLI owners |
| Audit/errors | Controlled operation/reason/error codes, before/after typed state, retryability and outcome certainty; no content-bearing strings | M1-02/05, all modules |
| Public snapshot | Independent aggregate DTO, message/thread units, sample count/time, unknown/stale/unavailable and partial-failure semantics | M1-05, M4-04/05 |

Separate job execution state, insert outcome certainty, verification status,
thread authorization and operator receipt state. A successful HTTP insert is not
yet fidelity-verified success; a stopped thread can still acquire the factual
result of an already in-flight insert. A receipt marked accepted is not business
completion. No shared catch-all enum should erase those distinctions.

Specify uniqueness separately for projection+source-message mappings, event keys,
action activation keys, initial projection work, explicit repair operations,
thread discovery epochs and retries. A generic job-type/message unique key must
not suppress an explicitly authorized repair or manufacture a new insert when a
retry should reuse existing work. RFC Message-ID and content fingerprints are not
source-message identities or proof of target provenance.

Define monotonic generation and stale-claim rules without treating History IDs
as contiguous counters. On restart, a stale pre-send claim may be re-evaluated;
anything possibly sent remains unknown/recovery until independently resolved.
Leases or elapsed time alone never justify a second insert. Rule removal,
blacklist removal, daemon resume, reconcile and restore must not implicitly
reactivate a stopped thread.

### 2. Transaction and crash-boundary map

For each operation, list read preconditions, one durable transaction's writes,
network work outside that transaction, confirmation timing, retry identity and
failure outcome. Include at least:

1. Request acceptance: request identity + typed command + accepted receipt commit
   before acknowledging. Pure local effects can commit atomically with acceptance;
   deferred effects use a durable execution transition/effect marker, not a claim
   that receipt acceptance and a future Gmail operation are one transaction.
2. Rule/action/stop: command dedupe, rule/tracking generation, affected unstarted
   jobs, typed audit and local effect completion have one consistent commit.
3. Claim/prepare/send: validate binding/active generation, claim ownership and
   byte reservation; persist intent before dispatch. Specify the local ordering
   point between stop acceptance and actual request dispatch, so an approved but
   not yet sent insert cannot slip through the in-flight exception unnoticed.
4. Completion: record known target facts even after stop; target verification,
   mapping, attempt outcome, job completion and unique-count effects remain
   consistent. Failed local recording after possible remote success is recovery.
5. History: page events/jobs durable before any cursor advance; all pages complete
   before final cursor commit; replay uses the old cursor and stable event keys.
6. Initialization/gap: H0/H1 durable before their scans; fixed epoch boundaries;
   unknown gap approval references scope and cannot reset cursor or bypass rules.
7. Maintenance: DB backup plus config/binding/credentials form one controlled
   bundle; restore records writes disabled pending live binding/recovery checks.

No DB read or write transaction is held across Gmail, OAuth, IPC response waits
or other network operations. Explicitly distinguish process/credential ownership
locks, which may cover a remote operation, from SQLite transactions. Persistence
failure leaves no successful receipt/cursor promise; outcome uncertainty remains
queryable rather than triggering a fresh request or empty database.

### 3. Single-writer protocol evaluation and selection

Compare a private local Unix-domain command endpoint, a bounded private typed
file inbox, and stopped-owner execution. Evaluate request delivery/replay,
backpressure, access controls, socket/file lifecycle, cross-container shared
volume behavior, bounded payload/timeout rules, offline lookup and operational
complexity. Direct independent CLI writes while the daemon owns the DB are not
an admissible alternative. A Dashboard HTTP mutation API is also out of scope.

The ADR must select one running-owner mechanism and a command-by-command stopped
policy; it must not leave consumers free to choose their own protocols. A likely
candidate is a private local endpoint with stopped lock-owning execution for
eligible local commands, but this plan does not freeze that choice. Remote checks
and queued jobs need explicit ownership and lifecycle even when daemon is stopped.

Record the full request lifecycle: client creates/holds key before submission;
TTY-generated key and digest are persisted in the owner-only typed journal first;
non-TTY requires a supplied key. The journal never stores the full command payload,
secrets or mail fields. Digest canonicalization includes command schema, normalized
typed payload, selected projection and semantic guard fields, without adding
unstable wait/output-format flags that change no business effect.

First-response-loss must work when no receipt was received: lookup by client key
returns accepted/completed/blocked/unknown/not-received with precise semantics.
Same key+same payload reuses the original durable operation; changed payload is
rejected. Pending commands do not create another effect. Client journal update
failure after acceptance cannot cancel or hide the server record. Restart without
the original payload still permits lookup; the journal is not a payload spool.

Bound request-key/receipt retention and lookup semantics. Do not silently recycle
keys or prune records needed for safe replay. In particular, restoring an older
backup may remove receipts for later external effects: a restored owner's absent
row cannot prove the original request was never accepted. Define state lineage/
restore fencing and the safe lookup/replay result before selecting any automatic
resubmission path. An incompatible/unknown lineage remains controlled attention;
do not claim exactly-once Gmail behavior or invent lost history.

### 4. DB and credential ownership through maintenance

Define a single lock hierarchy and ownership table for daemon startup/shutdown,
running CLI, offline read, stopped mutation, auth/reauth/refresh, backup, restore,
migration and one-off Compose commands. Include lock identity, holding process,
fixed acquisition order, timeout/refusal, release/cleanup, cache invalidation and
which lifecycle stages allow network work. No path may acquire locks in reverse
order or ask the credential manager for work while holding a DB transaction.

The process-lock anchor must remain stable while DB/config files are atomically
replaced. PID text, stale endpoint files or missing liveness response are not proof
that ownership is free; do not unlink a live owner's lock or socket and create a
second ownership domain. Resolve shared volume/path aliases and reject symlink or
ownership surprises rather than operating on an unrelated state directory.

Maintenance first verifies stopped daemon and obtains the coordinated DB and
credential ownership. Concurrent auth/refresh waits or fails predictably; tokens,
config and bindings cannot cross bundle versions. Scope/binding mismatch rejects
replacement; credentials do not pass through request receipts or public DTOs.
Cache reload/revision fencing prevents a paused worker from overwriting restored
or newly authorized credentials with stale state.

Offline inspect/backup/restore/migrate do not require live OAuth. Restore preserves
paused/stopped generations, jobs and unknown intents; sets
`binding_verification_pending`; and permits local diagnosis while refusing new
Gmail writes. Later startup verifies profiles and resolves unknown outcomes before
eligible writes resume. Backup/migration failure preserves recoverable old state,
never silently constructs an empty DB. Filesystem multi-file replacement is not
assumed atomic: specify bundle manifest, incomplete-operation recognition and
restart/rollback handoff requirements for M6-01/02.

### 5. Privacy, compatibility, and downstream ownership

Classify every field as internal persistent metadata, bounded transient content,
credential-only, explicitly opted-in local metadata, minimal local operation
result or public aggregate. Necessary bindings/rules/IDs can be private DB fields;
raw/body/attachments/full headers/per-message address or subject copies cannot.
All CLI modes forbid content, credentials and raw provider errors. Public status
has the stricter Dashboard boundary; masked identifiers are not public-safe.

Resolve local opaque operation/request/preview selectors separately from Gmail
IDs so required maintenance lookup is usable without exposing arbitrary private
rows. Public mode never contains operation receipts. Typed diagnostics and fixed
errors apply to validation, IPC framing, unknown command, DEBUG and failure paths
as well as successful results. Raw references never enter command/snapshot state.

Propose independent versions for storage schema, command envelope/payload digest,
public DTO and fingerprint/auth policy. Define compatibility/refusal and migration
ownership; versioning does not grant scope changes. Add a contract registry with
consumer packages and the reviewed freeze SHA. M1-02 owns executable schema and
repositories; M1-03 owns runtime writer/command integration; M1-04 owns credentials;
M1-05 owns public DTO/logging; feature handlers own their typed extension branches.
Shared changes go through those owners and renewed review before consumers code.

## Review and acceptance matrix

These are required ADR-level proof obligations and downstream test specifications,
not claims of implemented tests. Each case must have inputs, interleaving/crash
point, persistent facts, allowed next action, forbidden action and implementing
package. Review must find no unresolved choice in a contract being frozen.

| ID | Counterexample/scenario | Required result and future test owner |
| --- | --- | --- |
| CC-01 | Same source event replays; same RFC ID belongs to two source messages; explicit repair follows prior success | Correct per-kind keys; no lost work or extra ordinary insert; P1-02/M1-02/M2-04 |
| CC-02 | Crash before/after request acceptance, local effect commit, first receipt write or receipt response | Stable key lookup; one local effect; no blind resend; P1-02/M1-03 |
| CC-03 | Same key changed payload; generated-key journal write fails; owner restarts before response | Controlled refusal or original receipt; journal failure before send has zero submission; M1-03 |
| CC-04 | Second daemon, stopped CLI and one-off container compete; owner shuts down during submission | One writer, bounded refusal/handoff, durable accepted work; M1-03/M6-03 |
| CC-05 | Offline status/doctor during invalid_grant, daemon absent, DB busy or unknown schema | No Gmail/refresh/write-lock acquisition; honest controlled status; M1-03/04/05 |
| CC-06 | Stop races claim, intent commit, dispatch and insert result; old claim resumes after restart | Unsent stale work refused, actual in-flight fact retained, no reactivation; M2-03/04/M5-03 |
| CC-07 | Page 1 durable, later History page/commit fails; H0/H1 persistence fails | Old cursor retained, replay dedupes; no scan without persisted fence; M3-02/M4-01/02 |
| CC-08 | Insert succeeded but mapping/response lost; matching old target copy exists; search returns zero | Unknown retained; attribution gate required; no auto bind/reinsert; M2-04 |
| CC-09 | Credential refresh/reauth competes with backup/restore; credential cache is stale | One coherent bundle/revision; no late stale overwrite/deadlock; M1-04/M6-01/02 |
| CC-10 | Disk failure or crash between multi-file restore/migration steps; no live profiles available | Old state recoverable or incomplete maintenance detected; writes disabled; M6-01/02 |
| CC-11 | Old backup predates accepted command and remote effect; original client retries absent receipt | Restore lineage blocks false not-received proof and duplicate effect; M1-03/M6-02 |
| CC-12 | Content/provider exception/ID/path/token sentinels at request, row, journal, error and snapshot boundaries | Storage/output-specific allowlists; no content spool; P1-02/M1-02/05 |
| CC-13 | Unknown insert verification, cancelled/failed work, stale snapshot or no latency samples | Mutually exclusive accurate counts; no fake success/zero/healthy; M1-05/M4-04 |
| CC-14 | Network callback executes while DB transaction open; lock/endpoint path replaced or aliased | Explicit invariant failure and controlled refusal; no second writer; P1-02/M1-03 |

## Sequence, verification, and release of dependencies

1. Submit this plan's exact base and SHA-256 to the coordinator for independent
   plan review. Continue only read-only evidence gathering while review is pending.
2. Close findings in this plan; obtain review on its revised hash. Record P1-00's
   merged baseline and any changes affecting this work before ADR implementation.
3. On coordinator dispatch, write the two ADRs in the owned files. Include selected
   decisions, rejected options, field tables, sequence/transaction diagrams,
   invariants, CC case mapping and unresolved external evidence boundaries.
4. Obtain independent ADR/acceptance review tied to exact candidate SHA and
   contract revision. No self-approval or inferred approval from plan review.
5. Only after accepted freeze and integration can the coordinator release P1-02
   and M1-01 implementation. M1-02/03/04/05 consume their normal dependency outputs;
   this design does not bypass those prerequisites or AUTH/insert-attribution ADRs.

Document-only validation: whitespace, balanced fences, existing relative links,
named future ADR paths clearly marked as planned, no private data/host paths,
contract and work-package ID consistency. Review the explicit file diff. Before
any later commit/push, stage only owned files and run the repository index safety
check plus staged whitespace review. Existing spike tests need not be rerun merely
to claim prose correctness; no runtime/fault/privacy behavior is verified here.

## Risks, authority, and stop gates

No live Gmail/OAuth, mailbox mutation, scope expansion, deployment, image/release
publication, third-party contact or recurring automation is needed for P1-01.
Read-only upstream primary documentation is permitted. This package neither
selects a Gmail authentication trust algorithm nor proves insert attribution;
its extension points must fail closed until their separate ADRs are validated.

Stop dependent work and report to the coordinator if P1-00 integration changes
authority/contracts, another writer changes owned files, the chosen protocol
requires a public write API or new deployment service, restore replay safety
requires weakening disclosure/recovery promises, or any field requires forbidden
content persistence. Product/privacy/authority conflicts require a user decision;
ordinary compatible interface choices are resolved through independent ADR review.
Do not relax the contract to release blocked downstream implementation.

## Primary-source checks

Checked on 2026-10-02. These explain platform primitives; they do not establish
that the planned Facet protocol works.

- [SQLite transactions](https://www.sqlite.org/lang_transaction.html): SQLite
  permits one simultaneous write transaction; transaction error/rollback state
  must be handled explicitly. Facet process ownership is an additional contract.
- [SQLite WAL](https://www.sqlite.org/wal.html): local-filesystem/WAL constraints
  and reader/writer/checkpoint interactions inform the ownership design.
- [SQLite backup API](https://www.sqlite.org/backup.html): use the supported DB
  snapshot mechanism; config and credentials still need separate coordination.
- [Python 3.12 fcntl](https://docs.python.org/3.12/library/fcntl.html): available
  Unix locking primitives; platform/container behavior still needs M1/M6 tests.

## Current handoff

Plan-only candidate. ADRs, contract freeze, production source, tests and all
runtime verification remain pending. The coordinator owns review dispatch and
P1-00/base integration; this author retains only the three-file scope above.

## Execution handoff after plan approval

The preceding plan is the approved planning snapshot, whose original file SHA-256
was `68015c0dfffe72068b0e8b02ff678e8db44e17cf47d407ebefaac436adc0aeaf`.
Independent reviewer `phase1_plan_review` approved it without blocking findings.
The coordinator then reported P1-00 integrated via
[PR #6](https://github.com/GhostFlying/facet/pull/6) at
`2618eafad817aee4e491aa87ebede0f44f27a20b`, with
[main CI](https://github.com/GhostFlying/facet/actions/runs/36971068807) successful.
The independent reviewer explicitly approved carrying that plan from original
starting base `caba7c73895a303d329cf3eba1c89557530c38c5` to the P1-00 base because
the dependency changed approval/status/ownership records, not contract bodies.

On coordinator dispatch, the owned worktree fast-forwarded normally to exact
`2618eafad817aee4e491aa87ebede0f44f27a20b`; the original plan remained intact.
Fresh local `origin/main` and remote main queries matched that implementation
base. The original starting base above is retained as historical plan provenance.
This appendix changes the current file hash; it does not retroactively claim that
the approved hash covers the newly authored ADRs.

The two candidate revisions are `p1-core-v1` and `p1-writer-v1`. They choose a
private Unix-domain command socket, one writer actor, stopped auth/maintenance
ownership, stable request namespaces/first-response lookup, and explicit restore
revalidation. They define shared production type ownership for M1-01 and keep
P1-02's fake at Gmail-observable APIs without an invented attribution oracle.
The coordinator confirmed that M1-01's early package/types/config-read delivery
does not exempt config init/facet init from the eventual M1-03 writer protocol;
their real write handlers remain required for M1-06/G1 acceptance.

Current scope remains three documentation files only. No runtime, Gmail or
deployment result is claimed. Independent candidate review and CI precede any
freeze/integration; plan approval alone does not authorize downstream consumers
to treat these ADRs as frozen. Exact candidate SHA and review results are recorded
in [Issue #4](https://github.com/GhostFlying/facet/issues/4) and its focused PR,
avoiding a self-referential report-only commit cycle.

Local candidate checks passed for the three owned documents: relative links,
balanced fences, heading separation, table column structure, absence of private
host paths and trailing whitespace. The explicit staged diff and repository index
safety are checked before commit/publication. These are documentation checks;
no runtime lock, crash, Gmail or credential behavior was exercised by this unit.
