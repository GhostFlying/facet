# Fake production-path attestation closure

Status: plan for implementation; base `origin/main` is
`d916b9e54a71e25a4bb4fac8f25d1e5a4261310c`.

## Purpose and user-visible delivery

Make the existing CLI subprocess E2E exercise the same source admission logic
used by production. Fake OAuth/Gmail remains only a transport substitute; the
fake source message must pass the real `DkimSourceAuthProvider` using a
deterministic signed raw fixture and DNS public key. The command path remains:

```text
init -> auth authorize --fake -> rule -> preview (zero target writes)
-> explicit backfill start -> run --once --fake
-> discovery/metadata/raw DKIM admission -> insert/readback/mapping
-> second process run with no duplicate projection
```

No command will seed credentials, verified bindings, rules, epochs, readiness,
or mappings directly in SQLite. No live Gmail/OAuth/deployment/release action
is included.

## Files and bounded changes

- `src/facet/gmail/synthetic.py`: replace the unsigned source raw fixture with
  a checked-in synthetic signed message and public DKIM TXT fixture (no private
  key or credential-shaped material); expose a narrow factory-owned provider
  constructor/DNS seam for offline use.
- `src/facet/cli/bootstrap.py`: remove the fake runner's direct synthetic
  `VerifiedSourceEvidence` construction and use the synthetic factory's
  `DkimSourceAuthProvider`. Keep fake OAuth binding and target transport
  unchanged.
- `tests/cli/test_bootstrap.py` and focused Gmail/runtime tests: prove the full
  subprocess path reaches production DKIM admission, retains zero-write preview,
  durable mapping and restart deduplication; prove unsigned or altered raw
  transport enters attention and never inserts.
- `docs/development-status.md`: update only after exact review/CI with separate
  implemented/offline/live/final evidence levels.

## Reuse and non-goals

Reuse `DkimSourceAuthProvider`, `SourceAdapter` raw identity/size checks,
`ForegroundRuntime`, `ForegroundSync`, existing synthetic OAuth command path,
and target insert/readback. Do not add a new auth framework, private-key
generation, disk spool, schema, retry behavior, or live account operation.

## Acceptance and stop gates

1. A clean subprocess run completes init, fake authorization, rule, preview,
   explicit start, first fake run with one projected mapping, and second run
   with zero new projections; no readiness/rule/epoch/mapping pre-seeding.
2. The first run's candidate uses the real DKIM provider and exact raw/message
   binding; an unsigned or tampered source fixture is attention with zero target
   insert/mapping.
3. Raw fixture bytes and the public key do not enter DB, logs, receipts, or
   public output; repository safety passes and no private key is committed.
4. Focused tests, complete offline tests, Ruff/format, lock, wheel smoke,
   repository safety, independent implementation review, and candidate CI pass.

If fake-provider composition requires changing product semantics or a new
external permission, stop and return the decision instead of weakening the
attestation contract.
