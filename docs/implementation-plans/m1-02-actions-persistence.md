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

## Finite library source handoff

Implemented on pre-code documentation commit
`4e0ffd3233e0c1440207f072d0883da9d7624459`, retaining the original plan and
329-line supplement hashes above. The source adds only the three finite action
methods, an identity-enrolled same-UoW scope, fixed policy/enqueue receipt hooks,
full bidirectional nonselected-membership SQL checks, and OPEN/CONSUMED lifecycle
guards. A consumed scope remains attached until exit and rejects every later
repository mutation before SQL, including exact no-op/replay calls. The immutable
scope cannot accept caller-assigned receipt fields. No schema, migration, core
enum, read bridge, provider, dependency, CI, CLI or shared-status source changed.

Actual offline verification on Python 3.12.13 / SQLite 3.53.1:

- Locked offline dev sync, Ruff check and format check (151 files) passed.
- Full pytest passed: **1352 tests in 217.40 seconds**, consisting of the
  unchanged original 1188 tests and 164 new AP01-12 real-file cases.
- AP cases exercise actual WAL transactions, typed policy/enqueue producers,
  registration and job aliases, original provenance/origin preservation, all
  three kinds, current guards/historical replay, attention and cleanup matrices,
  selected-thread blacklist cancellation with prepared/dispatched/unknown/known
  insert facts and mappings, complete membership comparison including 501 prior
  members, and AFTER-SQL faults with caught rollback/reopen checks. Durable action
  reads use the already-qualified isolated synthetic snapshot reader, not a
  parent proxy presented as a genuine production read provider.
- Both CLI helps, `facet --json --version`, whitespace and repository safety
  checks passed. A fresh noneditable wheel build/install/import smoke passed:
  action producer and read-provider registries remain empty, the three finite
  methods import, and no test producer, test assets, private runtime artifacts or
  runtime/provider import side effects are packaged. No live provider was used.

This is an implementation handoff, not independent acceptance. A different Sol
xhigh worker must review the exact candidate and its new CI. PR15 remains Draft;
Issue9, whole M1-02, genuine M1-03 producer/RV11, G1 and all M5 learning, resolved
label binding, epoch/admission integration, source cleanup and mode-switch gates
remain pending. No real Gmail/OAuth, deployment, image, license or release claim
is made by these synthetic storage tests.

## Proposed r2: symmetric attention/business boundary

Status: clarification proposed after independent source review HOLD on
`62d75c0253a6d66710a9d4d4a4b4346b8b55c6db`; independent plan acceptance and
root release are required before implementing the R2 strategy below. The original
185-line plan and exact 329-line supplement retain their hashes above. This is
not acceptance of the held candidate or a production producer/provider gate.

The independent review reproduced attention followed by same-action admission
in one actual WAL UoW with the shipping producer tuple still empty. The existing
touched flag rejects the opposite order only. Attention is terminal and cannot
create authorization; neither operation ordering may commit both facts.

### Finite enforcement and lifecycle

Allocate one private boolean `_action_attention_completed` in `UnitOfWork`,
initialized false at construction/entry and reset by the existing fixed action
lifecycle invalidation on every exit. It is transient transaction state, not a
new scope, persisted field, caller proof, registry or public interface. Only the
actual successful PENDING-to-NEEDS_ATTENTION update in `complete_action` sets it.
The existing prerequisite remains: no OPEN/CONSUMED effect scope and no preceding
publish/admit/stop/enqueue call, including a semantic no-op, in that same UoW.

Once that boolean is set, the four existing finite business participants
publish_rules/admit_thread/stop_thread/enqueue reject CONSISTENCY_FAILURE before
their SQL and before any replay/no-op path. The sole private effect-scope entry
also rejects before its SQL. Their existing failure-poisoning wrapper ensures a
caught refusal rolls back the entire composing UoW, including the attention row.
This deliberately follows the already-approved transaction-level touched rule:
unrelated policy/job work uses another UoW rather than a same-UoW exception.

Standalone attention followed by reads and commit remains valid. Registration
and non-business event bookkeeping retain their existing finite semantics; this
clarification does not make attention a new all-repository mutation fence.
EXECUTED retains its stronger existing CONSUMED all-mutator fence until UoW exit.
No reset, second action scope, attention-to-executed transition, or business retry
is enabled. A fresh UoW resets the transient flag, not the durable action state.

