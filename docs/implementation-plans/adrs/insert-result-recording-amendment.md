# Proposed M1-02 insert-result recording amendment r3

Date: 2026-10-02. Status: proposed; independent review required before implementation.
This is an isolated design document, not a change to the writer ADR or SQL source.
Owned authoring base: `1b7cd58b4846aab86edcbb781a999abb968d047c` in the writer-design
worktree; current integrated input remains `f209fbe616dc65c70bbcdc4a104cf82b0d5dad27`.
The SQL engineer owns integration into the persistence branch and references this
exact reviewed revision in its execution record. No Git/source changes here.

Revision trace: r1 SHA-256
`8418dc6b1e7ea1af800a50e4ebc7122e714ebff5c60626782a084ddd1e4145c0`
received independent changes_requested for result-time ordering and an ambiguous
existing-recovery-job join. This r2 closes only those two findings and their paired
tests; it does not turn the original r1 into approved evidence.

r2 SHA-256 `383e87808382ead0e868e1957888d77b22fa18ba3a6eea54771f778f251d239c`
closed those findings but received one affected-consumer changes_requested:
a legally retried recovery claim retains its prior fixed error. This r3 changes
only that CLAIMED-row predicate and its regression case; all other r2 guards remain.

## Scope, trace and reason

The independently accepted storage r3 artifact is SHA-256
`da2cfcd0081eaca8b102436186c9f5d034947fbf71ca2f0b95a14ee25840cfa0`.
Its lines 426–493, 729–754, 787–791, 810–829 and 984 define attempt facts, CAS,
results and recovery, but do not completely specify incoming full-row revision
semantics or original-job disposition on unknown results. Its later History r4
amendment is separate and unchanged. The original approved implementation plan,
storage r3/r4 and writer r2/r3 remain byte-identical; this supplement is not an
assertion that these choices were already implemented or implicitly approved.

This amendment closes only record_attempt_result, its derived recovery work and
related claim/replay predicates. No table, column, enum, arbitrary patch API,
provider proof object or command receipt is added. It reuses actual core types,
InsertAttemptRow, SyncJobRow, RevisionGuard, WriteReceipt and the existing UoW.
No insert/network callback occurs in a transaction. Actual adapter invocation
classification and recovery attribution remain M2's independently reviewed work.

## Exact call and CAS contract

The proposed finite signature is:

`record_attempt_result(uow, projection_id:ProjectionId, row:InsertAttemptRow,
observed_at:Timestamp, guard:RevisionGuard) -> WriteReceipt`

observed_at is the sole new parameter, using the existing core type. It supplies
this recording operation's time without a hidden clock or replacing an earlier
provider result_at. It is not proof of effect, a new payload, or an optional
caller override. All values undergo exact type and axis validation first. Then
require the actual live writer session/UoW/projection, existing matching attempt,
and guard.expected equal to its current revision before considering replay.

- Exact replay: row equals every stored field, including revision. Return
  replayed, object_id=attempt_id, actual current revision; perform zero writes.
  observed_at may be later but causes no timestamp, job, claim, membership or
  scheduling update. Validate it is not before stored prepared/dispatch/result/
  verified times. No active claim is required to acknowledge identical historical
  facts, but no execution permission is conferred. Stale guard always refuses.
- Mutation: row.revision must equal current+1 with overflow checked; at least
  one allowed factual/state field must actually change. Unsupported differences,
  fake increments without changes, same revision with changed data, and gaps
  refuse. Return updated with attempt_id and the actual resulting revision only
  after the UoW succeeds. All affected job revisions increment once if changed;
  these are not substituted for the attempt revision in its receipt.
- A mutation's observed_at is at least every referenced attempt time, current
  affected job.updated_at and required live claim.acquired_at. Derived jobs use
  this time; existing provider result_at/dispatch_started_at are not overwritten
  merely because recording or readback happened later. Backward time refuses
  without losing the prior factual state; caller can reconcile its observation.
- When result_at changes null→value, require result_at>=prepared_at and, if
  dispatch_started_at exists, result_at>=dispatch_started_at. The upper bound is
  observed_at. These checks are separate from observed_at being after all times:
  dispatch=10:00, result=09:00, observed=11:00 is invalid. Existing result_at is
  immutable, not clamped/replaced to conceal clock rollback. A backward-clock
  result causes controlled refusal and whole-UoW rollback; the previous durable
  marker/facts and unresolved work remain, with no new invocation permission.

After lost commit acknowledgement, use existing get_attempt(view,id) and get_job
to inspect actual facts, then submit an identical row with a fresh actual guard
if a receipt is needed. Never increment blindly, infer success from revision
alone, bypass CAS, enqueue work on a replay, or repeat the remote insert.

## Allowed facts and current ownership

