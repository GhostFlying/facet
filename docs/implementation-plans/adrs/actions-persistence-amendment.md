# Proposed action persistence supplement r1

Status: design proposal, not implementation authorization or M5 acceptance.
Authoring base: `1b7cd58b4846aab86edcbb781a999abb968d047c`.
This bounded supplement consumes persistence-schema-v1 r3 (SHA256
`da2cfcd0081eaca8b102436186c9f5d034947fbf71ca2f0b95a14ee25840cfa0`),
its action_commands table and three finite action repository methods. It does
not amend that file, the 32-table schema, core enums, result/mapping/read-view
supplements, the product's learning policy or source permissions.

## Scope and implementation ownership

Retain exactly these external write signatures, each returning WriteReceipt:

- `register_action(uow, projection_id, row:ActionCommandRow)`.
- `complete_action(uow, projection_id, row:ActionCommandRow, guard:RevisionGuard)`.
- `record_cleanup(uow, projection_id, action_id:LocalId, cleanup:CleanupState,
  error:ErrorCode|None, guard:RevisionGuard)`.

Future implementation files: `src/facet/db/repositories/actions.py`, focused
`tests/unit/test_db_actions.py`, and finite private participation in
`db/connection.py` (UoW lifecycle), `repositories/policy.py` (three existing
policy operations) and `repositories/jobs.py` (enqueue receipt). Existing
repository export/typed selector registration may expose these three methods
and reuse the existing ActionCommandRow decoder; no generic dictionary API.
No label client, normalization, SDK, CLI, M5 actor, scheduler, schema migration,
network operation or public DTO is implemented by this slice.

All methods use the actual writer-owned UoW, projection/row identity, exact
closed types, fixed errors and caught-failure poisoning already required by r3.
No transaction spans network. A receipt is storage evidence, not a Gmail label
activation/policy decision or proof that cleanup ran remotely.

## Registration and immutable activation identity

New input is PENDING, revision 0, cleanup NOT_REQUESTED, executed_at/error null.
Load the referenced actual SourceEventRow. Require LABEL_ADDED key, non-null
resolved source_thread_id, matching projection/history record/label/thread, and
processing RESOLVED or CONSUMED. An unresolved, missing or attention event cannot
create an activation. observed_at equals that first event's stored observed_at.
Provider history IDs remain opaque strings, not timestamps or contiguous counts.
Kind is one of the three existing ActionKind values. Its correspondence to the
configured resolved label ID is the future M5 producer's responsibility; this
repository does not infer kind from label text or accept a current label snapshot
as a History event. No legacy observation is registered by this API.

Look up both action ID and unique `(P, history_record_id, label_id, thread_id)`.
If the ID already addresses another tuple, reject CONSISTENCY_FAILURE. For an
existing tuple require same kind and a valid incoming event with the same tuple;
multiple messages in one activation may legitimately have different event IDs,
local UUIDs and observation times. Return REPLAYED with the original action ID
and its actual current revision, preserving ALL first-row fields/state. Do not
insert alias rows or replace its event. A proposed alias ID already used by a
different activation rejects. No business work or cleanup is performed here.
Remove/re-add under a different real history record creates a different tuple.

All new fields are private normalized metadata. Rules alone hold learned values;
action rows never gain headers, label names, addresses or opaque payloads.

## Guard, revision and historical replay

complete_action loads by the canonical stored action ID, checks actual guard
first, then compares immutable fields (P, ID, event, history, label, thread,
kind, observed_at). Do not pass a registration alias ID to this method.
An exact full-row replay uses incoming revision=current and returns REPLAYED
without writes, hooks, generation checks, cleanup or re-enqueue. This remains
true after a later rule removal or thread stop: history is not reapplied.
Stale guards never become permission through an otherwise matching row.

A new transition uses incoming revision=current+1 with checked overflow.
Only PENDING→EXECUTED and PENDING→NEEDS_ATTENTION are enabled. An unchanged
PENDING row can only replay; no same-state arbitrary patch. NEEDS_ATTENTION is
terminal in this slice; explicit later resolution is a separately reviewed M5
consumer, not a reset-to-pending shortcut. EXECUTED cannot be rewritten through
complete_action, even to change cleanup. Other states reject CONSISTENCY_FAILURE.

PENDING→NEEDS_ATTENTION requires executed_at null, cleanup NOT_REQUESTED and a
non-null fixed ErrorCode, with no effect scope or business changes for this
action. It makes the unresolved work explainable, not successfully executed.
PENDING→EXECUTED requires executed_at `t >= observed_at`, null error and cleanup
NOT_REQUESTED, and the exact finite same-UoW witness below. Lack of a registered
actual producer/witness fails OWNER_UNAVAILABLE; contradictory facts fail
CONSISTENCY_FAILURE. Failure poisons the entire composing UoW.

