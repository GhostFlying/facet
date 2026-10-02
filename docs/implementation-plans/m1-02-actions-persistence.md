# M1-02 finite action persistence implementation plan r1

Status: plan preparation only; independent plan review and coordinator dispatch
are required before action source changes. Read-session ownership correction is
the current source priority. No action implementation is implied by this plan.

Authoring base: `d6c56d153728b853c3cc06cf8866fada2c3f22b8`. Its DB21 library
candidate has independent changes requested for single-session ownership; this
plan must carry forward to the actual accepted correction before source dispatch.
It consumes the already independently approved 329-line
`actions-persistence-amendment.md`, SHA256
`8ff9567b94024ebf260922797a50fae0b75626d202d4f9c0d9f861c9db2e35bc`,
currently in the design owner's isolated worktree. Copy those exact bytes only
after this plan's review and dispatch. Preserve the original SQL r3/r4, result,
mapping and read-view supplements and their evidence; none is rewritten here.

## Scope, ownership and dependencies

The SQL implementation owner owns this slice. Independent Astra implementation
and acceptance review must bind the final source SHA, not the preceding design
or read-session review. Ordinary fixes stay in scope; changed selection,
authorization, persistence or transition semantics require a written amendment.

| File | Bounded change |
| --- | --- |
| `src/facet/db/repositories/actions.py` | Three finite methods, exact private selection/effect scope, fixed producer registry and private participants |
| `src/facet/db/transactions.py` | Actual UoW scope/touched fields, entry initialization, open-scope commit refusal, exit invalidation |
| `src/facet/db/repositories/base.py` | Consumed-scope check inside the existing owned, failure-poisoning mutation entry |
| `src/facet/db/repositories/policy.py` | Finite before/after participants for existing publish/admit/stop operations |
| `src/facet/db/repositories/jobs.py` | Finite participant for actual selected enqueue and canonical replay receipt |
| `tests/unit/test_db_actions.py` | Synthetic producer and real-file AP01–12 controls; no shared root conftest changes |
| This plan and the exact action supplement | Reviewed design preservation and bounded execution handoff |

UoW lifecycle is actually implemented in `transactions.py`, not `connection.py`;
the supplement's lifecycle participation is therefore placed there. No change to
the read-session adapter, migrations, 32 tables, core enums/records, dependency
lock, CI, configuration, CLI, public DTO or provider protocol is planned.
Repository modules are imported directly; no generic registry/export is needed.

Implementation inputs are the accepted M1 contracts, finite SQL rows/keys and
policy/job repositories plus the accepted corrected DB21 test-read bridge.
Current production `_ACTION_PRODUCER_TYPES` is empty. Actual M5 label binding,
latest-external-sender learning, normalization/authentication and bounded selected
epoch composition are future consumer gates, not fabricated by a synthetic
producer. Actual M103 ownership, M5 remote cleanup and mode-change synchronization
remain separate; this slice never connects to Gmail or enqueues SDK work.

## Finite interfaces and allocation

Keep precisely the three externally callable repository signatures:

- `register_action(uow, P, row:ActionCommandRow) -> WriteReceipt`.
- `complete_action(uow, P, row:ActionCommandRow, guard:RevisionGuard) -> WriteReceipt`.
- `record_cleanup(uow, P, action_id:LocalId, cleanup:CleanupState,
  error:ErrorCode|None, guard:RevisionGuard) -> WriteReceipt`.

Reuse the existing `ActionCommandRow` decoder and finite selectors. No public
callback, new table, generic payload, arbitrary SQL method or new error code.

Private `_ActionSelection` has only `action_id:LocalId`, `rule:RuleRef` and
`expansion_job_id:LocalId|None`, with exact kind/nullability guards. The private
`_begin_action_effect(uow, P, selection, guard, producer)` uses an exact compiled
producer class from the initially empty tuple. Tests patch only one fixed
synthetic type in their process; no environment/config/import-path registration.

The identity-enrolled opaque effect scope contains exactly the supplement's UoW,
projection, selection, typed before-row snapshots, three real receipt slots and
OPEN/CONSUMED phase. It has no constructible/exported capability or dictionary of
caller proof. Scope entry loads actual canonical action/rule/ruleset/member/
thread/admission/job facts. Cross-UoW, stale or forged objects cannot enter.

