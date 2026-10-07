# Sync single-dispatch and source-missing acceptance

Date: 2026-10-07. Base: `4613a473df17936838c5e6f6549ac61fa0d93e03`.
Implementation candidate: `3df74f31bb8a4a7d65ce5eae1d3294e7fb0867b6`.
Plan: [bounded repair](../implementation-plans/sync-single-dispatch-transport.md),
SHA256 `cae6d73c2c87fe1c2db2a0eeb5dc24cf980ac2b68e7d2cba74837a1b8d802c9b`.
Independent Sol 6.1 xhigh plan reviewer `/root/sync_transport_plan_review`
approved this revision. Its initial review found the actual SDK's long-GET
POST override; the bounded read-only exception and regression resolved it.
Independent Sol 6.1 xhigh implementation reviewer
`/root/sync_transport_impl_review` approved the exact candidate. Independently
passed 59 affected wire/factory/History/runtime/CLI cases, 35 worker/sync cases,
and the explicit History-404 gap regression; no current-model blocker remains.

## Product evidence

Normal production Google request construction now uses access-only Requests
HTTP, with adapter retries disabled, redirects disabled, and no automatic
credential refresh/replay. httplib2 remains an SDK dependency/response value,
not the sync network transport. Existing credential-manager ownership and
durable intent/recovery behavior remain intact. A surfaced 3xx insert is unknown,
not permission to send it again. Source message metadata 404 atomically becomes
`source_missing` in the event and resolve job; restarting does not refetch that
terminal event. History-404 gap and target missing behavior are unchanged.

Real CLI subprocesses completed init, synthetic OAuth/binding, zero-write
preview, explicit start, an empty cycle, CLI rule addition, prospective History
discovery, full non-draft-thread insert/readback and durable mapping. These
commands used the normal production factory/runtime: only OAuth interactions
and the final Requests socket destination were substituted. No DB readiness,
binding, rule or epoch seeding occurred. A fresh process did not insert confirmed
mail again. Separate accepted-body/response-loss, 503, 307 and 308 cycles left
one durable unknown attempt with queued recovery; restarting sent no more POSTs.
Actual SDK/TCP tests also cover 401 and 429, preserve Retry-After, and prove no
authentication resend or redirect request within an invocation. Long valid
discovery queries retain the SDK's exact read-only POST override. Source/target
sessions are separate and close on normal success/failure/partial construction.
Synthetic mail/error/credential sentinels are absent from prohibited state,
command output and captured logs.

Root passed 107 affected/adjacent cases. Locked environment sync, repository
Ruff/format, spike help, diff and staged/tracked safety checks passed. The full
offline suite passed on this source candidate: 2751 tests in 562.05 seconds.
The subsequent handoff commit changes documentation only; it does not replace
the independently reviewed source candidate or exact-image provenance.

The unchanged pinned Dockerfile built on sgbox. Imported local image
`facet:3df74f3`, ID
`sha256:890937f02bb13b6201d9098df6a42fc436f5c44537e31ce35d3188894be2a230`,
has the exact candidate OCI revision and user `10001:10001`. With external
networking disabled, this image passed all five production CLI cases above
(success, response loss, 503, 307 and 308) in an isolated synthetic volume.
Only the read-only test driver/external fake was mounted; app source and real
state were not overlaid or mounted. Real SDK and Requests/TCP remained in use.

This is bounded offline/local-image acceptance, not a real Gmail success or
M1-M6 completion. GitHub CI/integration are tracked separately from this local
receipt. Merge, publication, deployment and live upgrade remain unclaimed. The
focused repair PR depends on the preceding History candidate, which is not yet
on main; it cannot establish acceptance of the entire unpublished parent stack.
The real service remains stopped; the old unknown insert, attention
events, credentials and scope are unchanged. No Gmail call, mailbox deletion,
service resume, scope expansion or old-insert retry occurred. Container Gmail
connectivity, qualified integration, and separately authorized live/recovery
validation remain explicit next gates.

## User-requested local revalidation, 2026-10-07