Prepared identity/provenance remains immutable: attempt/job/source IDs, generation,
binding role/revision, original claim_id, prepared_at, requested target thread,
raw digest, RFC Message-ID and date policy. dispatch_started_at is established
only by mark_dispatch, not this method. row.claim_id remains the original
acquisition even when a recovery job later has a different claim.

Existing nonnull result_at, target IDs, semantic digest/version and verified_at
cannot change or be cleared. Digest/version are null together or nonnull together;
null→pair is allowed only from real reviewed fidelity processing. Unknown→known
or definite-not-inserted by candidate assertion stays forbidden. Missing candidate,
HTTP text, successful parsing or arbitrary row construction proves nothing.
Visibility may enrich unknown→normal/spam/trash only after actual readback and
only for inserted certainty; any later visibility change belongs to target audit.
Non-inserted certainty requires unknown visibility. These finite differences do
not authorize storing headers, raw, exception text or per-message addresses.

Fresh direct results (dispatch_started→known_inserted/pending_recovery/
definite_not_inserted/needs_attention) require the original project_message or
repair_message job CLAIMED and its exact current-owner acquisition DISPATCHING,
with claim_id/generation/job revision matching the attempt and job. The original
binding revision must still resolve to the same immutable account; subsequent
credential rotation, pause, restore fence or source stop does not erase the
already-dispatched result. They do not authorize new dispatch either. An old
owner process cannot submit through a new owner's session or fabricate a claim.
Restart reconstruction is a separately reviewed owner/recovery operation.

Prepared→cancelled_before_dispatch/definite_not_inserted requires that original
current-owner acquisition PREPARING. No provider effect is claimed on this path.
Known-inserted same-state enrichment and known_inserted→needs_attention require
the retained original current-owner VERIFYING claim. Attention(inserted)→verified
is exclusively verify_mapping with actual fidelity/ownership evidence, not this
method. In particular a generic record row cannot mark verified or complete work.

Pending_recovery→needs_attention after original claim release requires the one
stable recover_insert job for this same attempt to be CLAIMED by the actual
current owner in PREPARING, with its real claim/job revision consistent. Recovery
uses the attempt's original source/generation but is a read/check operation;
stopped generation cannot convert it into new insert permission. Its claim must
not be substituted into row.claim_id. Only the three existing ClaimPhase values
exist; RECOVERY_MATCH is invalid and recovery acquisition starts PREPARING.

All other changed rows/edges refuse here. Exact historical replay remains separate
and never reconstructs a missing claim or repairs supposedly missing side effects.

## Atomic original-job and recovery-work mapping

Result storage and the following consequences are one UoW, not a result commit
followed by a second defer call. The original job identity/key/subject/first epoch
and attempt_count never change in this method. No rule/thread/generation is
reactivated. For any changed job, revision increments once and updated_at uses
observed_at; next_attempt_at is null in the blocked/attention branches.

| Accepted result mutation | Original project/repair job | Recovery job and claims |
| --- | --- | --- |
| dispatch_started→known_inserted | Keep CLAIMED and exact acquisition; change claim phase DISPATCHING→VERIFYING, acquisition job_revision retained | Do not create recovery job or release claim; no mapped-success yet |
| dispatch_started→pending_recovery | Set BLOCKED, last_error_code=insert_result_unknown, next_attempt_at=null; release original claim | Ensure one stable queued recover_insert for this attempt; no recovery claim until actual claim() |
| dispatch_started→needs_attention, unknown or inserted | Set NEEDS_ATTENTION with the fixed row.error_code, next_attempt_at=null; release original claim | Ensure one stable NEEDS_ATTENTION recover_insert row, no claim; attention is retained selected work, not successful completion |
| known_inserted→needs_attention | Same NEEDS_ATTENTION mapping; retain all positive target facts and release original VERIFYING claim | Ensure same stable attention recovery row; no automatic verification/reinsert |
| pending_recovery→needs_attention | BLOCKED→NEEDS_ATTENTION, fixed row.error_code; original claim remains absent | Current claimed same-attempt recovery job becomes NEEDS_ATTENTION with same code, release its PREPARING claim |
| Same-state known_inserted nullable fidelity/readback enrichment | No job mutation; retain CLAIMED/VERIFYING acquisition | No recovery enqueue or release |
| prepared→cancelled_before_dispatch/definite_not_inserted or dispatch_started→definite_not_inserted | Only persist result facts; retain current CLAIMED acquisition/phase | No recovery enqueue, no implicit retry, no new attempt |

BLOCKED above means an unresolved-effect blocker, not proof that insert is safe
to retry. This explicitly clarifies the core job-transition summary's narrower
safe-retry wording for this one result branch. It does not broaden generic
defer_job or permit BLOCKED→claimed insert while the unresolved attempt exists.
The core unknown/known-unverified blocker and storage uniqueness predicates stay.

