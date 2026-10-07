# Granular historical backfill acceptance

Date: 2026-10-07. Base: `f922e597182ee567524aa480c709ce282fe90854`.
Source candidate: `e391e982f9e2065aebc7d2f087d04829c920fe34`.
Plan: [bounded repair](../implementation-plans/granular-historical-backfill.md),
SHA-256 `f2807d845e8e1ce3c3122db94bceb3d56d3fccf81d22f7cdc43cbec72542e435`.

Independent Sol 6.1 xhigh `/root/historical_backfill_plan_review` approved the
amended plan before coding. Sol 6.1 xhigh `/root/historical_backfill_impl_review`
approved this exact source candidate without blocking findings. The reviewer
independently passed 49 affected CLI/DB/worker cases and checked that replaying a
committed start preserves a subsequently paused projection without a new epoch.

## Product evidence

Actual CLI subprocesses use production configuration, bindings, journal, SDK,
Requests/TCP, discovery, History and projection. Only external OAuth/profile
and the final Gmail socket destination are synthetic; no direct DB setup
substitutes for CLI readiness, rule or epoch commands. The tests establish an
empty initial scope, add a sender, create a zero-target-write replayable preview,
explicitly start a distinct historical expansion and copy genuinely pre-rule
mail/full non-draft threads with exact raw/readback and durable mapping checks.
Start preserves the shared checkpoint; subsequent polling uses it rather than
resetting to the new fence. A new process performs no duplicate insert or scan.

Cases also preserve old unknown attempts/mappings, resume persisted pagination
after a failed process, and keep a new uncertain insert pending without resending
while independent threads may proceed. Focused repository tests cover stale
guards, consumed previews, old/partial History coverage, terminal failures and
BlackList/stop changes across restart without widening the sealed allow query.
Synthetic body/header/error sentinels are absent from persisted state and output.

The unchanged pinned Dockerfile built on the authorized sgbox build host. Local
image `facet:e391e98`, ID
`sha256:b3327a1a23f986f6ee5d911d74c088d6a0603a2ae207225c84663465d3a1020e`,
has OCI revision equal to the source candidate and user `10001:10001`. It passed
all four historical CLI cases above with external networking disabled, read-only
rootfs, a fresh synthetic state volume and only the read-only test driver/fake
mounted. No application source, real state or credentials were overlaid.

Locked dependency sync, repository Ruff/format, spike help, whitespace/index
safety passed; the full offline suite passed with 2760 cases in 595.74 seconds.
The only subsequent changes are this receipt/current status and correction of
the CLI example to the actual `--preview-id` option; source/image inputs remain
exactly the reviewed candidate.

On 2026-10-07 the same image ran production standalone preview, stable-key replay
and status against real configuration/state with networking disabled. Preview
succeeded for the fixed six-month scope. Bindings/rules/epochs/partitions/threads/
events/cursor/jobs/attempts/mappings remained unchanged: nine confirmed mappings,
zero new attempts and zero new epochs. Only the intended preview journal metadata
was created. Old attention and recovery remain unresolved; source candidate counts
and real Gmail historical copying were not tested by this offline check.

PR CI/integration remain separate from local image acceptance.
The complete sync wrapper, real Gmail historical-copy acceptance and final
Phase 1 gates are not claimed. No live bulk start, insert, cleanup, unknown retry,
daemon restart, deployment, scope expansion or Release is authorized by this
receipt. The real sync service remains stopped.
