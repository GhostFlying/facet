# OAuth reauthorization for an already-verified role

Date: 2026-10-06. Revision: 4. Status: awaiting independent plan review.

## Goal and observed failure

`auth authorize --role source` currently assumes a first authorization. When a
role binding is already `verified`, a fresh request can be accepted as if it
were recovery and then stop with `consistency_failure` before opening OAuth.
The production symptom is an accepted operation with no credential change.

Add the smallest role-specific reauthorization path for an explicit, new
request while preserving initial authorization and fake/offline behavior.

## Bounded design

- In `src/facet/cli/bootstrap.py`, distinguish a new request for a verified
  role from recovery of the same request. A same-request accepted operation
  with no `credential_changes` row is a typed `REQUEST_OUTCOME_UNKNOWN` (or
  equivalent maintenance stop), never generic `CONSISTENCY_FAILURE`. A row in
  `requesting`/`attention` remains a typed maintenance/outcome-unknown stop;
  `validated` or `committed` is the only same-request recovery that may finish
  the operation. A new request must proceed to OAuth instead of entering the
  initial-binding recovery branch.
- Register the new request as `auth_reauthorize` with a distinct stable
  operation digest/version, retaining role, binding revision, current
  credential revision, and scope-policy revision in `operation_auth`. Keep
  request-id, owner-lock, config-digest, and cross-command conflict checks.
  Completion must accept this command only through a narrow reauthorize
  completion function; initial `auth_authorize` completion remains unchanged.
- The interactive sequence is fixed: (1) accept the new reauthorize
  operation; (2) open the existing loopback OAuth authorizer with the role's
  existing policy scopes; (3) receive `OAuthResult(secret, granted_scopes)`;
  (4) call the existing profile probe with that secret and require configured
  account equality and exact expected scopes before any credential file or
  binding publication; (5) begin the durable credential change under the owner
  lock with `operation_id`, `old_revision=current binding.credential_revision`,
  `new_revision=old+1`, while `binding_revision` remains the current role
  binding revision (unchanged), together with the current policy revision; (6) atomically
  publish the owner-only envelope; (7) CAS-publish the verified binding and
  commit the change; and (8) complete `auth_reauthorize`.
- If OAuth callback, token exchange, expiry, account, or scope validation fails
  before step 5, close the accepted `auth_reauthorize` operation as
  `rejected` with the typed error and `effect_completed=0` in the same writer
  protocol. This is not an unknown outcome: no credential file, binding, job,
  or Gmail operation has been published. A caller may retry with a new request
  key; replaying the rejected key returns its recorded typed result. If the
  operation or credential publication becomes uncertain after step 5, retain
  the existing attention/unknown recovery path and never create a second
  change for the same operation.
- Extend the narrow `CredentialManager.refresh` path with optional
  `operation_id`, parent/current revision CAS, and an explicit grant-kind
  override for this OAuth flow. Although the storage change uses the existing
  refresh publication/CAS machinery, an interactive OAuth replacement records
  `grant_kind=AUTHORIZATION_EXPLICIT`, not `refresh_*`; `grant_parent_revision`
  is null for this explicit grant. Existing background refresh continues to
  record `REFRESH_EXPLICIT`/`REFRESH_OMITTED_INHERITED` unchanged.
- On account/scope/expiry/authorization failure before publication, reject the
  accepted operation as above; after a requesting change exists, abandon it
  with its typed error. In both cases leave the old secret, verified binding,
  jobs, and revisions untouched. Publication/CAS uncertainty uses the existing
  attention path. Do not alter initial `authorize_role`, `auth --fake`,
  setup, scope policy, account binding, source/target roles, or Gmail API
  behavior. No direct DB credential mutation is permitted.

## Files and tests

- `src/facet/cli/bootstrap.py`: verified-binding request branch and durable
  operation completion.
- `src/facet/db/command_store.py`: narrow reauthorize operation registration /
  completion, preserving existing auth-authorize semantics.
- `src/facet/gmail/credentials.py`: optional operation lineage for refresh,
  with existing refresh CAS/error recovery unchanged.
- Focused synthetic CLI/manager tests: new verified-binding request reaches the
  OAuth seam, account/scope mismatch fails before credential publication,
  successful reauth increments only that role's credential revision and keeps
  binding/jobs, same-request accepted-without-change is typed
  outcome-unknown, same-request validated/committed recovery is idempotent,
  unknown change phase is typed maintenance, and initial authorize/fake tests
  remain unchanged.

## Acceptance and stop gates

- Offline tests prove the new verified-binding request creates an
  `auth_reauthorize` operation with the reauth digest and durable
  `credential_changes(kind='refresh', operation_id=...)` only after
  `OAuthResult` profile/account/scope validation; the row records
  `grant_kind=authorization_explicit`, null parent revision, and the exact
  current→current+1 CAS. Pre-publication failures are durable rejected
  operations with typed codes, not accepted/no-change residues. No secret or raw provider response enters
  SQLite/log/output.
- Failure before file publication leaves the old credential and verified
  binding unchanged and records the typed abandoned/attention state through the
  existing manager path. Unknown prior outcomes never create a second change.
- Existing initial authorization, fake authorization, completed replay,
  pending/recovery, lock, request-id conflict, and scope tests remain green.
- No real OAuth, Gmail API, mailbox, deployment, credential copy, or live
  state-volume operation is allowed. Stop if preserving initial semantics
  requires broad migration, scope expansion, or direct credential-table writes.
