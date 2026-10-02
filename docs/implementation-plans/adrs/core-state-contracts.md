# ADR: core state contracts v1

Date: 2026-10-02. Package: P1-01. Revision: `p1-core-v1`.
Status: selected design, pending independent candidate review and integration.
Implementation base: `2618eafad817aee4e491aa87ebede0f44f27a20b`.

This ADR implements the reviewed [P1-01 plan](../p1-01-core-contracts.md).
It freezes interfaces, not production behavior. The [writer protocol](writer-command-protocol.md)
defines their execution and persistence ownership. Product, Gmail, CLI and
Dashboard contracts remain authoritative; this document adds no live authority.

## Decisions and type ownership

Use closed typed records and small independent state enums, with one executable
definition per type. There is no universal event payload, free-text error, generic
JSON audit record or single enum combining job, insert and authorization states.
Runtime enum values below are lower-case ASCII strings. Unknown fields, variants
and unsupported versions fail validation; input coercion must not grant authority.

| Contract/version | Executable owner and path | Consumers |
| --- | --- | --- |
| Primitive identifiers, enums, records, provider result protocol; `p1-core-v1` | M1-01: `src/facet/contracts/` | P1-02 and all production modules |
| Storage schema v1, field constraints and transactional repositories | M1-02: `src/facet/db/` | Runtime, workers, audit, maintenance |
| Command wire v1, canonical digest v1, owner/claim protocol | M1-03: `src/facet/cli/command.py`, `runtime.py`, `db/lock.py` | CLI handlers, workers, maintenance |
| Credential file format/revision and manager | M1-04: `src/facet/gmail/oauth.py`, `binding.py` | Startup, transports, maintenance |
| Public DTO schema v1 and controlled diagnostics | M1-05: `src/facet/status/models.py`, `errors.py`, `logging.py` | CLI public profile, HTTP, Dashboard |
| Fingerprint v1 | M2-02: `src/facet/projection/fidelity.py` | Intent, verification, recovery |
| Authentication policy/evidence version | M1-06/M3-01 reviewed AUTH ADR | Admission only |
| Attribution policy/evidence version | M2-04 reviewed insert-attribution ADR | Recovery, repair and restore revalidation |

M1-01's package plan includes the minimal dependency-free contracts module before
feature handlers: standard-library dataclasses/enums/typing only, no DB, Google
client, web or runtime imports. M1-05 owns implementing public DTOs, not duplicate
copies of core enums. Feature owners extend their registered tagged records in a
focused reviewed contract change through the owning package; no local shadow enum.
Core type code is implementation work under M1-01's own reviewed plan, not P1-01.

P1-02 can build its synthetic Gmail service, fault controller and privacy scan
helpers in parallel with M1-01. Its fake exposes only the Google service's ordinary
observable method/response shapes; it does not need or import the future M2 adapter.
Fake assertions may use provider label names and scripted HTTP outcomes, not a
second implementation of Facet admission, jobs, recovery or generation decisions.
Tests that consume executable domain types wait for the M1-01 contract commit and
import it. Record this as an internal P1-02 integration prerequisite; its standalone
fake tests remain runnable meanwhile. Do not silently skip missing-domain tests
and call P1-02 complete. M1-02 waits for the completed P1-02 output as planned.

The fake has no `belongs_to_attempt`, trusted-authentication or provenance oracle.
Its private test script can know what happened, but production-facing calls return
only profile/list/history/get/insert/label observations and controlled transport
failures. Tests derive production conclusions through the real subject under test.
Synthetic raw stays in memory; fixtures may construct strings/bytes in source.

## Primitive values and field rules

`ProjectionId` is the configured single-projection selector, 1-64 ASCII characters
from letters, digits, `_` and `-`. Local generated IDs are UUID4 lowercase 32-hex
strings; they are not mail identifiers. Provider IDs are nonempty strings, bounded
to 512 UTF-8 bytes, with no NUL/control characters; History IDs are never converted
to counters or ordered numerically. RFC Message-ID is a separate validated optional
value, not a provider ID or unique message identity.

