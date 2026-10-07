# History incremental rule admission repair

Base: `40cbb49733e88ae903a6d90b67f1eebf6a1ad16a`. Root owns implementation;
independent reviewer owns plan and candidate acceptance. This repairs the
approved continuous sync contract; no new milestone or live authority.

## Observable delivery and scope

After explicit backfill start, `run --once` admits a previously untracked
thread when a new History message matches the current sender/domain rules,
expands its available non-draft history, and persists normal mappings. A
subsequent process continues without a second insert of confirmed messages.
Ordinary no-match events finish without false attention; stopped threads stay
stopped. Already-active threads retain their existing authorization.

Files: `src/facet/sync.py`, `src/facet/gmail/source.py`,
`src/facet/runtime/foreground_runtime.py`, focused source/sync unit tests and
`src/facet/db/repositories/events.py` for explicit no-effect message completion,
`src/facet/projection/admission.py` for a History-only prospective timestamp,
and the existing production CLI fake subprocess tests. Update current status and
one concise review record at handoff. No schema, CLI command, framework or
daemon protocol is needed.

Reuse the metadata adapter, pure admission evaluator, current persisted rules
loader, future-rule admission record, thread expansion worker, durable event
and job repositories, writer lock, insert intents and readback/mapping path.

## Required behavior

- Separate untracked, active and stopped states. Only untracked threads enter
  rule admission; active threads project new non-draft messages; stopped events
  are consumed without re-admission or generation changes.
- Initial discovery continues using its sealed epoch rules. History uses
  current persisted rules, reloaded after action-label effects, not the old
  backfill snapshot. Empty allow rules require no metadata fetch.
- Fetch candidate metadata outside SQLite transactions. Preserve typed
  provider failures for durable retries; malformed/mismatched metadata enters
  attention rather than default admission. No raw fetch for rule evaluation.
- For prospective History admission, use strict Gmail `internalDate` rather
  than metadata-fetch time as the conservative allow eligibility timestamp.
  Current enabled blacklists still deny admission regardless of message age;
  the timestamp applies only to prospective allow rules. Old
  messages cannot become implicit retrospective backfill after rule learning.
  API-imported old dates may consequently be excluded; this is not a latency
  guarantee or a claim that History exposes an event timestamp.
- Active tracked threads do not re-run sender rules. Check metadata identity
  and draft state before projecting a new message, including draft transitions;
  already confirmed mappings finish without fetching metadata again.
- In one transaction, recheck current ruleset and thread state, admit the
  untracked thread with `future_rule`, enqueue real-time full-thread expansion,
  and consume the event/complete its resolve job. Rule/state changes invalidate
  stale preflight results rather than disclose against stale permission.
- Add a narrow repository operation for consuming a `message_added` event
  without projection work. Existing generic classification restrictions and
  terminal attention handling stay intact: only error-free PENDING with a known
  thread can become CONSUMED, with exact completed replay; do not reopen
  RESOLVED/attention/source-missing effects. Never invent a dummy copy job.
- Keep explicit-start epoch ownership, H0/events/cursor ordering, source/target
  binding, blacklist, stopped generation and unknown insert recovery unchanged.
  Do not automatically replay old attention events or existing unknown inserts.

## Acceptance and stop gates

Targeted tests cover new exact sender and domain matches, no match/empty rules,
Spam/Trash/draft exclusion, blacklist, old-before-effective messages, changed
rules, stopped threads, provider failure retry, transaction fault/restart and
confirmed mapping deduplication. Existing CLI subprocess setup/auth/bind,
rules, preview/start/run paths gain a subsequent synthetic History arrival;
only external Gmail/OAuth is fake, never production DB readiness/rules/epochs.
Verify full-thread insert/readback, durable mapping and restart with no repeated
insert; assert privacy-safe output and no content persisted.

Run affected checks during development; final candidate runs required full
offline checks, safety scan and independent implementation acceptance. Build
the candidate image and run the synthetic path in isolated container state
before the PR handoff. Never mount real state into fake tests.

Stop on a product/privacy conflict, unsupported metadata requiring default
allow, or a need for new live authority. No real Gmail mutation, service resume,
deployment, scope change, deletion or recovery retry is part of this unit.

## Retry research boundary

Separately inspect primary community/upstream evidence for httplib2 POST replay
and mature transport alternatives. Do not treat `num_retries=0`, global
`httplib2.RETRIES`, or an unmerged upstream patch as proof of one wire attempt.
Transport replacement is not mixed into this History repair. No automatic
retry of the existing unknown insert is authorized by either investigation.
