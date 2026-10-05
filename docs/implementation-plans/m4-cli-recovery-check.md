# M4 recovery inspection and check

Status: integrated in PR #75 at main `e31392151c8b59a8bbb9f053f25063e5cc8e746b`.
Implementation candidate `aa646bb` has independent implementation approval;
the follow-up test-only FD-baseline fix `85f3cb9` also passed independent review.

## User-observable delivery

Add a usable maintenance path for an uncertain Gmail insert without creating a
second writer or retrying the insert:

* `facet recovery list --json` reports aggregate recovery/unknown-insert counts
  from the local SQLite snapshot.
* `facet recovery show --job <id> --private-metadata --json` reports
  the allowlisted typed attempt and its linked recovery job. The selected job
  must be a `recover_insert` job; its typed `JobSubjectRecoverInsert` provides
  the attempt ID and the implementation verifies that lineage.
* `facet recovery check --job <id> --private-metadata --json` performs
  only a target-side RFC Message-ID lookup and readback comparison. It may
  fetch the corresponding source raw message in memory to recompute the
  semantic digest. It never calls target insert, never changes SQLite, and
  returns `not_found`, `unique_match`, `duplicate_candidates`, or a typed
  unavailable/attention result.

The check is explicitly evidence gathering, not authorization to retry. An
unknown result never becomes a new insert attempt. Public output remains
aggregate-only; item IDs and provider facts require the existing private
metadata opt-in. No raw message, subject, sender, credential, provider error,
or target payload is serialized.

## Files and behavior

* `src/facet/cli/__main__.py` and `bootstrap.py`: parse and dispatch the three
  commands, preserving existing sanitized exit codes and fake transport test
  support. Remote check requires verified bindings and credentials; `--fake`
  substitutes only Gmail transport.
* `src/facet/cli/recovery_views.py`: offline read-only list/show views using
  the existing owner-only SQLite snapshot helper. Validate attempt/job lineage
  and reject public item inspection with `scope_required`.
* `src/facet/gmail/target.py` and the credential/read-only runtime seam only if
  needed: reuse the existing RFC Message-ID search and readback adapters; the
  remote check must use a read-only SQLite snapshot and must not acquire the
  sync-owner lease or hold a writer across Gmail I/O. Do not add a generic
  recovery framework or change insert behavior.
* `tests/cli/test_bootstrap.py` and focused recovery tests: command parsing,
  privacy, zero SQLite writes, no insert invocation, unique/duplicate/not-found
  checks, binding/scope failures, and fake transport subprocess behavior. The
  unknown-attempt subprocess fixture must be produced through the existing
  production insert-intent/fault-injection path (or a typed fixture builder
  that invokes the same guarded repository transitions); it must not seed
  readiness, bindings, rules, epochs, mappings, or a fabricated recovery
  result directly into SQLite. Fake transport may replace only Gmail/OAuth
  interaction.
* `docs/cli-spec.md` and `docs/development-status.md`: record this as evidence
  inspection only; leave recovery retry, repair, backup/restore and live
  Gmail verification explicitly open.

## Reuse and non-goals

Reuse `TargetAdapter.find_by_rfc_message_id`, `TargetAdapter.readback`,
`fidelity.inspect`, `CredentialManager.snapshot`, `_open_read_only`, and the
existing typed error catalogue. Do not add a new schema or migration, alter
`AttributionKind`, call `insert`, persist a recovery preview, claim a mapping,
or auto-select recovery jobs. Those require the later explicit recovery
authorization unit because an unknown insert cannot be safely retried from a
read-only check alone.

## Acceptance and stop gates

1. A synthetic subprocess creates an unknown attempt through the production
   insert-intent/fault-injection path, then executes `recovery check --job`;
   target search/readback proves a unique match without a second insert and
   with no DB mutation.
2. Zero, multiple, malformed, missing-RFC, source/target mismatch, and
   provider failure cases remain typed non-success/attention and do not write
   target or DB state.
3. `recovery list/show` are offline, owner-scoped, and do not import Gmail or
   OAuth; public output contains no item identifiers.
4. Focused recovery/bootstrap/credential tests pass; the full candidate CI
   (Python 3.12/3.13 and no-publish image build), Ruff/format/lock/safety and
   wheel smoke pass. No live Gmail operation is performed.
