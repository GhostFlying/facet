# Dashboard observability acceptance

2026-10-09. Root implemented; independent Sol 6.1 xhigh reviewer
`continuous_plan_review` owns plan/source acceptance. Plan SHA-256
`0af3b6a2fdb99feef5625dcf36f8545dd386b2f42a9a580dadc66ee89745689c`
was approved before coding. Source candidate
`ae950076530909eb8fa86ecb3efd4c47cc192fa6`, base
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
- The same script passed against a non-root UID 10001 read-only isolated local
  image based on the qualified production image, with only the new bundled
  page replaced. No production state/credentials were mounted. Packaged page
  SHA-256 matches candidate
  `c562c5e409eedd8b6d1b71b2e97501fef587a772e4a4e1155151760e71975020`.
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
