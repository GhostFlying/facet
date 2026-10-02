# Proposed existing-state migration entry supplement r1

Status: design only; independent review and root dispatch are required before
source changes. Authoring base is
`1b7cd58b4846aab86edcbb781a999abb968d047c`. This supplements the finite existing-state
migration seam in persistence-schema-v1 r3 SHA256
`da2cfcd0081eaca8b102436186c9f5d034947fbf71ca2f0b95a14ee25840cfa0`.
That document, initialization, snapshot_database, read-view r4, the 32-table
production schema and all other reviewed supplements remain unchanged.

## Scope and finite entry

Allocate `src/facet/db/migration_entry.py`, focused
`tests/unit/test_db_migration_entry.py`, finite model/export additions and private
trusted inspection helpers in `schema.py` / `migrations/__init__.py` as necessary.
No CLI, root opener, backup copier, provider implementation, credential operation,
M6 restore/install/rollback or M103 owner-run publication is part of this slice.

The only entry is:

`migrate_existing(connection:sqlite3.Connection, owner:OwnerSessionInfo, *,
backup:MigrationBackupReceipt|None, provider:object|None) -> MigrationResult`.

The target is the compiled current schema, never a caller-selected version.
Exact immutable, private metadata `MigrationResult` contains only:
`disposition:Literal['unchanged','migrated']`, `from_version:SchemaVersion`,
`to_version:SchemaVersion`, `state_instance_id:LocalId`,
`request_namespace:LocalId`. Its repr follows existing secret-safe DB records.
UNCHANGED requires equal versions; MIGRATED requires a registered increasing
step. It is not a WriterSession, command receipt or proof of runtime readiness.

The existing MigrationBackupReceipt's eight required fields remain exactly as
allocated by r3. DatabaseSnapshotInfo is not interchangeable with it. Constructing
either dataclass does not prove filesystem backup completion or ownership.

## Supplied-connection and real maintenance authority

`_MIGRATION_PROVIDER_TYPES` is initially an empty private compiled tuple. No
public registration, callback parameter, environment/plugin import, generic
object duck typing, test predecessor switch or boolean bypass is introduced.
None/unregistered provider fails MAINTENANCE_REQUIRED before ANY SQL inspection.
Wrong exact input types fail INVALID_INPUT without rendering their values.

The future fixed M103/M601 provider has exactly these private class methods:

- `_check_migration_connection(connection, owner) -> None`.
- `_validate_migration_backup(connection, receipt, state:MigrationState) -> None`.

These are fixed implementation methods, not caller callbacks. The first proves
this exact supplied connection is enrolled to this same PID/thread and actual
maintenance actor holding owner EX, view EX, then source and target credential
locks in reviewed order. It also proves no active UoW, refresh participant, live
reader or maintenance/restore conflict. The provider retains locks through the
entire entry and until connection disposition is known. An exact class instance
alone is not such proof; its real filesystem/participant implementation remains
an independent M103/M601 acceptance gate. M102's registry remains empty until
that implementation is reviewed and integrated.

The ownership check is safe to repeat during this entry's own internal SQL
transaction: it verifies the same enrollment/locks, not a blanket assertion that
connection.in_transaction is always false. External UoW/nested migration remains
forbidden; only the entry's recorded BEGIN→COMMIT interval is allowed. It performs
no network, snapshot or credential refresh and cannot release/reacquire locks
mid-migration. The initial connection checks below still require no transaction.

The provider must safely preflight the existing database without creating a root,
DB, WAL or SHM, using the independently accepted stopped/locked no-create
inspection strategy. It supplies a write-capable connection only AFTER identifying
an exact supported schema and acquiring the appropriate complete maintenance
freeze. For an actual upgrade the complete backup is published before opening
that writer connection; an unsupported/partial/unknown DB never reaches a path
that creates a writer or repairs sidecars. A supplied connection's first SELECT
is not itself a no-create filesystem proof. No raw mode=ro/immutable-live shortcut
is enabled here. Production preflight and handoff are future provider duties;
synthetic tests must provide genuine owned temp-file/lock participants.

The connection is exact sqlite3.Connection, autocommit=True, not in_transaction,
query_only=0, an existing local WAL database under the qualified runtime. Do not
turn on WAL for an unknown file, set user_version to match expectations, create
missing schema, call executescript, or call an arbitrary path opener. This entry
sets only safe connection-local flags needed for its inspection/transaction; no
checkpoint, VACUUM, journal-mode change or filesystem repair is permitted.
The provider owns closing on return/error. An uncertain transaction outcome
forces the entry to invalidate/close the connection; it is never returned as a
usable session. Other deterministic refusal does not adopt, delete or replace it.

