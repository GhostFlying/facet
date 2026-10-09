# Dashboard observability acceptance

2026-10-09. Root implemented; independent Sol 6.1 xhigh reviewer
`continuous_plan_review` owns plan/source acceptance. Plan SHA-256
`0af3b6a2fdb99feef5625dcf36f8545dd386b2f42a9a580dadc66ee89745689c`
was approved before coding. Source candidate
`9ff469be8202efd235c9a36aaa7a2393937ae8f8`, base
`7fa0cc7a761e29628b4753729bf452d994f30e00`. Later carry/docs changes do not change
that static asset or tests. Exact implementation verdict and required final
checks are recorded on the engineering PR before merge; approval is not inferred
from this file or a passing browser check.

## Product evidence

- Four existing cache-only API families are consumed. Fixed enums, validated
  operational scalars, explicit message/thread units, no percentage or ETA.
  Role verification means binding verification, not live token health.
  Unsupported metrics/global tracked counts/reconcile/audit stay unknown or
  unreported. No new collector, public DTO, account/scope or write entry.
- 44 affected endpoint/runtime/public-privacy tests passed. Actual Chromium
  140 desktop 1440×900 and mobile viewport 390×844 passed the committed bounded
  synthetic script: healthy/backlog/auth/gap/partial state, no samples, mixed
  stale/unavailable families, failed/malformed refresh then recovery, hung
  request abort/no overlap and aging. GETs only to the bundled page/four APIs,
  no external requests, addresses/digests or echoed negative fixture in DOM,
  no horizontal overflow. This is not physical-mobile acceptance.
- Independent review of original `ae95007` requested one bounded correction:
  receiving an already aged snapshot must not grant it another full lifetime.
  Source `9ff469b` uses each family's remaining age budget and the earliest
  monotonic deadline, including fetch time. The corrected script passed both
  viewports with a fresh response aged 29 seconds becoming unknown after 2.1
  seconds without another fetch. Seven affected HTTP/static tests also passed.
- The corrected script passed against a non-root UID 10001 read-only isolated local
  image based on the qualified production image, with only the new bundled
  page replaced. No production state/credentials were mounted. Packaged page
  SHA-256 matches candidate
  `37e594ff8c618e1180717ebf6f0899e9a76212f63c631a6b25cbadc2db30af15`.
  Synthetic desktop/mobile screenshots were visually inspected.
- Complete locked offline baseline and exact-head Python 3.12/3.13/image CI
  remain mandatory merge gates. Runtime/HTTP privacy tests remain the output
  boundary; front-end selection is not permission to publish forbidden fields.

## Live boundary

The real existing service keeps running qualified continuous sync while this
page is qualified. Its account/rules/window/volume are unchanged; no cleanup,
new OAuth scope, source mutation, extra backfill or Release. Live page smoke is
cached GET-only. A later qualified test image upgrade requires graceful stop,
writer-locked backup, immutable provenance and retained-state verification.
Phase 1 maintenance/restore/reconcile/audit and production dogfood remain open.

## Qualified current-test deployment

PR #112 merged at `d7232ddcbaa390a4317f25b230d218c454fbd359` after independent
APPROVE of source `9ff469b` and docs-only head `feebaa1`, the local baseline
(2944 tests) and exact-head Python 3.12/3.13/image CI. The published index is
`sha256:a1dfe6cf9fdfe8ec509562e228a50022a92ee7c9447a5977a733c4b4f8efe797`;
anonymous import and complete packaged source/static comparison passed. Both
SPDX 2.3/SLSA v1 payloads bind the corresponding amd64/arm64 subject and main SHA;
only amd64 execution is qualified here. Arm64 OCI metadata export hit a registry
TLS timeout at the empty config fetch; both needed attestation payloads had been
downloaded and their SHA-256 matched the manifest. No arm64 runtime claim.

The existing authorized Compose deployment was gracefully stopped (exit zero).
Normal owner preflight created integrity-checked SQLite/config/credential bundles
with 0600/0700 permissions before/after refresh/profile checks. Checked business
tables remained identical, 4351 mappings, zero target writes. Only the private
image selector changed; original project/volume/accounts/rules/window remained.
The service restarted with the published image, UID 10001 and read-only root;
successive cycles completed with zero inserts and queue/attention zero. Live page
hash matched qualified asset; actual desktop/mobile viewport smoke showed 4351
confirmed, Healthy, no overflow, no addresses/digests and only same-origin page/
four cached GET requests. Continuous sync remains running. This does not accept
production migration, remaining maintenance gates, 72-hour dogfood or Release.