The same immutable image ID/revision passed all five existing production CLI wire
cases again in 66.93 seconds, non-root/read-only with external networking disabled
and synthetic state on tmpfs. App source and real state were not mounted; only the
read-only existing test driver/fake was mounted. No implementation or test fixture
changed, so the existing exact-source independent review remains applicable.
Preview/start in this fixture is empty; full-thread copying is triggered by the
subsequent prospective History arrival, not a nonempty initial discovery scan.

Separate no-credential HTTPS probes on the actual Compose bridge reproduced direct
Google connection timeouts. Explicitly passing the existing host proxy environment
to that isolated one-off container reached Gmail/OAuth/Accounts public HTTPS roots
in 0.63/0.44/0.46 seconds (404/404/302). Those responses demonstrate TLS/HTTP
connectivity only, not account binding, token refresh or live mail projection.
Neither proxy values nor provider response bodies were logged in this receipt.
No proxy configuration was persisted or added to Compose, and no real credential
or state volume was mounted. The live sync container remains stopped; the old
unknown insert was not retried. Controlled live verification remains open.
No full suite/image rebuild was repeated because
source, dependencies and image did not change.

The subsequent user correction classifies proxy wiring as local deployment
configuration, not project scope or a release gate. A private, owner-only override
outside Git now passes existing host proxy variables to sync/setup without storing
their values. Compose resolution passed for both services; another isolated
no-credential probe using that resolved environment reached all three public HTTPS
roots in 0.43–0.65 seconds. The repository Compose/Dockerfile/image and stopped live
container were not changed. Subsequent authorized local operations must include
this override; no project proxy implementation is pending.

## Bounded authorized live Gmail trial, 2026-10-07

The user explicitly authorized one normal production `facet run --once` and
a fresh-process continuation check on the existing bound accounts and one
enabled sender rule. Both used the unchanged exact image/candidate above,
UID `10001:10001`, read-only root filesystem, existing Compose network/state
volume and private deployment proxy environment. No fake transport, app-source
overlay, DB readiness seeding or scope/rule/epoch change was used. Before execution,
normal StateOwner ownership protected a private SQLite-backup-API bundle of both
state journals plus config and credentials; ownership was released before the
actual CLI subprocesses. Backup integrity and owner-only permissions passed.

| Actual production process | Elapsed | History pages | Resolved events | New insert attempts | New confirmed mappings | New attention |
| --- | --- | --- | --- | --- | --- | --- |
| First `run --once` | 30.33 s | 2 | 22 | 9 | 9 | 0 |
| Fresh-process `run --once` | 4.62 s | 1 | 0 | 0 | 0 | 0 |

After each process, private comparisons confirmed unchanged bindings/config/rules,
the existing unknown attempt, and all 58 historic attention jobs. The unknown
count remains one, not a new trial failure; it was not selected for recovery or
resent. Subsequent read-only target inspection found nine mapped copies and the
original two permitted source-From SENT items, no drafts and no other unmanaged
content. Those outbound items were neither cleaned nor claimed as mappings.
A read-only search found zero candidates for the old unknown; absence does not
authorize another insert or establish its historic outcome.

Read-only source raw/target readback verified all nine stored mappings, persisted
digest/version consistency and equal semantic/MIME digests. Three source threads
map to three target threads. All nine valid Date headers match target internal
dates; there were no Date fallbacks. None of the copies has Inbox, Spam, Trash or
draft labels. Raw bytes stayed in memory; only aggregate counts/typed outcomes
were emitted and no content or private IDs were saved in this receipt. Verification
performed zero target writes and no business-state mutation.

Both CLI receipts report `discovered: 4700`. The completed partition returns its
historical observed-item total, not a cycle delta. Comparing its count, completed
pages and state with the stopped backup confirms the partition is unchanged and
zero new initial-discovery items. This is an output naming/cumulative-statistic
limitation, not evidence of a new whole-mailbox scan or 4,700 projected messages.

This extends the source candidate's existing independent/offline acceptance with
bounded real Gmail API projection and restart evidence; it is not another review
approval. Source/tests/dependencies/image were unchanged, so no redundant full
suite or build was run. No source mutation, deletion, old-insert retry, historic
attention reopening, new OAuth scope or long-running service restart occurred.
Main integration/publication, production outbound classifier/audit integration,
full CLI/action-label acceptance, Gmail UI checks, live fault/recovery and complete
backup/restore/deployment/72-hour gates remain open. The sync service is stopped.
