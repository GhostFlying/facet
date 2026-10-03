# M2 readonly action-label durable effect

Status: implementation plan for the next independent product unit. This plan
is based on exact `origin/main` `5a3f492d638a198cee0622fafe497e7585a25bc6`
and authorizes no live Gmail request, OAuth operation, target write,
deployment, image publication, or release.

## Goal and product boundary

Turn one persisted readonly Gmail label-added event into the first durable
rule/update capability: resolve typed source-thread facts, normalize the
selected external sender/domain, and atomically record the action, rule
revision, selected-thread authorization and expansion job. `AI/BlackList`
must stop only the selected thread and retain its historical mail. Removed,
unknown, ambiguous, malformed or duplicate facts become a durable event
attention state; they never create a rule or disclosure job.

This unit is deliberately limited to the existing single-writer SQLite
repositories and typed `ActionLabelProducer`. It does not implement automatic
discovery/backfill, History polling itself, Gmail authentication, target
insertion, MIME/fidelity/recovery workers, Dashboard, CLI, or a generic action
plugin/capability framework. A synthetic `ActionSourceReader` is sufficient
for offline end-to-end evidence; a Gmail-backed reader remains a separately
reviewed provider boundary and must not be fabricated here.

## Current reusable pieces and actual gap

- `HistoryProducer` already persists typed label events and `resolve_event`
  jobs, including event-key deduplication and replay-safe pages.
- `ActionLabelProducer` already performs exact label mapping, own-address
  exclusion, latest-external selection and attention-first decisions.
- `db.repositories.actions` already has strict action rows and same-transaction
  rule/thread/job verification, but its compiled producer inventory is empty
  and no production orchestration calls the effect boundary.
- `db.repositories.events.classify_event` can durably transition a pending
  event to `RESOLVED`, `CONSUMED`, or `NEEDS_ATTENTION`; it must remain the
  source-event authority.

The missing capability is a narrow owner-side consumer that performs those
typed transitions and calls the existing repository effect protocol without
network waits or ad-hoc SQL. It must not make the current label snapshot the
source of truth or silently classify a no-op as success.

## Owned files and interfaces

| Path | Responsibility |
| --- | --- |
| `docs/implementation-plans/m2-action-label-effect.md` | this plan and exact handoff evidence |
| `src/facet/projection/action_consumer.py` | typed consumer/orchestration; no provider calls, raw data or generic registry |
| `src/facet/db/repositories/actions.py` | release one fixed compiled `ActionLabelProducer` effect entry point and keep all relational checks inside the existing owner boundary |
| `src/facet/db/repositories/events.py` | permit a completed label action to finalize its source event as `CONSUMED` without inventing a projection job; preserve the existing guard for every other no-job event |
| `tests/unit/test_projection_action_consumer.py` | synthetic source facts, rule/action/blacklist decisions and attention routing |
| `tests/integration/test_projection_action_effect.py` | one real SQLite transaction/reopen/replay path with private-value assertions |
| `docs/development-status.md` | root-owned status handoff after review/integration |

No other worker-owned adapter, credential, History, target, CLI or Dashboard
file is edited by this plan. If the existing private effect protocol cannot be
exposed without changing its relational contract, stop and update this plan
instead of bypassing it.

## Public typed boundary

The consumer accepts one persisted `SourceEventRow`, a fixed
`PrivateActionLabelMap`, an `ActionSourceReader` returning typed
`ActionMessageFact` values, configured own addresses, and the current
projection/rule context. It returns a closed result containing either an
executed action receipt or a typed attention code. It must validate the event
is a label-added event for the requested thread and use its persisted
`observed_at` as the action effective time.

For `AI/AddSender`, normalize the selected sender exactly and publish an
`ALLOW_SENDER` rule. For `AI/AddDomain`, use the existing PSL/IDNA
`learn_domain` policy and reject source-primary/own/public/unknown domains.
For `AI/BlackList`, publish an exact sender blacklist, increment only the
selected thread generation and cancel unstarted work through the existing
repository transition. A successful allow action admits only the selected
thread and creates one `EXPAND_THREAD` job guarded by its generation. Existing
active authorization is not duplicated; replay returns the repository's
stable receipt. No historical matching threads are scanned.

The source event is classified only after the effect or attention decision is
ready. Because the action repository's consumed scope cannot be mutated again,
the successful effect and event finalization are two short owner transactions:
the first registers/completes the action and creates any allow expansion job;
the second marks the exact label event `CONSUMED` (with that job for allow
actions, or no job only when the completed blacklist action is found). A
restart between them replays the finalization by stable event/action keys.
`NEEDS_ATTENTION` uses a fixed `ErrorCode` and no business rows. A
provider/source reader exception is a controlled attention result; raw
exception text and source headers never cross the boundary.

The fixed compiled producer inventory may contain exactly the shipping
`ActionLabelProducer` type. There is no registration API, import-by-name,
callback, environment switch or caller-supplied producer class.

## Acceptance and stop gates

- Synthetic AddSender, AddDomain and BlackList events create the expected
  durable rule/thread/job effect in one transaction; reopen sees identical
  state and replay does not create a second effect.
- Removed, unknown, no-external, ambiguous, duplicate, malformed, draft/source
  failure and own-only facts become attention with no rule/job/disclosure.
- AddDomain refuses source-primary/own domains and uses the exact normalized
  registrable domain; BlackList does not affect unrelated tracked threads and
  does not delete target facts.
- Event/action/rule/job revisions and effective time are derived from persisted
  typed values; stale guards, forged producer objects, foreign threads and
  mismatched events fail closed through controlled storage errors.
- A completed blacklist action can finalize its label event without a fake
  projection job; a non-label or pending/unknown no-job consumption remains
  `OWNER_UNAVAILABLE`.
- No body, subject, full headers, attachment, raw bytes, credentials, private
  address or provider error appears in repr/str, logs, SQLite diagnostic fields
  or test-facing public result values.
- Existing DB action/repository, History and projection rule tests remain
  green; run focused tests, full offline pytest, Ruff, wheel/import smoke and
  `bash scripts/check-repo-safety.sh` on the exact candidate.

Stop before coding if the effect registry requires a new framework, if a
durable attention row cannot use the existing `SourceEvent` state machine, or
if an implementation needs a Gmail scope, target write, source-label mutation,
historical rescan or a raw-content cache. Such a change requires a revised
plan and user decision where it changes the approved product boundary.

## Review and handoff

An independent plan review must approve this exact plan before implementation.
The root agent implements the bounded unit directly. A different independent
implementation reviewer must approve the exact candidate SHA with focused,
full-suite, privacy, wheel, Ruff and safety evidence before the coordinator
merges it. This unit proves only the offline manual-tag durable effect; it does
not close automatic admission, target projection, G2, live Gmail or Phase 1.