## Exact private state and supported manifests

`MigrationState` is an exact storage-local immutable record with these required
fields: `projection_id:ProjectionId`, `state_instance_id:LocalId`,
`request_namespace:LocalId`, `schema_version:SchemaVersion`,
`config_revision:Revision`, `source_credential_revision:Revision`,
`target_credential_revision:Revision`, `last_owner_run_id:LocalId|None`.
It is loaded from the singleton projection and exactly two role bindings after
trusted schema inspection, never supplied as authority by a caller. Owner's
instance/namespace must match. Its owner_run_id is the provider-proven actual
maintenance actor; it is NOT required to equal the prior stored last_owner_run_id
and is NOT published by this function. Neither migration nor its receipt grants
ordinary writer attach or dispatch under a new owner run.

Production current manifest is exactly v0001. Production existing-step registry
is empty: there is no supported v0, spike import, downgrade or inferred partial
bootstrap. A higher version returns UNSUPPORTED_VERSION; unregistered older,
zero, empty or partial state returns MAINTENANCE_REQUIRED. Contradictory exact
known-version catalogue/checksum/ledger/identity/FK facts return CONSISTENCY_FAILURE.
All these refusals have no SQL mutation, initialized replacement or backup claim.

Allocate private immutable `_ExistingStep` with only `source: _SchemaManifest`,
`target: _SchemaManifest`, `statements:tuple[str,...]` and `checksum:Sha256Hex`.
`_SchemaManifest` has `version:SchemaVersion`,
`catalogue:tuple[tuple[str,str,str],...]` (trusted type/name/CREATE SQL),
`ledger:tuple[tuple[int,str,str],...]` (version/name/checksum),
`registry_digest:Sha256Hex`. These are compiled constants, never function inputs
or decoded from the DB. The checksum uses existing registry encoding:
SHA256 of UTF-8 statements joined with a single newline and no trailing newline.
Metadata digest/ledger equality, exact catalogue and application_id are all
checked; a matching user_version alone is insufficient.

At most one direct step to the current target is enabled by this finite engine;
no multi-step graph/path selection. A future real predecessor must independently
allocate its exact manifests/statements and compatibility before registration.
The finite engine requires the above identity/binding columns unchanged across
the step; a future step changing them needs a new reviewed extraction contract,
not arbitrary Python migration callbacks.

## Entry branches, backup check and atomic transaction

1. Validate exact types, registered provider and its live connection enrollment
   before SQL; verify connection-local conditions. Inspect against the compiled
   current manifest or the single matching trusted predecessor. Load state and
   compare owner instance/namespace; require foreign_key_check empty and
   integrity_check exactly `ok`. Never initialize on failure.
2. If exact current version, return UNCHANGED with observed identity. No SQL
   BEGIN/DDL/data/ledger/version change, no bundle creation and no backup receipt
   is required. If an optional backup was supplied it is not validated or claimed
   as used; no migration happened. Actual owner/provider enrollment is still
   required: current version does not bypass maintenance ownership.
3. For the one supported predecessor, require exact MigrationBackupReceipt.
   Compare its instance, namespace, schema version, config and both credential
   revisions to loaded state. Bundle ID/digest alone are not proof. Call the
   fixed provider's `_validate_migration_backup` BEFORE BEGIN; it validates durable
   owner-only complete manifest/files, hashes, actual config/bindings/accounts
   and both credential revisions under the same uninterrupted held freeze.
   A receipt from another root, state, namespace, revision, incomplete bundle or
   DB-only snapshot rejects. No provider/bundle, no SQL mutation.
4. Begin one explicit BEGIN IMMEDIATE. Re-inspect predecessor/state and require
   equality with pre-backup state, including prior owner run. Check the provider's
   ownership remains held, without network or backup creation. Apply the exact
   registered statements individually with execute. Update schema metadata,
   ledger and user_version to the target's compiled facts in the SAME transaction.
   The registry supplies all values; the source DB cannot nominate migration SQL.
5. Before COMMIT, inspect exact target catalogue/metadata/ledger, integrity and
   foreign keys; reload the identity/config/bindings and require unchanged values
   apart from schema_version. No mapping/job/intent/rule content is discarded to
   make validation pass. A trusted step's explicitly designed data changes must
   have their own independent semantic preservation tests.
