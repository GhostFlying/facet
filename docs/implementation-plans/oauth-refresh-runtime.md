# Production OAuth token refresh runtime seam

Date: 2026-10-06. Revision: 1. Status: awaiting independent plan review.

## Goal and boundary

Close the confirmed production gap in which an expired access token stops
`run --once`, the daemon, or non-fake `backfill start` without attempting a
refresh-token exchange. This is a credential-maintenance unit, not a new OAuth
framework, provider, scope, or mailbox feature. It must not change offline
`preview`, `status`, or `doctor` behavior and must not add retries around Gmail
insert/read operations.

## File scope and design

- `src/facet/gmail/refresh_exchange.py`: one narrow Google implementation using
  the pinned `google-auth` request transport (`google.auth.transport.requests.Request`)
  and `google.oauth2.credentials.Credentials.refresh`. It accepts only a
  manager-owned `ProviderSecret`; it never exposes a refresh token to a Gmail
  service client or writes files. Provider failures map to existing typed auth,
  scope, network, or persistence errors. The result is a `RefreshResult` with
  explicit granted scopes when the provider supplies them, or `None` to inherit
  the stored policy scopes; an omitted provider refresh token retains the old
  refresh token.
- `src/facet/gmail/credentials.py`: add a manager-owned `ensure_current` seam
  with a bounded short-expiry threshold and an injected exchange/profile probe.
  It invokes the existing single-flight, requesting/validated/committed CAS
  refresh path, then verifies profile account and exact effective scopes before
  envelope publication. Existing explicit reauth and ordinary synthetic refresh
  behavior remain compatible. No SDK-managed implicit refresh is introduced.
- `src/facet/runtime/foreground_runtime.py`: use the same manager seam for both
  roles before profile verification/snapshot and service construction. The
  daemon and `run --once` therefore share one path and one writer/credential
  ownership boundary.
- `src/facet/cli/bootstrap.py`: non-fake `backfill start` obtains a current
  source snapshot through the same seam; preview/status/doctor stay offline and
  never construct the exchange.
- Focused synthetic tests for exchange parsing/error mapping, explicit versus
  inherited scopes, omitted refresh-token retention, expiry/short-remaining
  refresh, source/target isolation, profile/account mismatch before publication,
  CAS/file/commit faults, invalid-grant recovery with jobs and old revision
  retained, and assertions that preview/status/doctor perform no refresh.

## Acceptance, privacy, and recovery

1. An unexpired credential performs zero exchange calls; an expired or bounded
   short-lived credential performs exactly one serialized exchange for its role.
2. Account and scope checks occur before `validated`, file replacement, binding
   revision publication, or Gmail service construction. A mismatch, invalid
   grant, network error, malformed response, or missing required scope leaves the
   old envelope/revision and pending jobs intact with a typed status.
3. Successful refresh uses the existing credential-change CAS and atomic owner
   file replacement, records no provider payload/token in SQLite/logs, and
   preserves the old refresh token when the response omits one. Concurrent
   refresh/auth/backup remains serialized by the existing owner protocol.
4. A failure after publication uncertainty follows the existing validated/
   attention recovery path; it never blindly retries Gmail inserts or creates a
   second change. Re-auth remains the explicit path for `invalid_grant`.
5. The threshold is bounded and documented as a maintenance guard, not a
   latency or token-lifetime guarantee. Long-cycle 401 handling is unchanged.

## Authority and stop gates

Only synthetic/offline tests and dependency/API inspection are in scope for this
unit. No real OAuth, token, Gmail, mailbox, state-volume, deployment, image, or
permission operation is authorized before separate acceptance. Stop if the
installed Google auth API cannot provide explicit refresh results, if profile
validation would require publishing first, if a new OAuth scope is needed, or if
the existing writer/CAS protocol cannot cover refresh and backup ownership.
