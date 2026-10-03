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
| `src/facet/projection/actions.py` | add explicit draft state to typed message facts and exclude drafts before selecting the latest external sender |
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

The consumer accepts the owner's session, projection ID, persisted event ID
and event revision guard, corresponding `RESOLVE_EVENT` job ID and job revision
guard, and an existing authorized expansion epoch ID for allow actions; a fixed
`PrivateActionLabelMap`, an `ActionSourceReader` returning typed
`ActionMessageFact` values, configured own addresses, and the current
projection/rule context. It returns a closed result containing either an
executed action receipt or a typed attention code. It must validate the event
is a label event for the requested thread. Action `observed_at` is the original
persisted event time; a newly published rule's `effective_at`, action execution
time and selected-thread admission time are the owner-captured execution time,
never the older event time. Preserve earlier effective times for already enabled
rules. The epoch is looked up, not fabricated: it must be a nonterminal existing
authorized epoch of this projection. This unit does not claim to create the
continuous runtime's future epoch contexts.

`ActionMessageFact` gains `is_draft: bool = False` for compatibility with
existing typed readers. The producer excludes explicit drafts; an empty eligible
external set yields attention. Readers must supply genuine mailbox draft state;
this unit tests that contract with synthetic typed facts rather than claiming a
Gmail reader exists.

For `AI/AddSender`, normalize the selected sender exactly and publish an
`ALLOW_SENDER` rule. For `AI/AddDomain`, use the existing PSL/IDNA
`learn_domain` policy and reject source-primary/own/public/unknown domains.
For `AI/BlackList`, publish an exact sender blacklist, increment only the
selected thread generation and cancel unstarted work through the existing
repository transition. A successful allow action admits only the selected
thread and creates one `EXPAND_THREAD` job guarded by its generation. Existing
active authorization is not duplicated; replay returns the repository's
stable receipt. No historical matching threads are scanned.

The exact lifecycle uses the existing repositories and no transaction spans
source reads:

1. Lookup persisted event and its exact resolve job by stable event key; check
   projection, kind, revision and subject. Lookup action by `(projection,
   history_record_id, label_id, source_thread_id)` BEFORE reading source facts.
   An already executed action goes straight to finalization, with no learning,
   new rule or re-admission. A terminal event/job returns its existing result.
2. Claim a queued/retry-wait resolve job with `jobs.claim`, a current owner-run
   `Claim(PREPARING)` and the persisted job revision. A restart encountering an
   old-owner claim on this exact `RESOLVE_EVENT` job uses guarded `defer_job`
   to retry-wait, then obtains a fresh claim. This is local non-insert work;
   there is no generic claim reset, inserted-mail retry or cursor-reset API.
3. Read typed source facts outside a transaction and calculate the decision.
   In the success transaction recheck the exact event/job/claim and classify
   `PENDING -> RESOLVED` with the event revision guard, BEFORE `register_action`.
   Then register, apply rule/thread/job effects and `complete_action` LAST;
   nothing mutates after its consumed scope. All these business effects commit
   together. For attention, classify the event `NEEDS_ATTENTION` and defer the
   claimed resolve job to `needs_attention`, with fixed codes and no rule/job
   disclosure effects. Removed/unknown labels take this branch without reading
   source facts.
4. In a fresh owner transaction finalize an executed action's event as
   `CONSUMED`, then `jobs.complete_noninsert_job` using the currently persisted
   claimed job revision. Finalization checks the action is `EXECUTED` and matches
   the exact event ID, projection, history record, label and source thread. The
   no-job exception additionally requires `kind == BLACKLIST`; it never accepts
   another completed action. Allow finalization identifies its durable expansion
   job by the selected thread/generation/epoch stable key; it does not allocate a
   second job. A crash after step 3 is resumed by the lookups in step 1; later stop
   generations are not revived. The implementation must return controlled
   attention if an old allow effect can no longer satisfy current generation
   guards rather than replaying its business effect.

Source reader errors are sanitized to fixed attention codes. The consumer has
no direct Gmail API calls; the injected reader may perform a separately reviewed
source read, always outside the transactions. Raw exception text and source
headers never cross the result/persistence boundary.

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
- Inject restart between claim/read, before effect commit, and between effect
  commit/finalization. The resolve job is eventually completed or visibly in
  attention, never orphaned queued/claimed after a reported terminal success;
  an executed action is inspected before any refreshed source facts are learned.
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