### Durable same-action admission boundary and historical replay

Independently of that transient flag, `admit_thread` must not create or reactivate
a thread through AdmissionRefActionLabel whose actual canonical action row is
NEEDS_ATTENTION. Check the actual stored state at the finite admission boundary
before any tracked-thread/admission write. This applies in a fresh UoW as well,
including after an exact historical attention replay; ending the first UoW is
not permission to turn its unresolved action into new disclosure authorization.
Existing kind/thread/projection/reference validation remains mandatory. A valid
PENDING action's ordinary admission and a real scoped EXECUTED composition keep
their current prerequisites; this is not a new producer requirement for every
ordinary policy call or a fabricated M5 admission capability.

Exact full-row `complete_action` replay, with the current guard checked first,
still returns the actual revision with zero writes and does not arm the transient
flag or reconstruct a scope. Exact already-active admission replay must preserve
its historical thread/admission rows and create no authorization; do not silently
rewrite or invalidate retained historical facts. A new/reactivated admission
through a NEEDS_ATTENTION reference refuses, while separate ordinary transactions
using an unrelated valid rule/action keep their existing behavior.

### Bounded files and paired real-file evidence

Only actions.py, transactions.py, policy.py and test_db_actions.py need this R2
delta; the existing base failure wrapper is unchanged unless a demonstrated
ordinary defect requires its already-allocated finite correction. No schema,
core record, API, provider registration, migration, read bridge, configuration,
dependency, CI, CLI or shared-document change is allocated.

Extend AP10 with both actual attention-to-same-action-admit and reverse-order
sequences, ordinary uncaught and inside-UoW suppressed failures, whole-schema
rollback and close/reopen comparisons. Pair the later business guard against all
four named operations, including actual valid no-op arguments and scope entry.
Add standalone attention/read/commit, fresh-UoW ordinary business, historical
attention replay with zero SQL writes and no transient flag, cross-UoW new and
reactivated same-action admission refusal, and retained historical exact-admission
replay controls. Retain all valid EXECUTED, consumed-fence, cleanup, AP01-12 and
original 1188 tests. The empty shipping producer tuple is tested unchanged for
the attention/admission counterexample; a test producer cannot hide the guard.

The separate source-review R1 is an existing-contract repair, not a new strategy:
captured enabled current-member rule identity determines the preserved-rule
branch, irrespective of a caller-selected next revision. Add detecting rollback
for that bypass plus preserved no-op and absent/disabled/out-of-snapshot positives.
New exact source, fresh wheel, full offline suite, both Python CI jobs and
non-author acceptance remain required before any root integration release.

### R2 independent approval and finite source-release receipt

Independent non-author Sol xhigh reviewer `phase1_os_acceptance_sol` approved the
exact 336-line clarification plan at SHA256
`60333e9ccddc88caf60c01d3cef3670b84f55d0a1db95a5a06c02c5c7cc7bf8f`.
Root read that report and released only the finite strategy above after this
author completed its separate independent corrected OS acceptance task. This
receipt is saved in a documentation-only commit before any R2 strategy code.
The bounded R1 repair remains an existing-contract correction. Historical source
`62d75c0253a6d66710a9d4d4a4b4346b8b55c6db` remains HOLD; no source acceptance,
production registration, whole M1-02/RV11/G1 or migration dispatch is inferred.

### R1/R2 corrected-source verification handoff

The reviewed R2 strategy was saved before implementation in documentation commit
`056f253eb835448124035a208126e4cafb9875c5`. Independently accepted OS foundation
main `ea80db286fe110a69450076581b0b25810dcaf91` was then normally carried through
merge `a7a5c1a24b19f602203e664c4889d4fdcf79a1a4`. All moving SQL repair bytes were
unchanged by that merge; all accepted OS bytes remain exact. Its OS acceptance
does not replace the separate corrected SQL source gate.

The bounded R1 repair selects enabled/current-member preservation from captured
before facts, rejects publication despite a caller-selected next revision, and
rechecks unchanged rule/revision/member/ruleset at completion. Actual detecting
WAL controls cover all three kinds and caught rollback after real preceding
enqueue SQL; preserved no-op and absent/disabled/out-of-snapshot publications
have paired positives. No existing rule identity/value is changed.

