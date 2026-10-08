# Learned-rule backfill policy provenance

Date: 2026-10-08. Root authored the bounded correction; independent review used
authorized Sol xhigh. This receipt separates source/image acceptance from the
scoped real Gmail trial.

## Cause and correction

The published runtime's first authorized historical cycle returned
`request_conflict`: action learning persisted the actual PSL/IDNA rule-policy
version, but BackfillProducer constructed admission references with `auth-v1`.
Repository validation correctly rejected their mismatch. The failed cycle left
nine existing mappings, the old unknown attempt, historic attention and retained
blocked/recovery work unchanged; there were no new insert attempts or mappings.
The explicitly started historical epoch remains available for continuation.

Accepted source candidate is `a89f4e83cced6c5d10200ea2d7922d1c159d00d9`, based
on `9c2f90bacfbd65ca41310ab7651a26b128e06bb4`. Plan amendment SHA-256 is
`eca9748d03f9a1fc0a067ce04c99b83f1dff2eca44883b455d9b3c56f24067a1`.
Backfill reads the exact selected rule revision inside its existing transaction
and uses that revision's persisted policy version for historical and known-gap
admission. Missing revisions fail closed before committed admission or progress.
No migration, rule rewrite, current-version substitution or guard relaxation.

## Independent and offline evidence

Independent plan and exact-source reviews approved the correction. Six focused
regressions passed independently: learned policy provenance, missing-revision
rollback, gap rule removal with both policy versions, and production CLI
action learning followed by historical/gap projection and restart deduplication.
Only external Gmail/OAuth is fake; E2E commands create the actual configuration,
bindings, rules and epochs. Synthetic privacy sentinels remain asserted.

Root's affected-file run passed 71 cases (101.28 seconds). Complete offline suite
passed 2784 cases (638.74 seconds); locked dev dependencies, repository-wide
Ruff/format, spike help, whitespace and repository safety checks passed.
These are check receipts, not the measure of product completion.

The unchanged pinned Dockerfile built local image `facet:a89f4e8`, ID
`sha256:b632e1f6f19553f19e816e7e0fdb7b9de3e0fba659ddb26242def25917b30030`,
with exact candidate OCI revision and UID `10001:10001`. Its actual production
CLI passed action learning -> historical/gap projection -> durable mapping ->
restart cases with networking disabled, read-only rootfs and external-only
fakes. Application source and real state/credentials were not overlaid.

## Scoped live trial boundary

The user approved the updated default six-month window for the existing accounts
and sole sender rule, including full admitted non-draft thread history. Fresh
account/scope/target checks and writer-locked private SQLite-API backups passed.
Preview and start stable-key replay matched, preserved the shared checkpoint and
created exactly one historical epoch with zero insert attempts.

Independent operator acceptance qualified private key/receipt persistence,
retained-row guards and a distinct corrected submission after proof of the known
pre-insert failure. The failed receipt is retained. Pending/uncertain runs cannot
auto-resubmit; this is not unknown-insert retry authority. The corrected local
image continues the same epoch without a new preview/start or rule/scope change.
The corrected real cycle finished in 2276.43 seconds: discovery completed 43
pages / 4234 candidates; two History pages and 30 resolved events; 215 new
verified inserts and durable mappings, 224 mappings total. All mapping attempts
are verified, target IDs are distinct and no claims remain. The old nine
mappings, one unknown, 58 attention jobs, retained blocked/recovery jobs,
rules/bindings and stopped generations remain intact. There is no new unknown,
attention, warning or terminal failure. There are still 4049 queued message
jobs; the historical epoch is catching up, not complete. The per-run production
job budget limits this cycle, not the authorized selected mailbox scope.

Independent read-only verification sampled 20 newly completed mappings while
the cycle was running. Semantic/MIME digests, mapped message/thread assignments,
all 20 valid Date/internalDate pairs and normal All Mail visibility passed.
This is a 20-message sample, not exhaustive fidelity acceptance. A final full
target ID enumeration classified 224 mapped copies, two permitted outbound
SENT items and zero other unmanaged items. No verifier performed target writes.

Three thread-expansion reads entered `source_rate_limited` / `retry_wait`, then
completed through safe scheduled read retries inside the same process. Their
retained error rows confirm this observation. The helper initially computed
`clean: true` from the final states, but that is insufficient for the trial's
stricter any-provider-deferral continuation gate. Independent focused review
approved preserving it as `end_state_clean` and atomically recording `clean:
false`, the observed recovered-deferral count and the fixed stop reason in the
private operator receipt after exit. Cycle2 was not executed. Real fresh-process
continuation remains unverified; offline restart cases remain valid. This is not
an insert retry or a production state mutation.

Most elapsed time was serial candidate metadata admission before queue copying;
completed discovery is persisted and is not repeated by ordinary continuation.
The source fix's independent/offline/local-image acceptance is not invalidated
by recovered provider read deferrals. Root will integrate this bounded fix;
assessing provider deferrals and qualifying a bounded continuation are the next
live gates, not a new generic retry framework. The installed continuous service
remains stopped. Old unknown/attention, source writes, cleanup, scope changes and
continuous daemon startup remain outside this trial. CI/main publication and
final Phase 1 gates remain separate.
