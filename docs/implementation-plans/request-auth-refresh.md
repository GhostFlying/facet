# Request-time credentials and interrupted projection continuation

2026-10-08. Base `e504b696913fba12bab5fc69dbe5ff3f838fd5a4` (complete
sync PR #99 merged). Root implements; independent Sol xhigh reviews this plan
and the actual implementation candidate. One coherent fix PR, no new framework.

## Delivery and observed cause

A production CLI batch must remain usable across access-token expiry and report
structured provider reasons rather than collapsing permission/quota failures
into authentication failures. The existing credential manager remains the only
refresh/publish owner. A restarted CLI continues the existing epoch/jobs/mappings;
it does not select new historical scope or resend uncertain inserts.

Read-only live evidence: the second continuation confirmed 648 more mappings
(1872 total), then target auth failures appeared immediately after the saved
token expiry. Startup had about 20 minutes remaining, above the existing
five-minute refresh threshold, but a 1000-job batch can take longer. Source and
target original credentials now both return 401 on read-only profile probes.
Current code checks only at cycle entry, then holds fixed tokens. Credentials,
accounts/rules/window and prior mappings are unchanged. No refresh or resume was
performed during that diagnosis. One new attempt is definitely rejected; another
has a direct successful insert response but failed readback. The old unknown
remains protected. The private operator marker is pending because its post-cycle
assertion rejected the changed attention set; it must not be blindly replayed.

## Minimal implementation

- `gmail/retry.py` and `gmail/refresh_exchange.py`: parse bounded JSON error reason fields, including OAuth's
  `invalid_grant`, into a closed `ProviderReason` enum. Pass it through
  `ProviderFailure`/rewrapping and explicit private CLI diagnostics. Unknown or
  malformed reasons become a fixed unknown/missing category, never arbitrary
  provider text. Use reason-based status classification rather than body substring
  matching. 401 is authentication; 403 permissions/domain policy/unknown denial
  use existing `scope_required`, rate reasons use role rate codes, storage uses
  the existing storage code. Daily quota retains its distinct reason and stops
  the batch rather than behaving as a token failure. No changes to frozen DB
  error enums/schema: DB retains existing normalized error categories; the reason
  travels through provider failures and the private diagnostic boundary.
- `gmail/sync_transport.py`, `service_factory.py`, and
  `runtime/foreground_runtime.py`: a small production-only callback obtains the
  current role access token before each permitted request. Cache the current
  verified snapshot and check its expiry in memory; at the existing five-minute
  threshold call the same manager's ensure-current/refresh/profile/scope checks.
  Update the token actually used by the client. Refresh profile probes themselves
  use a static access-only client to avoid recursion. No new account/scope choice,
  SDK implicit retries, shared transport, network-held SQLite transaction or
  competing writer. Existing synthetic service factories need no new framework.
  Startup profile verification also permits one manager-owned reactive refresh
  per rejected role on explicit 401, followed by fresh verification. Refreshed
  token profile probes stay static and do not recursively refresh/retry.
  Credential/profile failures raised before the HTTP request carry a proven
  `request_dispatched=False` boundary. Even after the worker's durable dispatch
  marker, they are definitely-not-inserted, never unknown. Only a received insert
  response with HTTP 401 triggers a reactive insert refresh.
- Reads (GET and the SDK's POST-with-GET-override) may synchronously refresh on
  an explicit 401 and replay that read once. A second rejection or failed refresh
  stops processing, retaining the reason. 403 is not a refresh trigger.
- Insert transport remains single-dispatch. In `projection/worker.py`, an explicit
  401 is first durably recorded as definitely-not-inserted and the job deferred;
  then refresh synchronously and make it due for a new, generation-checked claim
  and new durable attempt. At most one reactive refresh per rejected job per
  cycle; persistent failure stops that cycle. Never refresh-and-replay inside
  the HTTP insert call. Network/timeout/redirect/5xx uncertainty keeps recovery.
  Auth/permission/failed-refresh dependencies stop the batch after preserving
  the current work, rather than poisoning hundreds of subsequent jobs.
  `gmail/source.py` and `projection/action_consumer.py` must preserve that same
  failure across candidate/action normalization; ordinary per-item attention
  behavior is unchanged. Failures still durably retain the affected event/job.
- `projection/worker.py`, `sync.py`, and `db/repositories/mappings.py`: narrowly
  resume readback for existing `needs_attention` attempts with direct-response
  attribution, inserted certainty, target IDs, and a transient auth/network/rate
  readback error. Re-fetch source into bounded RAM, require its original raw
  digest, validate target ID/thread/visibility and semantic fidelity, then use
  existing mapping verification/job completion. A bounded repository helper may
  supply previously absent semantic facts after these checks; keep revisions,
  binding and active generation checks. Unknown, ambiguous ownership, fidelity
  mismatch, inactive/stopped threads and unrelated old attention are untouched.
  This path never inserts or searches/adopts unrelated target mail.
- Expose `run --once --verify-known-only` through the same production runtime
  and held owner. It only completes eligible existing direct-response readbacks:
  no History/discovery, expansion or insert. Existing durable attempt/mapping
  identities make retries idempotent, as with normal `run --once`. Normal cycles
  also perform this bounded completion before claiming copy jobs. After confirmed
  mapping, narrowly requeue unstarted `insert_result_unknown` attention jobs in
  that same active generation/thread only when they have no own attempt and no
  remaining unresolved thread attempt. These are dependent jobs blocked by the
  thread guard, not uncertain inserts; old unknowns are never requeued.
- `cli/bootstrap.py`: expose the closed provider reason in existing explicit
  private diagnostics only, not provider messages or arbitrary responses.
  Update concise development status and one acceptance receipt at handoff.

## Acceptance

Develop affected tests first, then prescribed full offline checks and CI at the
merge boundary. Independent review binds exact plan hash/candidate SHA. Exact
non-root local image must pass production CLI subprocess tests with external-only
Gmail/OAuth fakes before merge; no DB seeding of readiness/bindings/rules/epochs.

Tests cover structured/multiple/malformed/unknown reason privacy, private reason
propagation, 403 quota/policy not refreshing, threshold refresh mid-batch, early
401 despite unexpired local metadata, one bounded read replay, persistent 401 and
invalid-grant stopping, account/scope change rejection, manager-owned publication,
insert 401 with two distinct durable attempts, lost-response insert no resend,
pre-HTTP threshold refresh timeout/invalid-grant with zero insert requests and
no unknown outcome or new retry dispatch,
insert-success/readback-auth failure followed by restart completing the original
attempt through the zero-insert CLI mode, unstarted dependent job continuation,
previous mappings deduplication, old unknown and stopped-generation
preservation. Synthetic body/header/token/error sentinels must stay out of
DB/journal/stdout/stderr/logs/files and public output where forbidden.

## Merge and real-test boundary

User explicitly requested this fix PR/merge, then local continuation of the
existing real test. No cleanup, DB reset, new rules/window/backfill start, unknown
retry, source mutation, scope expansion, continuous service, formal deployment
or Release. After accepted source/local image/independent review/required CI and
merge, retain the stopped service and use the accepted image for bounded one-off
CLI tests on the same volume. Before writes: writer-locked SQLite-API private
backup; normal manager refresh and role/scope/profile checks; classify the one
direct-response known insert as owned pending verification, never as permitted
outbound or an adopted fingerprint match. Other unexpected content still blocks.

Diagnose and retain the failed resume2 receipt from durable marker/current DB,
without resubmitting its marker or treating it as clean. Establish a new reviewed
bounded continuation record against the exact existing state. First verify the
known readback without any insert; then run bounded same-scope copying and check
new attempts/mappings, unchanged prior mappings/old unknown/stops/scope, target
classification and sample readback. Stop on new insert uncertainty, permission/
refresh failure, unexpected content or failed invariants. Missing OAuth recovery
authority or a material contract conflict returns to the user; ordinary fixes
and in-scope checks continue autonomously.
