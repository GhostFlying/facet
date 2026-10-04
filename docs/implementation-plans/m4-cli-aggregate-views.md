# Read-only maintenance aggregate commands

Status: bounded maintenance-CLI unit on top of `origin/main` `7beeb95`.
It exposes existing aggregate state without changing the sync path or
pretending to provide item-level repair controls.

## User-observable delivery

Add three offline commands:

- `facet backfill status --json` returns the existing aggregate progress DTO;
- `facet queue list --json` returns queue counts and oldest runnable age;
- `facet review list --json` returns categorized issue groups and counts.

All commands use the existing read-only status snapshot, perform no Gmail/OAuth
or writer activity, and emit no message details, addresses, rules, provider
payloads, credentials, local paths, or raw errors. They report stale/unknown
semantics already present in the DTOs. Item-level queue/review show, approve,
retry, recovery, and repair commands remain separate later work.

## Scope and reuse

- Extend the CLI parser/dispatch and reuse `facet.cli.status.read_status` plus
  its allowlisted serialized DTOs.
- Add subprocess coverage for all three routes, offline provider guards,
  read-only file invariants, and aggregate output shape/privacy.
- Do not add queries, schemas, mutations, item identifiers, Gmail calls, or
  new public models.

## Acceptance and stop gates

Focused CLI/status tests, affected tests, full offline suite, Ruff/format,
wheel smoke, repository safety, independent implementation review, and
supported-Python CI must pass. If a command would need item identity, a write
operation, or new disclosure semantics, stop and leave that later command
unimplemented rather than expanding this unit.
