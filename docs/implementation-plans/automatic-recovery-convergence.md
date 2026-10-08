# Automatic recovery checks and event convergence

2026-10-08. Base `38e8c7275fd1d9e0f3f4ce7fbb354c1c17525301`.
Root implements; independent Sol xhigh reviews plan and exact candidate.

## User-observable delivery

Normal `run --once` automatically checks due unknown insert outcomes without
resending them, records checks and a durable next-check schedule, and distinguishes
not-yet-found, duplicate, fidelity and attribution problems. Restart does not
repeat insert or reset the schedule. Existing direct-response readback recovery
continues to verify mappings and unblock only current active generations.

Resolve false attention automatically where durable proof exists: completed
thread-action aliases, and message-added notifications already represented by
a confirmed mapping or an exact existing projection job. Unknown-blocked jobs
are durable work, not permission to create a second job or repeat insert.
Ordinary label removals can complete as no-ops; unknown/retired action label IDs
and genuinely ambiguous metadata remain explainable attention, not default allow.

## Boundaries and known technical gap

The existing persistence schema accepts only `none` and `direct_response`
attribution. No reviewed unknown-attribution producer exists. A unique content
match alone cannot legally become a mapping under the current product contract,
especially with permitted external SENT/DRAFT. This unit checks automatically but
does not fabricate ownership, introduce a fence framework or claim that unknown
mapping/retry is solved. Missing results remain scheduled checks; genuine ambiguity
retains a precise code. No new insert-attribution policy or contract change.
Implementation review correction: a confirmed source raw HTTP 404 retains
`source_missing`, including attempt/job/audit diagnostics; insertion certainty
remains unknown and no ownership, mapping or resend is inferred.

Historical attention is not blanket requeued. Automatic closure requires exact
canonical action completion, or an exact mapped/current-generation durable
message effect, with event/job revision, lineage, no-claim and error guards. Other
old errors remain untouched until their cause can be independently established.
These guards extend the earlier implementation-only prohibition on normal-sync
alias repair; they do not change disclosure, scope or user-review decisions.

## File scope and reuse

- `projection/recovery.py`: small bounded read-only Gmail evidence function and
  owner consumer; reuse target search/readback, source integrity and fidelity.
- `db/repositories/intents.py`: guarded check count/schedule update for the old
  unknown attempt and its owned recovery job; no new intent, mapping or insert.
- `db/repositories/events.py`: narrowly proven zero-effect completion of old
  aliases and existing mapped/project-job events, atomically with resolve work.
- `sync.py`: recovery checks before projection; bounded proof-based attention
  convergence without general attention override or historical scanning.
- The considered current-label filter is deferred: changing label IDs after an
  interrupted History page would change its persisted event count/digest. Do not
  introduce per-poll label-policy persistence or redesign pagination for this fix.
  Unknown/retired label events retain their existing explicit attention semantics.
- `cli/bootstrap.py`: reuse shared evidence function for explicit read-only
  recovery check; preserve its zero SQLite mutation/output boundary.
- Focused repository/worker/sync tests and production CLI external-only wire
  subprocess tests; update CLI spec, one review receipt and current status.

No schema migration, marker headers, spool, framework, new worktree, broad
attention retry, target cleanup, rule change or stopped-thread resurrection.

## Acceptance and external actions

1. Unknown insert created by production fault path; new CLI process searches and
   checks candidates, stores bounded count/schedule, performs zero extra insert.
   Empty search, delayed index, duplicate candidates, mismatch, external outbound,
   provider failures and crash/restart preserve unknown and thread blocking.
2. Exact already-completed action and exact durable message effects converge once;
   no extra rule/admission/expansion/insert, mapping count unchanged. Wrong key,
   generation, binding, error, claim or contradictory content does not converge.
3. Privacy sentinels absent from DB/files/logs and public/private CLI outputs where
   prohibited; raw remains bounded memory only. Network never spans SQL UoW.
4. Affected tests during iteration; final full prescribed checks, independent
   candidate review and CI. Build exact local non-root image and run production
   CLI with external-only fake Gmail/OAuth before creating PR; then qualified merge.

No live old-record mutation or unknown resend is authorized by this unit. A private
isolated SQLite backup may be inspected/tested offline with network disabled;
never use it as a second real writer. Report actual proven closures versus pending
technical/authorization gaps. Live repair, insert retry and deployment need explicit
selected scope, backup and authority; no inference from successful offline tests.
