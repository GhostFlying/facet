# M1 offline auth-status CLI

Status: implementation candidate in review on `feat/offline-auth-status`.

Implementation scope is limited to `src/facet/cli/auth_status.py`, the
`gmail auth-status` parser/dispatch in `src/facet/cli/bootstrap.py`, and the
subprocess/privacy coverage in `tests/cli/test_bootstrap.py`. The candidate
does not change the database schema or credential publication protocol.

## Delivery

Add the read-only maintenance command:

```text
facet gmail auth-status --json
```

The command reports each configured role's persisted credential state using
allowlisted metadata only: role, binding state, scope-policy mode, last profile
verification timestamp, credential expiry category, and whether a credential
change is unresolved. It distinguishes `verified`, `pending`, `expired`,
`missing`, `attention`, and `unknown`; it never treats token-file existence as
live Gmail health. Private metadata may include the configured role addresses;
default/public output must not.

## Scope and reuse

- Reuse the existing owner-only path checks, read-only SQLite snapshot helper,
  credential envelope decoder/metadata model, binding/config consistency checks,
  and typed CLI envelope/error catalogue.
- Add only the parser/dispatch and a narrow offline view module/tests. No
  CredentialManager refresh, profile probe, OAuth browser flow, Gmail client,
  writer lease, DB mutation, command receipt, schema change, or new public DTO.
- Read both fixed role files and the matching `bindings`/`credential_changes`
  metadata coherently from one read-only snapshot. Provider-unavailable and
  malformed/private-file failures remain fixed typed results without echoing
  paths, account values, tokens, or parser/provider text.

## Acceptance

1. Synthetic initialized states with verified, pending, expired, missing,
   unresolved-change, and malformed credential files return the documented
   categories and controlled exit codes. `--public`/default output contains no
   addresses, IDs, paths, scopes, tokens, or mail details; private output is
   explicitly opt-in and still excludes secrets.
2. The command works while the sync owner is running or stopped, performs no
   Gmail/OAuth import or network access, takes no writer lock, and leaves DB,
   WAL, credential files, and config bytes unchanged.
3. Role/binding/state-instance/config-artifact mismatches are rejected before
   exposing credential metadata. An unresolved credential change is reported
   as maintenance/attention, not silently treated as verified.
4. Focused CLI/privacy/credential tests, full offline checks, Ruff/format,
   wheel/help smoke, safety, and candidate Python 3.12/3.13 CI pass.

Current candidate evidence: the focused subprocess path and the existing CLI,
status/doctor, credential-manager, and codec tests pass. Full offline and
independent implementation review remain candidate gates until the corrected
binding-state handling is reviewed.

## Stop gates

Stop if coherent cross-file snapshotting requires credential refresh, a second
writer, new persistent rows, broader OAuth scopes, or a new output field outside
the existing private/public contracts. Real OAuth and Gmail verification remain
separate explicit operations.
