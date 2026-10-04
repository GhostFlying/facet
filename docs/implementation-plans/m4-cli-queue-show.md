# Read-only queue item inspection

Status: bounded maintenance-CLI unit on top of main `21c17d7`.
It adds one useful per-job diagnostic route without adding queue mutation or
recovery behavior.

## User-observable delivery

Add:

```text
facet queue show --job-id <local-id> --private-metadata --json
```

The command returns the selected persisted job's private maintenance metadata:
job ID, kind, state, priority, attempts, typed error code, created/updated/next
attempt timestamps, and source-thread ID only in the explicitly private local
metadata response. It binds the selector to the configured projection and
returns no raw provider error or mail content.

Public output is rejected with `scope_required`; malformed IDs return
`invalid_input`; a well-formed absent or foreign job returns
`owner_unavailable` without disclosing whether it exists elsewhere.

## Scope and reuse

- Extend the existing `queue` parser/dispatch and reuse the read-only status
  artifact checks and SQLite snapshot path.
- Add subprocess coverage for a real synthetic queued/completed job,
  selector/error/privacy behavior, provider/network guards, and unchanged
  state files.
- Do not enqueue, retry, claim, cancel, recover, alter schema, call Gmail, or
  expose body/headers/addresses/rules/provider payloads.

## Acceptance and stop gates

Focused CLI/status tests, affected tests, full offline suite, Ruff/format,
wheel smoke, repository safety, independent implementation review, and
supported-Python CI must pass. If showing an item requires recovery decisions,
mutation, or message details, stop at this read-only diagnostic boundary and
leave that operation for a later reviewed unit.