`Timestamp` is UTC RFC3339 with microsecond precision in command records; storage
uses signed integer microseconds since epoch. Durations use nonnegative integer
milliseconds, sizes bytes, counts nonnegative integers. Generation/revision is a
nonnegative signed-64-bit integer incremented transactionally, never reused.
Overflow is `consistency_failure`, not wraparound. A digest is lowercase SHA-256
hex plus explicit algorithm/canonicalization version. `null` means unavailable or
inapplicable and is not zero. Nullable fields below use `?`; collections are bounded
and ordered where stated. All enums and IDs carry their field-specific type.

`Role = source | target`; `SourceMode = readonly | convenience`.
Operational timestamps are not the email's Date. RFC Date is used transiently for
fidelity/date policy, not copied into public metrics. Private source internalDate
may be retained when needed for ordering; latency methodology is frozen separately.

## Projection, binding, policy and authorization

| Record | Required fields / optional fields | Invariants |
| --- | --- | --- |
| Projection | `projection_id`, `state_instance_id`, `request_namespace`, `config_revision`, `schema_version`, `daemon_paused`, `binding_state`, `restore_state`; `last_owner_run_id?` | Instance identifies initialized DB lineage; restore rotates namespace; no automatic spike import |
| Binding | `projection_id`, `role`, normalized account address, expected mode/scopes, `credential_revision`, `binding_revision`; actual scopes and `verified_at?` | Account/role immutable without separately reviewed rebind; source differs from target; actual scopes never inferred from config |
| Rule | `rule_id`, projection, `kind`, normalized value, enabled, `effective_at`, `origin`, `revision`, authentication policy version | Closed RuleKind below; exact values private; changing enabled state is audited, not retroactive disclosure |
| TrackedThread | projection, source thread ID, `active`, `generation`, admission origin/ref, `admitted_at`; `stopped_at?`, stop reason? | Key `(projection, source_thread)`; initial admitted generation 1; explicit stop and explicit re-track increment; deleting blacklist does not re-track |

`BindingState = verification_pending | verified | mismatch | auth_required`.
`RestoreState = normal | revalidation_required | maintenance_incomplete`.
`RuleOrigin = initial_config | cli | action_label`.
`RuleKind = allow_sender | allow_domain | blacklist_sender`.
`AdmissionOrigin = initial_backfill | future_rule | manual_thread | action_label`.
An admission origin reference is a typed rule/preview/action ID, never arbitrary
text. Store the admission policy version and applicable rule revision as provenance.

Startup has a new `owner_run_id` and requires fresh live profiles before new Gmail
writes; a cached `verified` row does not waive that runtime gate. Offline restore
can finish with `verification_pending`, preserving diagnostic access. Restored
stopped/paused state is not reset by successful binding verification.

Rule effective time is the owner-committed UTC mutation time, unless an explicit
backfill epoch declares a historical window. Persist the chosen value with the
receipt so replay cannot move it. Config reload does not reimport initial rules.
AUTH output is `admit | ignore | review` plus controlled reason/policy version.
Before the separate AUTH gate closes, automatic matched candidates can only be
`review`; manual thread selection remains a distinct scoped authorization path.

## Events, epochs and identity keys

Source events use three tagged records: `message_added(message_id, thread_id)`,
`message_deleted(message_id, thread_id?)`, and
`label_changed(message_id, thread_id, label_id, change=added|removed)`.
Each includes projection, string History record ID and `observed_at`. Optional
provider fields are omitted only where the provider actually lacks them; missing
thread context needed by a command creates a resolution job, not guessed IDs.

| Object | Stable identity / durable fields |
| --- | --- |
| Source event | `(projection, history_record, event_kind, message_id, label_id-or-empty, change-or-empty)`; typed fields above only |
| Action activation | `(projection, history_record, label_id, source_thread)`; business state and cleanup state distinct |
| Message mapping | `(projection, source_message)` primary key; source thread, target message/thread, intent/ref, digest/version, verified time, visibility |
| Target ownership | Unique `(projection, target_message)` for automatic mapping; conflicts require review, no silent overwrite |
| Thread targets | `(projection, source_thread, target_thread)`; anchor bool; preserve all actual targets without assuming one target per source thread |
| Message projection job | `(projection, project_message, source_message, thread_generation)`; retry reuses this row and its attempts |
| Authorized repair job | `(projection, repair_message, repair_operation_id, source_message, thread_generation)`; original mapping retained as audited history |
| Thread expansion job | `(projection, expand_thread, source_thread, epoch_id, thread_generation)` |
| Gap/reconcile/audit job | `(projection, job_kind, epoch_id, partition_key)`; partition key is a typed role/thread/page partition, not arbitrary JSON |
| Action cleanup job | `(projection, cleanup_action, action_command_id)`; never reruns business action |

