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
