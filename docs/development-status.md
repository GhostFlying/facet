# Facet development status

Updated: 2026-10-10 (PRC; historical UTC receipts retain their original dates)

This is the durable handoff for autonomous development. Update it with evidence
at the end of each coherent implementation unit. Do not store account addresses,
mail identifiers, private fixtures, tokens, or raw diagnostics here.

## Current state

### Dashboard diagnostics and rule-match activity — local candidate

The short plan [dashboard-diagnostics-activity](implementation-plans/dashboard-diagnostics-activity.md)
adds a sixth read-only `activity` snapshot and fixes the misleading all-Unknown
view during a running backfill. A verified binding now reports scope readiness;
the owner connection reports DB write mode; Linux memory and state-filesystem
free space report bounded pressure levels when available. Diagnostics accepts
only the full commit SHA baked into the image as `FACET_COMMIT_SHA`; it does
not treat a runtime image tag as source provenance.

The activity timeline is derived from durable first-verification mapping history
joined to the admission generation's sender/domain rule. It shows only rule
kind/value (or the explicit `Other authorized thread` bucket), matched mapping
count and server-local time, newest first; repair/replay cannot recategorize old
successes. No Gmail calls, message content, IDs or schema migration were added.

Targeted Dashboard/model/privacy/container checks passed; the exact-head
runtime/web subset is 20 tests, and the complete browser script passed synthetic
desktop 1440x900 and mobile 390x844 viewports. A real Dockerfile build was
completed after importing the pinned Docker Hub base layer through the approved
sgbox relay. The local Compose test deployment now runs that built candidate
with `FACET_COMMIT_SHA=123dfadfa68843220240216b5576951259263e12`.

The corrected candidate adds an explicit `cycle_in_progress` status flag:
an in-flight healthy-looking cycle is rendered as neutral Running/Backfill,
while degraded/blocked/stale states remain visible. Scope readiness requires a
committed credential-change record matching the current binding revision and
role policy; old binding state alone is no longer presented as current scope
evidence. The image workflow bakes the checkout SHA through a Docker build arg;
an arbitrary `FACET_IMAGE` tag is not treated as proof. The candidate has not
yet been merged or published to GHCR; the local image is explicitly a temporary
deployment artifact.

The implementation reviewer later found and the candidate fixed one retained
cycle-error propagation bug in `d7485fc`; focused runtime/sync/foreground/web/
status checks passed (44 tests). The required pre-implementation plan review
was not obtained because the review service twice reported capacity; this is
recorded as a process gap, not retroactive approval. The local test deployment
has now been upgraded with stopped-state backup and retained state, and has
completed zero-write real cycles plus a restart with unchanged mapping and
attempt counts.

Next: record an independent review against plan revision 3 and exact final
head, then use the resulting CI and review evidence to decide merge and GHCR
publication. The local deployment evidence is test-host evidence, not final
Phase 1 acceptance.

### Dashboard operational consumer — merged and running in the current test deployment

The [short plan](implementation-plans/dashboard-observability.md) and source
`9ff469be8202efd235c9a36aaa7a2393937ae8f8` add a responsive consumer of the five
existing cached public families: unique confirmed messages, exclusive queue
states, current-scope thread discovery, fixed exception suggestions, binding
state/times and DB/scope diagnostics. No new backend collector, Gmail access,
write control or public field. Unknown metrics and unreported reconcile/audit
remain explicit. Search candidates are not a final copy denominator.