## Finite private effect scope, not a marker-as-proof

The existing schema has no action→chosen-rule foreign key. The presence of an
enabled rule and an active thread is therefore insufficient to complete any
arbitrary action. Allocate a private, in-memory UoW scope, never a persisted
payload, public capability or serialization format. Existing three public
signatures remain unchanged.

Private exact selection `_ActionSelection` has only:
`action_id:LocalId`, `rule:RuleRef`, `expansion_job_id:LocalId|None`.
ADD_SENDER/ADD_DOMAIN require the expansion ID; BLACKLIST requires null.
It contains no raw learned value or caller boolean asserting an effect.
The sole private entry is
`_begin_action_effect(uow, P, selection:_ActionSelection,
guard:RevisionGuard, producer:object) -> None`.

The fixed production `_ACTION_PRODUCER_TYPES` tuple starts empty. Only a future
independently reviewed M5 implementation may register its exact compiled type;
no environment setting, import path, plugin, arbitrary callback or public
registration function. A type match alone does not prove the learned sender:
actual producer acceptance must prove label-ID/kind binding, latest eligible
external sender, own-address/domain exclusions, domain policy and selected-thread
authorization. A syntactic selection cannot substitute for these gates. Test
fixtures may patch the private tuple with one fixed synthetic producer, which
is not packaged in production or evidence that M5 is enabled.

The entry checks actual UoW/producer, canonical PENDING action and guard before
any business operation, then stores one opaque identity-enrolled scope. Only one
scope may be active in a UoW; no nested/interleaved second action. It captures
the exact action row, selected rule/current revision or absence, current sealed
ruleset revision/member for that rule or absence, selected thread/admission or
absence, and selected expansion job or absence. These are typed row snapshots,
not caller-supplied copies. The scope is not constructible via public exports.

The UoW also initializes private `_action_business_touched:bool=False` at entry.
Calls to publish_rules/admit_thread/stop_thread/enqueue set it, including matching
no-op calls; this flag is not caller-settable and only the UoW may reset it on
exit. Beginning a scope requires it false. PENDING→NEEDS_ATTENTION also requires
it false and no scope: that bounded branch cannot hide preceding policy/job work
in its transaction. Registration itself does not set this flag. Unrelated SQL
business composition should use a separate UoW, not relax this rule.

Its finite internal fields are UoW identity, P, selection, before_action,
before_rule, before_rule_revision, before_ruleset_revision, before_member,
before_thread, before_admission, before_job, rule_receipt, thread_receipt,
enqueue_receipt and phase (OPEN/CONSUMED). Nullable before facts mean absence;
all three receipt slots are WriteReceipt|None; null means the matching operation
has not completed. No free-form
proof list/dictionary is added. No SQL/exception/raw string is retained.

Private hooks in the existing publish_rules/admit_thread/stop_thread/enqueue
implementations record their actual successful matching operation receipts into
that scope AFTER their normal SQL/guards succeed. A caller-supplied WriteReceipt
cannot populate it. Receipts alone are insufficient: complete_action reloads
and validates the rows/relations below. While a scope is open, a second policy
mutation of the selected rule/thread, an unrelated policy mutation, or a second
different selected enqueue rejects; the prescribed one rule mutation plus one
thread operation plus matching enqueue are the finite composition. Ordinary
calls outside an action scope retain their existing behavior.

Commit with an OPEN scope rejects and rolls back, including when the composer
forgot complete_action. Any nested failure poisons the UoW, even if caught. A
successful complete consumes it; rollback/exit invalidates it. Reusing a scope
in another UoW, after commit, for another action or after an exception rejects.
This closes “business effects committed but command pending” without a new table.

## Kind-specific before/after evidence

All checks occur before updating the action row in the same write transaction.
The chosen rule must be present, current at the selected RuleRef, enabled, and
an exact member of the current sealed ruleset. Kind must be respectively
ALLOW_SENDER, ALLOW_DOMAIN or BLACKLIST_SENDER. A disabled/out-of-snapshot rule
is never proof. Normalization/authenticity are still actual M5/M1-06 gates.

Rule no-op: selected rule/revision and its enabled member already existed at
scope entry; require identical rule/revision/member and unchanged ruleset, no
rule receipt. Preserve its origin and effective_at: do not manufacture another
rule revision merely to attach an action. Otherwise require one captured
publish_rules receipt that introduced/enabled precisely the selected revision,
origin ACTION_LABEL, effective_at=t and ruleset created_at=t. Existing rule
identity/value cannot change; revision sequencing remains publish_rules' guard.
No bulk prospective-history expansion is implied by publishing this rule.

