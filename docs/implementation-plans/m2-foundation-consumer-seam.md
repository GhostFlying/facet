# M2 foundation consumer seam

Status: implementation plan for the first bounded M2 foundation slice.

Base: `5175fb2f552da40c0e165301cdc2c4bab5d76737`.
Approved M2 authority: reviewed revision
`c0acd7151ab109c4f579c181d6c0060186ac252a` (shared cleanup merged in PR 31).

The approved M2 plan requires the first product path to consume the shipping
initialized owner/state, credential/profile/binding verification, the durable
operation journal, guarded backfill preview/start, and the typed action-label
producer. The base currently exposes only the finite v2 bootstrap storage and
pure credential values. Its v2 migration deliberately accepts only bootstrap,
auth, and daemon operation kinds; it has no persisted preview payload or epoch
decision operation. This slice therefore implements the consumer seams that
are representable by the released schema and records the operation-journal
boundary as a stop gate rather than introducing an unreviewed schema fork.

## Scope

Files owned by this slice:

- `src/facet/runtime/state_owner.py`: production state-directory lifecycle,
  existing private-root/owner-lock acquisition, database initialization and
  reopen with the shipped migration/initializer.
- `src/facet/gmail/credentials.py`: owner-only credential envelope loading and
  injected provider profile verification. The manager checks role, projection,
  state lineage, revision, approved scopes and configured account identity;
  it never discovers credentials, refreshes implicitly, or exposes secrets.
- `src/facet/db/repositories/bindings.py`: typed binding verification update
  using the existing binding history and writer transaction.
- `src/facet/projection/actions.py`: closed action-label map/facts/producer
  seam that consumes typed History label events and returns an activation or
  attention value. It does not add a provider registry or execute business
  effects yet.
- Focused unit/integration tests for owner creation/reopen, profile mismatch,
  scope mismatch, credential privacy, and action producer registration.
- This plan and a handoff note; shared schema and migration files are out of
  scope until the M1-02 owner reviews and releases the operation extension.

## Acceptance tests

1. A clean temporary state directory is initialized through the production
   owner and v2 migration, acquires the existing owner lock, reopens through
   the owner lineage, and refuses a second owner. No rows are hand-built in
   the test path.
2. Synthetic credential envelopes are read only from explicit role paths and
   verified against an injected profile provider. Wrong role, projection,
   state instance, account, scope, or revision fails closed without exposing
   credential text. The provider boundary has profile-only calls and no
   send/delete/forward operation.
3. A successful source/target verification updates only typed binding metadata
   through a writer transaction and preserves the existing revision/history
   constraints. The source and target must remain distinct and both roles must
   verify before readiness is reported.
4. Action label values are private typed IDs. A label-added event selects the
   latest valid external sender from typed message facts; own addresses,
   malformed facts, removed labels, duplicate typed facts, and unknown labels
   produce a typed attention/no-op. No raw/body/subject/provider payload is
   accepted.
5. Privacy tests scan database, logs, stdout/stderr and temporary files for
   synthetic credential/body/provider sentinels.

## Explicit stop gate

The shipping v2 schema has no operation payload for `backfill preview` or
`backfill start`, and its command enum/check constraints reject those kinds.
This slice must not add a shadow table, reinterpret `auth_*`, or write direct
SQL outside the M1-02 repositories. Persistent request-id/payload-digest
lookup, preview invalidation, epoch/H0 decision publication, and CLI commands
remain blocked until M1-02 releases a reviewed typed repository/migration
extension. Once released, a follow-up slice will consume it without changing
the owner, credential, or action interfaces here.

## Risks and external actions

- This slice performs no Gmail network call, OAuth exchange, token refresh,
  label mutation, message insert, or target operation. Synthetic profile
  providers are injected at the boundary.
- Credential files are private test artifacts under a temporary directory and
  are never copied into the repository or test output.
- The slice does not claim M2/G2, M1-04, G1, or live Gmail evidence. It is an
  offline implementation input for the subsequent operation/discovery unit.
