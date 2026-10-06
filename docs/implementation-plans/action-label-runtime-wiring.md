# Production action-label runtime wiring

## Revision 3 — bind the live action path to the writer and preserve orphaned insert recovery

User live-validation evidence on 2026-10-06 exposed two implementation defects
without changing the product contract: the foreground seam passed `StateOwner`
where `ActionEffectConsumer` requires its owned `WriterSession`, and an
unexpected target-insert exception could leave a dispatch-started attempt
without a durable recovery job. This correction remains root-owned with
independent implementation review; no new user permission or Gmail scope.

- Pass the existing writer session into the action consumer; do not add a
  second transaction or owner abstraction.
- On an unexpected target insert exception, record `insert_result_unknown` and
  materialize recovery rather than allowing a generic defer to strand a
  dispatch-started attempt.
- At the next owner cycle, reconcile only dispatch-started attempts that have
  no claim and no recovery job into the existing pending-recovery/recover-insert
  state machine. Preserve all insert facts; never retry or query Gmail as part
  of this reconciliation. Make it idempotent and typed.
- Add synthetic orphan/restart tests plus the runtime owner-session regression.
  Existing partial-label tests and evidence remain valid.

Acceptance: a live action event can reach the durable action effect; unknown
insert state always has a recover-insert job; restart materializes a stranded
dispatch attempt without remote writes; recovery check remains read-only and
unknown outcomes never become a blind insert. No schema, public output, scope,
raw-storage or target-cleanup changes.

## Revision 2 — independently enable available categories

User decision: 2026-10-06, option 2. Base: `0790de4b29a4b42c115afd12ce166541eb71bad1`.
This revision supersedes the all-three-label precondition below. Plan and
implementation are owned directly by root under the user's later workflow
instruction; only review is delegated independently. No new framework or schema.

- Represent each of the three provider label IDs as `ProviderId | None` in
  `PrivateActionLabelMap`. At least one must be present, and present IDs must
  be unique. `kind()` resolves only present IDs; missing categories do not
  match unrelated IDs. No sentinel IDs or invented provider evidence.
- Resolve configured names through the existing read-only `labels.list` call.
  Return a partial map when any category exists; return `None` only when none
  exist. Duplicate configured labels and malformed/provider failures remain
  typed errors. Names/defaults/CLI persistence do not change.
- Existing runtime composes `ActionEffectConsumer` for the partial map. A valid
  AddSender event learns an exact rule and admits its selected thread even when
  AddDomain/BlackList are absent. Absent/unknown labels never create actions;
  existing removed/unknown attention semantics remain unchanged.
- Existing attention events are not automatically requeued, reset, or replayed.
  Live validation uses a fresh operator remove/re-add event after the reviewed
  local candidate image is ready. No manual DB edit or source label write.

Files: `src/facet/projection/actions.py`, `src/facet/gmail/source.py`; source,
producer/consumer and runtime integration tests; update the current action-label
passage in `docs/development-status.md` (and only any directly contradictory
concise spec wording). No change to insert recovery, generations, effective times, scopes,
raw memory-only storage or public DTOs. This authorized correction does not
promise safe sender/content authentication.

Acceptance: sender-only and domain-only/blacklist-only maps; all-absent, duplicate
and invalid maps; unknown ID never matches a missing category; an absent or
non-list `labels` response, a non-dict label entry, a non-string name/id, or an
invalid configured name map is a typed `ProviderFailure(INVALID_INPUT)` (while
an otherwise valid list with no configured names is the normal all-absent
`None` result); actual production
runtime composes with sender-only provider labels; synthetic durable AddSender
rule/thread/job effect plus replay/restart idempotency with the partial map.
Run affected tests during iteration, then Ruff/format, full offline pytest and
repository-safety at the final candidate boundary. Independent plan and exact
implementation review required. Build local image before PR/CI.

External boundary: no Gmail writes during engineering tests. Resume the already
authorized live test only after fresh user activation; do not insert arbitrary
threads, replay old attention, widen scopes, create labels or deploy elsewhere.
Stop if partial IDs require schema/public changes or weaken stopped-generation,
durable action deduplication, account/scope, privacy or unknown-insert guards.

## Historical revision 1

Date: 2026-10-05. Status: implementation candidate; plan and exact-candidate
review approved, CI/merge pending.
Base: `e1fa578d32be0aa301edd4edeeed891011a31bea`.

## User-observable delivery

The existing foreground production composition will consume the three fixed
readonly source labels (`AI/AddSender`, `AI/AddDomain`, `AI/BlackList`) when
they are present. A label event will use the durable `ActionEffectConsumer`
with source-fetched redacted thread facts, persist the rule/thread/job effect,
and remain restart-safe. If the labels are not present, normal sync continues
without an action consumer and any corresponding label event remains explicit
attention; Facet never creates or removes labels.

## Scope

- Make `SourceAdapter.action_label_map()` return no map when one or more fixed
  labels are absent; duplicate fixed labels and provider failures remain typed
  errors. Do not broaden Gmail scopes.
- In `ForegroundRuntime`, after the existing profile/account/scope checks and
  service construction, build `ActionEffectConsumer` from the source adapter,
  configured own addresses, and the bound source primary address. Pass it to
  the existing `ForegroundSync` seam; do not create a second writer or runtime.
- Keep source-path attestation unchanged and fail-closed. This unit must not
  use synthetic evidence, parse authentication headers, or auto-admit a new
  thread merely because an action label exists.
- Keep all label IDs, addresses, and source facts in memory only. Persist only
  the existing normalized action/rule/thread/job metadata.

## Files and acceptance

- `src/facet/gmail/source.py`: optional fixed-label map behavior.
- `src/facet/runtime/foreground_runtime.py`: production consumer composition.
- `tests/unit/test_gmail_source_candidates.py` or a focused adapter test:
  absent/complete/duplicate fixed-label responses.
- `tests/integration/test_foreground_runtime.py`: configured labels construct
  the consumer with the source adapter and own-address fence; absent labels do
  not block an ordinary cycle.
- Existing action-consumer restart tests remain the persistence evidence; add
  no alternate action protocol.

## Stop gates

- Do not run real Gmail or mutate source/target mail. No label creation,
  deletion, cleanup, or OAuth scope change is authorized by this unit.
- Do not claim automatic discovery or live projection completion: source-path
  attestation remains an independent admission gate.
- If the provider cannot distinguish missing fixed labels from a transient
  source failure using the existing typed boundary, stop and report the
  smallest contract decision instead of swallowing the failure.