`UnitOfWork` receives only `_action_scope` and `_action_business_touched` private
fields. Fixed lifecycle calls validate/invalidate the enrolled scope; no caller
callback is accepted. Local imports at those fixed lifecycle boundaries avoid
an actions→base→connection→transactions import cycle. Failure, rollback,
ambiguous commit and normal exit all invalidate the scope; it is never reusable.

Policy/job participants are fixed private functions in `actions.py`, called by
the four named existing operations after exact owner validation. Entry marks
business touched even for a semantic no-op. In an OPEN scope it validates only
the selected rule/thread/expansion operation; after the actual operation succeeds
it captures the real committed-in-UoW receipt and canonical job ID. Caller
receipts cannot fill slots. Ordinary transactions without a scope keep their
existing semantics and historical stable-key replay behavior.

## State transitions and proof

Registration validates a real resolved/consumed LABEL_ADDED event, non-null
thread and exact activation tuple. Preserve all first-row facts on tuple alias
replay, including its original event, observed time, ID/state/revision. Conflicting
ID/kind rejects; a different real remove/re-add history record is a new activation.
No current-label/legacy inference or learned address is stored in action rows.

Completion validates the current guard before any replay. Full same-row replay
returns current revision with zero writes, no scope reconstruction and no policy
or job call, even after later stop/removal. New transitions require next revision
with overflow checks. PENDING→NEEDS_ATTENTION requires a fixed error, no executed
time, no scope and no policy/job touched flag. Attention is terminal here.

PENDING→EXECUTED requires the actual scope and independently reloaded before/
after relations. Preserve an already enabled selected rule's origin/effective
time and the entire unchanged ruleset. Otherwise actual selected publication
uses ACTION_LABEL and the same execution time. Compare every nonselected sealed
member in both directions with fixed SQL set predicates; reject unrelated rule/
revision inputs. Recheck this complete relation at consumption, not only in the
publish participant. A 500-row materialized page is not the proof.

Allow actions require the actual active selected thread and a same-scope
EXPAND_THREAD enqueue receipt, canonical ID/key, current generation, subject
epoch and `epoch_jobs` membership. Existing active thread/admission facts remain
exact; absent/inactive thread requires the actual action-referenced admission.
Only the four allowed pending job states from the supplement prove outstanding
work, with their existing claim/error/deadline invariants. Old terminal/cancelled
work cannot satisfy the action. First job origin and alias-resolved ID persist.

Blacklist requires actual selected blacklist rule and no expansion selection.
An active thread needs the actual stop receipt/reason/time/generation+1;
untracked/already stopped remains absent/unchanged, without invented admission,
stop generation or cancellation of other threads. Preserve dispatched/unknown
insert facts and historical target mappings. No purge, resume or reinsertion.

Completion only updates action state/time/error/revision and consumes the scope.
The consumed scope remains attached until exit: every repository mutator,
including no-op replay, cleanup, non-policy methods and second scope entry,
refuses before SQL and poisons the whole UoW. Reads and final relational checks
remain allowed. OPEN scope at commit likewise rolls back the group.

Cleanup implements exactly the six-row supplemental matrix. Load actual source
mode and current guard; exact cleanup/error replay is zero-write before new
mode-dependent scheduling checks. New transitions change only cleanup/error/
revision. Readonly may record blocked failure but cannot queue/complete cleanup;
convenience retry is cleanup-only, never a repeat business action. No label
absence or this metadata marker proves actual remote removal.

## Verification and evidence

All AP tests use actual temporary WAL files and real writer UoWs. Reopen and use
the reviewed isolated read path for durable inspection. Do not replace mutation
or caught-failure assertions with a parent proxy's refusal. Tests preserve the
current suite, genuine live read controls and existing DB01–28 obligations.