ADD_SENDER/ADD_DOMAIN require the selected thread active at completion. If it
was absent/inactive at entry, require captured admit_thread receipt and the new
durable ThreadAdmission referencing this exact action ID, admitted_at=t, exact
post-generation/admission revision and normal current-generation guards.
If already active, preserve the entire tracked-thread and current admission
rows byte-for-field: no new admission, generation or attribution is fabricated.
A matching replayed admit_thread receipt is optional for this no-op branch.

In both allow cases require a successful same-scope enqueue receipt for the
selected actual expansion job ID (use actual receipt ID after stable-key alias
resolution). It must be EXPAND_THREAD for this exact selected thread/current
generation, its required subject epoch, valid same-P epoch and epoch_jobs link;
the current state must be QUEUED, CLAIMED, RETRY_WAIT or BLOCKED, with the existing
job state's valid claim/error/deadline invariants. Old cancelled/completed/failed/
attention/source-missing work does not prove this selected disclosure is pending.
First origin/ID is preserved on replay. This method does not choose an epoch or
manufacture a job: actual M5 must supply its reviewed bounded selected-thread
work composition. An unrelated epoch job, resolve job or empty job set cannot
stand in for full-thread expansion. No proof means no EXECUTED transition.

BLACKLIST requires the blacklist rule above and no expansion selection. If the
thread was active at entry, require the captured stop_thread receipt for that
same prior generation, reason BLACKLIST, stopped_at=t and generation+1, with
the existing stop implementation's cancellation/intent-preservation predicates.
Its resulting state must remain inactive. Do not merely count cancelled jobs.
If already inactive or absent, require unchanged thread/admission facts and no
stop receipt; do not increment generation, fabricate a stopped row, cancel
other threads or retag the earlier stop reason. Existing historical mappings
and dispatched/unknown insert facts remain intact. Rule removal never resumes it.

Require t not before newly affected policy/thread/job timestamps; existing
immutable earlier facts stay untouched. After all checks, update only action
state/executed_at/error/revision, consume scope, and return UPDATED. No new
AuditKind or action-shaped generic audit payload is introduced.

## Cleanup metadata matrix

record_cleanup loads canonical action, checks actual guard, and requires
EXECUTED. Exact `(cleanup,error)` replay returns actual current revision with
zero writes before any mode-dependent new-scheduling check. New transitions
increment action revision once and preserve all other action facts, including
executed_at. Use the actual ProjectionRow.source_mode, never a caller flag.

| From | To | Required error | Additional condition |
| --- | --- | --- | --- |
| NOT_REQUESTED | QUEUED | null | Current CONVENIENCE mode |
| QUEUED | BLOCKED | non-null ErrorCode | Records failure/refusal, including READONLY mode |
| BLOCKED | QUEUED | null | Current CONVENIENCE mode; explicit cleanup-only retry |
| QUEUED | COMPLETED | null | Current CONVENIENCE mode; actual M5 cleanup result |
| BLOCKED | BLOCKED | same existing error only | Exact replay, not arbitrary error editing |
| COMPLETED | COMPLETED | null | Exact replay only |

All unlisted transitions reject; BLOCKED cannot jump to COMPLETED, reset to
NOT_REQUESTED or execute business work again. READONLY rejects new queueing and
new completion; it may record a pending cleanup as BLOCKED without calling Gmail.
If a future mode-switch consumer permits a remotely in-flight cleanup to finish
after switching to READONLY, its factual result needs a reviewed bounded
handoff before that path is enabled; this signature does not fabricate such
authority. Mode switch/cleanup synchronization is an M5/M103 integration gate.

Storage does not infer cleanup success from label absence/current snapshot or
from this marker. Actual M5 must supply verified removal results and maintain
its real authorization/idempotence boundary. No cleanup job is silently created
or completed, no Gmail call occurs, and no business method is invoked here.
READONLY registration/business execution remain available; only remote cleanup
is prohibited. Convenience cleanup failure must leave EXECUTED business history.

## Required real-file acceptance and remaining gates

