# M1 CLI bootstrap and foreground preflight

Status: independently approved; implementation candidate in progress.
Base: `main` at `0a928369c8a1ee4f0684f7e4605899fec42af021`.

## Goal

Make the first production-shaped CLI lifecycle usable without pretending that
OAuth or Gmail synchronization is complete:

```text
facet init -> private config + SQLite owner state -> facet run --once
                                      \-> binding_pending before any Gmail call
```

This is the smallest prerequisite for the already merged `ForegroundSync`
vertical. It does not claim a live sync until credential binding and service
construction are delivered separately.

## Scope

1. Implement `facet init` only, using the existing strict config model and
   `StateOwner.create`. `facet config init` remains an explicit unavailable
   route in this unit; it is not silently aliased and does not create a
   misleading `CONFIG_INIT` journal entry. Require explicit source/target
   addresses and a stable `--request-id`, reject an external `--config`, keep
   the default readonly source mode, and use the fixed owner-only
   `<state-dir>/config.yaml` path.
2. Add a deterministic, bounded config serializer owned by the config module;
   it emits only the reviewed config schema and never serializes secrets,
   provider responses, or arbitrary caller mappings.
3. Add `facet run --once` parsing and a managed-state preflight. It loads the
   private config, opens one `StateOwner`, and refuses with the existing typed
   `binding_pending`/maintenance errors before constructing or calling a Gmail
   adapter when bindings are not verified. A provider/service factory is not
   invented in this unit; the command remains blocked until the OAuth unit
   supplies one.
4. Add subprocess and unit tests for successful initialization, conflict and
   rollback behavior, permissions/privacy, run preflight, and zero provider
   calls. Update the development handoff with exact evidence and remaining
   OAuth/live gates.

## Non-goals and contract boundaries

- No OAuth URL, token exchange, credential file, profile probe, Gmail read,
  Gmail insert, target mutation, label write, backfill start, or real mailbox
  access.
- No new daemon/IPC/request-receipt protocol, native/runtime/read-bootstrap
  layer, scheduler, raw spool, or public status route.
- `StateOwner.create/open` remains the sole initialized-state API; this unit
  does not add a second lock or silently bypass existing writer checks.
- Initialization writes only configuration and empty metadata state. It does
  not authorize disclosure, create rules beyond the current defaults, or
  import spike state.
- This unit requires the caller to provide `--request-id` in every mode; TTY
  request-key generation remains in the later complete command protocol, and
  this bounded bootstrap never generates a replacement key after a timeout or
  response loss. The accepted grammar is exactly the existing `RequestId`
  grammar:
  `rq1_<32 lowercase hex UUID4>_<32 lowercase hex UUID4>`. The first component
  becomes `OwnerSessionInfo.request_namespace`, the second becomes the
  bootstrap operation nonce; owner run/state IDs remain freshly generated.
- The durable local bootstrap journal is the existing `operations` plus
  `operation_bootstrap` SQLite rows created by `_initialize_database_v2`, not
  an IPC broker or a new receipt service. Its `config_artifact_digest` is the
  SHA-256 of the exact canonical serializer bytes. Stopped inspection reads
  those rows under the existing owner lock, compares the supplied request key
  and digest, and permits only the missing `config.yaml` publication to finish.
  This explicit-key-only restriction is temporary for the bootstrap slice;
  the complete G1 command protocol must add the reviewed TTY pre-submit client
  journal/generation behavior, while retries still never re-key.

## File ownership

- `src/facet/config.py`: canonical serializer only.
- `src/facet/cli/bootstrap.py`: init and run command registration/dispatch.
- `src/facet/cli/config.py`: managed init helper and private path checks.
- `src/facet/runtime/state_owner.py`: the existing owner API gains the minimal
  request-seeded create and stopped-bootstrap inspection/recovery methods; no
  second lock/session implementation is introduced.
- New focused tests under `tests/cli/` and `tests/unit/`.
- `docs/development-status.md` and `docs/phase-1-progress.md`: one integration
  handoff after acceptance; no concurrent historical rewrite.

## Acceptance

- A fresh private directory initialized with synthetic addresses contains
  owner-only config, credential/runtime directories, and a valid SQLite state;
  the command returns only aggregate projection metadata and no address unless
  the existing private opt-in is requested.
- `--request-id` is parsed as the closed
  `rq1_<32 lowercase hex UUID4>_<32 lowercase hex UUID4>` form and is
  persisted as the bootstrap namespace/nonce. A response-loss replay with the
  same request key and identical config digest returns the original initialized
  result without a second database; the same key with a different source,
  target, projection, or serialized config returns `request_conflict`.
- Existing config/state, symlink/permission violations, malformed addresses,
  same source/target, and partial config publication return fixed error codes
  without overwriting prior files or leaving a second database.
- `facet run --once --json` against the initialized pending-binding state
  returns `binding_pending` (or the durable maintenance code) with no Gmail
  imports, network calls, provider construction, or database raw-content
  fields. Closing/reopening the state preserves the pending binding.
- Initialization publication is ordered as durable owner/SQLite bootstrap
  first, followed by exclusive/fsynced `config.yaml` publication. If the
  config publication fails, the command returns a fixed persistence/maintenance
  result and leaves the durable DB as an incomplete initialization that a
  matching request replay may finish; it never creates a second state or
  silently rolls back WAL state. Fault injection covers the write/rename/fsync
  boundaries.
- The owner recovery API acquires the same private owner lock, validates the
  persisted request namespace/nonce and config artifact digest from the
  bootstrap journal, and returns a typed completed/incomplete result. A
  matching incomplete result may finish only the missing config publication;
  a mismatched request or digest is `request_conflict`, an active owner is
  `owner_busy`, and malformed/partial DB state is `maintenance_required`.
- The serializer's canonical bytes are hashed before create, stored in the
  SQLite bootstrap payload, and rehashed on replay/reopen; semantically equal
  input is accepted only when it produces the same canonical bytes.
- Focused tests, the complete offline suite, Ruff, wheel/import smoke, and
  repository safety pass on the exact candidate. No live Gmail or deployment
  action is performed.

## Stop gates

Stop and request a product decision if making `run --once` usable would require
new OAuth scopes, a real mailbox, target writes, a second writer protocol, or
weakening the no-content persistence/output contract. The next independent
unit after this one is OAuth/profile binding plus a verified Gmail service
factory; only then can the foreground runner perform an actual sync.
