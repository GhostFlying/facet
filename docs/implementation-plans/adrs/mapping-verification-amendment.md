# M1-02 direct-response mapping verification amendment r1

Status: proposed finite design; independent review and root source dispatch are
required. No implementation is authorized by this file's existence.
Date: 2026-10-02. Owned design base:
`1b7cd58b4846aab86edcbb781a999abb968d047c`; actual integrated core/test/output
input is main `f209fbe616dc65c70bbcdc4a104cf82b0d5dad27`.

This is a bounded supplement to the original M1-02 plan, storage schema r3
(`da2cfcd0081eaca8b102436186c9f5d034947fbf71ca2f0b95a14ee25840cfa0`)
and accepted insert-result amendment r3
(`2bf222b1819d80ddbed48387c8afd8fda5678db4b6425d1e89f396ea2687b427`).
Their files/prefixes remain unchanged. The integration owner records this reviewed
supplement in the implementation handoff, not by retrospectively rewriting them.
Later accepted History getter/replay amendments are unaffected.

## Purpose, ownership and hard boundaries

Storage r3 explicitly permits known_inserted and needs_attention(inserted) to
become verified through verify_mapping. Its result supplement releases the
original and recovery claims on attention. Neither document allocated the
attention completion disposition or readback visibility seam. This proposal
closes those points and first-map/replay group semantics, without changing SQL
tables, core enums, attempt identity or provider attribution.

M1-02 implements only the finite private repository transaction and synthetic
real-file tests after this exact proposal passes independent review. Actual M2
fidelity/readback consumers, reviewed M1-03 writer ownership and M1-04 immutable
account verification remain separate implementation gates. Constructing typed
rows or calling this Python method is not proof of remote fidelity/authorization.
There is no HTTP/CLI command or public "mark verified" interface here.

The future reviewed direct-response readback actor is the only production caller.
It reads the exact known target under the attempt's immutable target account,
uses the reviewed M2-02 versioned semantic/MIME comparison, and calls this method
only after a successful comparison and actual visibility observation. Network
work finishes before entering the DB transaction. A first attention resolution
must be dispatched through that reviewed actor; this library introduces no
automatic attention scheduler, retry or claim-resurrection policy. Until that
consumer exists, runtime attention resolution remains unavailable, not silently
implemented by trusting a generic row or a caller boolean.

Unknown outcomes, recovery search candidates, evidence attribution, missing
source/target, conflicting account/semantic facts and ambiguous candidate sets
cannot enter this operation. Unknown→known still requires the later independently
reviewed M2-04 extension. No repair authorization/registry is introduced; this
version handles first mappings from project_message only. Existing repair_message
subjects do not make repair/replacement valid before the separate reviewed repair
registry. Positive facts survive refusal; refusal never authorizes insert again.

## Finite API and private reads

Keep the exact existing mutation signature:

```text
verify_mapping(
  uow, projection_id: ProjectionId, attempt_id: LocalId,
  mapping: MessageMappingRow, history: MappingHistoryRow,
  ownership: TargetOwnershipRow, thread_target: ThreadTargetRow,
  guard: RevisionGuard
) -> WriteReceipt
```

All four row classes are the existing storage-local closed values, validated in
full; no optional patch/dict, callback, capability boolean or additional evidence
record. guard.expected is the current insert_attempts.revision, not the mapping
revision. A changed call returns updated, object_id=attempt_id, revision=old+1.
An exact already-verified replay returns replayed with the current attempt
revision and performs zero writes. Caller-supplied mapping_revision is separately
the mapping-history version and must be 1 for this first-map implementation.

Add only these two named, bounded storage-private reads to consume existing
thread-target facts without guessing their first owner or anchor:

```text
get_thread_target(view, projection_id: ProjectionId,
                  source_thread_id: ProviderId,
                  target_thread_id: ProviderId) -> ThreadTargetRow | None
get_thread_anchor(view, projection_id: ProjectionId,
                  source_thread_id: ProviderId) -> ThreadTargetRow | None
```

Each reads at most one row using the existing primary/unique index and obeys the
same view/session/projection/closed-output rules as get_mapping. No pagination,
provider I/O, raw connection, arbitrary query or additional table. A pre-transaction
read is not a guard: verify_mapping reloads and validates the facts inside its
one BEGIN IMMEDIATE UoW. A changed anchor/provenance input refuses, then a caller
may obtain the actual facts and retry with the actual current attempt guard;
this is local transaction retry, not a remote insertion retry.

## Entry facts, revision and finite execution branches

Always require a valid current writer session/instance/projection, active UoW,
exact record types, guard equal to current attempt revision and the stored
original project_message job/subject identities. Validate target role and the
attempt's historical binding revision; the current target binding must retain
the same immutable account identity. Source/thread/message/generation/job IDs
come from the stored attempt and original job, never from a new admission.