Key encoding is versioned, unambiguous length-prefixed tuple encoding, not delimiter
concatenation of unescaped provider IDs. Store source fields and enforce equivalent
SQL uniqueness; an encoded key or hash is not the only validation of key equality.
Ordinary new work checks existing verified mapping and outstanding insert intents
before scheduling another message projection. New generations do not authorize
recopying already mapped history; explicit missing-target repair has its own scope.

`EpochKind = initial_backfill | historical_expansion | history_gap | source_reconcile |
target_audit`. `EpochState = prepared | scanning | catching_up | draining | paused |
completed | completed_with_issues | needs_attention`.
Epoch fields: ID, projection, kind, state, fixed UTC start/end and optional discovery
cutoff, rule revision/decision reference, created time, scanned/discovered counts,
`discovery_complete`, known target count?, H0/H1?, committed cursor?, coverage time?,
short-lived page token?, typed partition progress. A page token is internal only and
is a restart hint, never proof a scan is complete. Empty successful History polls
update reliable coverage. Epoch state alone cannot declare all jobs successful.

`HistoryCheckpoint` stores committed cursor and last reliable coverage time, plus
an in-progress poll ID and persisted page progress. Only final-page success advances
the cursor. H0 precedes initial discovery; H1 precedes gap scanning. A gap with
unknown reliable start has `needs_attention` until a matching explicit range
decision exists. No reset-cursor API. Coverage and gaps retain rule effective-time
and stopped-generation guards; current labels do not reconstruct expired actions.

## Work, claims and dispatch

`JobKind = project_message | repair_message | expand_thread | resolve_event | operation_read |
recover_insert | scan_discovery | scan_gap | reconcile_source | audit_target |
cleanup_action`.
`JobState = queued | claimed | retry_wait | blocked | needs_attention | completed |
cancelled | source_missing | failed`.
These states form mutually exclusive job counts. `failed` means a concrete terminal
non-retryable reason, not a retry-budget shortcut for auth/network failure. Unknown
insert goes to recovery/attention, never terminal success or ordinary retry.

Job fields: ID, key/version, projection, kind, typed subject reference, epoch/command
reference?, thread generation?, priority, state, attempts, created/updated time,
next eligible time?, controlled reason?, claim?. `Priority = stop | realtime |
recovery | backfill | audit`; scheduler gives backfill a bounded fair share but never
bypasses stop/binding/unknown outcome guards. Exact fairness scheduling is M2-03's
local plan; it does not change keys or states.

`operation_read` carries only the operation ID and its closed read-task kind
(`thread_preview|review_preview|backfill_preview|repair_preview|recovery_preview|
gap_preview|doctor_live`). It may inspect untracked threads without admitting them;
its claim generation is absent until a tracked subject exists. The resulting
preview records expected-untracked state or the observed generation explicitly.
It cannot transition to an insert job except through a later valid scoped command.

Claim fields: unique claim ID, owner run ID, acquired time, source-thread generation?,
job revision and phase `preparing | dispatching | verifying`. A claim is an
exclusive ownership token, not a timer that authorizes duplicate remote effects.
Only the writer mutates claims. Workers return typed results through the owner;
they never open independent DB write connections.

| Transition | Preconditions and durable effect |
| --- | --- |
| queued/retry_wait → claimed | Eligible time and kind-specific guards; mutations require active generation/no existing mapping or unknown blocker/binding readiness; raw fetch reserves memory first |
| claimed → retry_wait/blocked | Only known safe-to-retry pre-send failure or definite remote non-insert; preserve attempts and reason |
| claimed → needs_attention | Ambiguous attribution/fidelity, explicit retry budget limit or invalid decision; keep source and intent references |
| claimed → completed | Applicable effect and verification persist; mapping uniqueness and count source agree |
| unstarted → cancelled | Stop/generation invalidation or explicit scoped cancellation; no deletion of attempts |
| claimed → source_missing | Source unavailable and target recovery has no recoverable result; unknown remote outcome first remains recovery/attention |

