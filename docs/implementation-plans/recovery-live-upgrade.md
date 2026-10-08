# Existing test deployment: recovery upgrade and bounded diagnosis

2026-10-08. User now explicitly requests updating the existing real deployment
and checking remaining unhandled work. This supersedes the prior unit's no-live-
operation boundary for this selected deployment, not its no-blind-retry contract.

## Selected operation

- Install published main `42c586ff1456e919a6c97ab3b434c5a18666b835`, index digest
  `sha256:f8343daef2211209af8150ff93d616dac5802a8367cc1cfc2e01a980fd091b89`.
  Verify anonymous access, source revision/non-root identity and local image ID.
  Published images currently lack an OCI revision label; verify the build's
  commit/digest evidence and actual image source-tree bytes instead, never
  invent a label. Record this packaging limit without expanding this operation.
- Preserve the existing Compose project/volume, bound accounts, enabled rules,
  action-label configuration and selected historical scope. Local proxy remains
  host deployment configuration, not a project feature. Original user checkout
  and its dirty historical-plan file remain untouched.
- Keep the continuous service stopped during backup and diagnosis. Reuse the
  accepted private backup helper: writer owner, SQLite backup including WAL,
  config/credentials/cleanup journal, private permissions and integrity check.
  Retain the prior qualified local runtime as the stopped rollback image.
- Update the private deployment image setting and recreate the Compose service
  without starting an unbounded daemon. Execute one actual production CLI
  `run --once` using the published image and unchanged production state.
  Normal already-authorized History/projection can process new eligible arrivals;
  no intentional new backfill scope, mailbox cleanup, rule override or resend of
  the old unknown. Record a private submission marker before invocation; do not
  resubmit on lost/failed output or kill a potentially dispatched insert.

## Evidence and stop gates

Before/after private metadata snapshots distinguish the expected 13 proof-based
old resolver closures, due unknown check updates, normal new mappings and new
errors. Existing mappings/attempt identities, binding/config, label configuration,
historical scope and stopped generations must be preserved. Current action-label
learning is normal authorized behavior, not blanket replay of old attention.
Known-window History recovery is the existing bounded contract; unknown-gap
approval is not inferred. Stop on a new unknown, unproven old-record mutation,
scope/binding failure or unexpected provider/write result. Do not restore a stale
DB after any Gmail insert; preserve recovery state and report.

After the cycle, inspect remaining job/event/error categories and read-only Gmail
facts under the same binding/scope checks, with IDs/rule values/addresses kept
private and no raw/content persistence. Distinguish current non-action/system
label events, absent source, rule ineligibility, unavailable consumer and real
unknown ambiguity; diagnostics do not requeue, learn, map or insert.

Independent review checks this bounded procedure and any new diagnostic helper;
reuse the already accepted production code and backup/CLI operations. No new
application implementation or repeat full-suite cycle. Keep one current status/
receipt with actual live results; engineering documentation can use the normal
reviewed PR workflow. No release, scope expansion, arbitrary old-job retry or
implicit continuous-service authorization is claimed by this bounded execution.
