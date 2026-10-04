# Production action-label runtime wiring

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
