# M1-02 finite existing-state migration entry implementation plan

Status: plan-only candidate awaiting independent review and root source release.
Date: 2026-10-02. Planning base: `a57dd77116ea79b44c177d03bb6b9815a5913795`.
Owned branch: `docs/m1-02-migration-plan`.
Planning/source owner: `phase1_sol_policy_review`, Sol xhigh.
A different Sol xhigh reviewer must assess this exact plan and later source.

## Inputs, actual readiness and scope

The copied [232-line design](adrs/migration-entry-amendment.md) is the previously
independently approved artifact, SHA-256
`3a9fedfcb3cf2fbaa410c982383fd459d8f1f1b73f58992e96883c9ad50042cf`.
Its original proposal/status/authoring observations are historical, not new source
authority. Preserve that file byte-for-byte, the original M1-02 503-line plan
prefix `abc9f87b813cb510205deab5e350c04ab5fa4a24498cceb43f44349125979e4f`,
schema-r3 prefix `da2cfcd0081eaca8b102436186c9f5d034947fbf71ca2f0b95a14ee25840cfa0`
and all result/mapping/read-view/action/restore supplements.

Qualified SQL library input is `16bcd0b99bf1118924b214bf9ded3976813f5e1a`,
historically independently accepted with exact CI 37014341329 success on both
Python 3.12/3.13 and 1188 offline tests. The later finite action candidate
`62d75c0253a6d66710a9d4d4a4b4346b8b55c6db` was inspected as actual frozen source:
1352 offline tests and exact CI 37023546672 passed, but its independent source
acceptance is pending. This planning author implemented that action unit and must
not approve its source. Both inputs remain Draft PR15/unmerged, not whole M1-02,
M1-03/RV11, production provider or G1 acceptance. Root names the independently
accepted actual source input and its CI before migration source starts.

Actual SQL `schema.py` inspects only the exact compiled v0001 catalogue, ledger,
digest, application ID and role/checkpoint shape. `migrations/__init__.py` contains
only pristine v0001 creation; there is no existing-step registry or entry.
`MigrationBackupReceipt` already has exactly eight required fields, while
`DatabaseSnapshotInfo` proves only a checked SQLite snapshot. The actual
`snapshot_database` requires a current-schema owned WriterSession; it cannot
pretend a predecessor/new maintenance run is such a session. These files/models
and the new action hooks were read at exact 62; their migration-related bytes are
unchanged from qualified 16. This slice preserves their existing contracts.

The full ordered project contracts, schema/supplements, writer plan
`3934f2a4d6bc1cf0e0ebf4748cd1ed8be426cc7a04f785ca5d1641ed5beaa64c`,
writer extension `3b9dc3e637ba727589768f0055c746193809f7e0fcd07bc94839dd565a0110c8`
and read-runtime plan
`9d28e18cee3dbaed00c939838686a6b715cefb569c268a4f3e73a0d1cc6c660e`
were read. Their actual complete freeze/preflight/bundle issuer remains pending.
Even accepted finite OS locks cannot mint a migration backup or register a
production migration provider.

Current permission is only this plan and the exact design copy. No source, test,
dependency, shared-status, commit, push or new PR is authorized in this task.
Prioritize root's separately dispatched independent corrected OS source review;
this plan-only unit may pause without modifying the frozen SQL candidate.

## Exact future file allocation

After independent plan acceptance, actual dependency alignment and root release:

| File | Finite allocation |
| --- | --- |
| `src/facet/db/migration_entry.py` | Sole migrate_existing entry, fixed provider gate, state extraction, exact one-step branch and transaction/uncertainty lifecycle |
| `src/facet/db/models.py` | Only exact private MigrationState and MigrationResult records using existing core/scalar validation and sealed repr; leave receipt/snapshot fields unchanged |
| `src/facet/db/migrations/__init__.py` | Private immutable _SchemaManifest/_ExistingStep and compiled current-manifest/empty-existing-step constants; preserve REGISTRY/CHECKSUMS/digest and v0001 creation bytes |
| `src/facet/db/schema.py` | Only private trusted-manifest inspection helpers required by the entry; existing _inspect remains exact current-v0001 inspection, not a permissive predecessor attachment |
| `tests/unit/test_db_migration_entry.py` | Exact values, actual files/WAL, fixed complete synthetic participant, finite test manifests, fault/privacy/no-op and empty-registry controls |
| `tests/integration/test_db_migration_entry_process.py` | Actual child death and parent lock reacquisition/reopen old-or-target checks, bounded process cleanup |
| `tests/integration/migration_entry_child.py` | Fixed synthetic before/after-commit cases only; no product callback, arbitrary SQL/path runner or installed helper |
| This plan | Append actual source-base/input alignment and measured handoff without changing approved design |

