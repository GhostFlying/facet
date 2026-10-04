# Production CLI sync-path wiring

Status: implemented by PR #53 and superseded for source admission by PR #71.
The original unit was reviewed against its pre-implementation `origin/main`
base and did not authorize a live Gmail run. Its historical acceptance and
the default-unknown statements below describe that CLI-wiring unit; the current
production source-auth provider is documented in
`m1-06-real-source-attestation.md` and is now explicitly composed by the
production runner. No live Gmail operation is authorized by either unit.

## User-observable delivery

After both roles have been explicitly authorized and a backfill preview has been
created, the production commands must no longer stop solely because the runner
is non-fake:

```text
backfill start --preview-id ...
  -> verify the existing source binding and obtain a source profile fence
  -> persist H0/epoch before discovery
run --once
  -> verify both role profiles/scopes
  -> load persisted rules
  -> run the existing ForegroundSync through Google Gmail adapters
  -> return only aggregate receipt fields
```

The default production source-auth provider remains `UnknownSourceAuthProvider`.
Unknown or untrusted candidates must become durable attention and must never
admit a thread or call target insert. No header parser or fake evidence is added
by this unit.

## Files and behavior

- `src/facet/cli/bootstrap.py`: dispatch non-fake `run --once` through the
  existing `ForegroundRuntime`; allow non-fake `backfill start` to use the
  verified source credential and profile fence while preserving request replay,
  preview guards, role/scope checks, and an exact provider-profile/account
  binding check before H0 is persisted.
- `src/facet/gmail/source.py`: reject a provider profile whose account differs
  from the constructor's verified source binding before exposing its History
  cursor to the backfill fence.
- `tests/unit/test_cli_production_path.py`, `tests/cli/test_bootstrap.py` and focused runtime tests: prove the production
  dispatch seam is selected only after binding checks, provider construction is
  injectable/offline, and the command output remains aggregate-only. Existing
  fake closure and preflight tests must remain green.
- `docs/development-status.md`: record exact implementation and offline evidence
  only after the candidate checks pass; explicitly retain the real attestation
  and live Gmail gates.

## Reuse and non-goals

Reuse `CredentialManager`, `GoogleGmailServiceFactory`, `SourceAdapter`,
`BackfillProducer`, `run_foreground_once`, persisted rules and the existing
operation journal. Do not add a daemon, IPC protocol, runtime/native bootstrap,
new capability framework, raw spool, new OAuth scope, automatic refresh side
channel, or live Gmail fixture. Do not treat Gmail headers, profile identity,
or synthetic evidence as trusted source-path authentication.

## Acceptance

1. Existing fake CLI closure, focused CLI/runtime tests, full offline tests,
   Ruff/format, wheel smoke, and repository safety pass.
2. A unit/integration test proves a production command can reach the injectable
   runtime composition only after verified bindings, while missing bindings
   still stop before any provider call.
3. The production path uses the default unknown-auth provider; an unknown
   candidate is not projected and the receipt/DB state contains no raw mail or
   credentials.
4. No test performs OAuth, Gmail network access, target writes, deployment, or
   release operations.

## Stop gates and external boundary

- If provider/profile verification or existing command invariants require a
  schema or contract change, stop and revise this plan before coding.
- Real OAuth account selection, live source/target reads or writes, additional
  scopes, host deployment, and release remain separately authorized.
- Real automatic admission remains blocked until an independently verified
  source-Gmail-path attestation producer exists. This unit records that limit;
  it does not weaken the product contract.
