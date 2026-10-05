# M2 recovery resolution — bounded product-path plan

Status: `CHANGES_REQUESTED` after independent review; implementation is paused
pending the target-writer boundary decision below.

## Decision required before implementation

Gmail History has no Facet-writer identity. A pre-dispatch History fence can
exclude an older unmanaged copy, but it cannot distinguish a post-fence
external/manual writer that creates the same RFC/raw message. The existing
contract therefore needs one of these explicit choices:

1. Phase 1 declares Facet the sole target writer (only Facet receives
   `gmail.insert`; competing target-side mutations are unsupported and any
   detected/ambiguous interval remains attention). The fence path may then be
   implemented, subject to the accepted migration artifact and backup receipt.
2. Keep the target non-exclusive. Unknown inserts remain in recovery/attention;
   `recovery check` stays read-only and no candidate is automatically mapped or
   retried until Gmail supplies a stronger provenance mechanism.

No code may resolve unknown inserts until this choice and the corresponding
existing-state migration/backup provider are accepted.

## User-observable delivery

After a production insert loses its response, the existing `recovery check`
must remain read-only. A separately explicit, owner-scoped recovery resolution
may consume a candidate only after an accepted *insert-attribution fence*, not
from RFC Message-ID, fingerprint, account, or mapping equality alone. The
resolution must persist the recovered attribution and mapping atomically,
complete the original and recovery jobs, and be idempotent after a process
restart. Zero candidates, duplicate candidates, source changes, fidelity
mismatch, account/binding mismatch, stopped generations, competing writers,
and expired/incomplete History evidence remain attention and never authorize a
new insert.

This unit does not add automatic retry or a live Gmail operation. It uses the
existing target RFC lookup/readback and source in-memory raw comparison; the
writer transaction starts only after network work finishes.

## Scope and reuse

- Reuse `recovery check` evidence gathering, `fidelity.inspect`, the existing
  insert-intent/result and `verify_mapping` transaction boundaries, stable
  `recover_insert` identity, one-writer ownership, and private CLI scope.
- The concrete attribution candidate for review is a target-Gmail History
  fence: capture the target History ID before dispatch, persist it with the
  insert intent, consume every History page after that fence, and require the
  unique RFC/fidelity candidate to appear as a `messagesAdded` event in that
  interval. History expiry, pagination failure, an overlapping/competing
  writer, or more than one matching event is not attributable. This is a
  proposal for review, not yet an accepted product fact; it must be checked
  against Gmail semantics and the target adapter.
- Add a distinct recovered-attribution value and the finite
  `pending_recovery -> verified` repository branch. Never encode a recovered
  candidate as `direct_response`, a caller boolean, an error string, or target
  IDs alone. The branch must atomically update the attempt, mapping/history/
  ownership/thread-target rows, original/recovery jobs, and audit facts, with
  stale-guard and exact replay checks.
- Because v1 has only `none`/`direct_response` and the current registry has no
  existing-state steps, the implementation requires a reviewed backup-first
  migration for v1/v2 (or a controlled refusal on unsupported state). It may
  not silently recreate the DB or mutate a live schema in place. No raw mail,
  provider payload, candidate list, or credentials may be persisted.
- The CLI grammar must be explicit and durable: a private, request-keyed
  `facet recovery preview --job <id> --request-id <key>` gathers evidence and
  writes no target; a separate `facet recovery resolve --job <id>
  --preview <id> --yes --request-id <key>` performs only an already-authorized
  unique-fence resolution. Same key plus same payload replays the original
  result; a changed key/payload cannot reuse it. A retry that creates another
  insert is a separate, risk-acknowledged policy and is not part of this unit.

## Acceptance

1. Synthetic subprocess creates an unknown attempt through the production
   insert path, records a pre-dispatch target History fence, obtains a unique
   matching target with exact source digest/semantic/readback checks, proves
   the candidate's `messagesAdded` event lies after that fence, and explicitly
   resolves it. Reopening the DB shows one recovered mapping, completed
   original/recovery jobs, and no second insert attempt.
2. Repeating the same request after response loss returns the recorded result;
   stale guards, changed source, duplicate/missing candidates, mismatched
   account/thread/fidelity, stopped generations, and partial/corrupt durable
   rows refuse atomically with no target write.
3. Raw sentinels, subjects, credentials, provider exceptions, unselected or
   ambiguous candidate IDs remain absent from DB/log/public output. The
   selected target ID is allowed only in the private durable mapping and
   private metadata; public output remains aggregate-only.
4. Focused recovery tests, full offline checks, Ruff/format/safety and
   candidate CI pass. Live Gmail, deployment, repair and arbitrary retry remain
   separate authorization gates.

## Stop gates

If target History cannot provide a reliable pre-dispatch fence under the
supported Gmail API semantics, or if the reviewed migration cannot preserve
existing state, stop this unit at the read-only check and report the exact
missing evidence/compatibility decision. Do not encode recovered evidence as
`direct_response`, revive stopped work, or turn an unknown result into a normal
queued insert.
