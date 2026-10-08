# Granular historical backfill repair

Date: 2026-10-07. Base: `f922e59`. Root owns implementation; independent Sol
xhigh reviews plan and actual source candidate. Current live sync stays stopped.

## Delivery and reuse

Existing production CLI preview/start/run must support a new historical epoch
after an empty initial backfill and a later sender rule. Reuse sealed DB rules,
operation journal, SourceCandidateAdmission query, BackfillProducer, shared
History checkpoint and normal worker/intent/readback/mapping paths. No complete
`sync` wrapper in this unit, schema migration, new provider framework or daemon.

## Files and behavior

- `cli/bootstrap.py`: read preview invalidation from the owner transaction,
  replace synthetic constant scope digest with a digest of actual bound scope,
  and preflight preview/start guards before credential/network calls. Replay uses
  persisted preview/start; one preview cannot create multiple epochs with new keys.
- `db/command_store.py`, `db/repositories/epochs.py`: first start remains initial;
  a fresh explicitly started preview after initial History is established creates
  `historical_expansion` using existing schema/decision types. Preserve initial
  pristine-checkpoint guard; expansion requires established cursor/coverage, no
  active poll/unresolved gap, and never writes/reset the existing checkpoint.
  Both paths retain expiry/rules/config/binding/generation and H0 journal checks.
- `runtime/foreground_runtime.py`, `projection/admission.py`: retain the sealed
  allow snapshot/query while applying current enabled sender blacklists during
  resumed discovery. Deny decisions use current admission time, not historical
  message time; later allow rules cannot widen the selected scope.
- `sync.py`: discover oldest unfinished initial/expansion scope (not an already
  completed partition). Load that epoch's sealed rules; historical admission can
  cover mail before effective_at without modifying the rule. Keep the initial
  epoch as the ordinary History/action anchor; consume the existing checkpoint
  rather than replacing it with the expansion H0. Finish an expansion only after
  complete History coverage of its fence and all epoch-linked work is terminal,
  using completed_with_issues for terminal failures. Unknown/pending work stays
  pending, and old unrelated attention/unknown is neither selected nor reopened.
  Completion requires a fully completed shared-checkpoint poll with coverage at
  or after the expansion fence, no active poll/unresolved gap, complete
  partitions and terminal linked jobs. History IDs are opaque, never ordered.
- `tests/cli/test_sync_wire.py`, external fixture and focused DB/sync tests:
  exercise actual production SDK/CLI with only external OAuth/socket interaction
  substituted. No direct DB seed of binding, rules, readiness or epoch in E2E.
- Current status and one concise review receipt: exact candidate/image evidence
  and remaining live/Phase 1 gates; preserve scope and historic failure records.

## Acceptance, risks and authority

Test init/auth -> empty initial preview/start/run -> CLI sender rule -> zero-write
historical preview and stable-key replay -> explicit start (distinct epoch,
unchanged checkpoint) -> nonempty source query/thread expansion -> insert/readback
and durable mappings -> new process no duplicate insert. Also test preview with
existing tracked generations, stale rules/stops/expiry, consumed-preview/new-key
refusal, sealed-rule queries, stopped threads, old unknown preservation, discovery
page/restart continuation and response-loss no resend. Check privacy sentinels in
DB/files/output, exact raw fidelity and no-network standalone preview/status.
Use genuinely old candidates preceding the learned rule. Restart a partial scan
after adding a blacklist and a different allow rule: blocked/untracked and stopped
threads stay unadmitted and the sealed query does not widen. Old/partial History
coverage and linked pending recovery prevent completion; terminal failed linked
work completes with issues, unrelated old attention/unknown remains untouched.

Iterate affected tests first; final candidate gets prescribed full offline checks,
independent implementation acceptance and non-root pinned-Dockerfile image E2E
before a focused PR/required CI. Do not repeat unchanged evidence gratuitously.
No real Gmail insert, bulk start, source mutation, cleanup, scope change, daemon,
deploy or Release. Local real-state standalone preview/status may be checked
offline; actual historical copying needs concrete rule/window authorization.
Stop for a contract conflict, unknown gap, or a need to reset state/retry unknown;
never bypass those guards or change prospective rule/action semantics.

## Authorized published-image trial, 2026-10-08

The user approved the updated default six-month preview window for the existing
bindings and sole enabled sender rule. Use qualified published runtime
`392fe31969d96c5be4e46dff0bce3fdb249c8fd3` on the already authorized test host,
not an application overlay or DB seed. The known-window gap prerequisite is
offline-qualified, not live gap acceptance. Keep the installed daemon stopped.

An owner-only operator helper in the private deployment directory persists
preview/start request keys before submission and uses actual production CLI
preview/replay, start/replay and one foreground cycle. If clean, run one further
cycle in a new process. Existing mappings, unknown attempts, historic attention,
rules/bindings and stopped generations must remain intact. New provider deferral,
attention, unknown or a guard failure stops continuation, even if the CLI envelope
says completed. No total subprocess timeout that kills an in-flight insert.
Read aggregate progress query-only; readback compares new mappings' MIME/date/
thread/visibility in bounded memory. Adapt the existing verifier's obsolete
zero-mapping/unchanged-discovery assumptions, not its production fidelity logic.
No automatic retries after operator-response loss, new rules/scopes, raw files,
mailbox cleanup, continuous service, Release or phase-completion claim.

## Live-found rule-version correction

The accepted published runtime's first historical cycle was blocked before any
insert or mapping: backfill hardcodes `auth-v1` in admission provenance while
action-learned rules carry their persisted PSL/IDNA policy version. Repository
validation correctly refuses the mismatch; no guard, database row or unknown
state should be weakened or rewritten. Read the selected `rule_revisions` row
inside the existing admission transaction and use its actual `policy_version`
for both historical and known-gap admission refs. Missing revisions fail closed.
Scope: `src/facet/projection/backfill.py`, focused backfill/gap regressions and
CLI external-fake historical/action-learning coverage where practical. Assert
durable admission provenance matches a non-default learned rule and preserve
sealed rule/stop/unknown/cursor guards. Run affected checks, independent focused
acceptance and a locally built non-root image before any new PR. Continue the
same authorized epoch only after confirming the failed cycle produced no new
attempts/mappings and a fresh preflight; never replay an uncertain insert.