`daemon_paused` blocks new target inserts and convenience label mutations, while
History ingestion, local commands and safe read-only recovery can continue.
Backfill pause is scoped to its epoch. Neither pause cancels an already invoked
request, advances unknown work or resets rules/generations.

Same source-thread prepare/insert/map is serial through one thread lane. A thread
lane's dispatch gate serializes stop and transport invocation. A worker must be
already running, with raw prepared; merely queued executor work is not in-flight.
At the synchronous entry of the actual transport invocation, under that gate, the
writer rechecks active generation/pause/binding/claim, commits the dispatch-start
marker, and hands the invocation ownership to that running worker. No queue or
deferred callback exists between this gate and invocation entry. Release the gate
before waiting for the network. The invocation-entry marker is the defined local
linearization point, not proof that a packet reached Gmail. A crash immediately
therefore creates unknown outcome even if no bytes actually left the process.

The gate is a writer-actor serialized admission decision, not a worker-held mutex
that the actor might block on. A running transport invocation requests that decision
at its pre-network entry and waits outside any transaction; stop/pause and that
request are ordered by the actor. The actor commits and replies without awaiting
the worker. This avoids a worker-holds-gate/writer-waits-for-gate deadlock. Denied
entry must return without invoking provider I/O; the permitted invocation is not
returned to an executor queue or delayed until another scheduler turn.

Stop obtains the same thread gate before committing inactive+generation+unstarted
job cancellation. If stop wins, invocation cannot begin. If invocation wins, stop
does not abort or roll back its external effect; its eventual known result must be
recorded. Persisted prepared intent alone does not establish in-flight status.
M1-03/M2-03 tests must pause before both competitors' gate entry and prove both
orderings. Network waits never hold the gate, writer actor or a DB transaction.

On process restart: release stale pre-send claims only after examining intents;
`dispatch_started`/uncertain attempts enter recovery, not queued insert. Kill/crash
does not allow another process to steal a live OS owner lock. In-memory raw is
discarded, never persisted to make claim restart convenient.

## Intent, mapping and outcome certainty

`InsertState = prepared | dispatch_started | definite_not_inserted | known_inserted |
pending_recovery | verified | needs_attention | cancelled_before_dispatch`.
`OutcomeCertainty = not_attempted | definitely_not_inserted | inserted | unknown`.
`Visibility = normal | spam | trash | unknown`.
`DatePolicy = valid_date_header | fallback_received_time`.

Intent fields: unique attempt ID, projection/binding revision, source message/thread,
thread generation, job/claim IDs, prepared/dispatch/result times?, fingerprint/version,
source raw digest, RFC ID?, date policy, requested target anchor?, state, certainty,
target IDs?, error code?, recovery check count/next time?, attribution evidence?.
There is at most one unresolved dispatched attempt for a source message; thread
successors wait while it is unresolved. Prepared intent records no raw or full
header. A positive insert response records IDs before independent fidelity readback;
failed readback never invokes insert again.

Attribution evidence is a closed extension slot: v1 admits only `none` and
`direct_insert_response(attempt_id, target_message_id, target_thread_id)` from the
executed transport call. Recovered candidates cannot manufacture this variant.
M2-04 adds reviewed evidence variants with version and checks; until then a search
match, even unique and fingerprint-equal, is `needs_attention`. Future attribution
must exclude unmanaged/spike copies and mapping conflict. Search zero is not
`definitely_not_inserted`; timeout/disconnect/ambiguous 5xx is `unknown`.

Verification persists a mapping only when content/date policy checks and attribution
allow it. A known inserted but mismatching target remains recorded as an attempted
effect with attention, not a verified-success count. Spam/Trash visibility is
reported separately; no reinsertion to obtain normal visibility. Recovery may
record factual mappings for a stopped thread but cannot start a new insert for it.

## Command, preview and controlled results

Command fields are specified by the [writer ADR](writer-command-protocol.md).
`OperationState = accepted | executing | completed | blocked | needs_attention |
rejected`; only completed/rejected are terminal local-operation outcomes. An
accepted command that creates jobs completes when its specified durable local
effect commits, with affected job counts; this does not claim those jobs copied
mail. Durable long-running audit/backfill operations expose their separate epoch
state. `blocked` is resumable and retains its reason/dependency.