Require inserted certainty, direct_response attribution, nonnull target IDs,
nonnull semantic_digest/semantic_version and dispatch/result timestamps. The
semantic pair must already be stored and stays unchanged. This operation has no
parameter capable of supplying a missing pair. Normal known-inserted callers
may first use the accepted result method with their original VERIFYING claim to
record actual nullable fidelity/readback facts. Attention with a missing pair
continues to refuse: introducing a new attention fidelity-recording operation is
not silently folded into this amendment.

Pause, stopped/retracked source generation and credential revision rotation do
not erase the old dispatched effect. Therefore mapping verification does not
require a newly active source admission or current-generation equality against
the tracked thread; it requires the original attempt/job/claim generations agree
where a claim is required below. It does not change any thread, rule, generation,
pause, binding or restore fence. Persisting a verified old effect cannot make a
restored projection ready or prove unknown post-backup effects absent. Lost-owner
or closed-session callers still refuse. Ordinary owner startup/reconstruction
remains M1-03's gate; no old acquisition is imported by this method.

| Attempt branch | Exact original job/claim | Same-attempt recovery job | Result |
| --- | --- | --- | --- |
| known_inserted | CLAIMED; actual current-owner original claim_id, same job_revision/generation, phase VERIFYING | Must be absent | First verified group; complete original and delete only this claim |
| needs_attention with inserted certainty | NEEDS_ATTENTION, no original claim, null next_attempt_at; fixed last_error_code equals stored attempt.error_code | Exactly one stable recover_insert, Priority.RECOVERY, NEEDS_ATTENTION, null next_attempt_at, no claim, last_error_code equals stored attempt.error_code | First verified group; complete original and that recovery job together; no acquisition/requeue step |
| verified | Original COMPLETED, no claim, null deadline/error | Absent or exact same-attempt stable recovery COMPLETED, no claim, null deadline/error | Exact complete durable-group replay only |
| Any other state/combination | No special exception | No repair of allegedly missing claims/rows | Controlled refusal; no writes |

For attention, stored attempt.error_code must be nonnull and permitted by the
accepted result amendment's inserted-attention error allowlist. Recovery identity
must have codec/key/subject/projection/priority matching that same stored attempt;
retain its first origin, ID and epoch memberships. No missing recovery job is
created here; BLOCKED/QUEUED/RETRY_WAIT/CLAIMED/FAILED/CANCELLED combinations
refuse. Thus a running recovery acquisition cannot be stolen or hidden. This
attention-only no-claim branch is the explicit new finite resolution choice,
not permission for generic no-claim completion or completion of unknown effects.

Normal verification does not accept a recovery job and does not guess why one
exists. Historical verified replay checks the whole durable group before any
live-claim lookup/requirement; success does not reconstruct claims or repeat work.
The current attempt guard is still mandatory. A lost first response with an old
guard refuses; callers use the existing get_attempt/get_mapping plus the two
finite reads above to inspect actual committed facts, never decrement a revision
or assume absence from an exception. There is no Gmail call on replay.

## Exact first-map four-row group

All projection IDs equal projection_id. Let A be the stored attempt and t be
mapping.verified_at. The current mapping and all mapping_history for this source
must be absent on first mutation; an older mapping, tombstone or superseded
history is not an invitation to replace/repair. Existing target ownership for
A.target_message_id must also be absent. A partially present group is corruption
or a conflicting input, never an upsert/adoption opportunity.

- MessageMappingRow: source_message_id/source_thread_id/attempt_id and target IDs
  equal A; mapping_revision=1; last_audit_at=null and target_present=null. This
  verification does not fabricate a weekly-audit record.
- MappingHistoryRow: same source/thread/attempt/target IDs, mapping_revision=1,
  verified_at=t, superseded_at=null. History identity/time are immutable.
- TargetOwnershipRow: target/source message IDs equal A; first_attempt_id=A.id,
  recorded_at=t. Ownership never migrates to another source or attempt.
- ThreadTargetRow: source/target thread IDs equal A. If the exact pair already
  exists, the complete supplied row must equal it, retaining first_attempt_id,
  created_at and anchor. The earlier first_attempt must be verified, have the
  same projection/source thread/target thread and a matching durable mapping
  history; it need not be A. Do not rewrite it for every message in that thread.
  If the pair is new, first_attempt_id=A.id and created_at=t. anchor=true iff
  there is no existing anchor for this source thread; otherwise anchor=false.
  Existing non-anchor pairs do not become anchors here. A caller cannot switch
  anchors or repurpose a target thread by passing a different bool.

Before any group write, validate all time relationships: t is a valid canonical
Timestamp and t >= A.prepared_at, dispatch_started_at, result_at, original job
updated_at, and (when present) original claim.acquired_at and recovery.updated_at.
For a reused thread target, its created_at must be <=t and its own verified
first-attempt/history facts must agree. Overflow of any increment refuses.
Do not clamp timestamps or rewrite existing times on wall-clock rollback.

Mapping visibility is an actual readback fact: normal/spam/trash only, never
unknown masquerading as normal. If A.visibility is known, input must equal it;
later changes belong to record_target_audit, not this transaction. If A.visibility
is unknown, this finite verify call may set it to the supplied actual readback
visibility in the same UoW; this applies to both accepted first-map branches.
It is not a certainty or attribution upgrade. Spam/Trash remains explicitly
Spam/Trash in both mapping and attempt, not proof of normal All Mail visibility
or a request to move/delete mail. This does not weaken the final target UI gate.

