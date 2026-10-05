# Configurable source action labels

Date: 2026-10-05. Revision: 4. Status: approved; implementation candidate under review.
Base: `a888655` (current `origin/main`).

## Goal

Make the names of the three source action labels configurable through the
maintenance CLI while keeping the action vocabulary and the existing defaults
stable. The action metakinds are fixed: `add_sender`, `add_domain`, and
`blacklist`. With no override, the effective names remain `AI/AddSender`,
`AI/AddDomain`, and `AI/BlackList`; an operator may set exact names such as
`Facet/AddSender` through the CLI.

This revision supersedes the earlier proposal for a static `source` config
block. The mapping is private, persisted state changed through the existing
single-writer command protocol, not an independently edited config artifact.
Facet only reads source labels and History. It never creates, renames, deletes,
clears, or otherwise writes a Gmail label, does not broaden OAuth scopes, and
does not require reauthorization of an existing source/target binding.

## CLI and persistence contract

- Add a nested `rules action-label` command family, following the existing
  parser conventions:
  - `set --kind <add_sender|add_domain|blacklist> --name <exact-name>` stores
    or replaces one override.
  - `remove --kind <...>` removes that override and restores the built-in
    default for the kind.
  - `list` is a private, read-only view of configured overrides and effective
    names; it does not contact Gmail.
  Each mutation requires the normal non-interactive confirmation and stable
  `--request-id` used by other CLI writers. Same request ID and payload is
  idempotent; reuse with a different payload is a request conflict.
- Persist mappings in a versioned SQLite table/repository keyed by projection
  and fixed action kind. The row stores the exact configured label name and
  typed mutation metadata; audit the set/remove operation through the existing
  audit path without storing message content, credentials, or provider
  responses. Apply the migration transactionally under the existing state-owner
  and writer lock. An empty table means the three built-in defaults, preserving
  old state and bindings without OAuth reauth or token replacement.
- Validate before the write: only the three known kinds, a non-empty bounded
  control-free exact name, and no duplicate active names. Reject malformed,
  whitespace-only, over-size, or ambiguous values with the existing sanitized
  CLI error. Do not add aliases, globs, substring matching, or a disable mode
  in this unit.

## Bounded schema upgrade (Revision 4)

Inspection of the shipping code found that existing-state migration producers
are intentionally unavailable and the owner accepts only the exact trusted v2
manifest. Therefore do not edit the already-shipped v0001/v0002 SQL, checksums,
or manifests. The recommended path is one compiled v2-to-v3 extension, not a
general migration framework and not storage in an unrelated business table.

- Add `src/facet/db/migrations/v0003.py` with only the projection-scoped
  mapping table and an append-only typed mutation receipt table. Receipts retain
  action kind, set/remove discriminator, request ID, exact private name when
  set, resulting revision, and time. They provide stable replay even after a
  later mutation replaces the mapping. Reject request-ID collisions with other
  existing command/rule mutations rather than sharing or reinterpreting them.
- Extend the compiled manifest registry and schema inspection to recognize both
  exact v2 and v3. Leave pristine initialization at v2: untouched installations
  need no upgrade; v2 runtime/list uses built-in defaults. Bootstrap replay,
  owner attachment, offline status/doctor, and existing writer operations must
  continue to inspect v3 without weakening exact-catalogue validation.
- The first explicit `action-label set/remove` mutation upgrades v2 while
  holding the existing uninterrupted owner lock and after config digest,
  projection, and binding validation. Before DDL, create a new owner-only local
  backup bundle using SQLite's backup API (not a main-DB file copy), the managed
  config, and the complete currently present credential envelope set. Never
  print paths, credentials, or private names in public output. Backup failure
  prevents DDL and mapping mutation; do not overwrite a prior bundle.
- Apply only compiled v3 DDL, append its migration ledger entry, replace schema
  version/digest metadata, and verify the exact target manifest in one owned
  transaction. Retain state-instance/request namespace, accounts, tokens,
  rules, checkpoints, jobs, action events, and existing ledger rows. Interrupted
  upgrade must reopen as exact v2 or exact v3; it must never bootstrap empty
  state or retry an uncertain commit. v1 and unknown catalogues remain blocked.
- Keep generic migration producer enrollment and unsupported general maintenance
  paths unchanged. A small private upgrade helper used only by the explicit
  action-label mutation and the current state owner is sufficient. Restore of
  the backup is operator-directed rollback with the prior image; no automatic
  downgrade or mailbox cleanup is introduced.
- Record typed set/remove receipts plus the existing projection maintenance
  audit entry in the same transaction as the mapping change. Do not change the
  shipped audit enum catalogue or write arbitrary JSON/log payloads.

Additional files: `src/facet/runtime/state_owner.py`, the narrow new upgrade
helper, `src/facet/db/schema.py`, compiled manifest/owner/bootstrap inspection,
and synthetic v2-to-v3 upgrade tests. No real volume is opened by tests.

