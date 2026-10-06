# Critical-path simplification and recovery fixes

## Objective

Repair the first runnable foreground sync path and remove deterministic Gmail
event noise without changing the privacy, authorization, writer, persistence,
generation, or unknown-insert contracts. This is a bounded implementation unit,
not a rewrite of the DB/runtime architecture.

## Scope

- `ForegroundSync._poll_history`: recover an active History poll through the
  existing UnitOfWork read path; add a real restart-continuation regression.
- History normalization: discard only deterministic Gmail system-label changes
  (`INBOX`, `UNREAD`, `STARRED`, categories, etc.) before creating business jobs.
  Preserve configured/legacy user action-label events for explicit attention.
- Event resolution: close an untracked `message_deleted` event as consumed with
  its resolve job completed; keep tracked-thread deletion visible for the
  existing source-loss/attention path.
- Action provider errors: preserve typed `ProviderFailure` retry codes and let
  unexpected programming exceptions fail the owner cycle instead of converting
  them into permanent attention. Preserve post-dispatch target unknown-result
  recovery unchanged.

## Verification

- Focused sync/history/action/worker tests, including provider rate/network
  retry, system-label noise, untracked deletion, and active-poll restart.
- Ruff check and format check.
- Repository safety check; full offline suite at candidate boundary.
- No Gmail/OAuth calls, target cleanup, schema migration, new scope, or public
  output changes.

## Deferred simplification

`read_bootstrap`/`read_launcher`/`read_qualification` removal, refresh-exchange
error taxonomy, CLI foreground exception taxonomy, and any model/schema cleanup
remain separate follow-up units after this path is green. `read_views`,
`private_root`, locks, migrations, request keys, and recovery state are not
removed by this plan.

## Stop gates

- Stop if event filtering would hide a configured or legacy action-label event.
- Stop if an unexpected target-insert exception can bypass
  `PENDING_RECOVERY/INSERT_RESULT_UNKNOWN`.
- Stop if tests require changing the product privacy or authorization contract.