## Atomic effects and replay comparison

One accepted first verification transaction:

1. Recheck the branch, CAS, identity, time, visibility and all four-row constraints.
2. Insert mapping/history/ownership, and insert the thread target only when new.
3. Set A.state=verified, verified_at=t, visibility as above, error_code=null,
   next_recovery_at=null, revision=old+1. Preserve every other attempt field,
   including original claim provenance, semantic pair and recovery_checks.
4. Set original job COMPLETED, next_attempt_at=null, last_error_code=null,
   updated_at=t, revision=old+1; preserve identity, priority, subject, first
   origin, created_at and attempt_count. Remove only the validated original claim
   in the normal branch. For attention, perform the identical finite completion
   update on its existing recovery job; there are no claims to remove.
5. Keep all epoch_jobs membership unchanged; epoch completion/counts subsequently
   read these actual completed jobs and unique mappings. No arbitrary epoch
   becomes complete as a side effect of this method.

No success receipt escapes before UoW commit. All failures poison/roll back the
entire UoW even if a caller catches StorageFailure inside its body. Reopen after
failure sees the complete pre-state, never a subset of the four rows or completed
work without its verified mapping. Commit ambiguity invalidates the session and
uses actual reopened facts; it does not invoke insertion or synthesize a receipt.

For verified replay, supplied four rows must equal their actual durable rows,
and attempt verified_at/IDs/semantic presence, original completed job and any
recovery completed job must agree. Recheck immutable historical target account
and thread-target provenance as above, but do not require a live acquisition or
reactivate stopped threads. A later target audit can change mapping visibility,
last_audit_at and target_present; the caller must use the actual current mapping
row for replay, and replay compares attempt's own original verification visibility
separately (audit is not allowed to rewrite it). Historical history/ownership/
thread-target fields remain immutable; stale pre-audit mapping input refuses.
Different t, source/target ID, revision, first ownership, anchor, partial group,
unfinished/corrupt job or stale guard cannot be called replay. No changed rows
are accepted in the verified branch. Return the actual attempt receipt only.

## Required real-file acceptance and consumer gate

| ID | Positive and detecting negative evidence |
| --- | --- |
| MV-01 | Normal direct known result with current original VERIFYING claim commits all four rows, verified attempt and completed job; DISPATCHING, wrong owner/claim/revision and missing semantic pair refuse atomically |
| MV-02 | Known→attention through actual accepted result API, then exact direct readback resolution completes original+stable recovery with no claim resurrection; unknown attention and missing/queued/claimed/wrong-key recovery refuse |
| MV-03 | Stop/retrack or pause after actual dispatch preserves verification of that old effect without new admission; no new job/claim/attempt or changed generation/fence, and normal branch still rejects another owner |
| MV-04 | Two messages sharing actual target thread retain its earlier first_attempt/time/anchor; actual fallback adds non-anchor pair; forged first owner, changed anchor or mismatched source thread refuses |
| MV-05 | First map revision 1/null audit/null superseded fields succeeds; existing source history/current mapping or foreign target ownership cannot be silently repaired/adopted |
| MV-06 | Stored unknown visibility becomes actual normal/spam/trash distinctly; known conflicting visibility and unknown input refuse. Attention lacking semantic pair still refuses, never fills it from arbitrary mapping data |
| MV-07 | Stale lost-ack guard refuses, actual get_attempt/get_mapping/thread reads allow exact verified replay without any write/revision bump or live claim; changed first facts and damaged durable group refuse |
| MV-08 | Real target audit after verification changes only the allocated audit facts; current mapping replay works and stale pre-audit input refuses, attempt's historical verification visibility stays unchanged |
| MV-09 | t equal to latest valid boundary accepted; result/claim/job/first-target time later than t, revision overflow and clock rollback reject without changing old facts |
| MV-10 | Inject failures after each group/job write, catch inside UoW and reopen real WAL DB: entire transaction rolled back, no false success/partial group, unresolved effect still blocks new prepare |
| MV-11 | Epoch joined original/recovery work is completed only by actual group commit; other unfinished/attention epoch work still prevents all-success; unique success counts map sources rather than attempts |
| MV-12 | Synthetic private IDs/digests are allowed only in allocated rows; no raw/mail headers/provider responses or errors in DB/WAL/log/stdout/public DTOs; malformed exact records yield only fixed StorageFailure |

This supplement adds no network/provider proof. Tests construct synthetic stored
direct-response/fidelity facts to exercise the real storage contract, not to claim
Gmail verification or certify the future M2 caller. Consumer integration must
separately show actual target-account readback, versioned semantic comparison,
correct attention scheduling/dispatch, no network inside UoW and no public data
leakage. First-map storage tests do not close repair, M2-04 recovery attribution,
G1/G3, CLI resolution, live Gmail or full Phase 1 acceptance.