Use direct `facet.db.migration_entry` import; no package-wide re-export, runtime
import, connection factory or generic migration dispatcher is needed. Existing
`connection.py`, transactions, repositories/actions, snapshot helper, codecs,
serialization, v0001, read bridge, CLI/private_paths, runtime/auth, shared conftest,
dependencies/CI and shared documents remain outside source scope. If actual
implementation requires another file/API/guard contract, stop for a written
independently reviewed amendment before coding.

## Closed entry and data

Retain only:

```text
migrate_existing(connection: sqlite3.Connection, owner: OwnerSessionInfo, *,
                 backup: MigrationBackupReceipt | None,
                 provider: object | None) -> MigrationResult
```

Connection is exact sqlite3.Connection, autocommit=True, no external transaction,
query_only=0 and existing local WAL under the qualified runtime. No path, requested
target, SQL list, callback, options map or skip/predecessor flag is an input.
Wrong exact types produce fixed INVALID_INPUT without value rendering. Missing
or unregistered exact producer produces MAINTENANCE_REQUIRED before any SQL.

MigrationResult has exactly disposition unchanged/migrated, from_version,
to_version, state_instance_id, request_namespace. MigrationState has exactly
projection_id, state_instance_id, request_namespace, schema_version,
config_revision, source_credential_revision, target_credential_revision and
last_owner_run_id. Load these from trusted schema and singleton/two-role rows,
not a caller copy. Owner instance/namespace must match; the actual maintenance
run may differ from the stored prior run and is never published/borrowed here.
UNCHANGED requires equal versions; MIGRATED one registered increasing direct step.

Private _SchemaManifest/_ExistingStep fields and newline checksum encoding are
exactly the design's compiled data records. Production current manifest is v0001;
production predecessor and _MIGRATION_PROVIDER_TYPES tuples are empty. There is
at most one exact direct step to the current target, not path search or user SQL.
No real v0/v1 upgrade, spike import, downgrade or v2 command schema is invented.

The only future provider methods are _check_migration_connection(connection,owner)
and _validate_migration_backup(connection,receipt,state). A class/dataclass alone
proves nothing. The actual participant must retain uninterrupted owner EX, view EX,
source then target credential freeze, creator/enrolled exact connection and safe
preflight through disposition. It must be safe to repeat ownership checks during
only this entry's own BEGIN interval, without accepting an external UoW. Missing
production M103/M601 preflight/complete issuer keeps the shipping registry empty.

## Fixed branches, no hidden initialization

1. Validate exact inputs/provider and actual enrollment before SQL, then connection
   conditions. Inspect only compiled current/predecessor manifests plus exact
   application ID/catalogue/digest/ledger, integrity=ok, no FK violations and
   singleton identity/role rows. A first SELECT is not no-create preflight proof.
2. Exact current returns UNCHANGED, with no BEGIN/DDL/ledger/version/business
   mutation or backup creation. Optional unused receipt is not validated/claimed.
   Owner/provider enrollment remains mandatory even for this no-op.
3. The single predecessor requires exact eight-field backup revision/identity
   agreement and actual complete-bundle validation BEFORE BEGIN. A DB-only snapshot,
   caller-constructed receipt, released freeze or wrong root/account/revision is
   insufficient. The provider publishes a real complete backup before supplying
   an upgrade writer connection; unsafe/unknown preflight never opens one.
4. BEGIN IMMEDIATE once; re-inspect predecessor and complete state including prior
   run, compare pre-backup facts, and recheck uninterrupted provider ownership.
   Apply only fixed compiled statements individually; no executescript.
   Schema metadata, full ledger and user_version update in this same transaction.
5. Inspect exact target, integrity/FKs and unchanged identity/config/role/prior-run
   facts before COMMIT. No discarded rows to make inspection pass; any registered
   semantic data step requires its own preservation tests.