R2 adds only the approved transient attention-completed UoW flag and the actual
stored-state guard on new/reactivated action-referenced admission. Both attention/
business orders poison and roll back the full UoW, including caught failures.
All four later business participants and scope entry refuse before SQL/no-op;
the flag resets on exit and historical full-row replay never arms it. Standalone
attention, registration/non-business event bookkeeping, exact retained active
admission replay and unrelated fresh transactions keep their reviewed semantics.
The existing stronger CONSUMED all-mutator fence remains unchanged.

Actual corrected verification on Python 3.12.13 / SQLite 3.53.1:

- Full offline pytest: **1525 passed in 256.21 seconds**. Actual collection
  retains the combined 1475-test baseline (1352 earlier SQL/ACTION plus 123
  accepted OS controls) and adds 50 new R1/R2 cases. Original ACTION test/helper
  AST bodies are unchanged; no original SQL test or accepted OS test was removed.
- Combined focused ACTION/OS suite: **337 passed in 80.36 seconds**; repeated
  AP05/AP10 subgroup: **61 passed in 25.53 seconds**. The first new positive
  publication fixture duplicated an existing normalized rule value; it was
  corrected to a distinct valid synthetic allocation without relaxing guards.
- Locked offline sync, Ruff and format check (158 files), both CLI help commands,
  production JSON version, whitespace and repository-safety checks passed.
  Original plan185/ADR329 and reviewed R2 plan336 prefixes preserve exact hashes.
- A fresh offline noneditable wheel build/install passed exact SQL/OS source,
  archive and installed-byte checks outside the repository. Production action
  producer, read-provider and qualified-runtime registries remain empty; no
  test producer/helper/probe/private artifact is packaged. Imports create no DB,
  file/FD, fork hook, network/subprocess participant, logging or provider effects.

Historical source62 remains HOLD. This is author verification, not acceptance:
the new exact corrected candidate needs independent non-author source/acceptance
review and its own Python 3.12/3.13 CI before root may release integration. PR15
stays Draft; Issue9, whole M1-02, actual M5/M103/RV11/G1 and migration source remain
pending. No schema, API, producer/provider registration, dependency, CI, CLI,
shared-status, Gmail, credential, deployment, image or release scope was expanded.

### R3 clarification: creator validation precedes lifecycle mutation

Independent non-author acceptance of exact source
`2466834f79c41dbbf95e2919072ea9f57f36e7cc` is HOLD despite its 1525 passing
tests and successful exact CI37028021323. The reviewer verified the R1/R2
repairs, then reproduced a public UoW lifecycle counterexample: a foreign Thread
calls `uow.__exit__(None, None, None)`, receives OWNER_UNAVAILABLE, but the
session-check failure handler first removes the creator's enrolled scope and
resets its business/attention flags. Creator exit can consequently commit OPEN
business effects without completion, or accept business after CONSUMED or a new
NEEDS_ATTENTION transition. No raw SQL or private-state mutation is needed.
Historical source62 and corrected source246 remain HOLD; this appendix is plan
only until independent review and an explicit finite root source release.

The existing thread-affine owner/finality contract requires refusal without
mutating another creator's transaction. Add a fixed private WriterSession
creator check, using its actual creator PID and a strongly retained exact
`threading.current_thread()` object, not only a reusable numeric thread ID.
The check compares identity before probing the connection, changing a flag,
removing enrollment, poisoning, rolling back, closing or invoking cleanup. It
returns OWNER_UNAVAILABLE on a foreign Thread or inherited fork process and has
no SQL, connection-close, registry or creator-state effect. No at-fork hook is
installed. Capture identity during the existing WriterSession construction; it
does not constitute a real M103 owner/provider or filesystem-opening capability.

Apply that check at WriterSession check/invalidation and each UoW lifecycle
boundary. Entry performs it before any entry flag or BEGIN; check/execute before
failure mutation; exit before its exception-handler cleanup; rollback before
SQL and finally cleanup; scope retirement before enrolled-set/flag changes.
Refused foreign entry/exit/cleanup cannot alter `_entered`, `_active`, `_failed`,
the session's current UoW, exact scope identity/phase/enrollment, captured facts,
receipts, business-touched or attention-completed state. Numeric thread-ID reuse
does not authorize a new Thread. Foreign refusal must not close or poison the
legitimate creator, including a connection with `check_same_thread=False`.

