# Dashboard observability consumer

2026-10-09. Base `7fa0cc7a761e29628b4753729bf452d994f30e00`.
Root implements; independent Sol 6.1 xhigh reviews plan and actual candidate.
Continuous sync is already running in the authorized current test deployment.
The independent docs-only live handoff is separate; no competing state edits.

## User-visible delivery

Replace the tiny count-only page with a responsive, useful read-only operational
view of the four existing public snapshot families. No new DTO, scheduler,
framework, account access, OAuth UI, content routes or backend collector.

## Files and behavior

- `src/facet/web/static/index.html`: overview, source/target permission/auth
  state, operational poll/insert/heartbeat times; unique confirmed messages;
  mutually exclusive queue counts; current-scope discovery/thread counters;
  nullable rate/latency samples with units; grouped exceptions and fixed
  suggestions; existing DB/schema/owner/pressure diagnostics. Fetch only the four
  cached GET endpoints, every ten seconds plus a read-only Refresh button.
- Preserve Unknown/Unavailable rather than fabricate missing metrics. Never
  treat known discovery candidates as a final message denominator: admitted
  threads and later incremental arrivals can exceed that count. No percent/ETA.
  Counts describe their actual message/thread/current-scope units; do not infer
  global tracked counts or reconcile/audit results not supplied by the DTO.
- Freshness applies to each family. Stale/unavailable/failed refresh cannot
  retain green Healthy, zero-error or zero-queue claims; show last observation
  only if explicitly stale-labelled, or clear it to Unknown. Failed/malformed
  responses use fixed text and never print fetched exceptions/raw responses.
  Avoid overlapping refreshes and late older responses overwriting newer ones.
- Use plain bundled HTML/CSS/JS, DOM textContent (never payload innerHTML),
  accessible headings/status, responsive small-screen rows. Persisted role
  verification time is labelled as binding verification, not the latest profile
  request. No addresses, custom labels, rule values, IDs, digests, mail links,
  URLs, config or raw logs. No write controls except cached-state refresh.
- `tests/unit/test_web_server.py`, bounded `tests/browser/` synthetic browser
  acceptance and optional test instructions: reuse public fixture shapes,
  endpoint-side output privacy tests and actual packaged asset. Desktop/mobile
  viewport, backlog/auth/gap/partial errors, unknown discovery/metrics, stale,
  unavailable/network failure then recovery, DOM/requests/content sentinels,
  no external or mutating requests. Browser tooling is development-only, not
  shipped in the Compose app; do not introduce a frontend build/runtime.
- `docs/dashboard-spec.md` only correct the obsolete unimplemented banner and
  clarify existing count/timestamp limits. Current state gets one concise handoff
  after integration; do not copy prior CI history into it.

## Gates and external boundary

Affected endpoint/privacy tests and actual browser acceptance first, packaged
non-root local image smoke, independent exact-candidate implementation review,
required complete baseline and CI before qualified merge. No skipped tests or
check disabling; pure wording changes retain source-review conclusions.
Browser synthetic routes replace only public aggregate snapshots, not production
DB/Gmail state. Optional live smoke reads the existing loopback dashboard only;
no new scopes, mail reads, Gmail writes or rule/window changes. Deploy only after
qualification under the existing current-test upgrade authority and stopped/
locked backup. Do not claim final maintenance/restore/reconcile/audit/72-hour
production dogfood acceptance from this page; unsupported collectors stay
explicitly unreported. A schema/authority/privacy conflict returns to the user.