## Runtime and source boundary

- `GmailSource` receives the effective name map from the persisted mapping
  reader and resolves names by an exact, read-only `users.labels.list` lookup.
  It retains duplicate/malformed provider-response failures and the current
  missing-label behavior; no label-write method or new OAuth scope is added.
- Foreground runtime and action consumption use the same effective map. A
  pending durable action event whose provider label ID belonged to a previous
  name mapping and is no longer recognized must become a typed
  attention/unknown result (or a clearly surfaced blocked configuration
  result), never disappear and never replay as a different action. Already
  consumed events remain durable. Changing a name does not rewrite history,
  migrate old provider IDs, or trigger bulk replay.
- Provider IDs remain observations from the current read-only lookup; the
  persisted contract is the configured name mapping. Existing source/target
  credentials, bindings, and scopes remain valid and require no reauth.

## Scope and files

- `src/facet/cli/bootstrap.py` and the existing command-store/audit modules:
  parser, private list output, set/remove mutation handlers, request-id
  idempotency, confirmation, writer ownership, typed audit, and sanitized
  errors.
- `src/facet/db/` schema migration and repository/model code for the
  projection-scoped action-label mapping. Migration must preserve all existing
  action events and be restart-safe; it must not initialize a new empty state
  on failure.
- `src/facet/gmail/source.py`,
  `src/facet/runtime/foreground_runtime.py`, and the action-consumer seam:
  pass effective names, perform exact read-only lookup, and surface pending
  old-provider-ID attention/unknown outcomes.
- Focused unit/integration/CLI tests for defaults, custom names, persistence,
  idempotency/audit, invalid input, source read-only calls, binding/no-reauth
  compatibility, and pending-event behavior.
- `docs/gmail-projection-spec.md`, `docs/cli-spec.md`, and the relevant status
  or runbook handoff: document the fixed action kinds, CLI commands, default
  fallback, private mapping persistence, exact-name/read-only/no-create
  boundary, migration behavior, and the no-reauth guarantee. Do not describe a
  static config block or automatic Gmail label creation.

## Compatibility and migration

1. Existing installations with no mapping table rows continue to resolve the
   three historical `AI/*` names. Existing bindings, tokens, scopes, mappings,
   and consumed action history are untouched.
2. `set` changes only future source-label resolution. `remove` deletes the
   override and falls back to the built-in name. Neither operation writes
   Gmail or rewrites historical events.
3. Pending events retain their original provider label IDs. If an ID no longer
   matches the effective map, processing records typed attention/unknown (with
   a safe reason and audit) and does not silently drop, reinterpret, or bulk
   replay it. The migration has no mailbox cleanup or claim/adoption behavior.

## Acceptance tests

- Help/dispatch accepts `rules action-label set/remove/list`; list is offline
  and private. Set/remove require confirmation and request ID, are idempotent
  for an identical request, and reject request-ID payload conflicts.
- Empty mapping state yields the three defaults. Set persists each custom exact
  name; list and a fresh process observe it; remove restores the matching
  default. Duplicate kinds/names, unknown kinds, empty/control/over-size names,
  and malformed input fail before any DB mutation.
- Schema migration is transactional and preserves existing action events and
  bindings. Audit rows identify typed mapping changes without raw content or
  provider payloads.
- An offline fixture built from the unmodified v2 SQL upgrades through the
  actual state-owner lock and complete backup path, then retains credentials,
  bindings, request lineage, action events, and ordinary CLI/runtime behavior.
  The original v2 backup opens with the prior exact catalogue; the upgraded
  state opens with exact v3. Fault injection before DDL, during DDL, and at
  commit/reopen proves old-or-target state and no empty initialization.
- Runtime resolves custom names exactly and retains missing/duplicate/malformed
  provider behavior. Synthetic transport assertions prove no Gmail label
  create/update/delete/clear call and no OAuth-scope change.
- A synthetic pending event with an old provider label ID becomes typed
  attention/unknown; an already-consumed event remains durable; no event is
  silently dropped or assigned a new kind. Existing binding fixtures run
  without reauth or token replacement.
- Focused tests, full offline pytest, Ruff/format, and
  `bash scripts/check-repo-safety.sh` pass. No live Gmail, mailbox data,
  deployment, or real credentials are used or claimed.

## Risks and stop gates

- Stop if the mapping cannot use the existing writer, request-id, audit, and
  state-owner protocols without bypassing locks or digest checks. Do not add a
  direct config-file replacement path.
- Stop rather than broaden OAuth, mutate source labels, infer aliases, rewrite
  history, auto-claim unmanaged data, or silently discard pending events.
- Stop and report the smallest contract decision if the migration would require
  reauth, a destructive mailbox operation, or a new public-output field.
- This unit is offline/synthetic only. Implementation starts only after the
  independent plan review approves this exact revision; live Gmail/OAuth/sync
  and deployment remain out of scope.
