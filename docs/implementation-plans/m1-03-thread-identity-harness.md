# M1-03 bounded actual Thread-identity harness correction

Status: plan-only; independent exact-plan review and root source release pending.
Owner: `m103_os_source`, Sol xhigh. Actual clean main/base:
`36b5a303856f00876c697f712ee98c9012c497c7`. Owned sibling worktree:
`m1-03-thread-harness`; branch `p/luchengxuan/m1-03-thread-harness`.

## Observed failure and fixed scope

Post-merge main CI37028856572 at exact36b failed Python 3.12: 730 tests passed,
and OL07's live-owner recycled-Thread helper failed because 64 sequential actual
Threads never reused the original `get_ident()` integer. Python 3.13 passed.
No foreign ownership acceptance or kernel/descriptor assertion failed. Original
candidate CI37027778087 and OS source/main qualification remain historical facts;
this new post-merge failure is retained, not erased by retry-until-green.

The helper repeatedly creates/joins candidates, implicitly assuming allocation
will choose the desired retired slot. Reuse is permitted, not promised within a
fixed sequential count. Twenty read-only local trials of held concurrent batches
after actual native retirement observed genuine original-identifier reuse in
20/20 cases. That diagnostic is evidence for this proposal, not source acceptance,
a performance/RSS result or a guarantee on arbitrary runtimes.

Only these three paths may change after review/release:

- `tests/integration/runtime_lock_child.py`: bounded native-retirement observation,
  actual held-candidate allocation and fixed detecting negative scenarios.
- `tests/integration/test_runtime_os_locks.py`: real subprocess/kernel controls,
  bounded scenario-specific handshake budget and detecting cleanup assertions.
- This written plan: factual approval/base/check handoff only, no self-SHA loop.

All production runtime/source, original approved OS/C1 plans, unit tests, contracts,
shared docs/conftest, dependencies and CI remain byte-identical to qualified
`ea80db2`/main36b. No public API, FD ownership, strong Thread, locking policy,
error/privacy behavior or source qualification limit changes. No SQL/migration
tree or source ownership is transferred. Migration readiness is deferred.

## Actual identifiers and bounded allocation

Retain the original actual Thread object and capture `get_ident()` plus
`get_native_id()` inside its genuine creator. Use native TID only to observe
that creator's `/proc/self/task/<tid>` retirement after bounded `join`; assert
the helper's own main task/proc directory exists before treating absence as
retirement. No other process or thread is signalled or operated on.