| Acceptance | Required paired evidence |
| --- | --- |
| AP01 | Resolved activation/first-tuple alias/remove-readd positives; unresolved/legacy/mismatched event and conflicting ID/kind negatives |
| AP02 | Actual guard/next-row revision and exact zero-change replay; stale/overflow/changed-immutable refusal |
| AP03 | Empty production registry, forged/cross-UoW scope/producer/receipt refusal; fixed synthetic scope positive only |
| AP04 | Three kinds with actual publish/admit-or-stop/enqueue, all durable rows and first provenance verified after reopen |
| AP05 | Enabled rule and active thread no-op retain ruleset, origin, effective time, generation/admission; real current expansion remains required |
| AP06 | Absent/stopped blacklist no invented rows; active stop cancels unsent while preserving dispatched/unknown facts and other threads |
| AP07 | Full {A,B} membership positive; drop/change B/add C negative, including >500 old members; wrong kind/epoch/generation/terminal child refusal |
| AP08 | Fault after each actual effect/before marker, forgotten completion and caught post-consumption policy/no-op/non-policy/second-scope failure roll back whole group; read-after-complete commit positive |
| AP09 | Stop/removal then historical completion replay has zero DB changes and no fresh scope/effect; stale/changed row refuses |
| AP10 | Attention with untouched business positive; prior business/scope, attention→executed, arbitrary patch and backward timestamp negatives |
| AP11 | Every listed/unlisted cleanup transition in both modes; no policy/job delta or business retry; readonly refusal remains explainable |
| AP12 | Fixed sensitive exception/input sentinels absent from forbidden DB/WAL/journal/error output; allowed private rule/ID metadata is not mistaken for public telemetry |

Use real SQLite AFTER-write aborts and inside-UoW exception suppression to prove
rollback, not merely raised Python exceptions. Check late invalid members also
roll back early selected work; no update-only marker may pass without effects.
Sensitive body/header/subject/raw exception inputs cannot become text/JSON proof
columns. Rules/IDs are legally private metadata, not a claim of Web privacy;
HTTP/DOM and actual M5 producer tests remain later consumer gates.

Run targeted action tests, then locked full pytest, Ruff check/format, both CLI
helps, whitespace and staged/tracked safety. Build a new wheel; verify outside
the repo with locked non-editable installation that the production producer tuple
is empty and synthetic producer/tests are absent. Candidate Python3.12/3.13 CI
and non-author independent source/acceptance review are mandatory before root
may dispatch integration. No action library proof closes actual M5 or G1–G6.

## Delivery, external scope and stop gates

After plan review/dispatch, first preserve the exact supplement plus plan, then
implement a coherent action/UoW-participant slice with its tests in focused
English-action commits. Normal push uses the existing Draft PR15 and Issue9;
do not close the issue or mark whole M102 ready from this library unit alone.
Shared status is updated only at a coherent handoff, not a self-SHA report loop.

Stop for unallocated row/transition/producer permission, necessary schema/API
change, changed historical replay or selected-rule semantics, inability to retain
an original real read/fault assertion, or actual new capability/OS failure.
Report the concrete counterexample and smallest written delta for independent
review. Do not fabricate a producer, weaken assertions or add a marker-only path.
No Gmail/OAuth, image, deployment, release, settings, automation or contact action
is authorized by this plan. Migration and restore source are not interleaved.

## Execution handoff: qualified base and prospective routing

The original 185-line independently approved plan remains byte-identical at
SHA-256 `1ade12ca0ef855790b32a2c80d5fa7f81e4f106dab58d0261fbca85f96097cbf`.
The separately approved 329-line action supplement is preserved exactly at
SHA-256 `8ff9567b94024ebf260922797a50fae0b75626d202d4f9c0d9f861c9db2e35bc`.
Their earlier model names and pending-base observations are historical records.

Root released this finite source unit after the corrected library
`16bcd0b99bf1118924b214bf9ded3976813f5e1a` received independent acceptance and
CI 37014341329 passed Python 3.12/3.13. Its 1188 offline tests and qualified
read-session ownership correction do not close whole M1-02, genuine M1-03
provider/RV11, production registries or G1. No original library gate is reduced.
Reviewed main policy `a57dd77116ea79b44c177d03bb6b9815a5913795`, whose main CI
37018290223 passed, was carried by a normal merge. The actual source base is
`497c4a6a9cd05495220a83d89ba7e62cbbaafe26`; no SQL API changed in that carry.

Source ownership is now `phase1_sol_policy_review` (Sol xhigh), acting only as
implementation author for this unit. A different delegated worker must review
its exact candidate; it cannot inherit this author's earlier policy review.
The latest prospective policy permits only Sol high/xhigh or bounded Luna, with
independent Sol xhigh for high-risk reviews; no new or reactivated Astra task.
The original independently authorized reviews retain their actual attribution.
Shared current-state documents and root integration remain the separate
`m103_os_source` worker's responsibility. This dispatch grants only the original
finite source/test/plan scope above. Any material interface or guard change needs
a written amendment and independent review before implementation.