Definite/cancelled disposition is deliberately composed later by the actual
worker's permitted defer/stop policy, preferably in the same UoW when known.
No method here guesses a retry time or turns cancellation into source_missing.
An existing stop transaction's already-cancelled identical attempt replays
without restoring its claim. A caller catching any failed later operation inside
the same UoW cannot commit the earlier result/claim/job changes: the UoW is poisoned
and rolls the complete group back. Claim-release alone cannot lose selected work.

Internal recovery creation is finite, not a public arbitrary job producer:
kind=recover_insert, subject=JobSubjectRecoverInsert(original attempt_id), existing
key codec v1, Priority.RECOVERY, new UUID4 LocalId, revision=0, attempt_count=0,
created_at=updated_at=observed_at, next_attempt_at=null, state/code as above.
Initial queued recovery has last_error_code=null; attention has its fixed error.
origin_epoch_id copies original job's first origin. Add epoch_jobs membership
for every already selected epoch containing that original job, in the same UoW;
do not change first origin when joining a preexisting stable recovery key.

Every existing recovery row must match projection, kind=recover_insert, the exact
attempt subject, key_version=1 and its recomputed stable key, Priority.RECOVERY,
and immutable attempt relationship. Preserve job ID, created_at, first origin
and attempt_count. Its created_at<=updated_at<=observed_at must hold. A conflicting
priority/key/identity is refusal, not silently normalized. The following matrix
is exhaustive for changed result calls (exact result replay does not join jobs):

| Requested result branch | Existing recovery row | Exact action |
| --- | --- | --- |
| First pending_recovery or first needs_attention | Absent | Create the exact queued or attention row defined above |
| First pending_recovery | QUEUED, no claim, next_attempt_at=null, last_error_code=null | Retain the entire job row, including priority, revision and updated_at; add only missing selected-epoch memberships |
| First needs_attention from dispatch_started or known_inserted | QUEUED, no claim, next_attempt_at=null, last_error_code=null | Set NEEDS_ATTENTION and row.error_code, keep next_attempt_at=null; updated_at=observed_at and revision+1 exactly once; preserve other columns |
| First needs_attention from dispatch_started or known_inserted | NEEDS_ATTENTION, no claim, next_attempt_at=null, last_error_code equals row.error_code | Retain entire job row including updated_at/revision; add only missing selected-epoch memberships |
| pending_recovery→needs_attention | CLAIMED, actual matching current-owner PREPARING acquisition, next_attempt_at=null, last_error_code null or an existing valid ErrorCode | Set NEEDS_ATTENTION and overwrite that prior last_error_code with row.error_code, updated_at=observed_at, revision+1 once; release exactly that recovery claim, retain other columns |
| Any above branch | BLOCKED, RETRY_WAIT, CANCELLED, FAILED, COMPLETED, SOURCE_MISSING, or any unlisted state/field combination | Controlled consistency refusal; no promotion, deadline clearing, error replacement or implicit resume |

A QUEUED or NEEDS_ATTENTION join does not update the recovery row merely because
the attempt changed. Adding epoch_jobs changes only that relation, not the job's
revision/time. A result needing pending recovery cannot reuse an attention row as
queued. Claimed recovery is accepted only in the explicit pending→attention row;
first direct-result completion cannot steal a recovery claim. All matrix failures
roll back the attempt, original-job disposition, membership and claim changes.
This restrictive join is not a general recovery scheduler or authority to resume
previously blocked work. A future owned scheduler needs its reviewed finite rules.

The CLAIMED row may be a legitimate second acquisition after the existing
recover-job defer_job(retry_wait, network_unavailable, retry_at) and later claim.
That claim clears its deadline but may retain the prior typed error; this is not
a reason to reject a newly observed ambiguity. Only the actual current claim,
same attempt/owner/generation and PREPARING phase permit the transition above.
The prior error is replaced only together with NEEDS_ATTENTION, never via a
same-state patch. Unknown strings, a still-pending deadline, stale/wrong claim or
unclaimed retry_wait still refuse. This adds no counter, deadline or retry API.

## Closed schedules and error changes

This minimal supplement **does not implement recovery scheduling updates**.
recovery_checks and next_recovery_at must equal their stored values on every
call here, including transitions. Initial attempts use recovery_checks=0 and
next_recovery_at=null as already prepared; a later separately reviewed scheduler
may own counters/deadlines, but this full-row API cannot increment/reset/change
them. Repeated check timing and M2-04 completion cannot be claimed from these
columns merely existing. No new timer/retry queue policy is invented.

Same-state error_code is immutable, including null: readback failure needing a
new error goes through the existing allowed needs_attention transition, not a
same-state generic patch. Same-state fidelity/readback enrichment is limited to
known_inserted with the actual VERIFYING claim as above. Other same-state calls
must be exact replay; terminal rows never enrich in this method.

