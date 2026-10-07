# Sync single-dispatch HTTP and source-missing repair

Base: `4613a47` on `fix/history-incremental-admission`. Root implements; independent
Sol 6.1 xhigh reviewers review this plan and the actual candidate. This is the
user-approved next bounded repair, not a milestone redesign or live authority.

## Observable outcome

Normal production Gmail insert uses the locked Google request constructor with
a Requests HTTP transport. If a synthetic server accepts the POST body and drops
its response, it receives exactly one POST; the durable attempt becomes unknown
and restart does not send it again. Source candidate/active metadata 404 becomes
durable `source_missing`, not a misleading input error or repeated fetch.

## Files and reuse

- Add `src/facet/gmail/sync_transport.py`: small access-only Requests transport,
  following the already wire-tested cleanup transport. Keep cleanup independent;
  never give sync DELETE/full-mail OAuth. No dependency change, vendored
  httplib2 implementation, capability framework or new runtime layer.
- `gmail/service_factory.py`: compose this transport with the real locked
  Google SDK; retain lazy imports and 30-second request timeout. No refresh token,
  credential callback, AuthorizedSession or automatic 401 refresh/replay.
- `runtime/foreground_runtime.py`: close per-cycle provider services on success
  and failure, including partial construction, with standard context management.
  Profile-probe and failed-build transports also close deterministically.
- `projection/worker.py`: a surfaced 3xx insert response is unknown, not proof of
  no insert. Preserve existing 401/429 handling and 5xx/response-loss recovery.
- `sync.py`: only message metadata 404 maps to `SOURCE_MISSING`; atomically finish
  the resolve event/job in the existing source-missing states. Do not globally
  reinterpret History 404 or target 404, or override old attention/unknown work.
- Adapt existing service-factory tests; add real TCP wire/worker/restart tests,
  metadata-404 tests and synthetic production CLI subprocess/container evidence.
  Update one concise current status and review record at handoff.

## Transport boundaries

Use Requests Session plus HTTPAdapter(max_retries=0), `allow_redirects=False`,
30-second timeout and in-memory Bearer access token. Retain normal proxy support;
tests route only the final Session socket call to loopback, not a new production
endpoint option. Accept HTTPS Gmail API hosts and `/gmail/v1/users/me/` paths.
Source currently needs GET and the locked SDK's read-only POST override to the
exact messages-list endpoint with `x-http-method-override: GET` for long search
URIs. Target needs GET and POST to messages.insert only. Add an actual-SDK long
discovery-query regression; the override is a read, not a new mutation or scope.
Do not add send/delete or currently undelivered convenience writes. Use
httplib2.Response only as the SDK response value, never httplib2.Http networking.
Return unfiltered provider bytes only to the existing error/adapter boundary;
do not log or persist them. Preserve original raw insert bytes and readback.

Keep existing credential-manager ownership/account/scope checks, single writer,
intent-before-dispatch, mapping/readback, stopped generations and memory-only raw.
No schema, setup command, OAuth policy or supported-runtime change.

## Acceptance and external boundaries

Independent plan review before coding. Development uses affected tests; final
candidate uses full required offline checks, safety scan and implementation
review. Local image validation precedes any PR workflow.

Actual Google discovery/client + real Requests/urllib3 loopback TCP tests cover
accepted body/drop response, 401, 429 with Retry-After, 5xx and 307/308 redirect:
one POST, no redirect/auth resend, exact raw payload, stable typed diagnostics.
Use production worker/intents to prove durable unknown and no restart resend;
retain meaningful privacy sentinels in DB/journal/log/public output assertions.
Source/target use distinct transports; resources close on all normal exception
paths. Source metadata 404 tests cover untracked and active threads, zero insert,
source-missing event/job, and no repeated fetch after restart. History expiry
and target missing behavior remain unchanged.

Run real CLI subprocess setup/auth-binding/rules/preview/start/run with only
external Gmail/OAuth substituted, then restart. Build the unchanged pinned
Dockerfile and validate in non-root isolated synthetic container state; never
mount real state into fake tests. No actual Gmail call, deployment, sync resume,
scope expansion, deletion, release or retry of the existing unknown insert.
Stop for a concrete product/privacy conflict or a need for new external authority.
