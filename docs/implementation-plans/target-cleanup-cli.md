# Explicit dedicated-target cleanup CLI

Date: 2026-10-07. Base: `7b402a4d616b6db8eb262bb07ae1ce5f8732f6eb`.
Owner: root implements; independent Sol xhigh reviews plan and candidate.

## Authorized outcome

The user approved an explicit maintenance-only exception to Phase 1's no-delete
rule and separate `https://mail.google.com/` consent. Deliver executable
`facet target-cleanup preview`, `status --preview <id>` and
`execute --preview <id> --yes --confirm-target <address> --oauth-client <path>`.
Real deletion still requires a separate decision on the actual preview; this
unit only implements/tests the command and may prepare the authorized OAuth
flow. Sync never invokes cleanup or receives broader credentials. No source
mutation, retention policy, duplicate repair, DB reset or insert retry.

## Files and reuse

- `src/facet/maintenance/target_cleanup.py`: finite private preview/receipt
  journal and target-only list/delete workflow, without a main-DB migration.
- `src/facet/gmail/cleanup_oauth.py`: ephemeral full-scope installed-app flow;
  reuse Desktop-client parsing and existing silent callback/state validation.
  Do not change normal credential enums, envelopes, policies or token files.
- `src/facet/cli/target_cleanup.py` and small `cli/bootstrap.py` dispatch:
  reuse managed config, StateOwner lock, binding checks, target-only credential
  manager refresh and access-only Google transport. Status works offline.
- Unit and real CLI subprocess tests with synthetic Google HTTP/OAuth only.
- Minimal contract exception in AGENTS, product/CLI/Gmail/project/phase plans,
  authority ledger and an operator runbook; one current-state handoff.

## Behavior and persistence

Preview/execute use the existing single-writer lock, so sync/auth cannot race
cleanup. Status reads the existing journal query-only without acquiring an owner,
creating files, loading credentials or contacting Gmail. Verify the config artifact and both stored verified bindings before
Gmail; reject same/source account and profile mismatch. Provider calls occur
outside SQL transactions. Preview uses normal target read credentials only;
refresh stays in the existing manager and cannot enlarge scopes.

Fully paginate messages with `includeSpamTrash=true` and drafts without fetching
raw, headers or bodies. Persist fixed message IDs, including the contained
message IDs of drafts, with draft classification for counts. A draft container
ID survives editing, so never delete by draft ID or adopt its replacement message.
Persist counts, projection/state-instance and binding
revision, config digest, 30-minute expiry and request key in one owner-only
SQLite maintenance journal under the managed state. Do not use Gmail estimates
as exact counts. JSON/text output includes aggregates and opaque local preview
IDs only, never provider IDs/accounts/paths or arbitrary errors.

Execute requires that preview, a stable request key, explicit irreversible-delete
acknowledgement (`--yes`) and exact target confirmation before OAuth. Real OAuth
is interactive-only; URL appears only in the controlling terminal, not JSON,
logs or Dashboard. Request only full-mail scope, online access and no incremental
union; validate actual granted scope/token/expiry. No refresh/access token is
persisted, and no normal source/target envelope is replaced. Recheck profile and
binding before deleting. Reject changed/newly conflicting previews. Expiry gates
only the first execution. Persist its request key, exact manifest and confirmation
before dispatch; the same execution may resume after expiry with fresh OAuth and
binding checks. Completed replay returns its receipt before expiry/OAuth gates.

Delete only fixed preview IDs, not newly arrived mail. Use supported per-message
delete calls (including draft-contained message IDs), with automatic retries disabled. Persist each dispatch
before HTTP and confirmation after success. 404 is already absent; other failures
retain pending/unknown progress and stop the operation, without claiming success.
For a restarted execute, an unknown dispatched deletion is checked with a
read-only messages.get with format=minimal and fields=id: absent confirms
completion, present permits the same ID's delete;
auth/network ambiguity stays unresolved. IDs are never replaced or expanded.
Persist request-key/payload identity before deletes and reject key reuse with a
different preview/confirmation. Completed replay does not request OAuth or delete.

Show existing mapping and unknown-insert counts as warnings; cleanup can remove
recovery evidence and cannot be undone via a metadata backup. Preserve all main
jobs, mappings, cursors, generation and insert attempts; clearing target is not
permission to retry unknown inserts or resume sync. An existing private state
backup is required by the live runbook, not a new general backup framework.

## Acceptance and stop gates

- Real CLI subprocess: init/binding command path -> synthetic preview with
  messages/Spam/Trash/draft -> explicit execute -> offline status/replay.
  No direct readiness/binding/rule/epoch seeding to bypass commands.
- Actual locked Google discovery/client with synthetic HTTP constructs list,
  message/draft list and message-delete requests; no send/insert/source mutations/raw reads.
- Faults: pagination failure gives no usable preview; lock conflict, wrong
  account, missing scope, changed binding/config, expiry, no confirmation,
  reused key, mid-delete crash/response loss, unresolved get, new arrivals,
  edited/sent drafts, resume/replay after expiry and status while writer is held.
- Sensitive content/provider/token sentinels absent from journal/output/logs;
  tokens remain memory-only; normal credential hashes and main business rows
  remain unchanged except normal target refresh/owner metadata.
- Focused tests during development; final full offline checks, independent
  implementation review and non-root candidate image CLI validation. Local
  image diagnostics first; PR/CI/integration remain their existing gates.
- Stop live deletion pending actual preview approval. No automatic cleanup,
  broad permanent sync token, silent state repair or phase-completion claim.

Google API references checked on this date:
[messages.delete](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/delete),
[drafts.delete](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.drafts/delete).