State changes set error_code only as follows:

- known_inserted: null; preserve any earlier immutable positive facts.
- pending_recovery: insert_result_unknown.
- needs_attention: one of insert_result_unknown, attribution_unknown,
  duplicate_candidates, fidelity_mismatch, consistency_failure; it is a reason,
  never evidence to bind a candidate or mark failure as verified.
- cancelled_before_dispatch: generation_stale or owner_unavailable; no remote
  dispatch/result claim. A normal stop's existing typed transition remains valid.
- definite_not_inserted: one of source_auth_required, target_auth_required,
  scope_required, binding_mismatch, binding_pending, generation_stale,
  owner_unavailable, owner_busy, wait_timeout, network_unavailable, invalid_input,
  source_missing, source_rate_limited, target_rate_limited, target_storage_full.
  Code alone is never sufficient: pre-dispatch actual local failure or reviewed
  direct-response rejection must establish certainty. Post-dispatch arbitrary
  error text/status, timeout or absent search cannot choose this state.

On a permitted state transition, replacing a prior error_code is allowed because
it describes the new state, unlike immutable provider identity/result facts.
No other nonnull overwrite is authorized; incompatible existing facts refuse.

## Finite examples and required acceptance (planned)

1. Claim project job → prepare → mark_dispatch → leave UoW → actual invocation →
   read current attempt → row known_inserted/revision+1 → record with observed_at
   and actual guard. Commit leaves original claim VERIFYING. Same-row/current-guard
   replay changes nothing. Actual verify_mapping, not this call, completes success.
2. After actual dispatch and response loss, record pending_recovery plus observed
   time in one UoW. Commit leaves original BLOCKED/no claim and one queued recovery
   job with original-epoch memberships. No new project job/attempt is generated.
3. claim the recover job in PREPARING; an actual unresolved/ambiguous check may
   record pending→attention with new attempt revision and observed time. Commit
   keeps original claim provenance and releases only the recovery acquisition.
4. Pre-call definite rejection records facts, followed by an explicitly permitted
   worker defer in the same UoW if its policy is already decided. Failure anywhere
   rolls back both, including if caught before leaving the UoW.

| Test | Positive / detecting negative control |
| --- | --- |
| IR-01 | Correct next-row revision and current guard update once; stale/current-with-change/skipped/overflow/fake-next replay refuse without writes |
| IR-02 | Lost-ack reopen/get_attempt/exact-current replay returns same receipt facts, zero job/claim/time/membership writes; absence/revision alone never permits invoke |
| IR-03 | Known result retains VERIFYING claim and post-stop facts; wrong attempt/source/binding account/claim/owner acquisition rejects; stop cannot delete target IDs |
| IR-04 | Same-state null semantic pair and actual visibility enrichment update once; conflicting/cleared IDs/digests/times, unknown certainty upgrade and terminal enrichment refuse |
| IR-05 | Pending result atomically original BLOCKED/no claim + one recovery key and epoch membership; valid QUEUED join retains revision/time/count/first origin, QUEUED→attention changes only listed fields; preexisting BLOCKED/RETRY_WAIT, wrong priority/key/subject, nonnull queued deadline/error or mismatched attention reason refuse with full rollback |
| IR-06 | Pending→attention requires actual same-attempt recover claim PREPARING; real defer_job(retry_wait,NETWORK_UNAVAILABLE)→eligible reclaim preserves prior error and may record ambiguity, atomically replacing error and releasing only current claim; stale first claim/wrong owner/attempt/phase/generation, nonnull deadline, untyped error and ghost RECOVERY_MATCH refuse; no new insert permission |
| IR-07 | Attention inserted retains direct-response target facts, never success; definite/cancelled result does not implicitly enqueue retry or allocate new attempt |
| IR-08 | Same-state counter/deadline/error changes and invalid pairs fail; prepared/dispatch=10:00,result=09:00,observed=11:00 refuses despite late observation; result>=dispatch and observed>=result succeeds, pre-dispatch result>=prepared succeeds; backward clock cannot rewrite existing result or lose the durable marker |
| IR-09 | Fault between attempt/job/recovery/membership/claim mutations, including caught exception, rolls entire UoW back; real file reopen shows old group or complete new group, never partial |
| IR-10 | Full actual stored rows/SQL/WAL/errors contain only permitted typed metadata; raw/provider/exception sentinels and hostile repr are not persisted or output |

These are additional obligations on existing DB-10/11 and UoW/privacy gates, not
claimed tests or a replacement for the package's remaining acceptance. Independent
review must approve this exact amendment before implementing the new signature
or disposition rules. SQL source/CI candidate approval remains a later separate
gate; actual Gmail adapter, worker/recovery attribution and live authority remain
pending. No product disclosure, privacy scope or milestone dependency changes.
