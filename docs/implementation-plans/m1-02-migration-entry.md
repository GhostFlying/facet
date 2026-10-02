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

## MG native immutable-metadata alignment amendment (plan only)

The first actual MG fixture batch found an existing compiled-schema constraint,
not accepted migration evidence: v0001's `schema_metadata_immutable_columns`
trigger rejects changing schema_version/registry_digest by SQL UPDATE, and its
`schema_migrations_immutable_delete` trigger rejects converting an initialized
v1 ledger into the synthetic predecessor. The batch reported 18 failures and six
value-test passes; most failures occurred during fixture construction. A separate
current no-op failure is a test's positional OwnerSessionInfo construction error
(owner_run_id precedes instance/namespace), not a new data-model contract.

Preserve the original 257-line pre-code plan, 217-line approval and complete
232-line design. This narrow amendment awaits independent review and explicit
root source release. Until then do not implement the following publication or
fixture strategy. Existing dirty source is unqualified; all historical accepted
SQL/OS inputs, production v0001 and shared documents remain unchanged.

Within the same already allocated one-step BEGIN IMMEDIATE interval, after exact
predecessor/state reinspection, replace only the singleton schema_metadata row
using fixed DELETE followed by INSERT. Read its exact original created_at cell
inside that transaction and preserve it byte/value-for-value, together with
singleton=1; only compiled target version/digest differ. Require exactly one old
row and one replacement. No UPDATE-trigger disabling, DROP/rebuild of a production
table/trigger, REPLACE conflict behavior, connection dbconfig toggle, arbitrary
SQL, extra callable/input/record field or additional transaction is introduced.
Every immutable-column trigger remains present and enabled. Append only the one
new schema_migrations row; never update/delete a predecessor ledger row/time.
Target catalogue/state inspection, COMMIT/final-check uncertainty, rollback and
connection disposition remain exactly the approved protocol.

Build the fixed test-only 9001 database as a new fixture from compiled v0001 table
and index statements and actual rows seeded through accepted v1 typed repositories.
Capture all 32 tables before closing the genuine v1 WriterSession. Insert those
same fixed rows into the fresh fixture, with only the explicitly synthetic initial
metadata/ledger facts changed. Install every exact compiled trigger before fixture
publication, then check exact source manifest, integrity and all foreign keys.
This avoids modifying an immutable v1 ledger, relaxing any shipping guard or
attaching a fake current WriterSession to 9001. Original real rules, mappings,
jobs, intents, identities, bindings and their timestamps must compare exactly.
All source/target manifest bytes still differ only by the one fixed target index
and explicitly test-labelled metadata/ledger. No synthetic schema ships.

Add paired native controls proving UPDATE of metadata and UPDATE/DELETE of old
ledger rows still refuse under both manifests, while the fixed transactional
singleton publication succeeds with created_at and old ledger timestamps intact.
Inject a real SQL fault after singleton DELETE, after replacement INSERT, after
new ledger INSERT, after user_version and before COMMIT; rollback/reopen must show
the original singleton, all old ledger rows/times, complete predecessor catalogue,
all 32-table business rows and prior owner. Existing complete-bundle, ownership,
no-create refusal, fork/Thread, SIGKILL, uncertain COMMIT/ROLLBACK, target no-op,
privacy/wheel and every retained baseline gate remain mandatory and unchanged.

Scope remains the existing four production modules, three MG test files, this
plan and untouched design copy. This allocates no production predecessor,
provider, schema-version bump, initializer/provenance policy, restore or CLI.

The exact compiled metadata trigger is BEFORE UPDATE with OLD/NEW inequality
for every metadata column and RAISE(ABORT,'consistency_failure'); old ledger rows
have unconditional BEFORE UPDATE and BEFORE DELETE guards. No compiled v0001
foreign key references schema_metadata, so the fixed singleton replacement
requires no FK suspension or deferment: entry foreign_keys=1 and final empty
foreign_key_check remain required throughout. A read-only disposable native
SQLite diagnostic confirmed UPDATE refusal and DELETE/INSERT rollback restoring
the original singleton/version/created_at under unchanged compiled triggers.
That feasibility probe is not migration-source acceptance or a durable-file test.

### Exact corrective pre-code release receipt

Independent nonauthor Sol xhigh review APPROVED the exact 323-line plan SHA-256
`fd60c0ed5fce0d0fae555de068b374920db550dd4be997fe767a1e8eba9cf33d`.
The complete 123-line review was read, SHA-256
`435e30eec68cbe3217cd7ea08a49a76510b4c7c6164477664ebf0afa7ba8cd4a`.
Its own unchanged-a9 native WAL/FK/trigger five-cut feasibility is only plan
evidence, not 9001/provider/process or complete source acceptance. Root separately
rechecked the plan/prefixes/design and released only this finite corrective
strategy. This receipt and original amendment are committed before any corrective
engine publication or fresh predecessor fixture implementation; existing dirty
source/tests are retained unstaged and unqualified. Preserve all original323,
257/217 and design232 bytes. Initial18fail/sixpass and later29-case partial controls
remain historical/partial results, not retrospectively qualified migration.

