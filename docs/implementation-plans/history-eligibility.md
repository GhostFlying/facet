# History candidate eligibility before sender parsing

Base: `f7e804cc02b029205577b9b85090867caf166dcc`, production base
`7bffd2193e07f14ac8178cbaaaf9a38c2e8baa8b`. Root owns this unit in the
existing checkout on `p/luchengxuan/history-eligibility`.

## Behavior and files

- In `gmail/source.py`, return a typed excluded-candidate result for valid
  metadata carrying SPAM, TRASH or DRAFT before interpreting From. Preserve
  strict message/thread identity, timestamp and label validation. Never invent
  a sender to satisfy the admission candidate type. This result is only an
  automatic-admission exclusion; tracked-thread expansion remains unchanged.
- Update all candidate consumers in `sync.py` and `reconcile.py`: exclusion is
  normal no-effect completion, with no rule, admission, raw fetch or insert.
  Reconcile counts it as successful metadata/no-rule, not an active issue.
  Malformed eligible sender metadata uses existing `invalid_input`; invalid
  metadata/identity uses `consistency_failure`, never request-key conflict.
  Preserve provider failure, 404 and authentication/retry classifications.
- Add a narrow legacy repair to the existing sync convergence pass: only an
  untracked message-added resolver with matching request_conflict event/job can
  be consumed after a fresh positive source metadata exclusion. Require no
  thread/admission, mapping, insert, claim, action command/receipt or other
  projection work for that message/thread; recheck exact event/job revisions
  inside one transaction and record an audit. No automatic retry/admission of
  eligible or malformed mail; missing/provider-failed reads retain attention.
  Do not close ambiguity or infer exclusion from search absence. No raw reads.
- Tests cover the actual Gmail adapter plus durable sync, exclusion precedence,
  eligible malformed metadata classification, tracked Spam/Trash and draft
  behavior, protected legacy repair, replay, failure and privacy. Update
  development status with actual evidence. No schema migration or public data
  expansion is needed.

## Verification and external actions

Independent plan review precedes implementation; a different independent
reviewer checks the committed candidate. Run focused tests then the repository
offline baseline (locked install, lint, format, full pytest, CLI smoke, safety).
Review staged files and author/committer identity, commit and push the focused
branch, and open its PR under the authorized repository workflow.

The user's 2026-10-21 request authorizes the fix/push and then a full source
reconcile to resolve current degradation on the existing test deployment. Use
the reviewed code on that existing host for guarded legacy repair and the
supported source-only full reconcile. Stop sync and make/verify a coordinated
SQLite/config/credential backup before changing the runtime. Prefer the
official immutable image after reviewed PR/CI; a reviewed local candidate is
acceptable for maintenance if publication is unavailable, with exact file
hashes and retained rollback image/config. Resume only the existing ordinary
sync scope; no source mutation, cleanup, new account/rule/window or direct
Target write by reconcile. Record progress and terminal counts, historical
warnings, queue, actual Dashboard health and running provenance.

## Stop gates and risks

Stop on writer/binding/scope mismatch, unknown insert or protected work; never
force a closure or edit production DB directly. Incomplete scans stay incomplete.
A valid excluded message can move out of Spam later; this repair consumes only
its current notification, does not stop future History or change rules. The
full scan can take tens of minutes and provider throttling/auth may prevent
completion. Preserve the request key and backup; report actual failures.
