# Observable continuous sync

2026-10-09. Base: `97c4093905aa94c8754054eefeeb5c2696143cf1`.
Root owns implementation; independent Sol xhigh reviews this plan and the actual
candidate. One product unit, not new milestones or a general tracing/audit layer.

## Delivery and reuse

Existing CLI setup/binding/rules, sealed discovery epochs, History/gap processing,
serial worker, refresh transport, five-minute unknown recovery, mappings and cached
Dashboard remain the implementation. Add the missing consumers so ordinary
container `run` can safely continue an existing scope and explain its progress.
No rebuilding the 4,325 already verified live mappings.

## Files and behavior

- `gmail/target.py`, a small `projection/target_inventory.py`, worker/runtime
  composition: once per cycle before the first new insert, enumerate ALL target
  IDs including Spam/Trash and draft-contained messages, using pagination. Compare
  IDs with durable mappings and independently attributable known insert responses;
  pending intents/fingerprints are not ownership. Read only labels and From for
  otherwise unmanaged IDs. Allow only SENT/DRAFT with a single valid normalized
  From equal to bound source. From stays in RAM. Unexpected/ambiguous items or
  incomplete/provider-failed enumeration block new insert, retain queued work and
  expose an aggregate error. Source durable ingestion and readback recovery can
  still run. Cache the successful check only within one cycle, never indefinitely
  or per unknown; account/profile/credential guards still run first. All production
  insert consumers, including selected jobs, must use the same check. Existing
  mappings/owned outcomes take precedence over outbound labels. Recovery must not
  auto-claim allowed outbound. Missing managed target items are reported, not
  silently reinserted. Concurrent external mailbox changes are not an atomic Gmail
  transaction; do not claim inventory creates one.
- `status/logging.py`, `gmail/retry.py`, `sync.py`, `projection/worker.py`,
  `runtime/foreground_runtime.py`, `cli/bootstrap.py`, `runtime/dashboard.py`:
  bounded structured cycle/phase/count/error events using closed stage/reason
  enums, HTTP status, retry delay and elapsed duration. Log handled provider errors
  at their real boundary without formatting exceptions/responses. Publish a first
  snapshot and throttled owner-thread snapshots between phases/jobs, outside DB
  transactions; HTTP remains cached/read-only. Progress is not a successful cycle
  or refreshed provider-verification fact. SIGTERM stops admitting new jobs after
  the current bounded request; dispatched uncertainty remains recoverable.
- Reuse RAM-only source `raw_digest`/semantic/MIME hashes. Permit optional validated
  SHA-256 in necessary local diagnostic events/private CLI; no raw cache, address
  hashes or digest in public HTTP/DOM/DTO. Full source EML hash identifies bytes,
  not a delivery occurrence and not target raw equality. Update AGENTS and privacy
  specifications for this explicit user decision, preserving Dashboard exclusions.
- `sync.py` discovery planner and search tests: domain rule uses bounded Gmail
  From-domain candidate search, followed by existing strict normalized domain/dot
  boundary admission. Never use unfiltered full-source enumeration. Consult
  official search docs and retain a provider evidence gate for parent/subdomain
  coverage: synthetic evidence is not proof of Gmail query behavior. Read-only
  probes use only already authorized accounts/window; if that evidence cannot
  establish the supported behavior, report the concrete remaining gap rather
  than silently broadening or claiming live acceptance.
- `docker-compose.yml`, operations/deployment docs: container-only log rotation,
  restart policy and bounded graceful stop; no deployment-specific proxy settings
  in the project. Update current status concisely; retain historical review notes.

## Acceptance and stop gates

Target pagination/failure/malformed metadata tests; mapped and known owned outcomes
before outbound classification; legitimate SENT/DRAFT versus wrong/multiple From;
recovery excludes unmanaged/outbound even if RFC/hash matches; one inventory per
cycle, repeat next cycle, zero new insert on blockage, source checkpoint retained.
Domain parent/subdomain/IDNA and evil suffix false positives, mixed sender/domain
queries, stable pagination and no rules/no source listing. Continuous CLI external-
only fake tests cover setup, current scope, insert/readback/mapping, restart,
unknown recovery, graceful stop, progress during long cycles and closed provider
reason logs. Sentinels must not reach DB/files/logs/HTTP; hashes allowed only in
explicit local events, never public output. Affected checks during development;
full required baseline, non-root local image E2E, independent acceptance and exact
PR CI before merge. No tests/checks removed or weakened. No new shared framework.

After local-image validation and qualified merge, upgrade the CURRENT TEST
deployment with stopped/locked SQLite backup and immutable image provenance; run
only existing accounts/rules/selected window, including restart/token refresh and
user-applied action labels. No arbitrary new historical scan, production migration,
deletion, sending, scope enlargement, token revocation or live repair. Ask for any
new external authority; unresolved Phase gates and 72-hour production dogfood stay
unfinished. Provider errors are not absence, stopped generations never revive,
and raw mail stays only in memory throughout.