AP01: valid resolved LABEL_ADDED registration versus snapshot/legacy/unresolved/
wrong label/history/thread; two messages in one activation alias to first ID,
different real remove/re-add history creates another; conflicting ID/kind rejects.
AP02: actual guard and incoming revision, exact replay zero DB changes; stale
lost-ack input refuses until caller reads actual receipt/facts, no new alias.
AP03: missing/forged/cross-UoW producer/scope/receipt cannot mark EXECUTED;
production registry empty yields OWNER_UNAVAILABLE, synthetic registry is test-only.
AP04: each of three kinds with real publish/admit-or-stop/enqueue methods in one
UoW; inspect all durable rows after reopen, not only action marker.
AP05: existing enabled rule + already active thread no-op keeps rule effective_at,
origin and admission/generation; still requires current valid expansion work.
AP06: already stopped/untracked blacklist keeps old facts/generation or absence;
active blacklist cancels unsent work while preserving dispatched/unknown facts.
AP07: wrong rule kind/member/revision, fake caller receipt, unrelated selected
thread/job/epoch, stale-generation/completed child and empty work all reject.
AP08: failure after rule, after admission/stop, after enqueue and before marker;
caught exceptions and forgotten complete roll back ALL effects on commit/reopen.
AP09: later removal/stop followed by historical EXECUTED exact replay never
revives/relearns/enqueues; changed full row or stale guard rejects.
AP10: pending attention fixed error with no business effects; attention-to-executed
and generic same-state patch refuse; overflow and backwards new timestamps refuse.
AP11: exhaust cleanup matrix in both modes; retries change only cleanup/error/
revision, no policy/jobs mutation; readonly never queues source work.
AP12: synthetic sensitive inputs/errors never enter action/audit payloads or public
output; typed metadata remains private, fixed error context does not expose values.

These are storage tests using actual temporary DB files and the accepted safe
read-view test path, not live Gmail or actual M5 authenticity/learning evidence.
No source dispatch until independent review of this exact supplement and the
implementer's bounded plan. Full actions/M5 acceptance still requires actual
registered producer, normalization/learning decisions, resolved label binding,
current selected-thread expansion composition, real cleanup and mode-change
handoff. Library tests with a synthetic producer do not close any of those gates.

## Proposed r2: final effect fence and complete membership comparison

Independent review found two missing enforcement boundaries in r1. Preserve its
first 269 lines, SHA256
`8b37e1cfee6c18d6dc67ed5fcc289ddc06d448910602547a43e26485bb4004fd`.
This appendix tightens only same-UoW finality and selected-rule publication; the
three external signatures, schema, producer gate and cleanup matrix are unchanged.

### R1: consumed scope remains a fence until UoW exit

CONSUMED does not clear the scope. Keep its enrolled identity and phase attached
to the UoW until commit/rollback/exit. After complete_action transitions it to
CONSUMED, every call to publish_rules, admit_thread, stop_thread and enqueue must
reject CONSISTENCY_FAILURE BEFORE any SQL or same-fact/no-op replay path. A
second `_begin_action_effect` likewise rejects. These prohibitions remain even
when the incoming arguments select another rule/thread/job or would do no work.
The failure poisons the composing UoW, so catching it cannot commit the already
written EXECUTED marker. Lifecycle cleanup must not clear this fence early.

Additionally complete_action is the final repository mutation in this UoW:
after CONSUMED, the common private mutation-entry guard rejects any other
repository write, including cleanup, job deferral/claim, event/epoch mutation or
another complete_action. Reads and the UoW's own final validation/COMMIT remain
allowed. Add only this finite consumed-scope check to repositories/base.py's
existing mutation decorator, in addition to the listed private participants;
it is not a new API or arbitrary transaction callback. The private scope entry
also checks explicitly because it is not an ordinary repository mutation.
Arrange needed event/work bookkeeping before complete_action in the same UoW;
later independent maintenance uses a new authorized transaction.

AP08 adds real-file sequences begin→effects→complete→stop or enqueue or second
scope→catch failure→exit: all rows must match the pre-transaction state on reopen.
Exercise no-op policy calls and a non-policy mutator too. The paired normal
begin→effects→complete→read→commit persists the whole group. Historical replay in
a fresh UoW remains zero-write and does not reconstruct a consumed effect scope.

### R2: publication preserves every nonselected member exactly

The selected-rule publish operation must compare the full sealed membership set
at scope entry with the proposed new snapshot. For every rule ID other than the
selected ID, membership must exist on both sides with identical rule revision.
No other old member may disappear, change revision, or be joined by a new rule
ID. Implement a complete SQL set comparison (both directions), not a PageLimit-
bounded list or a selected-member-only check. The scope's captured old sealed
ruleset revision selects the immutable before relation; no new payload snapshot
is needed. Also reject any nonselected rows in publish_rules' rules/revisions
mutation inputs. Carrying their unchanged members into the new snapshot is
required, not an unrelated mutation.

Only the selected rule may be added or have its revision replaced, as already
governed by r1. The publish hook validates this relation before accepting its
receipt; complete_action rechecks the same complete relation before consumption.
Existing enabled-rule no-op still leaves the entire ruleset revision unchanged.

AP07 adds prior members {A,B}, selection A: updating only A while retaining B's
exact revision succeeds; dropping B, changing B, or adding C rejects and rolls
back the entire transaction. Include more than the normal read page limit so
an omitted late member cannot evade validation. These tests complement the
existing selected-rule identity/kind/effective-time and anti-forgery controls.
