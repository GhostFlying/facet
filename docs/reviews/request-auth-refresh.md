# Request-time authentication and partial sync continuation

2026-10-08. Root implements; independent Sol xhigh reviews source and acceptance.

## Product behavior

The production CLI checks role-token expiry before requests, uses the existing
credential manager at the five-minute threshold, and reacts once to an explicit
401. Startup profile checks are covered; refreshed-token profile probes remain
static/nonrecursive. GET/read-override may replay once; insert cannot replay in
the transport/SDK. Its explicit rejection becomes durable definitely-not-inserted
before a new claim/attempt. Failed pre-HTTP credential preparation has a proven
not-dispatched boundary and cannot become an uncertain insertion.

Structured provider reasons cross adapters/rewrapping/private diagnostics via a
closed enum. Policy/scope/quota denial is distinguished from expired access and
stops the batch as appropriate. Account-wide reasons dominate transient reasons
regardless of error-array order. Provider messages/response bodies are discarded;
the OAuth SDK's scope warning is suppressed before policy validation. No DB schema
or frozen error enum changed; durable rows retain normalized categories.

`run --once --verify-known-only` uses the production owner/runtime but performs no
History/discovery/expansion/insert. It resumes only attributable direct-response
readbacks after source raw-digest and target fidelity/visibility checks, binding
and active-generation guards. Verified mapping and semantic facts share one
transaction. Only unstarted dependent jobs in that resolved active thread may be
requeued; jobs with their own attempts, unknowns and stopped work are excluded.
Normal cycles perform the same completion before claiming copying jobs.

## Candidate-bound evidence

Independent plan approval initially bound SHA256
`a8891fd9673d7e71b0e31d253c1bb863d5d272e26ef652436f2f65bc72cf6403`.
Source/action propagation and initial profile refresh were bounded clarifications;
final plan SHA256 is
`8dc73e5a51be42e887b69d622dfcdc5302869631f2af4f227a9fe15b77497496`.
Independent implementation/acceptance approved exact source
`1a8eef14937caf8f58bc8035eb964e3b7bcec38f`. Reviewer independently passed 72 initial,
63 amendment-focused and nine final CLI checks, plus Ruff/safety. The concrete
multi-reason precedence finding was fixed and both-order regressions passed.

Root passed affected worker/runtime/mapping/provider checks, four pre-HTTP/known
readback/stopped-dependent checks, reason/transport tests and actual CLI external
fakes. CLI proof covers threshold expiry after the first insert, both rejected
startup profiles, new durable attempts after insert401, zero-insert readback then
remaining copying, invalid grant, changed account/scope, policy/daily quota,
restart deduplication, retained unknown and privacy sentinels. Faults replace only
external OAuth/Gmail or clocks; no readiness/binding/rule/epoch DB seeding.

Exact non-root source image `facet:1a8eef1`, revision label matching the full SHA,
image ID `sha256:d78a728f9c671d7dfe550905529bf2d2bdf56b1cf80d8856eef0bcb79358fc2e`,
UID `10001:10001`, passed all **49** complete CLI/request-reason checks in 158.91s.
Image tests used loopback-only external fixtures, read-only root, ephemeral state,
and appended test dependencies; application source came from the image without
an overlay. The pinned base/build dependencies remain unchanged. The final local
offline suite passed **2837 tests in 695.20s**. Required PR #100 checks passed on
Python 3.12/3.13 and image construction; merge is
`0d885d45b61507b63d4a97a9bc7c608c0909142f`. Its production source/tests/build inputs
match the accepted local image source. Main image publication passed; anonymous
registry reads confirmed index
`sha256:133125dd1582fbcdeeb79196c599a35f87a6d93593fab6f05019d79a3d0fed1b`
with amd64/arm64 and attestation manifests. Both architecture attestations have
SPDX and SLSA v1 predicate layers. Main offline CI also passed. Publication is not
a new deployment/Release gate pass.

## Real-test boundary

The current real test is interrupted, not discarded: 1872 confirmed mappings,
one definitely rejected insert, one direct-response pending readback and its
unstarted dependent. The older unknown is frozen. The failed second-batch marker
must remain intact. Engineering qualification is not live acceptance.

User authorizes continued testing after merge on the same accounts/rules/selected
epoch/window. Use a private writer-locked SQLite-API/config/credential backup,
then a new independently reviewed operator record. First invoke zero-insert known
completion; require unchanged prior mappings/unknown/stops/scope and no new
attempts. Full target classification must pass before one same-scope copy cycle.
Stop on unsafe error/new uncertainty/unmanaged content, retain blocked receipts,
then perform read-only sample verification and backup. No cleanup, new scope,
live unknown retry, continuous service, deployment or Release is authorized here.

After merge and private backup, actual CLI zero-insert completion passed in
11.01s: one new verified mapping, 1873 total, no new attempts, and all required
protected rows/scope/checkpoint unchanged. Related known-insert attention cleared;
the pre-existing 58 attention jobs and one old unknown remain. Its independent
one-message sample passed MIME/digests, valid Date/internalDate, target thread and
normal All Mail checks. Fresh target enumeration found 1873 mapped items, two
permitted outbound items and no other unmanaged mail.

The new same-scope ordinary CLI cycle completed in **1795.16s**, with **1000 new
insert attempts / 1000 new verified mappings, 2873 total**, zero repeat discovery,
five History pages and 14 resolved events. Its durable clean receipt confirms
unchanged prior mappings, old unknown, attention, stopped generations, rules/window
and epoch/discovery identity. No new job problems or warnings; zero claims on exit.
Fresh target enumeration found 2873 mapped items, two permitted outbound SENT items
and no other unmanaged mail. Independent read-only sampling selected exactly this
cycle's 1000 new mappings and verified 20: MIME/digests, all 20 valid Date/internalDate
values, thread identities and normal All Mail visibility passed. It checked all
mapping attempts verified, distinct target IDs and unchanged prior mapping digests.
The post-test writer-locked private SQLite/config/credential backup passed.

Both saved role credential revisions advanced during preparation; their subsequent
read-only metadata checks showed valid tokens. This real continuation verifies
expired-credential startup, known-readback completion and restart continuation,
not an observed mid-cycle threshold crossing or reactive 401: those are proven by
the production CLI external-fake cases. Copying remains serial; the observed
throughput is not a Gmail limit or a product latency promise. 1400 historical jobs
and three normal projection jobs remain queued; the old unknown and 58 attention
jobs remain protected. No exhaustive/browser/complete-backfill or Phase 1
acceptance is claimed.

Private operator and read-only sample-selector plans/implementations passed
independent review with entirely synthetic guard checks. Submitted interrupted
legacy receipts remain immutable; lost responses cannot trigger operator replay.