6. COMMIT once, then exact target/state/provider recheck before MIGRATED. Failed
   COMMIT or post-commit check closes/invalidates the connection and returns fixed
   PERSISTENCE_FAILURE, never a success/WriterSession/readiness receipt.

Before attempted COMMIT, failure rolls back the entire open transaction; rollback
failure closes/invalidates and is PERSISTENCE_FAILURE. Commit/final-check uncertainty
requires provider-owned safe reopen and exact old-or-target inspection, not assumed
rollback, automatic retry, version lowering, file restore or empty initialization.
A trustworthy reopened target returns UNCHANGED without repeating migration/backup.
Deterministic pre-transaction refusal neither adopts nor deletes/replaces state.
Safe connection-local inspection flags are bounded by the design; no WAL setup,
checkpoint, VACUUM, filesystem repair, arbitrary PRAGMA or config/token operation.

## Actual synthetic evidence to implement, not results

Test constants only: exact 9001 predecessor and 9002 target, original production
business tables/identity columns and one fixed new rule_revisions
(projection_id,effective_at) index. Manifests/statements/ledger checksums are pinned
fixture facts, not learned from DB contents. Patch only the engine's private
compiled target/step/provider constants in tests; no installed registration/switch.
Do not attach a fake current WriterSession to 9001. Its fixed test participant
uses SQLite backup API plus exact synthetic predecessor inspection.

The complete synthetic participant uses fresh owner-only test files, actual
owner/view kernel locks and source/target mutex order, exact PID/strong Thread
and supplied connection enrollment, strict config/binding/account metadata and
both role credential fixtures, durable manifest/file hashes and uninterrupted
freeze. This is test evidence, not an implemented production M6 bundle adapter.
Unsupported/missing/unknown preflight snapshots paths/bytes before any RW open;
current no-op measures entry SQL effects separately after valid handoff. Child
helpers deny external network and signal only freshly owned children. No real
credentials/state/mail fixtures or tests are shipped in the wheel.

| Gate | Required paired real-file assertions |
| --- | --- |
| MG01 | Current v0001 + actual complete test ownership returns unchanged; zero SQL writes/BEGIN/version/ledger/business effects/no backup; missing provider refuses before SQL even with a typed receipt |
| MG02 | Empty/zero/partial/unknown/future or foreign application ID and contradictory known catalogue/digest/ledger/FKs refuse; independent filesystem before/after proves no replacement, root/DB/sidecar creation/removal or repair |
| MG03 | Actual 9001->9002 under a published complete private fixture bundle succeeds; typed marker, mappings/jobs/intents/rules, identity/config/role/prior-run facts survive physical reopen; exact index/ledger/digest match |
| MG04 | Bare receipt, DatabaseSnapshotInfo/DB-only file, wrong manifest hash/instance/namespace/config/role/account or missing credential participant/incomplete bundle refuses BEFORE BEGIN, zero source mutation |
| MG05 | Actual state drift after backup/before BEGIN, wrong Thread/fork, released/replaced lock or changed connection enrollment refuses; original backup cannot authorize newer state, no network |
| MG06 | Actual SQL faults after DDL/data/schema-metadata/ledger/user_version boundaries, caught refusal and FK-invalid target roll back all prior effects; reopen proves exact predecessor schema/data/ledger/identity |
| MG07 | Fresh child killed before COMMIT and after COMMIT; parent actually reacquires released kernel locks then safely inspects full predecessor or target, never partial; exception wrapper alone is not this gate |
| MG08 | Real exact-connection COMMIT/ROLLBACK/final-inspection refusal closes/invalidates; no uncertain success/rerun; reopen distinguishes old/target, and verified target no-op causes no extra backup/step |
| MG09 | Fresh noneditable installed wheel: only current production manifest, empty provider/predecessor registries, no 9001/9002 fixture/helper or runtime switch; fixed error/repr/default-public/log/file sentinels exclude content/credentials/provider text/private IDs/paths/SQL |

Faults may use fixed test-only SQLite authorizer/TEMP-trigger controls on the
actual exact Connection, not a subclass accepted by relaxing production validation.
Measure SQL operation boundaries and durable rows, not just marker/error counts.
Before/after child cases use bounded pipes/timeouts and finally cleanup. Signal
only new test-owned PIDs; SIGKILL is not a hardware power-loss/fsync proof.