`PreviewPurpose = track_thread | approve_admission | start_backfill | repair_missing |
retry_unknown_insert | approve_gap | change_mode | maintenance_restore |
maintenance_migrate | operational_change`.
Preview fields: ID, purpose, projection/binding revision, scope selector, rule/config
revision, relevant thread generations, epoch/window?, created time, expiry time,
known counts and disclosure flags, risk-decision requirement, consumer command kind.
Scope uses a typed single-object selector or bounded stored selection reference,
never an unconstrained mailbox wildcard. Existing backfill/discovery scans provide
resumable larger selections; requests do not smuggle unbounded lists.

Preview freshness defaults to 15 minutes for command selection, with validity
further constrained by all stored guards. Expiry affects authorization to start,
not an already accepted operation or the fixed discovery cutoff. New thread
messages alone do not revoke its disclosed ongoing scope. Rule/binding/generation
changes invalidate the affected preview. This is a technical guard timeout, not
a frozen-content promise or Gmail freshness guarantee. M1-03 owns the default;
changing it requires a reviewed command-contract revision.

`ErrorClass = input | guard | ownership | dependency | attention | persistence`.
Core error codes: `invalid_input`, `unsupported_version`, `request_conflict`,
`request_not_received`, `request_outcome_unknown`, `request_lineage_mismatch`,
`confirmation_required`, `scope_required`, `binding_mismatch`, `binding_pending`,
`preview_invalid`, `generation_stale`, `owner_unavailable`, `owner_busy`,
`maintenance_incomplete`, `wait_timeout`, `source_auth_required`,
`target_auth_required`, `source_rate_limited`, `target_rate_limited`,
`network_unavailable`, `target_storage_full`, `insert_result_unknown`,
`duplicate_candidates`, `attribution_unknown`, `fidelity_mismatch`, `source_missing`,
`target_missing`, `database_unavailable`, `persistence_failure`, `consistency_failure`.
Also register `maintenance_required` for a supported but non-automatic migration.
These are closed identifiers with fixed messages; provider errors map in memory.
Feature additions require registry review, not pass-through provider text.

Error record: code, class, role?, retryable bool, next retry time?, occurrence count,
first/last time, typed local operation/job reference?; no exception/reason string.
CLI maps class and command result to the existing CLI exit codes 0/2/3/4/5/6/7.
Successful status display of blocked work can be exit 0; diagnosing a failed check
uses its class. Accepted wait timeout retains receipt/status and exits 4.

Audit event: event ID/time, projection, closed action (`rule_changed`, `thread_admitted`,
`thread_stopped`, `command_completed`, `mode_changed`, `epoch_started`,
`insert_outcome_recorded`, `mapping_verified`, `maintenance_completed`), typed object
reference, controlled reason, typed before/after state or revision, command ref?.
No universal before/after dictionary. Private rule values live in rules storage,
not duplicated as arbitrary audit prose; revision references preserve provenance.

## Public and private output contracts

Internal DB records are never serialized to Web. Local CLI default permits fixed
status and opaque local operation/preview/request selectors needed to act; mail
IDs, bindings, rule values, fingerprints and filesystem paths need
`--private-metadata`. Even private CLI forbids body/raw/subject/per-message addresses,
full headers, attachment names/content, credentials and unfiltered provider errors.
The explicit interactive OAuth URL exception remains only in the auth terminal.

Public DTO envelope: `schema_version=1`, `sampled_at`, `freshness`, `age_seconds?`,
`scope=projection`, `data` as one of four closed records below.
`Freshness = fresh | stale | unavailable`; health components additionally allow
`unknown`. IDs, epoch UUIDs and local receipts are not public, including masked
forms; current epoch is described by kind/phase and operational start time.

| Record | Allowed fields only |
| --- | --- |
| Status | phase and health enums below; source/target role records with mode/auth state/last verified time; last poll/verified-insert/heartbeat times |
| Progress | discovery complete bool, scanned/discovered/completed thread counts, known message target count?, unique confirmed mapping count, all exclusive job-state counts, oldest runnable job age?, hourly/daily verified count, rate with unit/window/sample count, latency values? with unit/window/sample count |
| Issues | bounded groups of code/class/role, count, first/last time, retryable, next retry time?, fixed suggestion code; no individual object references |
| Diagnostics | app version, schema version, sync-owner count, DB readable/writable status, configured source mode, source/target scope readiness, memory/disk pressure enum, heartbeat/check sampled times |

