# Full source reconcile and exception convergence

Base candidate: `8c54e4c` (`p/luchengxuan/dashboard-activity-layout`).
This unit depends on the existing M2 discovery/projection path, M4 source
reconcile/gap contracts, and the M2-04 insert-recovery guards; it does not
replace those gates.

## Goal

Add an explicit, repeatable `facet reconcile --source --full` path and
`facet reconcile status` command.  The operation scans the current enabled
sender/domain rules over the fixed six-month window plus complete available
history for tracked threads, compares source candidates with durable mappings
and jobs, queues only confirmed missing projection work, and closes only
exceptions that the scan proves have converged.  It must never write Gmail
directly, reset cursors, delete rows, or claim unresolved work succeeded.

## Scope

- Keep reconcile as a foreground, single-writer maintenance command. It owns a
  durable run summary, but does not require a `reconcile_source` worker,
  background scheduler, or page-token continuation; an interrupted run is
  marked abandoned and a later invocation may scan the frozen scope again.
- Keep explicit CLI scope confirmation and a stable request key; no separate
  preview/start protocol is required for this foreground maintenance command.
- Reuse the Gmail source adapter's rule query, pagination, metadata parsing,
  candidate matching, and existing projection/recovery pipeline.
- Read source metadata through Gmail batch requests of at most 50 subrequests
  first. Measure the serial-batch path before adding concurrency; if it remains
  too slow, run at most four independent batches concurrently with separate
  transports. Each subrequest keeps independent error classification.
- Add a new controlled `source_metadata_unavailable` classification for an
  unadmitted History candidate whose metadata remains unavailable after the
  bounded recheck.  Keep managed source loss as `source_missing`.
- Persist aggregate reconcile facts and safe provider diagnostics.  No raw
  mail, message/thread/history IDs in public output, or unfiltered provider
  responses in DB/logs.
- Add source reconcile status to private CLI and read-only Dashboard aggregates.
- Apply the same reconcile closeout to the existing 217 legacy
  `source_missing` events; do not add a separate blind cleanup/reset path.
- Use a stable request key and explicit `--yes`/scope confirmation for starting
  a live source reconcile. The run records the immutable ruleset revision,
  fixed window and tracked-thread selector before remote reads.
- Recheck the frozen ruleset and generation before each durable batch commit;
  rule changes do not widen the run. If the binding, scope, or generation
  changes, stop the run with a controlled maintenance attention state.
- Use exact sender/domain query clauses and the provider's advertised domain
  capability. Unsupported domain recall fails closed; no unfiltered fallback.
  Metadata matching remains a local exact rule check. Tracked-thread metadata
  must use a Spam/Trash-inclusive provider read and filter drafts/non-draft
  history locally.

## Files and ownership

- CLI/bootstrap and a focused CLI reconcile module: command parsing, preview/
  start/status output, scope and writer guards.
- Gmail source/reconcile projection modules and repositories: candidate
  enumeration, durable partitions, comparison, projection enqueue, and
  proven-convergence transitions.
- Contracts, migrations, serialization, status/logging, and web snapshots:
  typed lifecycle/error fields, safe diagnostics, aggregate public models.
- Tests and docs: fake-Gmail pagination/restart/privacy tests, CLI subprocess
  coverage, product/CLI/dashboard status updates.

## Acceptance

1. Fake Gmail can run a full reconcile across multiple rule pages, deduplicate
   a message returned by multiple rules, rerun after an interruption without
   duplicate jobs, and include
   tracked-thread history older than the six-month window.
2. An eligible untracked candidate creates the normal authorization path
   (`tracked_thread` + `expand_thread`); an active tracked generation may create
   a `project_message` child. Stopped/unadmitted candidates never revive a
   generation. No Target call occurs during reconcile.
3. An unadmitted metadata 404 has a durable per-candidate recheck lineage; after
   one replay-safe recheck it becomes `source_metadata_unavailable`. A
   managed/mapped 404 remains `source_missing`. Unknown insert, recovery, auth,
   storage, and multi-candidate states remain active issues.
4. Reconcile closes only positive metadata/no-rule, exact existing-effect, or
   duplicate-effect cases. Candidate absence from a search is never proof of
   no-rule or deletion. Unresolved work leaves `completed_with_issues`. The 217
   legacy records are processed by this same path with no Gmail writes and no
   row deletion; a still-unreadable record is recorded as terminal unknown, not
   called a successful resolution.
5. Reconcile facts include run/scope/rule revision, aggregate
   counts, provider stage/status/reason, and a local diagnostic reference.
   Logs, DB public projections, Dashboard, and CLI public output pass the
   repository privacy tests.
6. A reconcile maintenance marker prevents ordinary sync from reading History
   or advancing its cursor while the foreground reconcile owns the writer; an
   abandoned marker is recoverable and ordinary sync resumes after completion.
7. Targeted tests, the complete offline baseline, repository safety, and CI
   pass before any real Gmail validation. Real validation is source-only first;
   no deployment or target write is implied by this plan.

## Review handoff

Before implementation, an independent reviewer must review this plan revision
against base `8c54e4c`. After implementation, the reviewer must re-check the
exact candidate SHA, including the new ErrorCode/catalog/schema/migration,
request guards, frozen scope behavior, and privacy evidence. A plan review does
not approve live Gmail reads or deployment.

## Stop gates

Live verification follow-up: investigate the tracked-history drain failure using
the production Gmail discovery schema; `threads.get` must use only supported
parameters (Spam/Trash visibility is intrinsic to get-by-ID, not a list filter).
Record provider throttling as incomplete coverage, not terminal source loss.
Persist final counters including legacy reads and do not close the legacy
events until the full scan and tracked-history stage have completed safely.

- Stop without resetting state if the ruleset, binding, generation, writer
  owner, or reconcile snapshot is inconsistent.
- Stop the run as `completed_with_issues` on provider pagination failure,
  incomplete persistence, unresolved recovery, or ambiguous candidate
  attribution.
- Do not run the real 217-record closeout until offline tests and independent
  implementation review pass on the exact candidate commit.

## Compatibility and state rules

- Add the new classification to the reconcile candidate table and fresh/upgrade
  schema manifests. Existing v5 state must migrate through a reviewed v6 step;
  opening an older state must never silently initialize an empty database.
- Store per-candidate recheck/terminal facts in a private durable table keyed by
  local reconcile run and event lineage. Aggregate counts alone are insufficient
  to make restart behavior safe.
- Reconcile may enqueue durable projection work, but only the ordinary sync
  owner may consume it and contact Target. The reconcile runtime composes a
  source-only adapter and must fail if a target transport is constructed or
  called.
- Public Dashboard/CLI models expose only allowlisted aggregate counts,
  timestamps, scope labels and controlled codes. Provider reason/status and
  local diagnostic references remain private diagnostics.