After creator validation, active-UoW identity is checked before taking lifecycle
actions: a stale/reused/inactive UoW cannot retire or roll back a different live
UoW on that session. An unentered UoW may be entered only by its session creator.
The genuine creator still performs the existing one-shot transaction sequence:
forgotten OPEN completion rolls back; CONSUMED permits reads but denies every
repository mutation; attention denies the four business operations/scope entry
including no-ops; caught owned failures poison and roll back the complete UoW.
Successful commit, owned rollback, owned close and failed/ambiguous persistence
retire only the actual owned scope and reset transient flags. The latter closes
the unusable writer and cannot return a success receipt. Creator identity alone
is not a substitute for active session, current-UoW or lineage checks; legitimate
closed/broken-session cleanup remains possible after identity is established.
No cleanup is attempted on an inherited SQLite connection in a refused child.

#### Finite R3 files and independent evidence

This correction allocates only these existing files and this plan:

- `src/facet/db/connection.py`: WriterSession-only retained PID/Thread fields,
  fixed private `_check_creator()` and creator-first writer check/invalidation.
  Preserve `_Session`/ReadSession behavior, permit bridge and read provider; no
  runtime lock factory, public export, callback or general connection protocol.
- `src/facet/db/transactions.py`: creator-first entry/check/exit/rollback and
  exact-current-UoW retirement ordering, including owned uncertain cleanup.
- `src/facet/db/repositories/actions.py`: creator-first scope invalidation;
  retain the same fixed enrollment, OPEN/CONSUMED phases and R1/R2 semantics.
- `tests/unit/test_db_actions.py`: bounded owned Thread/child controls and
  actual WAL/full-image/close-reopen evidence; no shared conftest or changes to
  existing test bodies. Keep all retained 1525 cases and original SQL controls.

Extend AP08/AP10 with each of the reviewer's actual OPEN, CONSUMED and attention
counterexamples. The foreign public exit must issue zero SQL and leave all
creator facts unchanged; pair creator forgotten-completion rollback, legitimate
EXECUTED/read/commit, and later-business detecting rollback after each refused
foreign call. Test foreign unentered entry, entered/repeated exit, exception exit
and session close; retain exact session/UoW/scope state and let the creator finish
its valid sequence. Add stale-UoW exit while a different UoW is active and verify
zero interference. Include `check_same_thread=False`, retained creator-Thread
versus an actual newly allocated Thread with recycled numeric ID, and an owned
fork child that invokes the public lifecycle then uses immediate child exit
without inherited SQLite finalizers; the parent remains usable. All joins and
child waits are bounded and clean up only the test's own participants.

Pair legitimate creator rollback/close with real preceding SQL and full-schema
reopen comparisons. Retain actual after-SQL abort, caught-failure and ambiguous
commit/rollback controls; add scope/flag/enrollment retirement checks without
relaxing uncertainty handling. Do not assert rollback after an ambiguous commit
as a guarantee; independently reopen to inspect the durable old/new outcome.
No migration, restore, row/table/core enum, producer registration, dependency,
CI, CLI, Gmail, credential, runtime lock source or shared-document change is
allocated. A further material ownership strategy or extra file requires a new
written amendment before code. Save exact independent approval/root release in
a pre-strategy documentation commit, then require new exact source, measured
full/targeted suites, fresh noneditable wheel, both Python CI jobs and non-author
acceptance before any integration or downstream migration release.

#### R3 independent approval and finite source-release receipt

Independent non-author Sol xhigh reviewer `phase1_os_acceptance_sol` approved the
exact 490-line R3 clarification at SHA256
`01f36afd3066f95729c54b3648a42cba73e99d320b11f25a156f4cf982c925f6`.
Root read the complete review and released only the finite WriterSession/UoW/
scope correction and additive tests above. This receipt is saved in a normal
documentation-only commit before any R3 strategy source. Neither historical62
nor source246 is accepted; downstream migration source and restore plan remain
paused, and a new exact candidate needs separate non-author acceptance and CI.