`PublicPhase = uninitialized | initializing | backfill | incremental | recovering |
paused | maintenance`; `PublicHealth = healthy | degraded | blocked | unknown`.

Known message total is unavailable during discovery; no percentage/ETA until the
denominator is known. Unique success comes from verified mappings, never attempts,
operation receipts or total target mail. Missing-target/visibility counts are
separate audit issues, not removal of historical verified facts. Per-job counts
are exclusive; failed/review/cancelled rows remain visible. Metric samples absent
means `null` plus zero samples, not latency zero or healthy. Counts retain units
and scope. HTTP reads cached snapshots and has no Gmail/raw/command capability.

## Restore fence and transaction invariants

Restore rotates request namespace and owner run, preserves stopped/paused state,
sets binding pending and `restore_state=revalidation_required`. An older backup
may omit later accepted commands and inserts, including attempts that do not
exist in that backup. Therefore absent receipt/mapping/intent after restore is
not proof of no prior external effect. Safe receipt lookup and administrative
resume cannot clear this fence by themselves.

Revalidation treats any unverified projection/repair work from the restored lineage
as potentially affected, including subsequently rediscovered messages. It may
verify existing mappings and inspect candidates, but cannot insert merely because
target search is empty. M2-04's reviewed attribution/explicit-risk policy supplies
per-work release decisions; until then such work is attention. This is a safe
default extension point, not a claim that arbitrary DB loss can be reconstructed.
New local diagnostic/config commands in the new namespace are still usable.
Successful live binding verification alone does not clear restore revalidation.

| Transaction boundary | Atomic facts before external continuation |
| --- | --- |
| Accept command | Unique request identity+payload digest, typed command, receipt, and optional immediate local effect |
| Execute local command/action | Deduped execution marker, rules/tracking/generation/jobs/audit, receipt completion |
| Claim and prepare | Current job/claim/generation; raw budget is transient; intent durably prepared before send |
| Dispatch entry | Rechecked guards and dispatch-start intent marker under thread gate; commit before remote I/O |
| Result and verification | Factual attempt result always retained; verified mapping/job completion/count basis committed together |
| History page | Typed events and derived jobs; final page additionally advances committed cursor/coverage |
| Maintenance finish | New bundle/version/namespace flags and completion marker; no Gmail side effects |

Transactions never span network waits. A failed commit cannot be advertised as
accepted/completed or a checkpoint advance. Disk failure after remote invocation
halts further writes/advance and leaves recovery work. In-memory worker completion
cannot overwrite a newer generation or erase a known in-flight result.

## Review evidence and CC matrix

Each test scenario uses synthetic IDs/content and must assert durable facts and
forbidden actions, not mirror a second business state machine. This ADR plus the
writer ADR specify CC-01 through CC-14 from the plan:

- CC-01 keys/repair and CC-06 claims/stop: object-key table, work transitions and
  dispatch gate; P1-02/M1-02/M2-03/M5-03 tests.
- CC-02/03/04/05: request/owner/offline rules in writer ADR; M1-03 subprocess tests.
- CC-07: epoch/History transaction map; M3-02/M4-01/02 fault tests.
- CC-08: outcome certainty and fail-closed attribution extension; M2-04 tests.
- CC-09/10/11: maintenance locks, bundle recovery and restore namespace/fence in
  writer ADR; M1-04/M6-01/02 concurrency and crash tests.
- CC-12: field classifications and output allowlists; P1-02/M1-02/05 sentinels.
- CC-13: exclusive counts and unknown/stale/partial semantics; M1-05/M4-04 tests.
- CC-14: no-network transaction invariant and stable owner/view locks; M1-03 tests.

No AUTH accept algorithm, target attribution heuristic, implementation test result,
Gmail verification or release gate is approved by these tables. Independent review
and integration freeze this revision at their actual candidate commit, recorded
in the package Issue/PR rather than a self-referential SHA inside this file.