6. Commit once. Re-inspect trusted target/identity and provider enrollment before
   returning MIGRATED. Never return a successful receipt after a failed final
   check. No owner run, binding verification, namespace, credential or command
   receipt is updated by this entry; later owner admission is a different gate.

Any failure before attempted COMMIT rolls back if the transaction is open.
Successful rollback leaves the prior trusted schema/ledger/user_version/data;
failed rollback closes/invalidates the connection and reports PERSISTENCE_FAILURE.
An exception during COMMIT or post-commit validation is an uncertain result:
close/invalidate, return fixed PERSISTENCE_FAILURE, and require provider-owned
safe reopen/inspection before deciding whether old or target state committed.
Do not infer rollback from an exception, blindly rerun, drop tables, lower a
version or initialize an empty DB. A repeated call after trustworthy inspection
of a committed target returns UNCHANGED, not a second migration.

SQLite rollback proves only its transactional schema/data changes. Complete
bundle publication, credential files, directory sync and image rollback are
outside this transaction. Rollback to an incompatible old image requires the
validated complete bundle and separately reviewed M6 install procedure; no
automatic file copy/overwrite/restore is allocated here.

## Test-only predecessor and paired evidence

Tests may patch the two private compiled manifest/step constants and provider
type tuple only in an isolated test engine. The fixed synthetic predecessor
uses schema version 9001 and target 9002 with the same production business tables
and identity/binding columns, an explicitly test-labelled metadata/ledger, and
one fixed target-only index on rule_revisions(projection_id,effective_at).
Its exact catalogue/statements/checksums are fixture constants, not read from
the DB. It is never production v0/v1, included in package exports, accepted by
CLI, selected with an environment variable or a user-supplied SQL file. No test
registers it in the production registry artifact. Missing actual M601 capability
is not simulated as already production-complete.

MG01: real current v0001 state + legitimate test-only maintenance participant
returns UNCHANGED, no SQL writes/version/ledger change, no backup created; missing
provider refuses even with a syntactically valid receipt.
MG02: unknown/zero/empty/partial/future schema and foreign application ID refuse;
snapshot all existing paths/bytes before provider preflight and after failure;
no empty replacement, new sidecars or removal of the old file is acceptable.
MG03: synthetic 9001→9002 with real private coordinated fixture bundle and
matching manifest proof succeeds; marker data, mappings/jobs and metadata survive
reopen, target index and complete ledger match exact fixture constants.
MG04: bare dataclass/DB-only snapshot, wrong digest/role revision/instance/
namespace/config/account, missing credential participant and interrupted backup
all refuse before BEGIN, with zero source mutation. Normal cleanup of owned
temporary fixture output is not a production backup implementation.
MG05: changed state between backup and BEGIN or lost lock enrollment rejects;
the backup cannot authorize migration of a newer state. No network is called.
MG06: fault after each DDL/data/metadata/ledger/version boundary and caught failure
restores exact prior logical state on rollback/reopen, including foreign keys;
the fixture target with a deliberate FK violation cannot commit.
MG07: actual child-process death before COMMIT and after COMMIT; parent reacquires
locks and inspects, observing a complete predecessor or complete target, never
partial schema. A wrapper-thrown exception alone is not crash-durability proof.
MG08: COMMIT/rollback/final-inspection error invalidates supplied connection;
uncertain outcome cannot be reported successful or automatically rerun. After
safe target reopen, current-version call is a no-op, not another backup/migration.
MG09: production installed wheel contains only approved production manifest,
empty predecessor/provider registrations, no fixture migration or runtime switch;
fixed errors/repr/public rejection contain no private IDs, paths or SQL text.

These tests prove only the finite library and test participant composition.
Actual M103 lock ownership/startup and M601 durable complete-bundle issuer and
preflight must be independently implemented/accepted before production migration.
The existing internal snapshot primitive remains NOT a complete backup.
Predecessor snapshot compatibility is also not inferred: the current primitive
accepts an inspected current-schema WriterSession, not an arbitrary old version.
Before registering a real future predecessor, M601/M103 must independently
qualify its exact stopped snapshot/manifest adapter; this supplement does not
loosen snapshot_database or fake an older WriterSession. Synthetic predecessor
tests use SQLite backup API in their fixed test participant, with exact fixture
schema inspection, not the production helper under a false current version.
DB21 actual read-provider gates are not waived. Restore's intent-aware job/claim/run
disposition gap remains explicitly deferred; this document allocates no restore
transition, command receipt replay, new schema version or production predecessor.