Retain every original qualified SQL test, including read-session ownership,
same-inode WAL controls, result/mapping/unknown/stop, snapshot and action gates.
After actual reviewed source carry: locked offline dev sync with the qualified
Python 3.12.13 runtime, targeted MG/process tests, full existing-plus-new pytest,
Ruff/format, both CLI helps/JSON version, staged safety/whitespace, fresh
noneditable wheel and Python 3.12/3.13 exact-head CI. Record actual counts/limits;
no skip/xfail, removed test or fake participant may replace a failing gate.

## Sequence, risks and stop gates

Independent exact-plan review -> root records accepted SQL input/base and assigns
finite source ownership -> normal reviewed base carry and pre-code plan commit ->
implement paired MG unit/process controls and library -> independent exact-source
review/CI -> root-gated integration by the separate integration owner. This task
does not reserve or authorize source execution from plan approval alone.

Risks are false bundle authority, unknown DB side effects before recognition,
backup/state drift, manifest permissiveness, partial schema publication, ambiguous
commit/rollback, accidental owner-run publication and private error leakage.
Stop for required extra callable/file, changed receipt/state columns, unsupported
runtime/mount/connection semantics, inability to prove complete synthetic freeze
or no-create rejection, changed product/privacy/authority or actual provider
registration. Root handles missing actual M103/M601/credential/runtime authority.

No CLI or production migration is enabled here. Full M1-02/M1-03/RV11/G1, M6
complete backup/restore/install/image rollback, actual predecessor snapshot adapter,
Gmail/OAuth, host deployment, release/license, images/settings, new chats/automations
or contacts remain separate pending gates. Shared docs remain m103_os_source-owned;
this author submits evidence instead of editing them. Preserve the canonical
36-card DAG/waves/authority and historical actual-model attribution.

## Oct3 qualified input, ownership transfer and pre-code release

Root explicitly transferred this previously plan-only tree from
`phase1_sol_policy_review` to `m103_os_source` (Sol xhigh) and released only the
original finite source/test allocation plus this plan and unchanged design copy.
The old `docs/m1-02-migration-plan` branch remains at its original a57 base. The
new collision-checked `p/luchengxuan/m1-02-migration-entry` branch starts at exact
qualified combined input `a9c4e36de6ad70294002a83e678a2a7cf1b012d6`; no other
worktree, source change or history rewrite was used to adopt the two documents.

Independent nonauthor plan approval binds the original 217-line prefix SHA-256
`2116d042a8065ba44b818eb7f832414e883cf7ebec27ba4c51ab4e3717746af4`
and complete 232-line design
`3a9fedfcb3cf2fbaa410c982383fd459d8f1f1b73f58992e96883c9ad50042cf`.
The full independent plan-review report has SHA-256
`1b999743240f140b12ce5772c0b067b72eadd16974134835b2cd51d0011fea01`.
Both artifacts and the report were read completely; this factual release receipt
is saved and committed before any migration source/test edit.

Exact a9c parents are independently accepted SQL c0bb and accepted main befe.
Combined nonauthor source approval report
`46f66822589ec0d2289534c21c3f886bab766df86e84fccdd75d3f6b381eeff6`
measured 1625 full/73 R3/150 OS/eight actual WAL controls and fresh wheel. Fresh
CI37038807962 passed both Python jobs; both actually checked out `8e703daf`,
whose tree equals a9c. Accepted main befe also has successful main CI37037683010.
PR15 remains Draft/open/unmerged; historical62/246/a410 HOLDs and main36b failure
are retained. Actual migration-related models/schema/registry/snapshot bytes
match qualified16; all other accepted SQL/OS/harness inputs are preserved.

The separate docs handoff froze exact1bb9190 on main befe and its fresh PR23
CI37041715062 started before this migration adoption. Its own acceptance/merge
is separate. Migration uses the exact approved entry/records/private helpers and
three fixed MG test paths only; no API or strategy changes are released. Shipping
migration provider/predecessor inventories remain empty. Actual complete-bundle,
preflight/credential/runtime providers, no-state bootstrap source, restore source,
whole M1-02/M1-03/RV11/G1 and live/deployment/image/release gates remain distinct.
The future focused Draft PR targets `feat/m1-02-persistence`, depends on PR15 and
references Issue9 without closing the whole package. New exact-source independent
acceptance/CI and separate root integration release remain required.
