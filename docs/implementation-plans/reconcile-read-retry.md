# Reconcile read retries

Keep serial batches of at most 50. Retry source list/get/batch reads only:
429, allowlisted rate-limit 403, network failures, and 500/502/503/504.
Respect delta-seconds and HTTP-date Retry-After. Use exponential delay starting
at one second, capped at 60 seconds before 0-25% jitter, never earlier than the
provider deadline. Allow eight retries per failed set and 1800 seconds total
run waiting. If a wait exceeds the remaining budget, retain incomplete work.

Persist page candidates as seen before metadata reads. Retain successful batch
results; retry only failed members. Never count retries twice or retry inserts.
Check owner/rule/binding guards before retries, keep waits outside transactions,
and propagate interruptions. Preserve source-only scope and old History rows.

Files: provider Retry-After parser, focused reconcile read retry helper,
SourceReconciler integration, safe retry diagnostics, CLI interruption handling,
and synthetic behavior tests. No schema or command change.

Acceptance: injected-clock delta/date/header/budget tests; partial batch,
outer failure, pagination, exclusions, interruption, durable seen and dedup
tests; privacy checks; independent plan and implementation review, full CI;
then immutable local deployment and authorized source-only measurement.