The recycled value under test is Python's actual `get_ident()` integer, not a
Linux native-TID-reuse requirement or a patched identifier. Python documents the
two different identifiers and possible recycling; Linux exposes one task directory
per live native thread. See [Python Thread identifiers](https://docs.python.org/3.12/library/threading.html#threading.get_ident)
and [Linux task directories](https://man7.org/linux/man-pages/man5/proc_pid_task.5.html).
The desired cache-slot explanation is an allocation inference, not a measured
glibc-internal claim.

After retirement, start at most 64 actual candidate Threads in the fresh helper.
Each reports its real identifier and strong current Thread, then stays held on
an Event. Previously allocated candidates cannot be repeatedly freed/reused while
search continues. Use per-candidate readiness under one monotonic allocation
deadline, not unbounded sleeps or 64 multiplied timeouts. Success requires actual
integer equality and a different strong Thread object; neither a generic foreign
Thread nor exhausting the budget counts as success.

The actual matching candidate must exercise all four existing root/lease
check/close/release calls, require fixed OWNER_UNAVAILABLE and leave the original
enrolled inventories/phases unchanged. Only then publish the existing fixed
`recycled_refused` handshake. The live case must still be externally owner_busy
until this fresh helper exits; the terminal case must remain externally available.
Keep both original positive tests, their real kernel probes and after-exit success.

Always release candidate Events and join every actually started candidate in
`finally`, even after assertion/start/allocation failure. Capture worker failures
explicitly; a Thread warning cannot be mistaken for success. Bound creator join
to two seconds, native retirement to two, allocation to four and whole candidate
cleanup to two seconds. Use a scenario-specific 14-second outer handshake budget
for these Thread scenarios only, exceeding the composed inner bounds; other
helpers retain their existing eight-second budget. Existing finally cleanup may
signal only the freshly spawned owned helper PID if it genuinely fails to finish.
No Thread killing, daemon-thread abandonment, stack-size override or GC resource
cleanup is introduced. Count actual candidates, not a claimed RSS bound.

## Detecting controls and verification

Add fixed negative controls using a genuinely still-alive watched Thread:
native retirement must not be reported, and a bounded held-candidate search for
that still-live integer must refuse rather than substitute any foreign Thread.
Use actual creator objects/identifiers and a small fixed control budget, never
fake IDs, class/boolean ownership participants or monkeypatched Thread identity.
The original genuine owner remains checkable/externally contended before and
after refusal; its creator explicitly releases its resources when told to finish.
All started candidate Threads must be joined and no test-owned process/FD remain.

| Gate | Required evidence |
| --- | --- |
| TH01 | Both original live and terminal child cases observe actual retired-ID reuse by a different strong Thread and preserve four-call refusal/kernel controls |
| TH02 | Fixed still-live retirement and exhausted allocation negative controls detect false success; original actual owner/inventory remains intact |
| TH03 | Candidate-start/check/timeout failure paths release Events and join bounded actual children; no background warning or fallback can pass |
| TH04 | Twenty repeated complete child controls with live/terminal/negative cases, then all OS focused and original-plus-new full tests; retain every old test without skips/xfails |
| TH05 | Production runtime and approved OS plan bytes match qualified ea80 exactly; fresh noneditable wheel excludes all helpers/tests/new plan and preserves runtime import/exports/privacy |
| TH06 | Locked offline sync, Ruff/format, both actual CLI helps/JSON version, whitespace/staged safety and fresh exact-head Python 3.12/3.13 CI, followed by independent nonauthor source acceptance |

Local baseline is CPython 3.12.13 on the previously qualified Linux 5.15/eUID1001
synthetic trusted tmpfs fixture. Exact prior CI used Linux Python 3.12.3/3.13.16;
record the new actual runtimes/counts. Do not weaken trusted-root policy or claim
other kernels/mounts/native-fork paths qualified. Missing proc visibility,
nonretiring creator, exhausted real allocation or resource limits fail this gate
with fixed test diagnostics; no skip, generic-foreign fallback, CI disable or
repeated CI rerun replaces the actual detecting evidence.

## Delivery and stop gates

Independent exact-plan approval/root release precede source edits; save their
receipt before implementation. Preserve reviewed plan prefix and all failed-run
evidence. After coherent real controls, freeze an atomic English-action user/
noreply commit with both author/committer verified, normal push and focused Draft
PR under Issue13/Epic1. Root binds new independent exact-source review/CI and
actual branch rules before qualified normal integration. Never modify prior
published heads, force, self-approve, fabricate another GitHub reviewer or change
settings/identity/history. Main36b post-merge CI is not labelled passed here.

Stop for a required extra file/public API, production change, fake/undetecting
participant, unsupported runtime or inability to keep cleanup bounded. No shared
status edit, SQL/migration code, Gmail/OAuth/scopes, host/image/release/license,
external contact, new chat or automation is authorized. Canonical M1-03, whole
M1-02/RV11, actual provider/credential/runtime/daemon consumers, migration source,
G1–G6 and live/Compose/deployment gates remain pending.

## Independent pre-code release receipt

On 2026-10-03 PRC, independent nonauthor Sol reviewer
`phase1_os_acceptance_sol` approved the exact 124-line plan SHA-256
`2f621d9f2e37486a22695b86e4b1faabe0f4c61d059a6fe67f3919af48867d5e`.
Root read the full verdict and explicitly released only the two existing test
files and this plan. This receipt was saved before any harness implementation.
Production runtime/OS-plan bytes stay frozen; historical failed main36b CI is not
relabelled passed. New exact-source nonauthor review/CI remains required.

## Local source handoff, 2026-10-03 PRC

The two allocated test files now observe actual native retirement, hold at most
64 genuine candidates under shared deadlines, and require original Python-ID
reuse by a different strong Thread before all four fixed refusal calls succeed.
Primitive creator/phase/enrollment/descriptor snapshots remain unchanged. Every
started candidate is released and joined in finally, with native retirement
checked before the handshake. Worker exceptions are captured, not Thread warnings.

Five detecting controls cover a genuinely still-live native task, exhausted
allocation for its still-live identifier, and fixed start/check/readiness-timeout
faults. Real started workers are required in the fault cleanup paths. Parent
processes additionally verify native task counts, original kernel contention,
post-exit acquisition, and unchanged filesystem bytes/metadata and parent FDs.
The two original positive tests and all 40 original OS test-function ASTs are
retained unchanged; no skip, xfail, generic-foreign fallback or CI change exists.

Actual local evidence on CPython 3.12.13, Linux 5.15.120.bsk.3-amd64, eUID1001:

- Seven initial positive/negative/fault cases passed in 2.73 seconds.
- Twenty fixed complete batches, each containing all seven child scenarios,
  passed in 55.63 seconds. An earlier focused OS run passed 148 tests in 71.83
  seconds; its primitive inventory snapshot was subsequently strengthened.
- The final full suite passed **756 tests in 85.62 seconds**: all 731 retained
  tests plus five individual detecting cases and twenty seven-scenario batches.
  It includes every final focused OS and repeated child control.
- Locked offline sync, Ruff, format check (101 tool-selected files), both CLI
  helps, actual JSON version, whitespace and repository safety passed.
- All production source and the complete approved OS/C1 plan match qualified
  ea80 byte-for-byte. The fresh noneditable wheel excludes tests/helpers/plans;
  its SHA-256 remains `a09b3bd4f82b3e5ba732bf23554e2ac6af1295eee925e80c765db6108ea5d0d5`.
  Installed-wheel fixed exports, empty inventories and no Facet import hooks,
  filesystem/network/SQL/provider/CLI/logging effects passed.

The original 124-line approved plan prefix remains unchanged. This is local
source evidence, not independent acceptance or a claim that historical failed
main36b CI passed. Fresh exact-head dual-Python CI and nonauthor source review
remain required before root-qualified normal integration. No migration, SQL,
shared-status, production runtime, Gmail or deployment action was taken.

## Proposed bounded inventory-oracle correction, 2026-10-03 PRC

Status: plan-only amendment; independent exact-plan approval and root source
release required before editing either test file. Preserve the preceding 174
lines byte-for-byte and source candidate `a410ca1dab1e0f0a8980f77d0443f88a92e7b982`.

Independent acceptance placed a410 on HOLD: the focused run passed 147 tests and
failed one complete batch in `thread_timeout_fault`, before its handshake, at
`test_original_inventory_changed`. Its full 756 run and both CI37033521251 jobs
passed; those successes do not override the detecting failure. A paired isolated
probe passed without sibling activity but deterministically reproduced the error
with ONE freshly owned sibling directory. Only inventory component5, full native
`fstat` results, changed: ancestor directory nlink3->4, size60->80 and mtime/ctime.
Primitive components0–4, enrolled objects, dev/inode/UID/mode and phases remained
identical; real kernel contention and creator cleanup remained correct. The
author's separate owned-sibling probe confirmed the same causal oracle defect.
This is test overcomparison, not observed lock ownership acceptance.

### Exact comparison and retained controls

Only the same two test files and this plan remain allocated. Production runtime,
the entire qualified OS/C1 plan, SQL/migration/shared docs, dependencies and CI
stay unchanged. No ownership policy or runtime callable is altered.

Keep every current primitive PID/strong-Thread/object/phase/entered/lease/terminal
and inode-enrollment snapshot field. For every actually retained descriptor,
compare its integer, enrolled descriptor-object identity and saved `_Identity`,
plus actual `fstat` device/inode/UID/mode. For regular lock files also compare
actual nlink and size: stable lock files still require one link and zero bytes.
Do not compare directory nlink/size or native atime/mtime/ctime: ordinary sibling
activity can change them without changing any enrolled descriptor or ownership
invariant. Ancestor safety and private-directory/file policies remain enforced
by the unchanged production checks; this does not exempt any path or filesystem.
Parent tests retain their exact private-root tree/bytes/mtime and FD before/after
oracles. The original sibling is outside that private root, not a mutation of it.

Add exactly two fixed paired whole-child scenarios to existing detecting cases
and each fixed twenty-batch run, preserving every prior case and timeout:

- `thread_timeout_sibling`: retain the actual live creator/root/owner, capture the
  baseline, then create ONE fresh owner-only sibling under the test-owned parent.
  Keep it present through actual started-worker readiness-timeout/finally joins
  and the corrected inventory comparison. Require unchanged enrollment/identity/
  phases, original creator checks and real external owner_busy. Finally remove
  only this freshly created empty sibling, finish/join the creator, and prove
  post-exit acquisition plus no fixture/parent-FD leak. No generic retry is used.
- `thread_oracle_negative`: a genuine creator retains an actual root/owner, then
  changes only its fresh synthetic owner.lock mode0600->0640. The real retained
  FD comparison must detect the actual mode change while enrollment and phase
  snapshots initially remain unchanged. Call the genuine owner's check_lock;
  require its fixed refusal and actual invalid phase transition to be detected
  too. Restore0600 only on that owned file, retain original kernel contention
  through the handshake, then explicitly release/close in creator finally.
  Parent proves post-exit availability and unchanged final bytes/tree/FDs.

The negative uses supported real owned-file policy drift and legitimate creator
validation/cleanup, not fake IDs/participants, manual registry/phase mutation,
closing/reopening foreign descriptor integers or a new native-attack API. Keep
actual retirement, strong-Thread difference, all four original refusal calls,
captured worker failures, maximum64 held candidates and common allocation/cleanup
deadlines unchanged. Every actual Thread/helper is joined/reaped in finally;
signals remain limited to fresh owned children. No skip/xfail/fallback/CI change.

### Acceptance and immutable handoff

Require the deterministic sibling-positive and descriptor/phase-negative pair,
all seven original child scenarios, twenty fixed complete nine-scenario batches,
all original focused OS cases and full retained756 plus two new cases. Record
actual runtimes/counts instead of predicting results. Repeat existing locked,
Ruff/format, CLI, privacy/safety, original test-AST/prefix/production-byte and
fresh installed-wheel controls. Preserve a410 HOLD and main36b failed CI receipts.
Save exact independent approval/root release before test edits; freeze a new
ordinary user/noreply commit, normal push and fresh exact-head dual-Python CI for
independent nonauthor acceptance. Neither green CI nor this plan author can
qualify/merge the correction; root must release normal integration separately.
Stop for a required extra file/API, weakened actual identity/file policy,
unbounded cleanup, inability to prove the detecting pair or any production change.

## Independent H1 pre-code release receipt

On 2026-10-03 PRC, independent nonauthor Sol `phase1_os_acceptance_sol`
approved the exact 252-line amendment SHA-256
`fe9bb5b913e873f73b09dc2306248fc6c03be00cc3d7e1426fba56d7fd8b5edd`,
including actual unchanged-runtime feasibility. Root read the full verdict and
explicitly source-released only the same two test paths and this plan. Save this
receipt in an atomic user/noreply commit before either test edit. Require a
separate actual primitive root/lease phase difference after restoring0600, not
whole-inventory inequality explained only by mode. New source acceptance/CI and
separate root integration release remain required; a410 HOLD/main36b FAIL persist.