## MG02 stopped-WAL test preflight correction (plan only)

This appendix awaits independent nonauthor plan review and explicit root source
release; it authorizes no test edit yet. Preserve all original338 lines (SHA-256
`17ef18d316c726fab27f19425da88340517b496c696064bb2214b308dbafa5ea`), approved323,
257/217 prefixes, exact232 design and the 5af1095 corrective pre-code receipt.
The supplied-connection production engine and empty shipping provider/predecessor
registries are unchanged. Only the existing test participant's preflight strategy
is defective; this is not production opener/provenance or full M6 acceptance.

### Actual causal evidence and current disposition

The author measured 80 focused MG cases passing in 27.36s and all1705 tests
(1625 retained plus80 new) passing in379.88s before discovering this missing WAL
case. The fresh installed wheel SHA-256
`7053796b092e982e6473049fd16085abd9191a1041865f32cf3c9806046e73d6`
also passed its recorded privacy/import/export checks. Keep those historical
passes, the initial18fail/sixpass and later partial results; none qualifies MG02
or the unfrozen source now. No candidate source commit, push or PR was produced.

On CPython3.12.13/SQLite3.53.1 and the owned trusted local test mount, a genuine
Scope first held ownerEX/viewEX and both source-then-target credential mutexes.
Its exact native connection committed user_version=2, with actual native
SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE enabled only to construct the stopped WAL fixture.
After native close and all original holder cleanup, a new genuine Scope reacquired
all four locks. Physical main header remained1; committed WAL inspection returned2,
while both observed ledgers still contained only the original (1,v0001,checksum)
row. This is a refused future/contradictory fixture, not a supported migration.

Actual main/WAL/SHM sizes were843776/4152/32768 bytes. Before/after snapshots covered
the entire original fixture tree, names, device/inode/UID/mode/link-count/size,
mtime_ns and file bytes. Raw original mode=ro observed2 then refused, but changed
only database.db-shm; no name was added or removed. A separate unix-excl readonly
probe had the same defect. EXCLUSIVE locking-mode readonly returned native3850,
with no source delta but no committed-WAL inspection, so it is not a solution.
A separate fresh private DB+WAL copy, without copying SHM, allowed readonly SQLite
to observe committed2 and the original ledger with zero original-tree delta.
These bounded disposable diagnostics prove feasibility only, not new acceptance.

### Finite correction, source isolation and resource bounds

Allocate implementation only in tests/unit/test_db_migration_entry.py and this
plan. Retain the two existing MG process files unchanged unless an ordinary
same-protocol assertion is necessary; no fourth test path or production edit is
allocated. Keep Scope.preflight's return shape, two fixed provider methods and
all entry/record/manifest APIs unchanged. A private test-only context manager may
accept only the actual held Scope and yield its finite inspection Connection;
it is not a path opener, registration seam, callback or installed callable.

Before opening any SQLite handle on an unknown original DB, Scope.held must prove
the same enrolled PID/strong Thread, real root/ownerEX/viewEX and both ordered
credential locks. Require the original database and, when present, both WAL/SHM
to be owner-only regular0600 single-link files with stable physical identities.
One missing sidecar refuses without copy or SQLite inspection. Capture the full
original fixture-tree oracle before any inspection output and retain the freeze
through all captures, copying, inspection, final source comparison and cleanup.

For existing WAL+SHM only, create a fresh owned0700 disposable inspection directory
under the already verified trusted test anchor, outside the original fixture-tree
oracle. It is independently owned test output, never inside the source root or
an existing backup/bundle, and is cleaned in finally on success or refusal.
Copy only the main DB and its exact committed WAL bytes to fresh0600 O_EXCL files
using O_NOFOLLOW/CLOEXEC source descriptors, checked fstat/path/root identities
before and after each read. Never copy or touch original SHM; SQLite may build
only the disposable copy's own SHM. Require distinct source/output device-inode
pairs and no hardlinks/symlink alias, existing target, permission alteration or
source database/sidecar create/delete/rename/chmod/fsync/checkpoint/repair.

The fixed synthetic fixture limit is16MiB each for main and WAL, at most32MiB
copied bytes and64KiB read chunks. Bound the original fixture-tree file bytes to
64MiB before capturing at most two full oracles; these are storage/buffer bounds,
not an RSS guarantee. Use one disposable inspection Connection and at most two
source file descriptors closed in finally. A common8-second monotonic
capture/inspection deadline is checked while copying and by a finite SQLite
progress handler; timeout/native fault is a failing/refused control, never a
skip, fallback, warm-up, retry or permission trick. Qualified local test storage
is required; this is no hard bound for a stalled kernel or NFS/SMB qualification.

