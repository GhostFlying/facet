# Successful source coverage closes unadmitted History failures

Base: `ae25f0b` (documentation PR #123; production code already merged at
`ff696599`). User approved this correction on 2026-10-14.

## Outcome

A complete, current-scope source reconcile closes old unadmitted message-added
History failures as historical unknowns, not projection successes. Preserve
events, original error evidence and explicit run lineage; never merely hide rows
in Dashboard or set Healthy because a reconcile exists.

## Minimal implementation

- Add a narrow repository convergence function using existing source_events,
  sync_jobs, audit_events and epoch_jobs. No migration, new reset API or scheduler.
- Only a `completed` run with zero remaining issues/errors/404/seen candidates,
  complete candidate accounting, unchanged rule revision/source binding and the
  initial-backfill lower bound may authorize closure. Require the covering
  source-reconcile epoch (not necessarily completed: queued scan work can leave
  it NEEDS_ATTENTION). Require a run created after v7 migration; its backfilled
  binding revision cannot prove an older run's binding. Hold the unique writer;
  perform changes in one DB
  transaction, with no Gmail or waiting inside it.
- Only old `message_added` / `resolve_event` source_missing pairs predating the
  frozen window_end fence qualify (event.observed_at and job.created_at/updated_at
  must be no later than it). Require known message/thread references; exclude
  tracked/admitted threads, mappings, any insert attempt, claims and action work.
  Records first failed/updated after the fence, other event kinds, managed loss,
  ambiguity, authentication or storage failures remain active.
- Transition eligible events to consumed and resolver jobs to completed, not
  confirmed projection. Append a job_state_changed audit per job retaining
  original source_missing, before/after state and revisions; the existing schema
  restricts maintenance_completed audits to projection objects. Link each job to the actual
  reconcile epoch via epoch_jobs. This is the durable coverage receipt; replay
  must not duplicate receipts or reset counts. Never invent absent provider data.
- At successful SourceReconciler finalization invoke this helper atomically;
  terminal replay of the same successful CLI request may apply the missing
  convergence to a previously completed run, without another mailbox scan.
  Failed/abandoned/partial runs cannot authorize it.
- CLI/reconcile Dashboard summary shows an aggregate historical warning count.
  Add that count to the existing Issues DTO and render a historical-warning
  paragraph in the main page (no new fetch family). Count distinct closed job
  IDs across retained covering-run receipts, not only the latest run. Render it
  separately from active issues. Normal health still derives from
  real job/epoch/auth/freshness state. No public identifiers or diagnostic refs.
- Update current status and relevant contract/spec/previous plan wording:
  History is not scanned; post-run convergence still handles covered old errors.

## Acceptance and risks

Persisted proof is exact: completed_at is non-null, page_token and terminal error
fields are null, and candidate counts/classifications agree with listed,
metadata_success, matched, mapped and queued counters. No seen/unavailable/
attention candidate qualifies. The covering epoch has epoch_id=run_id,
kind=source_reconcile, matching requested-reconcile operation/ruleset and exact
window/cutoff fields; epoch terminal state is not the proof. Event and job both
must have the exact source_missing state/error. Exclude any admission or action
work/effect, not just active tracked threads. A receipt is the job_state_changed
audit (original source_missing, source_missing -> completed, revisions) joined
to epoch_jobs for that exact source-reconcile epoch; count distinct job IDs.

Successful finalization updates the run and applies convergence in the same
transaction; successful terminal replay calls it before returning. Require
one-row state/revision updates and roll back run/event/job/audit/link changes
together on failure. The receipt claims only historical notification retirement
under completed current-scope coverage, not deletion, no-rule or projection.

Real SQLite tests cover eligible closure/audit/run lineage, idempotent replay,
rollback, partial coverage and guards, late errors, stopped/tracked threads,
mapping/insert/action/claim protection, unchanged cursor/insert/confirmed counts,
and actual reconciler integration. Dashboard/privacy tests verify historical
warnings stay visible while Healthy returns only when no active faults remain.
No weakening of unknown-insert, stopped-generation or provider-error policy.
Also test migrated-v6 binding evidence, mismatched epoch/counters, an event
between window_end and run.created_at, and warnings after later successful runs
and alongside active faults in a browser.
Independent plan and candidate review, full offline baseline and CI precede merge.

## Authorized live follow-up

Stop ordinary sync; make a locked SQLite/config/credential backup. Validate the
existing successful run against current scope/binding/accounting, then replay its
original supported source-only CLI request on a reviewed local/official image.
Expected: 217 old resolver failures close with receipts, no Gmail insert, mapping
and cursor unchanged. Stop on a stale scope, unexplained protection, incomplete
coverage or DB error; do not force it. Deploy the accepted immutable image and
resume existing sync. Verify active issues, historical warning and real health.
