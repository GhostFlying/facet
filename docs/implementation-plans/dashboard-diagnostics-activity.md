# Dashboard diagnostics and rule-match activity

2026-10-10, revision 2. Source base: `0366a5f`; prior exploratory candidate
`53114b4` is not qualified for merge/deployment. Root implements; independent
Sol xhigh reviews this corrected plan before follow-up implementation and then
the exact final candidate. No historical review is fabricated.

Review status: the required pre-implementation plan review was not obtained;
two attempts failed because the review model service reported capacity. The
implementation review was therefore performed after the first candidate and
found/fixed cycle-level error retention in `d7485fc`; this is implementation
evidence, not retroactive plan approval. The candidate remains unqualified for
merge or deployment until an independent review records a decision against
revision 2 and the exact final head.

## User-visible delivery

The read-only Dashboard will explain previously unreported diagnostics instead
of turning available local facts into `Unknown`, show the running image's
40-hex commit SHA when the deployment supplies it, and add a reverse
chronological activity section. Each activity row contains only the configured
sender/domain rule value, the number of newly verified mappings attributed to
that rule, and the server-local operational timestamp. It never exposes Gmail
message/thread/history IDs, subjects, addresses outside the already approved
rules view, content, digests, or provider errors.

## Implementation scope

- Extend the closed Diagnostics model/serializer and frontend with optional
  `commit_sha` and real local DB/scope/resource checks.
- Keep health evidence conservative: add an explicit `cycle_in_progress` flag,
  display a neutral Running badge when the fresh snapshot is unknown during a
  cycle, and preserve degraded/blocked errors. Do not turn old verified bindings
  into proof of current Gmail health. Start/progress, final and idle snapshots
  retain their actual verification/error states; stale snapshots stay unknown.
- Derive scope readiness from committed credential-change metadata matching
  current binding and credential revisions plus configured role policy. This is
  last-verified grant evidence, not live token-health evidence; missing evidence
  stays unknown. DB diagnostic is explicitly writer-transaction readiness, not a
  promise that the next disk write will succeed; no mutating probe is added.
- Classify container memory using readable cgroup v2 limits/usage; unlimited
  cgroup falls back to explicitly host memory from `/proc/meminfo`. Disk uses the
  state filesystem's free-space ratio. Fixed thresholds: below 5% critical,
  below 15% elevated, otherwise normal; unavailable reads stay Unknown.
- Add a bounded `activity` public snapshot. Build it from durable mapping
  first-verification timestamps (`mapping_history`, revision 1) joined through
  that insert attempt's generation to the historical thread admission rule;
  group by rule and UTC minute, newest first, capped at 100 recent rows. Repair,
  replay and re-admission cannot recategorize/count old successes again. It is
  admission-rule attribution, NOT a fresh sender match of every later message.
  Manual/legacy admissions without rule evidence get an explicit Other
  authorized thread bucket, not invented rule values or silently omitted mail.
  Sender/domain values in this private Dashboard family are the user's explicit
  extension of the rules-view exception, never generic logs/CLI/public exports.
- Add `/api/v1/activity`, static rendering/tests, and update the Dashboard spec
  and development handoff.
- Bake the source commit into the Docker image via build arg supplied from
  existing Actions checkout SHA. Diagnostics validates the full 40-hex value;
  local dirty images can supply no revision and display Unavailable. Do not
  treat a manually injected image tag as proof of packaged source. No new
  dependency/action or workflow permissions.

## Acceptance and boundaries

- Existing five snapshots and privacy allowlist remain compatible; the sixth
  activity snapshot is independently validated and stale/unavailable-safe.
- Synthetic DB tests prove diagnostics states and activity aggregation; HTTP and
  browser tests prove no IDs/content appear and that newest activity sorts first.
- Focused synthetic writer-owned tests cover successful cycles and in-flight
  status, retained failures, scope lineage, disk/cgroup availability, new
  sender/domain activity, manual fallback, repair/replay/re-admission and
  restart. HTTP/sentinel and desktop/mobile browser checks cover six fresh
  families, stale/failure handling, bounded timeline and SHA rendering.
- Final candidate runs complete required offline baseline, independent
  implementation/acceptance review and exact-head CI before engineering merge.
  Isolated non-root read-only container smoke uses no real credentials/state.
  Current test deployment upgrade only after qualification, stopped/locked
  SQLite/config/credential backup, immutable-image proof and rollback reference.
- No Gmail calls, writes, schema migration, rule changes, or new external
  authorization are required. This unit does not claim final Phase 1 acceptance.
