# Automatic five-minute unknown-insert recovery

2026-10-09. Base main: `0a9bb911c44270144ffe5da4cd17fd4bdfabf068`.
Root implements; independent Sol xhigh reviews plan and exact candidate.
The user explicitly replaced the uncommitted manual-preview/one-budget proposal:
ordinary startup/cycles handle pending unknowns older than five minutes without
per-item operator intervention. This is acceptance of residual duplicate risk,
not a Gmail indexing guarantee. Original uncertainty is retained, not relabeled
as definite non-insertion. No M1-M6 gates, mailbox ownership or privacy change.

## One product path

Use existing `run`/`sync`, UnknownInsertChecks and serial ProjectionWorker.
After the persisted dispatch deadline (five minutes), a successful zero-candidate
RFC search, unchanged RAM-only source digest/RFC, current ready accounts/bindings,
active generation and no mapping permit automatic requeue of that exact project
job. Query failure is not absence. Missing RFC, candidates/ambiguity, changed or
missing source and stopped threads do not permit resend. Include Spam/Trash in
candidate search. Preserve the ordinary target-precondition classification;
do not add full mailbox enumeration for each unknown. Empty checks before the
deadline schedule that deadline; provider failures retain bounded existing
backoff. Process a bounded batch each cycle, never a bulk unconditional resend.
Replacement unknowns follow the same five-minute policy, not a one-attempt cap.

## Minimal durable change

Discard only root-owned, uncommitted manual recovery CLI/grant/budget drafts and
their proposal-specific tests; retain/rewrite relevant fault/privacy tests.
Reuse existing writer, refresh/profile checks, job/claim/intent/mapping APIs and
backup migration. Add a small v5 `insert_absence_retries` table: projection,
original attempt, successful absence-check timestamp, source/target binding
revisions. Its retained identity records an automatic policy decision, not
ownership or failure proof; no preview/request keys, budget or replacement grant.

In one owned transaction, validate the deadline/account/generation/no-mapping,
record the decision, complete the old recovery check task and requeue the original
project job. Preserve old attempt certainty/attribution/dispatch/digest/target
facts; normal check counter/revision changes remain audit evidence. A crash
before commit leaves recovery pending; after commit ordinary worker continues.
Under the startup writer lock, hand off only claims retained from a previous
owner: honestly retire an undispatched prepared intent before requeueing;
materialize a stale dispatched attempt into existing pending recovery without
changing its dispatch time; route an attributable known result to readback-only
completion, never absence retirement/resend. Use existing typed result and job
transitions, not another recovery framework or network-layer insert replay.

The two unresolved UNIQUE indexes otherwise prohibit retaining old uncertainty
alongside a replacement. Replace them with lookup indexes and equivalent
INSERT/UPDATE guards exempting only attempts with a retained absence decision.
All other unresolved attempts remain exclusive per source message/thread. Use
the same exact exception in prepare, defer/restart and dependency guards.
Verified mapping resumes legal unmapped current-generation dependents. Normal
401 refresh/retry remains valid for definite rejection; no manual budget suppresses
it. Repeated unknowns must each obtain a fresh aged absence decision. Recovery
aggregates distinguish active unknowns from historical assumed-absent outcomes.

## Files and acceptance

Files: v5/registry/schema/owner backed-up startup upgrade; focused absence-decision
repository; intents/jobs guard changes; projection recovery/worker; existing
CLI recovery aggregate; targeted unit/subprocess/fake tests; AGENTS and canonical
contract/spec/status/decision-ledger updates. No new framework or command path.

Tests: before/at deadline; restart retains deadline; multiple pending threads;
candidate and provider-error branches; source/binding/generation guards; repeated
unknown cycles; atomic decision/requeue and prepare/dispatch/map fault boundaries;
unrelated unresolved constraint rejection; definite 401 retry; mapping/dependency
continuation; original uncertainty preserved; v4 backup/rollback/reopen; fresh
process crashes/reopen at prepared, dispatched and known-result claims; actual
CLI setup/history/unknown/ordinary-run/restart via external-only fake transport;
non-root local image and DB/files/log/output privacy sentinels. A fake clock may
replace time for tests, but do not manufacture production readiness/mappings or
directly insert recovery decisions. Run affected checks in development, then
mandatory complete checks, independent acceptance, exact PR CI before merging.

Live authority remains the existing accounts/rules/window and exact old unknown
plus its three dependencies: after qualified local image/review and stopped
writer-locked backup, exercise the same automatic checks/worker on that frozen
selection, not a manual DB correction or new History/backfill. No deletion,
scope expansion, perpetual daemon or pre-insert restore after target writes.
Live results and final Phase acceptance remain separate from offline evidence.