Open only the disposable database with native mode=ro, autocommit=True and bounded
busy timeout. Inspect actual WAL-committed version/application/catalogue/ledger/
digest/integrity/FKs and full state against existing compiled fixture manifests;
compare real projection/config/binding/role credential context exactly as before.
No immutable-main ignore-WAL branch or source RW handle may recognize such state.
The existing immutable readonly branch is retained only for genuinely stopped
source state with neither sidecar. Source byte/mtime/identity/name comparison
must hold even when inspection refuses; atime from bounded reads is not claimed.

This detached read image is only a test recognition oracle, NOT a backup receipt,
SQLite snapshot primitive, native-inode provenance issuer or production preflight
adapter. Supported predecessor recognition still invokes the actual SQLite backup
API complete-bundle publication under the same continuous freeze BEFORE the
original writer open. No copied image authorizes migration, no backup is claimed
for current no-op, and no future/unknown fixture reaches original SQLite RW.

### Required paired native controls and unchanged gates

Add fixed stopped-WAL cases using the actual native no-checkpoint-on-close fixture
construction and genuine reacquired owner/view/credential participants, not fake
flags, simulated WAL bytes or connection subclasses. Verify main-header facts
independently from committed-WAL truth; they cannot be an acceptance substitute.

- A paired original-ro detecting negative observes committed future2, refuses
  UNSUPPORTED_VERSION and proves its original SHM mutation, while the corrected
  participant refuses the same fixed condition with complete source-tree equality.
- The nine fixed refused WAL states are unknown0, future2, foreign application1,
  extra view, missing audit_recent index, wrong known metadata digest, extra
  immutable ledger row, namespace drift and config revision drift. Commit only
  the test condition into WAL before stopped close; retain all native guards.
  Wrong digest uses the already approved singleton replacement, preserving its
  created_at; extra ledger uses INSERT, never forbidden old-row UPDATE/DELETE.
  Projection-context mismatch uses actual allowed request_namespace/config drift
  against unchanged private configuration, not mutation of immutable projection
  keys or bypassed foreign keys/triggers. All nine refuse before original writer/
  bundle opening, preserve physical files, and retain fixed private-safe errors.
- Supported current-v1 WAL contains a committed allowed prior-owner change absent
  from main; recognized state must observe that actual value, preserve source
  through preflight and then return UNCHANGED without SQL writes or a backup.
- Genuine known9001 WAL recognition and complete bundle then migration, and known
  target9002 crash/reopen no-op, must consume full committed state rather than
  main-only state. All32 tables/old ledger/timestamps/prior-owner facts remain.
- Missing WAL versus SHM and preexisting non-private/symlink-aliased source files
  refuse before copying, with no additional source change. Genuine disposable
  Connection authorizer denial is a native inspection-fault cleanup control.
  A fixed recursive readonly query must reach the actual monotonic deadline and
  be interrupted by that Connection's real progress handler, not a fake clock,
  caller success/failure flag or shortened acceptance deadline. Both controls
  preserve the source and clean disposable output; kernel contenders stay busy.

Instrument actual sqlite3.connect calls to prove all rejected WAL-source inspection
occurs only in the new disposable tree, never the original SQLite path; source
descriptor reads remain strictly readonly. Retain whole original-tree before/after
equality, including bytes/mtime and paths, without masking SHM or directory changes.
No old case, signal boundary, privacy oracle or production source byte is removed.
Retain all80 existing MG cases, four actual before/after-COMMIT death/control cases,
1625 baseline tests, all earlier faults and the native current/synthetic guards.

After exact plan acceptance/root release, save the pre-code receipt and atomic
plan-only user/noreply commit while preserving dirty source/tests; implement only
this test strategy, run expanded focused/full suites, locked Ruff/format, both CLI
helps/version, safety/whitespace and fresh wheel/privacy/import/empty-registry
checks. New immutable source/PR actual Python3.12/3.13 CI and independent nonauthor
source acceptance remain required. No claims for shipping preflight/provider,
initializer/native binding, whole M1-02/M1-03/RV11/G1, restore or live/deployment
are added. Stop for any additional file/API, lock/connection/schema guard change
or inability to preserve WAL truth and original physical state simultaneously.

### Exact stopped-WAL corrective pre-code release receipt

Independent nonauthor amendment review APPROVED the complete484-line plan SHA-256
`17b9fc430fb56296aea7823066e4171c8e1b94cdcc859c3daf617438bf1c1c93`.
The complete119-line report was read, SHA-256
`d62c5018ef0e647056368567d5825a09c34418564fd437e2eef12c9cb2ce33a0`.
That reviewer authored the original217 prefix but not this new146-line amendment;
it did not reapprove its own prefix or any migration source. Root read the full
report and separately released only the existing unit-test correction and this
receipt; process files retain only their existing same-protocol allocation.
Preserve484/338/323/257/217 and design232 bytes, all staged unqualified source/test
bytes and the previous5af1095 receipt. This plan-only user/noreply commit precedes
every new inspection strategy edit. Native bounds, real progress/authorizer faults,
source no-delta/original-ro paired controls and genuine complete-bundle publication
remain required. Historical80/1705/wheel7053796 precede this counterexample; new
exact source/CI and independent third SOURCE acceptance remain outstanding.