Actual Chromium desktop/mobile viewports passed synthetic backlog, auth, gap,
partial completion, mixed-family freshness, request failure, malformed-response,
timeout and recovery checks on the bundled page, including a 29-second-old
snapshot expiring within its remaining budget. The same checks passed in an
isolated non-root read-only candidate container; no real state or credentials
were mounted. Endpoint/runtime/public-privacy checks passed. Review and final
candidate checks belong to the [acceptance record](reviews/dashboard-observability.md)
and linked engineering PR, not a claim that every Phase 1 gate is finished.
PR [#112](https://github.com/GhostFlying/facet/pull/112) merged at
`d7232ddcbaa390a4317f25b230d218c454fbd359` after independent acceptance, the complete
local offline baseline and exact-head Python 3.12/3.13/image CI. Its official
image is anonymously imported; all packaged source/static bytes match the
qualified candidate. Both architectures' SPDX/SLSA payloads match their image
subjects and source; this machine verifies amd64 runtime, not arm64 execution.

The existing test Compose service now uses that full-commit image. Graceful stop
exited zero; writer-locked SQLite/config/credential backups and ordinary profile
verification passed with **4351 mappings**, unchanged checked business state and
zero target writes during preflight. Restart completed zero-insert cycles with
4351 mappings and no queued/blocked/attention jobs. Actual cached-page desktop/
mobile viewport checks passed privacy, GET-only requests and no overflow.
Underlying continuous-sync behavior below is unchanged; accounts/rules/window/
volume are preserved. This is current-machine testing, not production migration.

### Observable continuous sync — merged and running in the current test deployment

The user authorized current-machine continuous testing, not production migration
or a new historical scope. PR [#110](https://github.com/GhostFlying/facet/pull/110)
merged at `7fa0cc7a761e29628b4753729bf452d994f30e00` after independent plan/source/
acceptance review, the complete offline baseline and Python 3.12/3.13 plus image
CI. The reviewed [short plan](implementation-plans/observable-continuous-sync.md)
and [acceptance record](reviews/observable-continuous-sync.md) retain exact
candidate and evidence boundaries.

Implemented consumers: lazy cycle-shared target inventory before project-job
claim, proven ownership before allowed source-From SENT/DRAFT classification,
queued fail-closed writes while History stays durable; bounded domain search
with strict local admission; closed operational stage/provider-reason logs;
owner-thread progress during discovery/History/worker pagination and jobs;
graceful between-request stop; Compose restart/log rotation. Necessary source EML
hashes are permitted only in validated local logs/private DB/CLI, not public DTOs.

The official full-commit image is published and anonymously imported; both
architectures have matching-source SPDX/SLSA evidence, and all packaged source
and static files match the qualified source. The non-root Compose service uses
the original volume, accounts and selected window, with rotated logs and graceful
shutdown. Necessary source EML hashes remain private, never public DTO fields.

Normal writer-owned refresh/profile verification passed with locked backups and
unchanged checked business tables; no new OAuth was needed. Within the existing
window, eight source-only searches found no omitted IDs for three exact-sender
samples versus domain/parent queries, including two subdomain samples. This is
finite real-provider evidence, not exhaustive recall. Pre-upgrade inventory found
4325 managed items, two permitted outbound items and no other unmanaged content.

The first ordinary continuous cycle completed in 73.621 seconds: **15 new
insert/readback/mappings, 4340 total confirmed, queue empty, active unknown and
attention zero**. Owner snapshots showed in-cycle counts. Graceful stop exited
zero, a stopped/locked post-write backup passed, and a new process completed a
zero-insert cycle; mappings and total attempt count stayed unchanged. Fresh
read-only target enumeration confirmed all 4340 mapped items plus the same two
permitted outbound items, with no other unmanaged content. The historical assumed-
absent unknown remains an audit fact, not active recovery.

Continuous testing remains running. Next: observe new incremental/user-label work
and finish remaining maintenance, restore and browser acceptance. The role
`last_verified_at` currently reports persisted binding/credential verification,
not every successful profile request; cycle freshness is reported separately.
This diagnostic timestamp refinement is not a new sync blocker. Production
migration, Release and the planned production dogfood gate remain unfinished;
this is not completed Phase 1.

### Configured polling, server-local times and current rules — implementation in progress

The short plan [configured-sync-interval](implementation-plans/configured-sync-interval.md)
now covers the user-requested fix. New configurations default to a 60-second idle
wait; an explicit `--interval` remains an override, and `run --once` validates but
does not wait. During idle time the owner refreshes only local aggregate snapshots
within the existing freshness budget; it does not poll Gmail or advance sync state.
Persisted instants remain UTC, while public Dashboard/aggregate CLI timestamps are
formatted using the sync server's local offset.

The read-only Dashboard now has a fifth `rules` snapshot showing current configured
sender/domain values and action-label text, enabled state, and no message details,
IDs, credentials, or binding addresses. This explicit user-approved exception is
private Dashboard configuration; it is not a write API and is not added to other
public DTOs, logs, or exports. Targeted config/runtime/HTTP/privacy tests passed;
candidate merge, image upgrade and live 60-second observation remain pending.

### Rule-scoped automatic backfill — reviewed local candidate

The current candidate detects newly enabled sender/domain rules during the next
sync cycle and schedules one deterministic, rule-scoped historical epoch from the
project fixed six-month anchor to a fenced processing snapshot. It reuses the
existing preview/start journal, H0/History ordering, discovery, projection worker,
mapping and recovery paths; it does not scan an unfiltered mailbox or widen an
already sealed scope. Rule removal blocks new admission but does not revoke
tracked-thread authorization. No live Gmail write has been performed for this
change.

The implementation plan is [rule-scoped backfill on add](implementation-plans/rule-scoped-backfill-on-add.md).
The real CLI history, wire, and complete-sync subprocess suites assert rule
addition followed by `run --once` creates the scoped operation/epoch and durable
mappings, with restart deduplication. The complete-sync request key is stable
across credential refreshes and rule changes: its saved scope replays unchanged,
while a newly added rule gets an independent automatic scope. The durable
discovery transaction rechecks current BlackList policy after provider metadata
reads; a focused race test covers a blacklist added in that interval. Rules
effective no later than the initial epoch creation are treated as covered by the
initial scope. The full offline suite is 2954 passed, the affected focused suite
is 130 passed, and Ruff/format/diff/repository-safety checks pass. PR #116
merged the rule-scope implementation at
`0e6e93de0da0eae83a89e35e62f8a4a01044d05f`. A follow-up production-wiring
candidate now makes the same domain capability available from
`GoogleGmailServiceFactory`; its focused service-factory, complete-sync, sync,
and transport suite is 72 passed. Sender and domain rule backfill are locally
executable: the production Google Gmail service factory now advertises the
versioned `gmail-from-domain-v1` capability, while unrelated adapters remain
fail-closed. Full offline validation and PR CI for this follow-up remain
pending; real Gmail rule backfill and deployment remain separately authorized
gates.

## Previous qualified delivery

### Automatic five-minute recovery merged; exact live recovery passed

The user replaced the uncommitted per-item preview/grant/one-budget proposal.
Ordinary startup/cycles now automatically requeue pending unknowns at least
five minutes after persisted dispatch, only after successful empty lookup and
valid source/account/generation checks. This accepts residual duplicate risk;
it is not proof of non-insertion. Preserve old unknown facts and ordinary
intent/mapping/restart guards. Replacement unknowns follow the same policy.
PR [#108](https://github.com/GhostFlying/facet/pull/108) merged at
`32b2ce4333f2931ec6fc83d5585307ba886050be` after independent plan/implementation
acceptance and final Python 3.12/3.13 CI plus image build. Full local checks passed;
all eight complete CLI/fresh-process recovery and crash scenarios also passed in
the exact-source non-root image. See [acceptance and live evidence](reviews/automatic-insert-absence.md).

The separately authorized frozen old unknown and three dependent projection
jobs completed through production recovery/worker APIs in 35.08 seconds, without
business SQL correction or new History/backfill. Confirmed mappings are now
**4325; active unknown and attention are both zero**. The original unknown remains
truthful historical evidence with one retained absence decision, not a pending
action. Before/after writer-locked backups, fresh read-only target checks and a
fresh-process production CLI recovery view passed. All prior mappings, rules,
label configuration, selected scope, generations and checkpoint were preserved.
Target contains all 4325 mapped items, two permitted outbound items and no other
unmanaged items. Continuous Compose sync remains stopped.

The existing shipping runtime has no full-target inventory/precondition consumer.
This incremental recovery unit does not claim that gate complete. The exact
authorized live trial requires a fresh full-target read-only precheck and frozen
job selection; unattended/general deployment acceptance still needs a shared
single-cycle target precondition. No per-unknown mailbox scan is introduced.

The trial used qualified local image `facet:automatic-absence-beb71d2`, whose
packaged source matches merged main. Schema v5 migration passed. The official
full-commit image is published and selected by the stopped Compose container;
anonymous import, dual-architecture SBOM/provenance and all 116 packaged source
files passed checks. Independent read-only stopped-state and pre/post backup
acceptance passed. Do not select e165 against migrated state or restore a pre-write DB.
Next product gap: the shared target-precondition consumer, then remaining
maintenance/Dashboard/restore/dogfood gates. This bounded success is not complete
Phase 1 acceptance or authorization for a new scope/perpetual service.

## Historical evidence

### Current-label model installed; bounded live verification passed

PR [#106](https://github.com/GhostFlying/facet/pull/106) is merged at
`e165ac54baa31827ce129466fbaf7122e8f90b8b`. Independent plan/implementation review,
full Python 3.12/3.13 PR and main checks, dual-architecture publication and anonymous
pull passed. The exact-source non-root image passed the complete synthetic CLI
path and restart/fault qualification; source acceptance is recorded in the
[candidate review](reviews/current-label-observations.md).

With subsequent explicit user deployment/run authority, the existing Compose
project now selects that immutable image. Writer-locked pre/post SQLite/config/
credential backups passed. One production `run --once` completed in 68.49 seconds:
one History page, 28 resolved events, 12 inserts/readbacks/confirmed mappings,
zero new attention and zero warnings. Runtime upgraded schema v3 to v4 and
normally completed all eight frozen old-label notifications: **attention 11 to
3, mappings 4309 to 4321**. No manual business SQL repair or old action replay
was used. Prior mappings, account/binding lineage, rules, action-label config,
selected historical scope and stopped generations were preserved.

One old unknown remains protected and was not resent; the three remaining
attention are projection jobs depending on it. There are no queued jobs; one
blocked job and one retry-wait recovery remain, not a fully successful queue.
Subsequent bounded diagnosis found no stored definite-rejection evidence. After
normal writer-owned credential refresh/profile verification, another read-only
recovery check returned zero candidates; attempts, jobs, mappings, tracking,
rules, events and epochs remained unchanged. The initial read-only CLI refusal
was an expired access snapshot, not evidence that interactive OAuth is required.
Empty search does not prove non-insertion. No replacement was authorized or
submitted; scoped risk-preview/retry execution remains unimplemented.
Fresh read-only target enumeration found 4321 mapped items, two permitted
outbound SENT items and zero other unmanaged items. No new label activation or
rule learning occurred, so live AddDomain/reactivation is not claimed. See the
[live receipt](reviews/current-label-live-upgrade.md).

Continuous Compose sync remains stopped; no new historical scope, source
mutation, deletion, unknown resend or perpetual daemon was authorized. Next is
a separately bounded decision for the old unknown, not a blanket queue retry.
Full Phase 1 maintenance/Dashboard/restore/dogfood gates remain unfinished.

### Published recovery installed; historical cleanup and exact restoration passed

PR [#103](https://github.com/GhostFlying/facet/pull/103) is merged at
`42c586ff1456e919a6c97ab3b434c5a18666b835`; required PR checks, main offline
checks and image publication passed. Under the user's subsequent deployment
authorization, the existing Compose project now selects that full-commit image.
Anonymous pull, published digest/local image identity, non-root UID and all
112 packaged source files were verified. Writer-locked SQLite/config/credential
backup preceded the update; accounts, rules, action-label configuration, volume
and selected historical scope were preserved. Continuous sync remains stopped.

One actual production `run --once` completed in **26.37 seconds**: one History
page, 19 resolved events, three new inserts/readbacks/verified mappings, zero
new attention and no warnings. **4309 verified mappings** now exist. The normal
consumer closed 13 proven old resolver events, reducing attention **58 to 45**;
all retained old attention and previous mappings remained unchanged. The old
unknown was checked once, retains unknown/no-attribution and a retry deadline,
and was not resent. No new unknown or duplicate insert attempt was created.
Fresh target classification found 4309 mapped items, two permitted outbound items
and no other unmanaged mail. A post-run writer-locked backup also passed.

Subsequent explicit operator authority allowed exact no-effect completion and
conditional one-time correction of verified historical state. Independent plan,
helper and synthetic acceptance preceded each live DB correction. Backup, writer
lock, frozen selection, durable submission and atomic typed audit/state updates
were verified. First, 24 no-effect event/job pairs were completed (**45 to 21**
attention). Then six eligible message notifications and four identified action
additions were restored to pending/queued (**21 to 11** attention). No business
consumer was replayed: ten queued notifications are not ten copied messages.
**4309 mappings and one unknown remain unchanged**, as do all unselected records,
rules, account/label configuration, scope, thread generations, epoch and cursor.
No Gmail writes occurred in these operator steps.

Remaining eleven attention jobs, not eleven distinct failed emails:

- Eight events refer to one unavailable user-label ID: four additions with lost
  meaning and four removals. The installed image
  still sends unknown-label removals to attention; this is its classification
  gap, not a purely historical artifact. Neither lost additions nor this common
  gap were swept into the conditional one-time correction.
- Three projection jobs depend on the old unknown; its owning projection remains
  blocked. Source still exists and RAM-only raw/RFC checks match the saved intent.
  Both RFC query forms return zero candidates; full target enumeration found all
  4309 mappings, two permitted outbound items and no other unmanaged mail. There
  is no presently identified copy to claim. The unknown predates the earlier
  target cleanup, but inclusion in that deletion is unproven; it was not resent.

Only one effective configured action label is currently present in source.
Local label configuration is unchanged; no source labels were created. No live
AddDomain learning is claimed. See the compact
[new operator/diagnosis receipt](reviews/attention-cleanup-diagnosis.md) and
[deployment receipt](reviews/recovery-live-upgrade.md); the earlier
[engineering acceptance](reviews/automatic-recovery-convergence.md) remains
candidate-bound historical evidence.

Next live step: qualified current-state consumers can process the restored notifications
only within separately applicable live scope; the DB correction itself did not
execute them or broaden Gmail authority. Fix the unnecessary unknown-label-removal
classification using current tags (D12 supersedes lost-intent reconstruction), and define any bounded
unknown repair without guessed ownership or blind retry. No generic recovery
framework is required for the completed historical exceptions. Broader maintenance
CLI, live gap, audit/restore,
Dashboard/browser/deployment and dogfood acceptance remain unfinished; this is not
full Phase 1 acceptance or authorization of an unbounded daemon/unknown resend.

The following sections retain their candidate/time-bounded evidence. Pending
statements are historical; only the current summary above states present status.

### Credential repair merged; same-scope real continuation verified

Complete CLI sync PR #99 is merged at `e504b696913fba12bab5fc69dbe5ff3f838fd5a4`;
its main offline CI and image publication passed. Full Phase 1 is not accepted.
The continuous real container is stopped; no new epoch/rule/window is selected.

The second real bounded batch added 648 verified mappings, **1872 total**, before
token expiry interrupted it. Pre-repair source/target tokens both returned
401 in read-only profile probes; runtime checked expiry only at cycle entry.
At interruption 159 source-read jobs were retryable. One target attempt was
definitely rejected; one directly succeeded but needed readback/mapping completion.
A subsequent unstarted same-thread job was blocked by that pending attempt. The older unknown
is still protected. The failed operator receipt is retained, not resubmitted.

The independently reviewed [request-auth plan](implementation-plans/request-auth-refresh.md)
is merged in PR #100 at `0d885d45b61507b63d4a97a9bc7c608c0909142f`:
structured closed provider reasons,
manager-owned request-time refresh, durable rejected-insert retry, zero-insert
known-readback completion and same-scope restart continuation. Actual CLI external
fakes have passed rejected-insert refresh/new-attempt and known-readback restart
checks. Independent acceptance approved source `1a8eef14937caf8f58bc8035eb964e3b7bcec38f`;
its exact non-root local image passed all 49 complete CLI/request-reason checks.
The final local full suite passed 2837 tests; required PR checks passed on both
Python versions and the image build. Main offline CI and image publication passed; anonymous
registry reads confirmed amd64/arm64 manifests and attestation manifests.
See [the current acceptance receipt](reviews/request-auth-refresh.md).

After a writer-locked private backup, the real installed production CLI completed
`run --once --verify-known-only`: one pending directly attributed insert became
a verified mapping, **1873 total**, with zero inserts/new attempts and unchanged
old unknown, unrelated attention, rules/window, stopped generations and checkpoint.
The linked unstarted dependent is retryable again. Independent read-only checks
of that newly recovered mapping passed MIME/digests, valid Date/internalDate,
thread identity and normal All Mail visibility. Fresh full target classification
found 1873 mapped items, two permitted outbound items and no other unmanaged mail.
The new same-scope ordinary cycle then completed: **1000 new verified mappings,
2873 total**, in 1795.16s, with five History pages / 14 resolved events and zero
repeat discovery. Existing mappings, old unknown, original 58 attention jobs,
rules/window, stopped generations and discovery/epoch identity are unchanged.
No new job problems/warnings or claims remain. Fresh target enumeration found
2873 mapped items, two permitted outbound items and no other unmanaged mail.
Independent read-only sampling of 20 mappings added by this exact cycle passed
MIME/digests, all 20 valid Date/internalDate values, threads and All Mail visibility.
A post-test writer-locked private backup passed. Both roles' saved credential
revisions advanced; no new OAuth or scope was needed. Mid-cycle threshold/401
faults passed offline; this real cycle started with refreshed credentials and
does not claim to have crossed their next expiry.

Next: continue the already selected queue under bounded guards: 1400 historical
jobs and three normal projection jobs remain queued. The old unknown/attention
is still retained, not repaired or treated as successful. Bulk backfill and full
Phase 1 acceptance are incomplete; broader CLI, live gap, audit/restore,
Dashboard/browser/deployment and dogfood gates remain unfinished.
No cleanup, old unknown retry, new scope or permanent service startup is implied.

### Complete CLI sync qualified offline; real historical projection continuing

The production CLI supports setup/role binding, persisted sender rules,
zero-write preview, explicit historical start and `run --once`. It now includes
full-thread projection, durable readback/mapping, restart deduplication and
resumable known-window History-gap recovery through the same production runtime.
Rule eligibility uses processing/scan time; H1 catchup, stable query scope,
current allow removal, stopped generations and unknown-insert guards remain.
The complete `facet sync --once --yes` entry now composes those same operations;
without `--once` it uses the existing foreground loop. It is independently
reviewed and offline/local-image qualified, but its PR integration and real
invocation remain separate gates. Broader maintenance commands remain unfinished.

PRs #93–#98 are merged. Main `c4e3181680910fdc73b700ea617890cfc0b415e0`
passed both Python CI versions and image publication; its anonymous public
manifest includes amd64/arm64 and qualified provenance/SBOM attestations.
The installed continuous container remains stopped; real tests use one-off CLI
processes with the qualified local image and retained production state.
Historical integration evidence is in [history/gap acceptance](reviews/history-gap-recovery.md).

The user explicitly approved the refreshed default six-month window for the same
accounts and sole sender rule. Private writer-locked backups and fresh role/scope/
target checks passed. Actual CLI preview/start replay was identical, created one
historical epoch, preserved the shared checkpoint and made zero target inserts.
The published runtime's first cycle exposed a pre-insert rule-policy mismatch;
no attempts/mappings were added. Root corrected historical/gap admission to use
the selected persisted rule revision, retaining repository validation.

Source candidate `a89f4e83cced6c5d10200ea2d7922d1c159d00d9` passed independent
plan/implementation review, affected/full offline checks and actual CLI historical/
gap tests in its exact non-root local image with external-only fakes. That same
image then ran the real production path on the existing state, with no app-source
overlay, schema migration, rule change or new scope. See the current
[correction and live receipt](reviews/backfill-rule-policy.md).

Real product evidence: discovery completed 43 pages / 4234 candidates. After the
original 215 new copies, a bounded fresh-process continuation added **1000 new
verified mappings, 1224 total**, with zero repeat discovery, no claims on exit,
distinct target IDs and unchanged prior mappings/protected work. The old unknown,
58 attention jobs, rules, selected window and stopped generations remain intact.
Independent read-only sampling of 20 copies newly added by this continuation
passed MIME/digest, valid Date/internalDate, thread mapping and normal All Mail
checks. Fresh target enumeration found 1224 mapped items, two permitted outbound
SENT items and zero other unmanaged items; a writer-locked private backup passed.
See [bounded continuation evidence](reviews/historical-continuation.md).

The original cycle's three temporary source read deferrals and its corrected
stop receipt are retained, not overwritten. Independently reviewed continuation
guards distinguish safely completed source reads from insert uncertainty while
preserving all original protected states. The first continuation took 1758.43s
for 1000 copies; **3049 historical message jobs plus one normal History job remain
queued** at that receipt. The second batch later stopped at 1872 total as recorded
above. The copy path is serial; this throughput is implementation
behavior, not a Gmail limit or product latency promise. Bulk backfill is not yet
complete.

Complete-entry candidate `c7d95d1390eefc079d2e8fcc26dd6b8f110ebcb9` passed
independent plan/implementation acceptance. The preceding source passed the full
2801-case offline suite; the final text-only confirmation correction passed its
affected tests. Its exact non-root local image passed all 17 complete CLI cases,
with external-only Gmail/OAuth fakes and no application overlay or seeded state.
See [complete-entry acceptance](reviews/complete-sync-entry.md).

Next: drain the already selected real queue under bounded continuation guards;
integrate the qualified complete-entry candidate through required PR CI. No
unknown retry, cleanup, new scope or continuous live startup is inferred. Domain
discovery remains fail-closed pending candidate-query evidence; broader CLI,
live gap recovery, full target audit, backup/restore, Dashboard/browser/deployment
and dogfood gates remain unfinished. Sampled Gmail API checks are not exhaustive
or browser/UI acceptance; a stopped container does not establish Dashboard health.

The sections below retain their original candidate/time-bounded evidence;
their historical pending gates are superseded only by the current summary above.

### Granular historical backfill repair (qualified local candidate)

Production source candidate `e391e982f9e2065aebc7d2f087d04829c920fe34` fixes
preview with existing tracked generations and supports a fresh explicitly started
historical expansion after initial History is established. It reuses sealed rules,
the shared cursor and normal projection/recovery, without resetting mappings or
reopening old unknown/attention. New allows cannot widen an existing scope; current
BlackList and stopped generations still apply. An expansion completes only after
History covers its fence and linked work is terminal; unknown remains pending.

Independent plan/implementation reviews passed. Full offline checks passed
(2760 tests, 595.74 seconds), and the exact pinned, non-root local image passed
four production CLI/SDK cases: historical copying/restart dedup, old unknown
preservation, failed-page continuation and a new uncertain insert without resend.
Only external Gmail/OAuth interactions were synthetic. See the
[repair plan](implementation-plans/granular-historical-backfill.md) and
[acceptance receipt](reviews/granular-historical-backfill.md).

The same image also ran standalone preview/replay/status against the real
configuration/state with external networking disabled. Preview now succeeds;
protected business tables are unchanged, nine mappings remain, and there are
zero new insert attempts/epochs. No real historical copy, unknown retry, service
resume or deployment occurred. The real service remains stopped. PR CI/main
integration, authorized nonempty Gmail historical backfill, the composed `sync`
entry and final Phase 1 gates remain separate. Earlier receipts below describe
their original candidates, not the current repaired preview behavior.

### External-agent outbound contract correction (documentation only)

The 2026-10-07 user decision replaces the sole-mailbox-writer/read-only-agent
assumption. The dedicated target may contain authorized external-agent sent
mail/drafts using the bound source as From; replies go directly to source.
These are not sync errors, projection successes or automatically claimable
unknown-insert copies. Facet remains insert-only; DB/process single-writer,
credential ownership and normal scopes are unchanged. Sending credentials,
send-as and reply routing belong to the external agent/Gmail integration.
Recipient-derived rule discovery is deferred beyond Phase 1; source replies
still require normal rules or existing tracked-thread authorization.

Canonical contracts and acceptance requirements now reflect this boundary.
Current setup remains profile-only: target content classification, its full
audit integration and recovery exclusion are still open runtime/acceptance
requirements, not implemented or Gmail-verified by this docs-only change.
No Gmail operation, state migration, deployment or service resume occurred;
the transport candidate and its existing offline evidence remain unchanged.
Independent plan and exact-candidate documentation reviews passed; see the
[bounded plan](implementation-plans/target-agent-outbound.md) and
[review receipt](reviews/target-agent-outbound.md). Main integration and CI are
separate gates, not implied by this documentation approval.

### Complete sync entry decision and granular test

On 2026-10-07 the user requested a complete CLI sync entry implemented entirely
through the granular commands' shared operations, with no mandatory manual
preview/start sequence. The proposed spelling `facet sync [--once]` is planned,
not implemented. An intentional sync selects current enabled rules/default fixed
six-month window; internal scoped preview/start and stable operation keys retain
all account, scope, H0/gap, stopped-generation and unknown-insert guards. Ordinary
setup/preview/run/restart and prospective rule/action learning do not expand
history. The current image/Compose entrypoint is unchanged; current testing uses
granular commands. See [bounded documentation plan](implementation-plans/sync-command-composition.md)
and [independent acceptance](reviews/sync-command-composition.md), plus the D10
decision in the execution plan. Documentation approval is not implementation.

Read-only diagnosis explains the nine live copies below: all nine mappings came
from three `future_rule` threads. The existing initial epoch was created before
the sender rule and sealed **zero rules**; its completed discovery does not cover
that later sender's old threads. Thus incremental projection is Gmail-verified,
but nonempty sender-history backfill is **not** verified or complete.

Granular checks used the unchanged non-root image and real configuration/state
with external networking disabled. `backfill preview` returned `preview_invalid`:
the CLI hardcodes invalidation revision zero, whereas the store checks current
tracked-thread generations. No preview success/replay is claimed. `backfill status`
succeeded offline, showing nine confirmed mappings, 58 attention jobs, one
blocked projection job and one queued recovery job, with the old epoch draining.
Bindings/rules/epochs/partitions/threads/events/cursor/jobs/attempts/mappings were
identical before/after; no new insert or epoch, source mutation or service resume.

Next product gap: correct granular preview's current-state guard and connect
explicit historical-expansion preview/start/runtime using a new epoch. Current
start rejects a second initial epoch. Reuse the existing rule-query, H0/History,
worker and mapping paths; do not clear discovery/DB/cursor or reopen old unknown
and attention. Complete-entry orchestration uses that same path afterward.
Engineering needs bounded plan/independent review and local-image evidence;
real historical copying still requires concrete rule/window authorization.

### Bounded live Gmail projection trial

On 2026-10-07 the user explicitly authorized one production `run --once` and
a fresh-process continuation check for the existing bindings and one enabled
sender rule. The unchanged reviewed candidate `3df74f3` ran in its exact
non-root local image, with normal production Google SDK/runtime, real state
and this host's private proxy override; no fake or application overlay was used.
A stopped, writer-locked private backup used SQLite's backup API for both state
journals and included config/credentials before either CLI process started.
Existing role credentials had been refreshed normally; profiles matched bindings
and account/scope/rule/epoch configuration remained unchanged throughout.

The first process finished in 30.33 seconds: two History pages, 22 resolved
events, **nine confirmed inserts and nine durable mappings**, zero new attention.
The fresh process finished in 4.62 seconds: one History page, zero resolved
events and **zero new insert attempts or mappings**. Read-only verification
compared all nine source/target MIME digests and mapped IDs/thread assignments;
three source threads map to three target threads. All nine valid Date headers
match target internal dates, with zero fallbacks; copies have normal All Mail
visibility without Inbox/Spam/Trash/draft labels. Target metadata now classifies
nine mapped copies, the original two permitted source-From SENT items, zero
drafts and zero other unmanaged items. This local inspection does not implement
the still-open production outbound classifier/audit/recovery exclusion gate.
The user subsequently inspected the copies and reported no apparent issue; this
is bounded visual confirmation, not exhaustive attachment/UI or Phase 1 acceptance.

The old unknown insert and all 58 historic attention jobs are unchanged. Its
read-only RFC-ID search still found zero candidates, which is not proof of no
historic insert or permission to resend. No old recovery retry, source mutation,
cleanup, rule/scope expansion, epoch restart or long-running service resume
occurred. The CLI receipt's `discovered: 4700` is the completed partition's
historical observed-item count, **not 4,700 newly scanned or selected messages**;
comparison with the backup confirms zero new initial-discovery items. The
receipt's cumulative/delta naming remains an observability limitation.

Remaining gates: qualified main integration/publication, full maintenance CLI
(including missing `auth status` dispatch), action-label live acceptance (only
one of three configured labels was present), production outbound classification,
authorized old-unknown recovery, Gmail UI checks, broader failure/backup/restore
and deployment acceptance, and 72-hour dogfood. The service remains stopped.
This proves bounded real projection and restart deduplication, not whole Phase 1
acceptance or an all-healthy historic queue. Next: resolve the granular historical
backfill gaps above and integrate the qualified engineering stack; any new bulk
copying, continuous live run or recovery action needs its own
scope/authorization. See [trial evidence](reviews/sync-single-dispatch-transport.md#bounded-authorized-live-gmail-trial-2026-10-07).

### Sync transport and source-missing repair (offline candidate)

Candidate `3df74f31bb8a4a7d65ce5eae1d3294e7fb0867b6` replaces normal sync's
httplib2 networking with access-only Requests: no automatic retries, redirects
or credential refresh/replay. Actual production CLI subprocesses, normal Google
SDK and real loopback TCP passed setup/binding, preview/start, new-rule History
admission, full-thread insert/readback/mapping and restart deduplication. Accepted
POST response loss, 503 and 307/308 remain durable unknown with no restart resend.
Metadata 404 now becomes precise durable `source_missing`, not generic attention;
existing terminal attention/unknown work is not automatically replayed.
Independent plan and exact-candidate implementation reviews passed. The exact
non-root local image passed the same five CLI cases with external networking
disabled and isolated synthetic state; the factory/runtime were not replaced.
Complete offline checks passed. GitHub CI/integration are tracked separately;
main merge/publication, real Gmail and live upgrade are not claimed. This focused
repair depends on the preceding History candidate, not yet on main. Real sync
stays stopped and its existing unknown attempt remains unchanged. Next: qualified
integration and controlled live validation using this host's local network configuration. See
[review receipt](reviews/sync-single-dispatch-transport.md).

User-requested local revalidation on 2026-10-07 passed all five real CLI/SDK/TCP
cases again in the exact non-root image (66.93 seconds), with no external network
or real-state mount. Normal History admission projected two non-draft messages,
read them back and durably mapped them; a new process inserted no duplicates.
Response loss, 503, 307 and 308 retained unknown recovery with no restart resend.
Initial preview/start was empty in this fixture; this is not evidence of nonempty
six-month backfill or live Gmail/API/UI acceptance.

Unauthenticated HTTPS probes from an isolated one-off container on the existing
Compose bridge failed on direct Google connections. Passing the host's existing
proxy environment made Gmail/OAuth/Accounts HTTPS endpoints reachable in
0.44–0.63 seconds (404/404/302 at public roots; connectivity, not API authorization).
The user clarified that proxy wiring is deployment-environment configuration, not
a Facet feature or project acceptance gate. A private override outside the
repository now passes existing host proxy variables to sync/setup; resolved Compose
configuration and no-credential HTTPS probes passed (0.43–0.65 seconds). No proxy
values were saved in the override or public evidence. Repository Compose,
Dockerfile and image remain unchanged; this local override must be included in
subsequent authorized operations. Real sync stays stopped; no mailbox credential,
real state, OAuth exchange, recovery retry or Gmail write was used. The local
connectivity configuration is ready; qualified integration and controlled live
validation remain open, not blocked on a project proxy implementation.

### History current-rule admission (offline candidate)

Candidate `a3cd969e6529336fe60676dc8d8887e39a06e553` repairs new untracked
message admission through current sender/domain rules, full-thread expansion,
ordinary no-match consumption and durable retry. Stopped threads stay stopped;
active threads retain authorization while drafts are excluded. The production
CLI subprocess path passed empty preview/start, a later CLI rule addition,
History admission, two-message insert/readback/mapping and restart without
another metadata read or insert. No DB readiness/binding/rule/epoch bypass was
used. Provider Retry-After scheduling is covered by a regression test.
Independent plan and exact-candidate implementation reviews passed. The exact
non-root local image passed the same CLI path with external networking disabled
and isolated synthetic state. Complete offline checks passed; CI/merge and live
upgrade are not claimed. Source metadata disappearance is corrected in the
transport candidate above, without reopening old attention. Real sync remains
stopped and the existing unknown insert is unchanged. See the
[bounded review and replay research](reviews/history-incremental-admission.md).

### Explicit target cleanup (controlled live cleanup complete)

The user approved an independent `target-cleanup` CLI maintenance exception and
ephemeral full Gmail consent, not automatic sync deletion. The local commands
now provide fixed-ID preview, offline status and explicitly confirmed execution;
normal sync credentials/business rows remain separate. Independent plan review
passed; real CLI subprocesses have passed synthetic init/binding, preview,
execution, response-loss/restart, wrong-account and writer-exclusion checks.
Candidate `864670323790e4000327cd724a7d0b90267c6694` has independent implementation
approval, complete offline checks and non-root local Compose-image acceptance.
Production CLI commands in an isolated synthetic volume completed init/binding,
preview, explicit deletion with injected response loss, restarted recovery and
completed replay with no new HTTP calls. Fixed IDs only were removed; later
arrivals survived and normal credentials/business state remained unchanged.
Real requests/urllib3 wire tests separately prove one destructive dispatch on
response loss and same-ID GET on recovery. On 2026-10-07 the user separately
approved the actual fixed preview, then completed ephemeral target-only full
Gmail consent. The qualified local image permanently removed all 134 approved
messages: the durable receipt is completed, remaining and unknown deletions are
zero. A subsequent read-only account-verified check found zero messages
(including Spam/Trash), zero drafts and no remaining list pages. No new arrivals
were added to the manifest. A fresh private metadata/credentials/journal backup
passed SQLite integrity checks before execution; it cannot restore deleted mail.
Comparison against that backup confirmed unchanged normal credentials, config
and business rows except writer-owner lineage. Zero mappings and the existing
one unknown insert remain; no source mutation, persistent full-scope token, DB
reset, insert retry or sync restart occurred. CI/merge/publication and a
live-service upgrade are not claimed. See [runbook](target-cleanup.md) and
[review receipt](reviews/target-cleanup-cli.md). The live sync gaps below remain.

### Historical pre-trial live gate and insert adapter correction

The following records the earlier blockers; the bounded live trial above is
the current projection result and supersedes its zero-mapping/live-gap status.

The recent local build/Compose acceptance is not yet a working live projection.
The real state was backed up with SQLite's backup API plus private config and
credentials while the service was stopped. Existing action-label configuration
was preserved. A bounded production `run --once` refreshed credentials and
consumed History but confirmed zero mappings; one existing unknown insert
remains in recovery and was not retried. Read-only recovery search found no
candidate, which is not proof authorizing another insert.

Earlier read-only target inspection found unexpected/unmanaged content,
including a draft at that time, while the DB had no mappings. The separately
authorized explicit cleanup above resolved that observed target prerequisite;
the follow-up check found an empty mailbox. This is a point-in-time observation,
not permission to delete future arrivals or waive subsequent startup checks.
Normal sync remains stopped for the insert/recovery and admission gaps below.
Existing attention events have not been automatically replayed. New untracked
message admission is repaired in the offline candidate above; that is not yet a
live-service or all-success claim.

The concrete insert blocker was reproduced offline with the locked real Google
client: `neverMarkSpam` is not supported by `messages.insert`, so request
construction raises before HTTP. The bounded fix removes that keyword and adds
real-discovery tests with only HTTP substituted, including Date policy, thread
anchor, exact raw bytes and single-attempt provider failures. Four new cases
failed on the old adapter; 90 focused adapter/worker/CLI cases pass after the
fix. Independent implementation review approved exact candidate
`1b09b8f629d00e7ba7573e311ff6c764664d76fe`; see the
[bounded review record](reviews/gmail-insert-discovery-compatibility.md).
The unchanged Dockerfile built on sgbox and the resulting non-root local image
passed actual-client request construction with networking disabled. On an
isolated synthetic Compose volume, production CLI subprocesses completed init,
fake authorization/binding, sender rule, preview, explicit start, insert/readback
and durable mapping; a second process confirmed the mapping without another
insert. No readiness, rule, binding or epoch was seeded directly into the DB.
The shared-fake alignment follow-up at
`9d2d6ef1b799c10c864eab461cb27957538255e0` was independently approved and
passed the complete offline suite: 2653 tests. Repository Ruff/format, locked
environment sync, CLI help and safety checks passed. Production source and
image build inputs did not change in that follow-up, so the prior local image
evidence remains valid. No CI/merge/publication, real-service upgrade or
successful live projection is claimed.
Container Google connectivity also needs an environment-specific solution;
temporary host-network/IPv6 resolution overrides proved the bounded live CLI
path, not a generally usable Compose network or public Dashboard deployment.

Next live gate: the dedicated-target prerequisite was checked after approved
cleanup; the existing unknown attempt stays in recovery until an authorized,
evidence-based recovery action is available. Cleanup review additionally reproduced a concrete
httplib2 automatic wire resend despite Google `num_retries=0`. Normal sync's
corresponding transport risk is now corrected and wire-tested in the offline
candidate above, not yet deployed. Current-rule incremental admission is also
an offline candidate; a usable container Google network path, qualified
integration and authorized live/recovery evidence are still needed.

The package ledger below retains historical package evidence; it is not the
current executable-command checklist. The current live result and next gaps
are stated above.

| Unit | Status | Evidence / remaining gate |
| --- | --- | --- |
| Phase 0 Gmail spike | Complete within its scope | See [redacted results](phase-0-gmail-spike-results.md); production behavior not implied |
| Repository bootstrap | Complete | Public `main` published with account noreply identity; Python 3.11/3.12 offline CI passed |
| Phase 1 execution planning | User G0 approved; plan integrated | Exact approved/merged `caba7c7`; independent review/QA and candidate/main CI passed; not milestone completion |
| P1-00 execution baseline | Integrated | PR #6 exact `2618eaf`; independent plan/implementation review, candidate/main CI passed |
| P1-01 core/writer ADRs | Reviewed and integrated design freeze | PR #8 exact `09031e7`; core-v1/writer-v1, independent review and candidate/main CI passed; no runtime/G1 claim |
| P1-02 test foundations | Reviewed and integrated, including mandatory CT | PR #12 exact `1b7cd58`; independent review, candidate/main CI and 92 core-compatibility cases passed; Issue #5 closed, later feature-consumer tests remain |
| M1-01 package/config/CLI foundation | Reviewed and integrated | PR #11 exact `b1e4ae0`; 287 offline tests, independent whole/closure reviews, 3.12/3.13 candidate/main CI and installed-wheel checks passed; not complete init/CLI/G1 |
| M1-02 persistence | Finite SQL/DB21/action library and combined input accepted, unmerged; whole gate open | Corrected `c0bb4b0` and normal carry `a9c4e36` independently accepted with fresh exact CI; combined 1625 full tests and wheel passed; PR #15 remains Draft/open/unmerged, historical `62d75c0`/`2466834` HOLDs retained; actual provider/RV11, released migration source, restore and whole DB-01..28 remain |
| M1-03 writer/runtime/CLI | Bounded writer foundation and corrected Thread harness integrated; production sync owner open | PR #20 exact `ea80db2` and PR #22 exact `befe278` actually merged after nonauthor review and candidate/main dual-Python CI; corrected harness retains production OS bytes, 150 focused/758 full tests; no-state bootstrap source separately released, not accepted provider/actor/credential integration |
| M1-04 OAuth/binding | Early pure values/codec/client parser integrated; full package open | PR #18 actually merged exact `ff77e63`; 120 OP/608 full tests, independent source/head review, wheel and candidate/main 3.12/3.13 CI passed; actual OAuth/profile/files/publication remain |
| M1-05 public status/privacy | Early pure/logging library integrated; full consumer gate open | PR #16 actually merged exact `f209fbe`, independent review and candidate/main CI passed with 488 offline tests; actual DB/auth/runtime/HTTP/DOM/Compose consumers still pending |
| M1-06 authentication/initialization | Metadata/rule admission implemented; live Gmail gate open | User decision on 2026-10-05 formally removed source-path attestation and Facet-side sender-authentication from automatic admission. DKIM/DNS provider and evidence seam were deleted; source candidates now use Gmail metadata, account binding, visibility/draft checks and exact rules. Legacy `rules.authenticity: require_trusted_auth` is read-only compatibility and omitted on write; persisted `auth-v1` remains a stable rule token. Focused and full offline tests are the current evidence; no live Gmail operation has been performed. |
| M1 foundation as a whole | Incomplete | `facet init`, production OAuth/profile ownership, and the non-fake `run --once`/`backfill start` dispatch seams remain. Source-path attestation is no longer a product gate; full maintenance CLI, controlled live Gmail verification and G1 remain open |
| M2 automated projection core | Foreground synthetic vertical integrated | PR #45 merged at `0a928369c8a1ee4f0684f7e4605899fec42af021`; fixed-window discovery, H0→History pagination, typed candidate/admission bridge, action-label effects, serial projection/readback, pre-dispatch recovery, and durable attention/retry convergence are offline-tested. This does not claim CLI/OAuth, live Gmail, Dashboard, Compose, Actions or Phase 1 completion |
| M3 continuous recovery and Dashboard alpha | Foreground aggregate and action-label consumers integrated; recovery remains open | PR #55 and PR #57 merged at main `5b6097f`; one-process `facet run` publishes aggregate snapshots, gates Gmail on verified bindings plus explicit backfill start, and composes readonly action-label effects; no live-account claim |
| M4 complete maintenance CLI and advanced rule maintenance | Recovery inspection candidate reviewed; CI pending | `facet recovery list/show/check` now inspect aggregate or private unknown-insert evidence without insert/retry/SQLite mutation; queue/review mutation, recovery preview/retry/repair, BlackList competition, offline backup/restore and optional label cleanup remain open |
| M5 self-hosted delivery | Immutable image workflow integrated and first image published | Main `1a42938`; PR multi-arch no-publish build and main publish passed; public GHCR SHA tag, digest, anonymous pull, amd64/arm64 manifest and UID 10001 smoke verified; host deployment/Nginx remain open |
| M6 real deployment and v0.1 | Not implemented | Backup/restore, live Gmail, selected host and 72-hour evidence |

## Current product-first handoff (2026-10-09)

The configured polling and Dashboard rules unit is merged in PR [#114](https://github.com/GhostFlying/facet/pull/114)
at main `86091918f286de75507b898d1a9dbb2d720eab27`. Candidate `cdc09a7` passed
independent implementation review, 2949/2949 offline tests, Ruff/format/safety,
and exact-head Python 3.12/3.13 plus PR image CI. Main published the immutable
image `ghcr.io/ghostflying/facet:86091918f286de75507b898d1a9dbb2d720eab27`;
the verified amd64 manifest digest is
`sha256:6c1a742e7c5990f206484d4a27a9e98c45146d6981974484dac19fd09c65728d`.

The unit adds a 60-second default for new configurations, explicit interval
validation for production and fake `run --once`, local-only aggregate heartbeat
refresh during idle time, server-local operational timestamp formatting, and a
read-only fifth Dashboard `rules` snapshot. The rules snapshot shows the current
sender/domain values and action-label text only under the explicitly approved
private Dashboard exception; it does not add message details, IDs, credentials,
binding addresses, or rule values to other DTOs/logs/exports. Rules have a
separate 2 MiB serialized bound sufficient for the 1024-entry/512-byte model
limit; other public envelopes retain their existing limit. UTC instants remain
the persistence and ordering representation.

The current test deployment was stopped, backed up and refreshed with that
immutable image. The locked preflight reported unchanged business state, 4364
confirmed mappings and zero target writes. The resumed same account/rule/window
reached 4365 confirmed mappings, zero nonterminal/failed jobs and no issue
groups. A private Compose override supplied `--interval 60` while leaving the
managed configuration's explicit 30-second value and artifact guard unchanged.
Two idle-cycle observations began about 68.6 and 71.5 seconds apart, proving
the configured idle wait plus cycle time; heartbeat timestamps advanced without
changing `last_poll_at`. The test process uses `TZ=Asia/Shanghai`, and local plus
direct Tailscale Serve checks show `+08:00` server-local times and the eight
current rules. The ordinary HTTPS proxy returns 530 for the tailnet hostname;
direct tailnet access works and the Serve mapping itself was not changed.

This unit is merged and live-tested, not a claim that the complete Phase 1 or
production migration is done. Browser Playwright acceptance was not rerun on
this machine because a compatible Chromium/Playwright pair is unavailable;
synthetic browser coverage and packaged static/HTTP checks remain in CI.

Both `facet` and the isolated `facet_spike` are now packaged for Python 3.12+.
Production imports/CLI never adopt spike cursors/tokens. The foundation tests cover
closed types, strict YAML, no-follow private reads and real CLI subprocess
JSON/exit/privacy/zero-effect behavior, alongside all existing spike tests. They
do not verify a production sync process, trusted admission, backfill, History ingestion or rendered Dashboard.

The integrated M1-05 early library adds independent allowlisted public models, a closed
error catalogue/serializer and fail-closed structured logging. It does not expose
HTTP or read actual DB/auth/runtime state. Real snapshots and raw third-party
OAuth/provider logger consumers, browser/DOM and Compose remain later gates;
Issue #14 stays open. M1-04's current pure slice contains closed credential value
models, an in-memory byte envelope codec and a strict Desktop-client parser. It
does not open private files, create capabilities, invoke OAuth/Gmail, fetch profiles,
refresh or publish credentials, or make a production binding ready. Issue #17 stays
open. PR #18's actual integration and successful main CI are recorded below.

The user's latest model policy on 2026-10-02 permits only Sol high/xhigh or Luna
for prospective tasks. Complex design and high-risk independent review use Sol
xhigh; Astra receives no new work or reactivation. Earlier authorized reviews
retain their actual model/reviewer/SHA attribution. G1-G6 remain incomplete.

本次交付顺序已按用户 2026-10-03 的纠偏决定更新：第一条产品能力是自动
discovery、固定六个月 backfill、History 全分页/cursor/事件去重、readonly action-label
规则更新和可恢复投影；不以手动选择 thread 或 one-shot 复制为入口。产品没有同步延迟
承诺。支持运行模型是官方 Docker image 内一个前台 sync/writer 进程；runtime/native/
read-bootstrap 证明、独立 daemon/IPC/request receipt、跨 thread 并发四路、实时优先、
公平调度和复杂 raw budget 不再是第一交付或 milestone gate。它们不代表已删除的代码，
而是从当前关键路径移除的工程方案。

## Latest product-first handoff (2026-10-05)

The user formally deleted source-path attestation and sender-authentication as a
Facet automatic-admission requirement. Gmail remains responsible for SMTP
authentication and mailbox classification; Facet does not claim sender or
content safety. The current candidate uses metadata/rule admission, keeps raw
mail only for target projection, and retains all account, scope, privacy,
single-writer, durable-ordering and unknown-insert recovery defenses. Historical
DKIM/attestation notes below are retained as evidence of prior candidates, not
as active gates.

- The former PR #71 DKIM/source-attestation implementation is superseded and
  removed. Its historical evidence is not a current product gate. The active
  candidate's next product-bearing delivery is the complete CLI vertical path
  with fake Gmail/OAuth transport, followed by a separately authorized
  controlled Gmail run.

- Historical PR #73 (`8c241c8d62c92426815664a9957cdfadbd2bec36`) proved the
  earlier signed-fake CLI path. Its DKIM/provider-specific admission behavior
  is superseded by the 2026-10-05 decision and is not a current gate. The
  durable CLI evidence (init, role authorization, sender rule, write-free
  preview, explicit start, discovery, insert/readback, mapping and restart
  continuation) remains valid and is re-tested by the metadata-only candidate.

- Candidate `aa646bb` adds `facet recovery list/show/check`.
  It creates an unknown insert only through the production insert-intent path in
  the synthetic command test, then searches and reads back target evidence
  without a second insert or SQLite mutation. Duplicate, missing and changed
  evidence stay attention. Independent implementation review is approved; the
  focused 61-test set and all 2546 non-flaky tests pass, while one existing
  full-process FD-snapshot test remains environment-flaky (isolated rerun and
  its file pass). Full candidate CI, recovery retry/repair and live Gmail are
  not claimed.

- The next product-shaped candidate composes the existing foreground sync owner
  and aggregate Dashboard in one supported process. `facet run` without
  `--once` validates managed configuration, retains one SQLite writer owner,
  runs the existing foreground cycle, and publishes only allowlisted in-memory
  snapshots to the fixed read-only HTTP routes. `Dockerfile` and Compose now
  use this foreground entrypoint with the persistent `/var/lib/facet` state
  volume; `facet run --once` and `facet web` remain separate commands.
- The candidate handles listener startup failure and SIGINT/SIGTERM with owner
  cleanup. Snapshot freshness uses a monotonic clock; failed collection
  invalidates readiness, and unknown discovery totals/rates remain null. The
  Dashboard reports lifetime confirmed mappings separately from current-epoch
  discovery and surfaces durable discovered/completed thread-job counts and
  partition-level attention without exposing message details, rules, addresses,
  IDs, or provider payloads. Scanned-thread count remains explicitly unknown
  when the DB has no safe aggregate for rejected candidates.
- The candidate now gates every provider cycle on DB-only verified bindings and
  an active, explicitly-started epoch. Before that gate passes, it publishes a
  blocked/unknown aggregate snapshot and does not construct or call Gmail.
- PR #55 is integrated at main `e2b9b1727cbbe2743d1b887e9ec3d2250bc61431`.
  Independent implementation review approved the corrected exact candidate
  `bbddd4c`; the final offline suite passed 2516 tests, focused evidence passed
  52 tests, and candidate Python 3.12/3.13 plus no-publish image CI passed.
  This proves the supported one-process composition and aggregate Dashboard,
  not live Gmail projection, action-label
  production wiring, or Phase 1 completion.
- The next product-critical delivery is production action-label consumer wiring
  plus the remaining recovery boundaries. A real
  Gmail run still requires explicit live-account/test-scope authorization; no
  such operation was performed by PR #55.
- PR #57 is integrated at main `5b6097f3f0a6e0ab2a0bf55157a9e9f7518bf5a8`.
  The historical all-three-label precondition is superseded by the approved
  partial-map correction now under local validation: any nonempty configured
  subset composes the existing durable `ActionEffectConsumer`, while missing
  categories remain unmapped and their events stay explicit attention. All
  labels absent still leaves ordinary sync running without an action consumer;
  duplicate labels and malformed/provider failures remain typed failures. This
  correction has not yet been merged or live-verified, so the prior candidate
  evidence remains historical and does not prove a Gmail action event.

- The offline maintenance CLI unit is integrated in PR #59 at main merge
  `2033be505e36217da7dbaf2b547caeef5819260b` (implementation candidate
  `c4779ac39d6e56bc5214abd3c8aba33bb077847`; plan:
  `implementation-plans/m1-status-doctor-cli.md`). `facet status --json` and
  `facet doctor --json` read the managed SQLite WAL through one deferred,
  read-only transaction without taking the writer lease or constructing
  Gmail/OAuth clients. They reuse the four aggregate Dashboard DTOs, report
  offline snapshots as stale/unknown rather than fabricating live health,
  retain typed doctor findings with catalogue exit codes, and privately check
  both declared/verified role addresses plus projection binding consistency.
  Nine focused subprocess tests pass; the complete local offline suite passes
  2528 tests, with Ruff, format, safety, wheel smoke, and candidate/main CI
  passed. SQLite's normal `-wal`/`-shm` coordination sidecars may appear on a
  read snapshot; no business rows, config, credentials or mail content are
  written. This closes only the offline status/doctor unit, not the complete
  CLI, live Gmail, recovery, deployment or Phase 1
  gates.

- The exact domain-rule mutation is integrated in PR #61 at main merge
  `6a2a5d7` (implementation candidate `7c7ae20`; plan:
  `implementation-plans/m1-cli-domain-rule.md`). `facet rules add-domain`
  reuses the existing single-writer ruleset publication and request replay
  path, applies the existing PSL/IDNA/public-suffix policy, and refuses new
  mutations while bindings are pending. The candidate passed 43 CLI bootstrap
  tests, 105 related rule/admission/action tests, 2530 full offline tests,
  Ruff/format/safety, wheel import/help smoke, independent implementation
  review, and Python 3.12/3.13 plus no-publish image CI. This adds maintenance
  rule control only; it does not resolve live Gmail, recovery, or final Phase 1
  gates.

- The explainable backfill-preview unit is integrated in PR #63 at main merge
  `440b0de` (implementation candidate `3d62c21`; plan:
  `implementation-plans/m2-cli-preview-explainability.md`). Preview JSON now
  reconstructs its persisted fixed window, discovery cutoff, ruleset revision,
  explicit-start requirement, thread-wide disclosure semantics, and
  `target_writes: 0`; replay returns the same scope. The candidate passed 52
  CLI/status tests, 46 backfill/epoch/sync tests, 2530 full offline tests,
  Ruff/format/safety, wheel help smoke, independent review, and Python
  3.12/3.13 plus no-publish image CI. This closes preview explainability only;
  it does not resolve live Gmail, recovery, deployment, or final Phase 1 gates.

- The aggregate maintenance-view unit is integrated in PR #65 at main merge
  `535e096` (implementation candidate `4835a42`; plan:
  `implementation-plans/m4-cli-aggregate-views.md`). `facet backfill status
  --json`, `facet queue list --json`, and `facet review list --json` reuse the
  existing offline, read-only status snapshot and expose only progress, queue
  counts/oldest runnable age, or categorized issue groups. Guarded subprocess
  tests confirm no Gmail/OAuth import or network access, no writer lease or
  mutation, and no account/path/message details in output. The candidate passed
  61 CLI tests, 2531 full offline tests, Ruff/format/safety, independent
  implementation review, and Python 3.12/3.13 plus no-publish image CI. Item
  inspection, retry/approval, recovery, and repair commands remain open; this
  is not complete maintenance CLI or a Phase 1 gate.

- The persisted-rule inspection unit is integrated in PR #67 at main merge
  `21c17d7` (implementation candidate `5613113`; plan:
  `implementation-plans/m1-cli-rule-views.md`). `facet rules list --json`
  reports only the sealed current ruleset revision and rule count. `facet rules
  show --rule-id <id> --private-metadata --json` reads one current rule's
  private value, revision, effective time, origin, and policy metadata; public
  show is rejected and missing/foreign selectors do not disclose existence.
  The read path is offline and SQLite read-only, with no Gmail/OAuth import or
  writer lease. The candidate passed 62 CLI tests, independent implementation
  review, Python 3.12/3.13 CI, and no-publish image build. Rule deletion,
  blacklist mutation, and item-level review/recovery operations remain open.

- The read-only queue-item inspection unit is integrated in PR #69 at main
  merge `4a23c06` (final implementation candidate `4b5adaa`; plan:
  `implementation-plans/m4-cli-queue-show.md`). `facet queue show --job-id
  <id> --private-metadata --json` returns only typed job/source-thread IDs,
  kind/state/priority, attempts, error code, and timestamps from the configured
  projection's SQLite snapshot. Malformed selectors return `invalid_input`,
  well-formed public selectors return `scope_required`, and absent/foreign
  selectors return `owner_unavailable` without existence disclosure. The
  candidate passed 63 CLI tests, a focused precedence fix review, Python
  3.12/3.13 CI, and no-publish image build. Queue retry/claim/cancel/recovery
  remains unimplemented; this is not complete maintenance CLI or a Phase 1
  gate.

- The bounded Dashboard/Compose HTTP unit is integrated on main `e2b9b17`
  after independent plan approval. `facet web` serves only the
  allowlisted aggregate routes (`/api/v1/status`, `/api/v1/progress`,
  `/api/v1/issues`, `/api/v1/diagnostics`, `/healthz`, `/readyz`) through a
  silent fixed-output HTTP handler. Until a runtime collector publishes a
  snapshot, every aggregate response is explicitly `unavailable`/`unknown`;
  GET does not call Gmail, DB, or provider I/O. The bundled page contains only
  aggregate fields. Compose runs one non-root UID 10001 web process on
  container `0.0.0.0:8080`, published only to host loopback, with a persistent
  `/var/lib/facet` volume and read-only root filesystem. Seven focused web/
  subprocess tests pass; full offline suite is 2508 passed. Docker Compose
  config parses. The bundled image and actual non-root container smoke are
  recorded in the image handoff below. This is an HTTP/container boundary
  fixture, not a usable live Gmail deployment or Phase 1 completion. Plan:
  `implementation-plans/dashboard-compose-alpha.md`.

- The immutable image delivery unit is integrated on main `1a429386f7670ae11f211e21105b19a6587f59f7`.
  Dockerfile uses the frozen Python manifest and `uv sync --locked --no-dev`.
  PR #51's Python 3.12/3.13 checks and multi-architecture no-publish Buildx
  job passed. The main publish job passed at run `37200289682`, publishing only
  `ghcr.io/ghostflying/facet:1a429386f7670ae11f211e21105b19a6587f59f7` with
  manifest digest `sha256:9fcbb5b46fcbffd2df79072613be6eb8fd68f94349ccb76ead08c322f2ea6e41`.
  Anonymous `skopeo` inspection and pull verified the public manifest contains
  linux/amd64 and linux/arm64; a temporary container ran as UID 10001,
  returned `{"status":"ok"}` from `/healthz`, and correctly reported
  `{"status":"unavailable"}` from `/readyz`. This proves artifact delivery,
  not live Gmail sync, host deployment, Nginx, or release completion. Plan:
  `implementation-plans/image-delivery.md`.

- The next bounded CLI slice is implemented locally on top of main: plan
  `docs/implementation-plans/m1-cli-bootstrap.md` was independently approved.
  `facet init` now serializes the closed config schema, creates private SQLite
  state with the caller's exact request namespace/nonce, atomically publishes
  `config.yaml`, and can replay a completed or incomplete bootstrap without a
  second database. `facet run --once` opens managed state and stops at
  `binding_pending` before any Gmail/provider construction. Focused subprocess
  evidence is `tests/cli/test_init.py` (8) plus the retained CLI suite (40);
  exact candidate review and Python 3.12/3.13 CI passed on `37dd244`; the
  bootstrap slice uses
  explicit request IDs only; the complete G1 TTY journal/generation protocol,
  OAuth/profile verification and a real Gmail service factory remain open.

- PR #45's first candidate was held by implementation review for three concrete
  gaps: readiness was checked too late, the production candidate/admission seam
  was not connected, and unsupported History jobs stayed queued. Revision 1 of
  `m2-foreground-sync-cli.md` narrows the repair to those gaps. The current
  unmerged candidate adds a preflight before any provider call, a
  `SourceCandidateAdmission` adapter over `SourceAdapter.candidate`, and
  durable `needs_attention` versus due-only `retry_wait` handling. The prior
  exact candidate had 39 focused and 2473 full offline tests; this follow-up
  adds a runner-level due-retry test. It remains synthetic/offline evidence
  only until the new exact review, full CI and merge.

- The first product-shaped foreground composition is now implemented locally
  (candidate not yet merged): `ForegroundSync.run_once` reopens an initialized
  owner, resumes pre-dispatch claims safely, completes fixed-window discovery,
  creates/resumes the initial H0 History poll, persists typed events before the
  cursor, resolves tracked `messagesAdded` events, consumes readonly action
  labels through the typed source bridge, and drains the serial projection
  worker to target readback and mapping. The initial epoch remains `DRAINING`
  as the explicit live authorization epoch for subsequent checkpoint action
  effects. No daemon/IPC/runtime-bootstrap layer or disk raw spool was added.
- Plan `docs/implementation-plans/m2-foreground-sync-cli.md` was independently
  approved after revisions covering outside-transaction candidate/auth facts,
  aggregate `epoch_partitions.state=needs_attention` for unknown admission,
  H0 poll creation, message-added resolution, restart claim boundaries, and
  the retained live authorization epoch. Synthetic vertical evidence is
  `tests/unit/test_sync.py`; the focused set passed 38 tests and the exact
  offline suite passed 2469 tests. This is implemented/offline-tested only;
  it is not live Gmail, CLI-complete, deployment, or Phase 1 acceptance.

- The next bounded runtime-wiring plan
  `docs/implementation-plans/m2-cli-runtime-wiring.md` was independently
  approved and is implemented locally on the merged main base. The new
  composition performs profile probe, expiry/account/scope verification,
  pending-binding publication, access-only service construction, and then
  invokes the existing `ForegroundSync` through one injectable factory seam.
  Synthetic evidence is `tests/integration/test_foreground_runtime.py` plus
  the credential consumer/manager suites (36 focused tests); the Google
  factory never receives refresh tokens and no provider payload is persisted.
  This is offline-tested only. The CLI still stops at its preflight until the
  production OAuth command and persisted-rule admission loader are delivered;
  no live Gmail operation has occurred.

- M1-04 credential binding is integrated through PR #35 recovery head and the
  separately reviewed explicit-scope follow-up PR #37. Main contains
  `4c07766` and `a61c474`; both Python lanes passed for the follow-up. The
  remaining non-gate hardening note is cleanup of a manager-owned `.pending`
  temp file after a pre-replace write/fsync failure.
- Historical M2 PR #36 is integrated at main `28077e4`. It delivered only the fixed,
  offline policy/rules and typed attention-first admission seam: exact sender/
  domain matching, bundled PSL/IDNA, blacklist/effective-at boundaries, and
  lineage-bound `auth-v1` rule-token checks. Its final implementation review
  approved exact `6b13ca7` as bounded pure preparation only; focused 39 tests
  passed and candidate Python 3.12/3.13 CI passed.
- This historical preparation was not automatic admission, G2, or the first
  runnable production sync. The current action-label consumer and production
  History/Backfill wiring are tracked separately. No Gmail, target write, DB
  mapping, or live-account operation was performed by that unit.
- PR #41 is the first integrated durable action-label consumer on main at
  `fbb9fc8048239ae10a7620ddf7e179fa09172eb8`. Synthetic SQLite/WAL tests cover
  AddSender, AddDomain, BlackList, draft-only attention, retryable source
  failures, and file-backed restart replay without a second source read. The
  final candidate `cd50e2f93d7258868a7bb61d0af242aee9ec59c8` received an
  independent implementation review with no P0/P1 findings; 361 focused
  consumer/integration tests and the full 2450-test offline suite passed,
  together with Ruff, wheel import smoke, Python `-S` import, safety, and
  candidate Python 3.12/3.13 CI. It does not call Gmail or target APIs. The
  next production-critical seam is real source History/Backfill discovery and
  worker wiring; M2 and the first runnable production sync remain open.
- The bounded serial projection worker implementation is prepared in candidate
  commit `39215847c3165174dc5c8f1165d5fcb5ebe62398` on reviewed main base
  `5dd9b06fe0828fb4052efda22b721f170a1a82a8`. It expands admitted threads from
  typed metadata, excludes drafts, inserts one in-memory raw message at a time,
  verifies target MIME semantics/thread facts, persists mappings, and leaves
  uncertain insert outcomes in recovery without a blind retry. Synthetic
  temporary-owner tests cover two-message ordering/anchor reuse, target
  readback, replay-safe no-op reruns, raw/privacy sentinels, and response loss.
  Twenty-eight focused worker/adapter tests plus expansion/result tests passed;
  complete offline regression and independent implementation review are still required. CLI
  execution, History scheduling, recovery attribution, stale-claim takeover,
  Dashboard, Compose, Actions and live Gmail remain open.

## Active implementation record

- On 2026-10-02 the user explicitly approved G0 at
  `caba7c73895a303d329cf3eba1c89557530c38c5` and requested multi-agent execution.
  [PR #2](https://github.com/GhostFlying/facet/pull/2) is actually MERGED at that
  SHA via normal fast-forward. Independent technical review/QA and
  [candidate CI](https://github.com/GhostFlying/facet/actions/runs/36968387054)
  passed; [main push CI](https://github.com/GhostFlying/facet/actions/runs/36969107636)
  also passed Python 3.11/3.12. No force, platform merge commit or rule change.
- [P1-00 plan](implementation-plans/p1-00-execution-baseline.md) r2 received
  independent approval at SHA-256
  `b77d4f90d44ea61aad286851454e9db7d98cef0e1c703ad5968470e4d7242bae` before
  implementation. [PR #6](https://github.com/GhostFlying/facet/pull/6) actually merged
  at `2618eafad817aee4e491aa87ebede0f44f27a20b` after independent implementation/
  acceptance approval and [candidate CI](https://github.com/GhostFlying/facet/actions/runs/36970748778);
  [main CI](https://github.com/GhostFlying/facet/actions/runs/36971068807) succeeded.
  The shared current-state
  docs owner and 36 actual package states are in [the ledger](phase-1-progress.md).
  Initial Issues: [P1-00 #3](https://github.com/GhostFlying/facet/issues/3),
  [P1-01 #4](https://github.com/GhostFlying/facet/issues/4),
  [P1-02 #5](https://github.com/GhostFlying/facet/issues/5).
- Independent startup baseline QA on main `caba7c7` passed Python 3.11.2,
  24 offline tests, Ruff lint/format (33 files), spike CLI help and safety.
  This preserves the spike baseline; it is not production Python 3.12/runtime,
  Gmail, Compose or maintenance verification.
- P1-01 [PR #8](https://github.com/GhostFlying/facet/pull/8) actually merged exact
  `09031e723af1ef6590dc6746744ee52894501e38`, after independent reviewer
  `phase1_plan_review` approved the corrected candidate and
  [candidate CI](https://github.com/GhostFlying/facet/actions/runs/36974129495) passed.
  [Main CI](https://github.com/GhostFlying/facet/actions/runs/36974823051) passed
  Python 3.11/3.12. Frozen core `p1-core-v1` and writer `p1-writer-v1` are engineering
  inputs, not evidence that storage/writer/recovery runtime exists or G1 is closed.
- M1-01 [plan](implementation-plans/m1-01-package-config.md) r3 received independent
  approval at SHA-256 `feeabe53d454c931da343964aa7d0a923508d86d3710a03e7c69dc413d534101`
  before coordinator dispatch. The integrated foundation implements 47 canonical core
  exports, strict bounded YAML/config defaults, safe standalone config reads and
  actual `facet config validate/show`, with empty mutable-field registry. Init/apply
  and managed reads are controlled unavailable; no temporary writer/view protocol.
  Local locked checks passed CPython 3.12.13 with SQLite 3.53.1: 149 foundation-snapshot
  tests (24 retained spike plus 125 new), then 287 full tests after the normal merge
  of reviewed P1-02 partial inputs, Ruff lint/format (69 files), both entrypoint help and wheel
  build/non-editable install smoke. Dependency bootstrap used authorized network;
  production tests made no Gmail calls and subprocess guards forbid network/spike/DB
  imports. The preexisting local 3.13.5 lacks `_sqlite3`; it is not a full-runtime
  verification substitute. [PR #11](https://github.com/GhostFlying/facet/pull/11)
  actually merged exact `b1e4ae08f7e361518eaa4f7fb1ae9f7f0b278f28` after independent
  whole/affected-boundary approval and [revised candidate CI](https://github.com/GhostFlying/facet/actions/runs/36980149544).
  [Main CI](https://github.com/GhostFlying/facet/actions/runs/36980646059) passed
  Python 3.12/3.13 at the same SHA. [Issue #7](https://github.com/GhostFlying/facet/issues/7)
  is closed only for this foundation, not Gmail/deployment/G1 or the full CLI.
  The earlier combined candidate `f00cf27` independently passed whole review and
  3.12/3.13 CI, but the coordinator held merge for two parser/help corrections.
  Current revised candidate adds specific child text/JSON help and canonical
  `config apply --file` parsing; apply still reads/writes nothing and returns
  unavailable. Twelve additional subprocess regressions and the required revised
  exact-SHA review/CI passed before integration; the earlier hold is historical.
- P1-02 provider/helper partial [PR #10](https://github.com/GhostFlying/facet/pull/10)
  actually merged exact `c18bfbee09b985ee7b9bb5c230ee2a70427c7edc` after independent
  reviewer `phase1_plan_review` approved the metadata-format correction and
  [candidate CI](https://github.com/GhostFlying/facet/actions/runs/36978399171) passed.
  [Main CI](https://github.com/GhostFlying/facet/actions/runs/36978909460) passed
  at the same SHA. This partial slice supplies synthetic API/fault/privacy helpers,
  not, by itself, a completed P1-02 compatibility gate. M1-01 preserves its atomic core/config
  commits and normally merges that reviewed input without history rewriting;
  the combined tree requires a new whole-candidate review and 3.12/3.13 CI.
- P1-02 mandatory compatibility [PR #12](https://github.com/GhostFlying/facet/pull/12)
  actually merged exact `1b7cd58b4846aab86edcbb781a999abb968d047c`, consuming reviewed
  merged M1-01 types. Independent review, 92 CT cases/379 full offline tests,
  [candidate CI](https://github.com/GhostFlying/facet/actions/runs/36981977390) and
  [main CI](https://github.com/GhostFlying/facet/actions/runs/36982879970) passed.
  Issue #5 closed and the engineering dependency for M1-02 released; this does
  not validate future Gmail/repository/runtime feature consumers.
- M1-02 [Issue #9](https://github.com/GhostFlying/facet/issues/9) / [Draft PR #15](https://github.com/GhostFlying/facet/pull/15)
  is in actual implementation against independently approved schema r3. Values
  and 32-table STRICT/WAL initializer/session slices received independent review,
  including real SQL sealed-snapshot/NUL negative controls. Exact `56eaac6` passed
  450 full offline tests and [3.12/3.13 CI](https://github.com/GhostFlying/facet/actions/runs/36987351921).
  The initial finite-repository candidate `bf0bf0b` was held for audit relationships
  and caught-error rollback defects; corrected `e3eb14b` received independent
  acceptance and exact CI. Subsequent independently accepted/exact-CI slices are
  epochs `397282f`, History lifecycle `a6235f8`, events `a4cf745`, reviewed r4
  private getters/poll revision `07b452c`, expansion epoch work `d7874f3`, and
  History origin-epoch work `0fb0f10`. Known holds were corrected, not waived.
  Insert preparation/dispatch `32c4c66`, recovery claim allocation `f5279c7`, bounded
  SQLite WAL snapshot `c589b4c`, own-child SIGKILL tests `bb27213`, actual result/
  recovery-work recording `d1a89d8`, fact-only target audit `d2fb6a1`, and SQLite
  row-stepping/caught-failure rollback `c03e62f` also received independent slice
  acceptance and exact Python 3.12/3.13 CI. That earlier SQL snapshot passed
  879 full offline tests; [exact CI](https://github.com/GhostFlying/facet/actions/runs/37000255749)
  succeeded. These are storage-library facts, not Gmail invocation/fidelity or
  scheduler acceptance. SIGKILL is not physical power loss; a DB snapshot is not
  a complete credential/config bundle or migration receipt. Typed sessions are not
  real process locks; fresh-owner publication belongs to M1-03's reviewed extension.
  A real DB-21 probe found that `mode=ro` followed by the current supplied-connection
  view adapter created WAL/SHM for a clean stopped database. This is a retained
  historical failure, superseded for the finite library by independently accepted
  exact `16bcd0b99bf1118924b214bf9ded3976813f5e1a`: 1188 full offline tests and
  8 ownership controls passed; the prior d6 single-owner finding was closed by
  reviewed source before the model-policy change.
  [Exact CI](https://github.com/GhostFlying/facet/actions/runs/37014341329) passed
  Python 3.12/3.13. Production provider/runtime registries remain empty: actual
  managed-read/RV11, action consumers, migration/restore and whole DB-01..28 are
  incomplete.
  No immutable-live shortcut or sidecar repair is enabled. PR #15 stays Draft/open
  and unmerged. Later bounded action/policy persistence source
  `62d75c0253a6d66710a9d4d4a4b4346b8b55c6db` passed 164 AP/1352 full tests,
  installed-wheel checks and
  [exact CI](https://github.com/GhostFlying/facet/actions/runs/37023546672), but
  independent acceptance placed it HOLD on two required findings. At that
  snapshot R1 correction and independently approved R2 plan60333e9 strategy were
  released for bounded repair, not accepted corrected source. Later R3 and
  combined acceptance are recorded in the Oct3 handoff below; this historical
  HOLD is not relabelled. Production action/read registries remain empty; no
  actual M5 producer was enabled. The independently approved migration
  entry plan has SHA-256
  `2116d042a8065ba44b818eb7f832414e883cf7ebec27ba4c51ab4e3717746af4`;
  at that snapshot source still awaited accepted actual action input, qualified
  OS input, exact dependency CI and explicit root dispatch. The later finite
  release below is not a complete backup provider, migration/restore
  implementation or whole-package acceptance.
- M1-03 [Issue #13](https://github.com/GhostFlying/facet/issues/13) has an approved
  implementation plan and independently approved r3 wire/command-storage design,
  and a separately independently approved bounded OS root/lock plan. Root released
  that finite source slice against main `ff77e63` after the qualified SQL library
  and exact CI above. The policy pause ended after PR #19 integration. Historical
  OS `183dc6d` independently remains HOLD despite green CI: ordering failed across
  two opaque handles for the same physical root. The reviewed C1 terminal-metadata
  refinement was independently approved before code at full-plan SHA-256
  `4b7895159612699a05f7278652e9c45c884a914478ff61490a63f3358dcc898f`.
  Corrected `ea80db286fe110a69450076581b0b25810dcaf91` received nonauthor Sol
  acceptance: 123 focused/731 full offline tests, paired actual kernel/descriptor
  ordering and 256-cycle live/terminal controls, fork/Thread/uncertain-close checks,
  fresh noneditable-wheel/privacy/import controls passed. R1/C1 are resolved at
  this exact source, not waived for the historical candidate.
  [Candidate CI](https://github.com/GhostFlying/facet/actions/runs/37025751696)
  passed Python 3.12/3.13. [PR #20](https://github.com/GhostFlying/facet/pull/20)
  actually merged at that exact SHA via authorized normal fast-forward; no force,
  bot merge commit or settings change.
  [Main CI](https://github.com/GhostFlying/facet/actions/runs/37026826339) also
  succeeded on Python 3.12/3.13 at that exact SHA. Only low-level Linux
  root/owner/view/key resources are integrated: actual managed provider, actor,
  bootstrap/receipts, storage/credential participants and second real daemon
  refusal remain pending. Arbitrary mounts, NFS/SMB and native descriptor/fork
  paths outside the declared discipline are not qualified. M1-06 r2, M2-01 r2
  and M6-01 r2 designs
  are also independently approved preparation only, not implemented consumers or
  permission to skip their dependencies. Production authentication remains
  metadata/rule admission is now the active contract; controlled live Gmail
  verification remains separately authorized.
- M1-05 [Issue #14](https://github.com/GhostFlying/facet/issues/14) / [PR #16](https://github.com/GhostFlying/facet/pull/16)
  early pure-model/catalogue/serializer/logging unit received independent source
  acceptance at `c455f71ae63fa435c9bb02b82767aff4a032c30c`. Local verification passed
  488 full offline tests (including 33 logging subprocess cases), Ruff, CLI and
  installed-wheel export/privacy smoke; [exact source CI](https://github.com/GhostFlying/facet/actions/runs/36989013627)
  passed Python 3.12/3.13. The two-doc handoff also received independent affected
  review at `f209fbe616dc65c70bbcdc4a104cf82b0d5dad27`, which actually merged via
  normal fast-forward. [Main CI](https://github.com/GhostFlying/facet/actions/runs/36989986570)
  succeeded at the same SHA. The full package stays open for actual consumers.
- M1-04 [Issue #17](https://github.com/GhostFlying/facet/issues/17) /
  [PR #18](https://github.com/GhostFlying/facet/pull/18) early pure source
  `b94b610aec070617a4bd3c1249b58437cc9bfbae` received independent implementation/
  acceptance review; 120 OP cases/608 full tests, Ruff, both CLI help entries,
  installed-wheel privacy/export checks and
  [exact CI](https://github.com/GhostFlying/facet/actions/runs/37000045729) passed.
  Its coherent docs/head candidate received independent review and actually merged
  exact `ff77e63a823dc8bcb130836243746c067778b94f`;
  [main CI](https://github.com/GhostFlying/facet/actions/runs/37001014793) succeeded
  on Python 3.12/3.13. No file/network/OAuth/profile/token publication or full
  binding gate was exercised. Issue #17 stays open; SQL remains unmerged.
- Prospective model-policy [PR #19](https://github.com/GhostFlying/facet/pull/19)
  actually merged exact `a57dd77116ea79b44c177d03bb6b9815a5913795` after independent
  nonauthor source acceptance and candidate CI.
  [Main CI](https://github.com/GhostFlying/facet/actions/runs/37018290223) succeeded
  on Python 3.12/3.13. The temporary OS pause was an ownership handoff, not
  cancellation. At that handoff `m103_os_source` retained OS source and sole
  shared-status/integration ownership; `phase1_sol_policy_review` owned bounded
  SQL corrections and migration plan-only work and independently reviewed OS
  source it did not author. `phase1_os_acceptance_sol` independently reviewed
  SQL source and approved the C1 OS and bounded status-handoff plan. Current
  ownership transfers are recorded below. Historical model attribution,
  package dependencies, external authority and milestone gates are unchanged.

## Oct3 source and main-health handoff

- The [PR #21](https://github.com/GhostFlying/facet/pull/21) status snapshot actually
  merged exact `36b5a303856f00876c697f712ee98c9012c497c7`. Its
  [main CI37028856572](https://github.com/GhostFlying/facet/actions/runs/37028856572)
  failed on Python 3.12 while Python 3.13 passed: OL07 assumed 64 sequential
  Threads would reuse a retired Python thread ID. This is retained failure
  evidence, not observed runtime ownership bypass. The first harness candidate
  `a410ca1dab1e0f0a8980f77d0443f88a92e7b982` separately received independent H1
  HOLD despite full/CI success: legitimate sibling activity changed ancestor
  directory metadata included in its test oracle. Neither finding is waived.
- Corrected [PR #22](https://github.com/GhostFlying/facet/pull/22) actually merged
  exact `befe278285cfbd77798ffa58e8ef5d35b12e203a` at 2026-10-02T16:59:36Z after
  independent nonauthor acceptance, concurrent 150 focused/758 full tests,
  twenty complete nine-scenario child batches, real sibling-positive and
  descriptor/invalid-phase negatives, and fresh installed-wheel controls.
  [Candidate CI37036616826](https://github.com/GhostFlying/facet/actions/runs/37036616826)
  and [main CI37037683010](https://github.com/GhostFlying/facet/actions/runs/37037683010)
  succeeded on both Python jobs. Actual main logs show CPython 3.12.3 and 3.13.16,
  758 full tests and 40 CLI smoke tests each. All production OS and complete
  approved OS/C1-plan bytes remain the qualified `ea80db2` input; only bounded
  test-harness/main-health evidence changed, not runtime/provider qualification.
- SQL `2466834f79c41dbbf95e2919072ea9f57f36e7cc` remains historical R3 HOLD for
  foreign UoW exit invalidating the genuine creator lifecycle. Corrected
  `c0bb4b02277942f335ce278d359b60c16a46fd48` received independent acceptance with
  1598 full/73 R3-focused tests, eight actual WAL controls, installed-wheel
  checks and [CI37032060497](https://github.com/GhostFlying/facet/actions/runs/37032060497)
  both-success. Its actual ACTION plan is 546 lines with unchanged full hash;
  the earlier review's 535-line description was a clerical count error, not
  different source or retrospective acceptance of either held candidate.
- Normal combined carry `a9c4e36de6ad70294002a83e678a2a7cf1b012d6`, parents c0bb
  then befe, now has independent nonauthor combined acceptance: 1625 full tests,
  73 R3-focused/150 OS-focused/eight actual WAL controls, byte-preserved SQL/
  OS/harness inputs and fresh noneditable wheel. Author full 1625 also passed.
  [Fresh CI37038807962](https://github.com/GhostFlying/facet/actions/runs/37038807962)
  succeeded on both jobs. Actual checkout logs identify PR merge commit
  `8e703daf8a8739411324457dec98cc34c0dff036`, whose tree
  `b33a7679c0ed4e3f2cc6885d084ac3c0eb479cab` exactly equals candidate a9c's tree;
  run head metadata alone is not the tested-revision proof.
  [PR #15](https://github.com/GhostFlying/facet/pull/15) remains Draft/open/unmerged.
  This docs branch remains based on accepted main befe, not that SQL branch.
- Root explicitly transferred the approved migration plan/tree and released its
  finite source allocation to `m103_os_source`; source work starts only after
  this docs freeze/CI start.
  The preserved 217-line plan is SHA-256
  `2116d042a8065ba44b818eb7f832414e883cf7ebec27ba4c51ab4e3717746af4` and the
  232-line design is `3a9fedfcb3cf2fbaa410c982383fd459d8f1f1b73f58992e96883c9ad50042cf`.
  Source implementation/independent acceptance/CI are not yet complete. The
  approved 229-line restore-fence plan hash
  `1cee159f355ef6df39ec781cc75cf31ad43e26966c47d9c34ad306dd7c29c0ba`
  and 307-line design hash
  `3e8bd09eb9d6068d29d2e1bdf2eba617dcc20be695a65ba8b38f2e26f70aadf8`
  remain plan-only without source release. Neither supplies a complete
  config/binding/credential bundle, installation/provenance issuer or restore
  recovery/clearance consumer.
- `phase1_sol_policy_review` separately owns the source-released no-state
  read-bootstrap foundation under approved 217-line plan SHA-256
  `87321fe4ae703356a7aee8eb8c2f4a80a372f3bfc2ef8ba86c27e1c142029094` and preserved
  229-line design `9d28e18cee3dbaed00c939838686a6b715cefb569c268a4f3e73a0d1cc6c660e`.
  Its bounded launcher/latch/in-memory probe allocation is not accepted source,
  a state opener, managed-read producer, qualified runtime, daemon or RV11.
  Shipping action/read-provider/runtime inventories remain empty. Source
  authors do not approve their own design or implementation; root dispatches
  exact independent acceptance and separate integration gates.

`m103_os_source` remains the sole shared-status/integration writer. This separate
three-document handoff needs its own exact-source nonauthor review and fresh CI
before root-qualified integration. Whole M1-02/M1-03, actual M5 consumers,
credential ownership, complete backup/restore/migration, full maintenance CLI,
G1-G6, live Gmail, Dashboard and Compose remain incomplete.

## Historical planning and bootstrap record

The following records describe their then-current candidates. Current approvals,
engineering integration and remaining gates are in the sections above.

- Historical planning/normalization records below retain their original SHA/
  verification scope. Their then-pending G0/Draft states were superseded by the
  explicit approval and actual integration recorded above, not retroactively
  relabelled as approval or runtime proof.
- User authorized product-first reordering of the total plan, not G0 approval:
  goals → operating loop → overall acceptance → scope/non-goals → milestones →
  work packages/execution. Eight acceptance groups summarize existing contracts;
  the 36 card bodies, DAG, waves, CLI ownership and authority ledger are preserved.
  The file-based reordering plan received independent Astra high approval before
  editing. Exact candidate review and CI belong to this revision and are tracked
  in [draft PR #2](https://github.com/GhostFlying/facet/pull/2); earlier approvals
  do not imply approval of the new overview. No production work has started.
- [Repository bootstrap](implementation-plans/repository-bootstrap.md).
- User requested a complete maintenance CLI and atomic English commit subjects
  (`feat: impl ...`, `fix: fix ...`, other types with action verbs), plus one-time
  main-history normalization. [CLI specification](cli-spec.md) now covers full
  command families, offline/Compose maintenance and CLI-01 through CLI-08 gates.
  Stable request keys before submission, explicit preview producers and coordinated
  DB/credential ownership address preliminary review feedback. This substantive
  extension received its own independent Astra high technical approval at
  `eca99118b46db765960c7439246b6a1c5f4e5ccb`; preliminary findings were closed.
  [History normalization](implementation-plans/commit-history-normalization.md)
  was separately reviewed, executed and independently accepted. The reviewed
  CLI candidate maps to `5d623f201b4e4f8c701b196d3f017bf874f3e79a` with an
  identical tree, identity and original dates; this traceability does not extend
  the old `7c68991` review to the substantive CLI changes.
- [Phase 1 planning record](implementation-plans/phase-1-planning.md),
  [complete execution plan](phase-1-execution-plan.md), and
  [agent workflow](agent-workflow.md). [Epic #1](https://github.com/GhostFlying/facet/issues/1)
  tracks this planning unit and later ready work-package Issues. The planning
  worktree is isolated. Local document links/fences/headings, whitespace, private
  host-path checks, 36-package dependency references/acyclicity and staged-index
  repository safety passed for the initial candidate. Independent review of
  `a8e87de` requested changes. Independent technical re-review approved
  `7c68991ef5f47ba65cc61a0dcc2dfd80fdb0ca46`, closing R1-R3 and C1; 36-package
  uniqueness/missing-node/cycle checks and manual wave review passed. Prior
  [draft PR CI at `af3b793`](https://github.com/GhostFlying/facet/actions/runs/36960852657)
  passed Python 3.11/3.12; it does not cover this new CLI extension. The new
  CLI candidate received separate review and
  [new candidate CI at `5d623f2`](https://github.com/GhostFlying/facet/actions/runs/36965268013)
  passed Python 3.11/3.12. At that planning handoff G0 remained pending. These runs
  validate their exact candidate SHAs, not a later report-only commit. The
  [review record](reviews/phase-1-plan-review.md) preserves historical and current verdicts and
  responses. No
  production package, daemon, Gmail request, deployment, or image is
  introduced by this unit.
- This planning unit's locked local baseline passed on Python 3.13.5: environment
  sync, Ruff lint/format (31 files), 24 offline tests and spike CLI help. These
  checks preserve the existing spike baseline; they do not validate planned
  production behavior. No mailbox credentials or live Gmail calls were used.
- On 2026-10-02 the user authorized delegated Phase 1 work, multiple worktrees,
  Issue/PR tracking, atomic commits, Astra high / 6.1 Sol xhigh as needed, and
  root coordination/reporting only. Complex plans need independent review before
  implementation, then independent implementation and acceptance review.
- The user also authorized autonomous merges of engineering/work-package plan
  PRs inside the approved phase after those review and CI gates, and public
  `ghcr.io/ghostflying/facet` main full-SHA image publication through Actions once
  the phase starts. They clarified that the overall Phase 1 plan itself needs
  their review and explicit approval; the draft planning PR must not merge
  beforehand, and technical review/CI cannot start implementation. PRs only
  build; formal version tags/GitHub
  Releases, live Gmail operations and host deployment are not included. No
  image has been built or published yet.
- Repository: [GhostFlying/facet](https://github.com/GhostFlying/facet), verified
  PUBLIC with default branch `main`; `origin` points to it. On 2026-10-02 the user
  explicitly requested public visibility and their account's GitHub noreply email.
- Local verification: 24 offline tests passed; Ruff lint/format, spike CLI help,
  shell syntax, tracked/staged safety scan, documentation links/fences, and staged
  whitespace checks passed. No live Gmail requests were used for this bootstrap.
- The first push was rejected by `GH007`. The unpublished root commit was
  replaced using the current configured user/noreply identity, without changing
  saved Git configuration or email privacy protection. GitHub confirmed both
  author and committer use the account's noreply identity and attribution is
  `GhostFlying`. The rejected old commit is not in public history.
- Initial published commit: `53ac21b`. Its [offline CI run](https://github.com/GhostFlying/facet/actions/runs/36955887359)
  completed successfully on both Python 3.11 and 3.12: 24 tests in each job,
  tracked-content safety baseline, locked install, lint, formatting, and CLI smoke.
- The user-requested one-time main-subject rewrite now maps that root to
  `34818fe9f5d2d7bcb30353939b146418b2d5a814` and old `9d8595d` to current
  `main` `2f78fdf69cba786d2568689b0d0566d827d4285a`. All six reconstructed
  commits passed independent tree/header/identity/date/topology acceptance;
  the base-to-plan diff is unchanged. Private local rollback refs are retained
  and were not published. [Fresh main CI](https://github.com/GhostFlying/facet/actions/runs/36965264011)
  passed Python 3.11/3.12. [PR #2](https://github.com/GhostFlying/facet/pull/2)
  was then Draft/unmerged with G0 pending; the later approval/integration is above.
  Complete mappings and rollback
  anchors are recorded in the history-normalization execution appendix.
- Published GitHub tree checked: source/tests/docs/configuration only; no private
  runtime directory or credential files. The baseline scan is not a substitute
  for the production privacy tests still required by later milestones.
- Runtime credentials/evidence are ignored local files. No live Gmail writes are
  part of this bootstrap, and no experimental state is adopted as production data.

## M2 runtime composition handoff (2026-10-04)

- The exact-SHA review of the first runtime candidate found and blocked two
  issues: the CLI was not actually dispatching the library seam, and invalid
  Google factory paths constructed an untyped `StorageFailure`. The revised
  plan now explicitly names this unit library runtime composition; `facet run
  --once` now dispatches the reviewed production runtime after local binding
  checks, while the default unknown-auth provider remains fail-closed.
- The follow-up candidate adds typed factory failures, access-token-only
  construction tests, and missing/swapped/expired/mismatched credential tests
  with unchanged bindings and no sync service on failure. The focused runtime
  and factory suite passes (36 tests including credential consumers); the
  complete offline suite passed 2490 tests, both CI lanes passed, and the
  candidate merged as `bc3922a908458ba0e8db1d1573773bfd22fe6dbd`. No live
  Gmail or deployment action was used.

## Current product closure

The bounded unit in `implementation-plans/cli-sync-closure.md` is accepted at
candidate `e2d38ef`. From a clean private state directory, the CLI can execute
`init`, fake authorization/profile binding for both roles, exact sender rule
creation, write-free backfill preview, explicit backfill start, and
`run --once --fake`. The first run discovers one synthetic thread, inserts and
reads back one message, and persists one mapping; a second process run produces
zero new projections. The subprocess evidence is in
`tests/cli/test_bootstrap.py`; the focused closure/credential/command-operation
tests passed 67 cases and the complete offline suite passed 2495 tests.

The candidate also validates request-key replay and cross-command conflicts,
including atomic start activation and restart recovery. Rule replay currently
uses deterministic rule identity rather than a separate operation row and
payload digest; that is a documented P2 follow-up, not evidence for the full
CLI contract.

This is implemented and offline-tested, not live-Gmail-verified or Phase 1
complete. The follow-up OAuth binding unit at candidate `723c9cf` adds the
production role-specific loopback authorization path with TTY-only URL output,
actual-grant scopes, profile/account verification, and durable role publication.
The candidate received independent approval; its focused tests passed 73 cases
and the complete offline suite passed 2501 tests. No live OAuth/Gmail evidence
  is claimed. The fake runner exercises metadata/rule admission; controlled
  Gmail verification remains a separately authorized external gate. Dashboard,
  Compose, Actions, scheduling and remaining maintenance commands
remain outside these closure units.

## Production CLI sync-path wiring handoff (2026-10-04)

The production command seam is integrated in PR #53 at merge
`727e1d99c174019b0c432653e2e274b2f10743b7`; its implementation plan is under
`docs/implementation-plans/production-cli-sync-path.md`. After both role
bindings are verified, non-fake `backfill start` uses the Google Gmail service
factory to obtain the source profile fence and persist H0/epoch. Non-fake
`run --once` verifies both profiles/scopes, loads the persisted ruleset, and
dispatches `ForegroundSync` through the reviewed production composition. The
receipt exposes aggregate counts only.

The current production path performs metadata/rule admission without a
source-auth provider, raw fetch for admission, or DNS lookup. No Gmail network
call, OAuth exchange, target write, deployment, or release was performed by
this unit. Focused CLI/runtime tests and the complete offline suite (2512
tests) passed, as did Ruff/format and repository safety. This is
implemented/offline-verified only; a controlled live Gmail run remains a
separately authorized external gate.

## Product-first recovery correction (2026-10-06)

The bounded correction in `implementation-plans/critical-path-simplification.md`
is implemented locally and offline-verified. The foreground path now resumes a
persisted History poll through the real owner transaction after a typed
provider failure; Gmail system-label changes are filtered before business-event
creation; untracked message deletions are consumed without false attention;
and typed provider failures remain retryable while unexpected programming
failures are no longer converted into permanent attention. The post-dispatch
unknown-insert recovery path is unchanged.

Focused sync/history/action tests passed 109 cases and the complete offline
suite passed 2645 tests. This remains synthetic/offline evidence only: no live
Gmail, OAuth, deployment or target mutation was performed. Removal of unused
bootstrap/launcher modules and broader exception-taxonomy cleanup are deferred;
the next product gate is controlled live Gmail sync after this unit is
committed and reviewed under the existing authorization boundary.

The local Compose runtime was then exercised with the candidate source under
the image's non-root UID, read-only root filesystem, and persistent state
volume. `init`, fake authorization, sender-rule publication, preview, explicit
backfill start, and two `run --once --fake` invocations completed; the first
reported one projection and the second reported zero new projections with no
attention. The official Dockerfile rebuild itself was attempted but Docker Hub
timed out before fetching the pinned base; the runtime check therefore used a
cached local diagnostic base with only the committed source overlaid and is not
an image-publication or Dockerfile-build claim.

That build limitation is now resolved for this candidate: Tailscale SSH to
sgbox allowed the unchanged Dockerfile to build against its pinned base digest
and locked dependencies. The image was streamed back with `docker save/load`
and verified locally as
`sha256:9cf1757ae273353ab860fb33551f2e2375fc19e7e30ed82336c5c56ac81ce086`.
The same Compose command path passed again using this freshly built image and
a separate synthetic volume: first run projected one, second run projected
zero, both with zero attention. The stopped DB confirmed one mapping and one
verified insert attempt; image source and lockfile checksums match the local
candidate. This is a local Dockerfile/Compose acceptance, not GHCR publication,
multi-architecture acceptance, deployment to real state, or live Gmail evidence.

## Historical next-unit note (superseded)

This old note proposed a source-Gmail-path evidence producer; the 2026-10-05
user decision superseded it. The current product-bearing work is the smallest
integration that exercises metadata/rule discovery through the existing
adapter, action/repository and BackfillProducer owners. Ordinary phase-internal
plans/engineering PRs advance under the approved autonomous gates; material
product/privacy/authority changes return to the user. The complete M1/M2
foundations and their remaining runtime/provider consumers remain open. M1's
minimum scope is:

1. Establish the production Python package/CLI without breaking the spike.
2. Validate configuration and explicit source/target bindings; refuse identity
   swaps or identical accounts, and separate private internal configuration from
   allowlisted public diagnostics.
3. Implement schema v1, migrations, durable repositories, process/writer locks,
   rule effective times, and metadata-only typed payloads.
4. Establish private OAuth/token handling and synthetic tests; require separate
   authorization for real account setup or additional scopes.
5. Define Dashboard response models and privacy sentinels before exposing HTTP.
6. Keep Gmail authentication/classification provider-owned; test that
   authentication headers do not become a Facet admission gate.

Production live copying, bulk backfill and deployment require their recorded
scope/target decisions. Dependency-ready offline engineering can proceed while
an external gate remains pending; keep final milestone gates in order and record
actual verification scope instead of marking a partial gate complete.

## Known limits and decisions still needed

- Gmail insert is not exactly once; target search timing is not an SLA. Production
  crash/recovery and ambiguous-ID tests remain necessary.
- Default raw processing is memory-only with no disk spool; source loss may
  prevent recovery. DB contains only necessary metadata and state.
- Production target must be newly created and dedicated to the projection and
  authorized external agents. Source-identity unmanaged SENT/DRAFT is permitted
  under the product-contract classification, not a projection success or an
  automatically claimable recovery copy. Account/content checks cover normal
  mail, SENT, drafts, Spam and Trash; other unexpected/unmanaged content or
  account mismatch blocks new projection writes, report-only with no automatic
  delete, claim or migration. Existing mappings/independently proven insert
  ownership take precedence. Labels/From/metadata do not prove application
  writer identity; DB/process single-writer remains required. Runtime target
  classification/audit/recovery integration and live acceptance remain open.
  See [product contract](product-contract.md).
- AI connector retrieval is an AI-product responsibility, not a Facet gate.
- Real bank domains, live account/test scope,
  dogfood host/local volume/Nginx entry, license and formal version release remain
  undecided. GHCR/package public visibility, main full-SHA publication, public
  anonymous pulling, and the first multi-arch artifact are verified above;
  source publication does not substitute for deployment or live-sync checks.
- Authentication trust, unknown-insert attribution (excluding old unmanaged/spike
  copies), and daemon/CLI single-writer coordination are required early ADRs.
  Unique fingerprint matches alone do not establish this insert's provenance.
- Overall Phase 1 G0 is approved at the exact reviewed SHA; production milestone
  completion is not implied. Internal merge/GHCR scope does not authorize new
  live Gmail or host actions. Final milestone live
  gates remain separate from dependency-ready offline engineering outputs.
