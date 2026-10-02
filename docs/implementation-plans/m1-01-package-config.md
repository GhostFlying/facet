# M1-01 package, strict configuration, and CLI foundation plan

Date: 2026-10-02. Revision: r3 (final inventory alignment).

Status: plan preparation only, pending independent review and coordinator
implementation dispatch. P1-01's reviewed contract freeze is now integrated;
this draft does not authorize production implementation. G0 approved the overall plan at
`caba7c73895a303d329cf3eba1c89557530c38c5`; it does not waive this package's gates.

## Assignment and baseline

- Package: M1-01, W0b; parent [Epic #1](https://github.com/GhostFlying/facet/issues/1).
- Owner: delegated `phase1_plan_author`, `gpt-6.1-sol` / xhigh. Independent reviewer
  is assigned by the coordinator and must not be this author.
- Owned worktree: sibling `../facet-worktrees/m1-01-package-config`; branch
  `feat/m1-01-package-config`.
- Starting base: `2618eafad817aee4e491aa87ebede0f44f27a20b`, checked against fresh
  remote `main`. [P1-00 PR #6](https://github.com/GhostFlying/facet/pull/6) is merged;
  its [main CI](https://github.com/GhostFlying/facet/actions/runs/36971068807)
  succeeded. Those are engineering baseline facts, not G1 evidence.
- Final alignment base: `09031e723af1ef6590dc6746744ee52894501e38`; PR #8 is actually
  merged at that same SHA. Independent reviewer `phase1_plan_review` approved the
  ADR candidate; [PR CI](https://github.com/GhostFlying/facet/actions/runs/36974129495)
  and [main CI](https://github.com/GhostFlying/facet/actions/runs/36974823051) succeeded
  on Python 3.11/3.12. This is a design freeze, not runtime or G1 verification.
- Applicable inputs read: repository AGENTS; development status, product contract,
  project/Gmail/Dashboard/CLI specifications, execution plan, workflow/progress;
  P1-01's full plan and its currently unreviewed core ADR candidate.
- The existing distribution installs only `facet_spike`, supports Python 3.11+,
  and CI runs 3.11/3.12. No production package/config/types/CLI exists. Do not reuse
  the spike CLI's live doctor, masked output or state-creating parser behavior.

The integrated P1-01 revisions are `p1-core-v1` and `p1-writer-v1` at the exact final
alignment base above. This plan has been compared with both exact files; future
contract changes require renewed alignment/review before implementation. Preparation
does not require P1-02 completion; tests using
its shared fake wait for that output, while this package's pure/offline tests do
not import the fake or any future M2 module.

The r1 plan received independent approval at SHA-256
`a128a1f2b2c42c58f020ca527eb4c26f864325e9670428139b6880db33d30b9e`.
The r2 draft clarified managed-state read ownership, mutable-config registration
and bounded types at SHA-256
`ac622db5feb58145f0eb128b7d3c24baabac8f2a0fb281f97f46d7d01525a171`.
This r3 still needs independent plan review: it binds the exact P1-01 r2 inventory
at merged `09031e723af1ef6590dc6746744ee52894501e38`. Its design freeze does not
waive this package's plan/implementation gates. Core file SHA-256 is
`795f80ab672ed4e0130eafc330bc0403981360f2e70bf935579973065c64f2f6`;
writer file SHA-256 is
`5f0e5af9cc238f7967a88590fb53acc91c4697ffa27d19773cc66cf5ccc41368`.
The older `b56cfdd` candidate's changes-requested result is historical, not approval
for missing types. Final merged base/CI/review is recorded in tracking; no report-only
repository commit is needed to make a design freeze a runtime success.

## Outcome, owned files, and explicit limits

Deliver an installable Python 3.12+ production package, dependency-free shared
types, strict offline configuration, and genuinely functioning config validate/show.
The early engineering gate includes read-only schema/template/parser support;
config init and facet init mutations require M1-03 ownership and M1-06 G1 integration.
Retain the independent `facet-spike` entrypoint and experimental state. This is
CLI-01/CLI-08 foundation evidence, not completion of all CLI-01, G1 or G6.

| Owned path | Change and boundary |
| --- | --- |
| This plan | Scope, review responses, tests and durable package handoff |
| `pyproject.toml`, `uv.lock` | Add production entrypoint/package, Python floor, bounded YAML dependency and locked resolution; preserve spike entry and existing locked dependencies where compatible |
| `src/facet/__init__.py`, `__main__.py` | Production version and module/console entry; import has no state/network side effects |
| `src/facet/contracts/__init__.py`, `primitives.py`, `enums.py`, `records.py` | Single definitions of the final bounded core-v1 primitives/enums/closed shared value types; standard library only, not full storage/wire/public DTO records |
| `src/facet/config.py`, `private_paths.py` | Strict config models/load/validation, pure initial-template construction and non-mutating path inspection; no config/DB/token writer |
| `src/facet/cli/__init__.py`, `__main__.py`, `bootstrap.py`, `config.py` | Parser/command registry, local result envelope and validate/show handlers; mutation returns controlled unavailable, no wire/receipt/daemon implementation |
| `tests/unit/test_contracts.py`, `test_config.py`, `test_private_paths.py`; `tests/cli/test_bootstrap.py` | Pure validation and real console subprocess tests, private temporary state only |
| `.github/workflows/ci.yml` | Minimal supported-runtime matrix 3.12/3.13 and production help/config smoke checks; retain spike smoke/all offline tests and existing action pins/permissions |
| `README.md`, `docs/development-status.md`, `docs/phase-1-progress.md` | One coherent implementation handoff by this shared-doc owner: actual package capability, P1-00 integrated/P1-01 actual state, limits/checks/next dependencies; do not rewrite contracts/cards |

Current writable scope is this plan only. Do not modify the other owned paths until
contract freeze, independent plan approval and coordinator implementation dispatch.
Do not edit P1-01 ADRs, P1-02 `tests/fakes/`, root `tests/conftest.py` or fake self-tests.
Other worker evidence reaches shared docs through Issue/handoff, not parallel edits.

M1-02 owns SQL schema/repositories/migration and DB initialization. M1-03 owns UDS,
writer/view/maintenance locks, durable commands/digests/request journal/receipts,
config apply execution, and runtime integration. M1-01 owns the closed mutable-config
field registry, initially empty; no unregistered field is accepted for apply.
M1-04 owns OAuth/binding/credential files.
M1-05 owns public DTOs, fixed diagnostic messages and production logging. M1-06
owns full rule normalization/PSL/authentication, integrated init/doctor. Config init
and facet init must become actual safe initialization commands at M1-03/M1-06 G1
integration; no auth/status/doctor/run or config apply is advertised as implemented
here. Unknown/unavailable commands return a controlled result, never call the spike.

## Shared contract implementation and compatibility

Consume the exact bounded inventory in the reviewed core candidate above once
integration freezes it. `contracts/` contains only these allocated public names:

| Group | Exact inventory / test boundary |
| --- | --- |
| Primitives | `ProjectionId`, `LocalId`, `ProviderId`, `Timestamp`, `Count`, `Generation`, `Revision`, `Sha256Hex`, `PolicyVersion`, `ProviderPageToken` |
| Core enums | `Role`, `SourceMode`, `BindingState`, `RestoreState`, `RuleOrigin`, `RuleKind`, `AdmissionOrigin`, `EpochKind`, `EpochState`, `JobKind`, `JobState`, `Priority`, `InsertState`, `OutcomeCertainty`, `Visibility`, `DatePolicy`, `OperationState`, `PreviewPurpose`, `ErrorClass`, `ErrorCode`, `Freshness`, `PublicPhase`, `PublicHealth` |
| Additional enums | `LabelChange`, `ReadTaskKind`, `PartitionState`, `ClaimPhase` |
| Values / closed unions | `RuleRef`, `AdmissionRef`, `EpochDecisionRef`, `PartitionRef`, `PartitionProgress`, `SourceEventKey`, `SourceEvent`, `JobSubject`, `ThreadGenerationGuard`, `Claim` |

Use frozen standard-library dataclasses for validated values and union branches,
with typed unions/enums, immutable fields and explicit primitive validation. No
annotation-only `NewType` is treated as runtime validation. Internal branch helpers
must not create additional business records or an alternate public inventory.
Every field in the ADR inventory is required, including required-nullable fields;
`None` is not an omitted key/default or fabricated ID. Every union requires its
fixed literal tag and permits exactly that branch's fields. Unknown variants,
wrong nested types and extra fields fail controlled validation. Materializing these
values does not implement their repository/state-machine behavior.

Canonical imports are from `facet.contracts`; its `__all__` lists exactly the
inventory above, implemented by `primitives.py`, `enums.py`, `records.py`. Closed
unions are type aliases of their concrete frozen dataclasses; constructor names
in `records.py` follow `<UnionName><PascalCaseTag>`, for example
`SourceEventKeyMessageAdded`, `SourceEventKeyLabelChanged`, `AdmissionRefManualThread`,
`JobSubjectOperationRead`, `ThreadGenerationGuardTracked`. These are constructors
for existing union branches, not additional independent business records or top-level
inventory. Each requires its literal `tag` and exact branch fields. RuleRef,
PartitionProgress, SourceEvent and Claim use their same-name constructors. P1-02
compatibility tests can import the canonical aliases and these branch constructors;
neither side invents a provider protocol or duplicates domain classes.

| Value | Field, nullability and structural guard alignment |
| --- | --- |
| `RuleRef` | Required `rule_id: LocalId`, `revision: Revision` |
| `AdmissionRef` | Four tags exactly equal AdmissionOrigin; initial backfill has epoch/rule/policy, future rule has rule/policy, manual has preview, action has action-command; no fake trusted-auth evidence |
| `EpochDecisionRef` | Six closed backfill/gap/scheduled-or-requested reconcile/audit branches with exactly the operation/preview/ruleset revision fields specified; empty scheduled-target-audit branch has tag only |
| `PartitionRef` | source-window/source-thread/target-catalog/mapped-target-set; only source-thread carries ProviderId |
| `PartitionProgress` | Required partition/state/completed-pages/observed-items and nullable page-token/after-source-message; token only source-window/target-catalog, after-ID only mapped-target-set; not-started counts 0/cursors None, complete clears provider token |
| `SourceEventKey`, `SourceEvent` | Three tagged keys: message-added/deleted have projection/history/message, label-changed also label/change; SourceEvent requires key/observed-at and nullable source-thread. Missing thread is not guessed; History remains opaque string |
| `JobSubject` | All 11 JobKind branches exactly match ADR fields; three mutation/expansion branches have generation >=1; resolve-event carries original key, operation-read carries operation/read-kind, recover-insert carries attempt; scan partitions restricted by kind, no fresh attempt from a read/recovery value |
| `ThreadGenerationGuard` | untracked tag only or tracked with required generation >=1; do not make absent tracking generation 0 |
| `Claim` | Required claim-ID/owner-run/acquired-at/job-revision/phase and nullable thread-generation; ownership/generation relation to actual job is repository/runtime validation, not guessed in a value constructor |

Primitive tests preserve core bounds: ProjectionId safe ASCII 1-64, UUID4 LocalId,
ProviderId nonempty/control-free <=512 UTF-8 bytes, UTC-aware Timestamp, integral
Count/Generation/Revision 0..2^63-1 rejecting bool, 64 lowercase SHA256 hex,
PolicyVersion registry syntax/length and opaque ProviderPageToken <=16384 bytes
without NUL. Syntax validity does not enable policy, prove binding or authorize work.
Same-projection reference resolution, contradictory thread/key rejection and
immutable operation/attempt relationships belong to M1-02's reviewed repositories;
M1-01 tests only the exact shared shape and applicable pure invariants.

Do not generate full Projection/Binding/Rule/DB Job/Intent/Audit/Checkpoint rows,
command records or public snapshots from prose descriptions. Storage records belong
to M1-02, command/wire records to M1-03 and public DTOs to M1-05 through their reviewed
extensions, consuming this minimum core. Provider-result protocol/records are
deferred to M2-01 and must not be guessed or implemented as an undefined ghost type.
Future extensions preserve the full product requirements, not reduce delivery scope.

SourceEventKey equality preserves its complete tagged fields. M1-02's key encoder
and uniqueness implementation must retain the ADR identities for resolve-event
(SourceEventKey), operation-read (`operation_id: LocalId`) and recover-insert
(`attempt_id: LocalId`); this
plan does not invent an unallocated JobKey type or SQL encoder. P1-02's owned
`test_fakes_contract_compatibility.py` must consume the actual merged M1-01 inventory
before its closure/M1-02 release. Standalone provider-fake tests may run earlier,
but neither package skips compatibility and calls the combined gate complete.

Constructors validate primitive bounds/types and cross-field structural invariants
specified by the freeze; bool is not an integer count, History IDs remain strings,
UTC timestamps/counts/bytes/generation/digest versions retain explicit units.
Unknown variant/version/fields are refused. Single core definitions are imported
by later owners and P1-02 tests, not copied into local shadow enums. Core imports
must not reach Google clients, SQLite, config, CLI, runtime, public DTOs or tests.
Do not implement an AUTH pass algorithm or fabricate recovered-insert provenance.

CLI bootstrap uses the core codes/classes and the canonical CLI schema/exit meanings,
but only local result serialization; M1-03 owns command wire and durable envelope
implementation. M1-05 may extend fixed message/allowlist implementation without
duplicating code enums. ADR version mismatch stops implementation for re-review;
the first shared type commit becomes a precise downstream test dependency.

## Strict configuration

YAML has one UTF-8 document, string keys and exactly the five sections from the
[Gmail specification](../gmail-projection-spec.md). Use a private SafeLoader subclass
with explicit scalar resolution, duplicate-key rejection and no custom constructors.
Accept only plain mappings/sequences and expected scalar types; reject Python tags,
merge keys, anchors/aliases, multiple documents, recursive graphs and unknown fields
at every level. Bound input before parsing (1 MiB), nesting (16 levels) and collection
items (1,000) as parser resource guards, not product/mailbox limits. No interpolation,
environment substitution or implicit settings discovery. Parser errors become fixed
codes/known field names, never excerpts of input or arbitrary YAML exception text.

Use standard-library immutable dataclasses and explicit validation rather than adding
a second schema framework. Missing optional sections/fields receive defaults below;
projection ID/source/target are required when validating a usable config. Pure
initial-template construction requires explicit source/target addresses; the future
config init handler uses it, not a secretly accepted placeholder binding. Empty/blank addresses, display names,
multiple mailbox values and control characters fail structural validation. Declared
source and target are compared conservatively for obvious equality; no plus/dot or
own-address alias inference. Actual Google identity/scopes require M1-04/06 live
profile verification; config validity never claims that has happened.

| Field | Default / accepted shape and boundary |
| --- | --- |
| `projection.id` | Required core `ProjectionId` (1-64 safe ASCII characters); init defaults `gmail-default` |
| `projection.source_email`, `target_email` | Required single plain mailbox strings; private declared roles, different; live verification still pending |
| `projection.source_mode` | `readonly`; core `readonly`/`convenience`, configuration never grants modify scope |
| `projection.own_addresses` | Explicit list; default only the declared source, no inferred aliases/settings access |
| `sync.poll_interval_seconds` | Positive integer; default 30 |
| `sync.backfill_lookback_months` | Exactly 6; any other initial-discovery value rejected, historical expansion remains a separate explicit epoch |
| `sync.thread_concurrency` | Positive integer; default 4; actual raw budget/rate-limit scheduler is M2-03 |
| `sync.source_reconcile_interval_hours` | Positive integer; default 24 |
| `sync.target_audit_interval_hours` | Positive integer; default 168 |
| `rules.allow_domains`, `allow_senders`, `blacklist_senders` | Explicit string lists; default empty, no candidate hotel/bank allowlist automatically inserted |
| `rules.authenticity` | Only `require_trusted_auth`; no pass/ignore bypass configuration |
| `target.inbox` | Exact boolean; default false, optional placement does not mirror mailbox state |
| `target.projected_label` | Null or nonempty/control-free string; default null, no label creation/scope inference |
| `web.enabled`, `host`, `port`, `refresh_interval_seconds` | True, `0.0.0.0`, 8080, 10; exact bool, IP literal, integer port 1-65535 and positive integer refresh respectively; container listener does not authorize public host publishing |

Mailbox/domain list validation here is structural, not automatic admission policy.
Nonempty initial rule lists return a fixed `rule_validation_pending` warning until
M1-06's canonical normalizer/PSL validation is integrated; they cannot enter a DB or
authorize work in this package. Config `show` reports counts/mode/operational values
by default; addresses, rule values, label text, projection selector and paths require
explicit `--private-metadata`. Config comments or unknown keys are never echoed.

Defaults and schema are versioned internal config behavior; unsupported declared
schema versions fail, not fall back. Do not add a top-level file schema field unless
the final reviewed core/config interface requires it. M1-01's initial mutable-config
field registry is empty, so all config apply requests are refused; no generic map
or automatic registration of every schema field. Before G1 config-apply completion,
M1-01 registers supported operational fields one by one in a reviewed plan extension
with types/ranges, effect, restart requirement and tests; M1-03 then connects its
executor under the writer protocol. Identity/binding, initial rules, state root,
lookback/auth policy and OAuth scope are not mutable operational shortcuts.
This staging does not remove complete config apply from CLI-01/G1 delivery.

## Private paths and initialization boundary

Default state root is `.facet` relative to the invocation cwd; `--state-dir` selects
an explicit root. Default config is `<state-root>/config.yaml`; explicit `--config`
is resolved relative to invocation cwd, without silently changing the state root.
Future DB/credentials paths remain `<root>/facet.db` and `<root>/credentials/` with
separate role token names. Return typed paths only to local internals; never read or
import `.facet-spike/`, search for tokens, create DB, request journal or credentials.

Non-mutating load/validate/show and help/version do not create directories, chmod,
truncate, touch DB/WAL/lock/token files or call Gmail. Inspect existing paths using
no-follow checks for every traversed component: reject symlink/non-directory state roots, unsafe config links,
wrong ownership or group/world-readable config/state. Do not silently repair user
permissions or resolve a path alias into another ownership domain. Existing ancestor
directories such as cwd are not chmodded. A missing private root reports
uninitialized, not proof that DB/WAL will operate there or permission to create it.

M1-03 exclusively implements the coordinated read-view provider (`view.lock SH`
while reading a coherent managed bundle; never DB writer ownership). M1-01 consumes
that provider after it exists and is reviewed. Before then, default state-root
config reads and any managed-bundle route fail with controlled `owner_unavailable`,
or `maintenance_incomplete` when a known incomplete marker is detected. Do not open
the DB/tokens or read managed config without the provider; missing/unresponsive
lock/socket/PID or apparently absent DB is never an unlocked fallback. Readonly
commands do not create root/lock paths or acquire an independent imitation lock.

Early actual validate/show support pure structural parsing of an explicitly selected
independent config file outside the configured state root, including before any
state is initialized. Output identifies structural-only validation and pending
managed-state/binding checks, not a coherent runtime/config revision. Opening the
independent input uses no-follow directory-relative checks and validates owner/mode/
regular-file identity on the opened descriptor, not an earlier path stat; bounded
read plus descriptor checks refuse observable concurrent input changes. A config
under the state root cannot be reclassified as independent to bypass read ownership.

Presence checks for `locks/`, `bootstrap.json`, DB or maintenance markers only detect
reasons to refuse; their absence never proves exclusive/consistent access. Concurrent
bootstrap or restore must not create a check-then-unlocked-read window: the managed
route stays refused until the shared provider is used, and pure independent parsing
never inspects/claims bundle state even if initialization starts after a check.
Once integrated, the provider keeps view ownership and opened bundle handles through
the read and releases them before a mutation/live request. Tests inject root/marker
creation and inode replacement at check/open/read boundaries; no successful managed
read can emerge from an absence check or second protocol. No claim that the view
lock is already implemented in this package.

Root resolved the cross-package boundary: config init/facet init are stopped
one-shot owner commands under M1-03's stable request-key/receipt protocol. There is
no pre-owner persistent-command exemption. First root/mutex/namespace creation is
specified by the reviewed writer ADR, not an independent M1-01 bootstrap protocol.
This package constructs a typed template in memory and performs only read checks.
It does not mkdir/chmod/write temporary configs or produce successful init receipts.

At G1 integration, the responsible M1-03/M1-06 handler must create owner-only state
(directories 0700, config 0600), no-replace durable config publication, reject
existing/unrelated state and honor stable requests/concurrent ownership. Those
future writer/failure tests remain mandatory, not M1-01 early gate evidence. Do not
reuse spike helpers unchanged: `resolve()` and chmod-on-read violate this boundary.

Local-filesystem suitability cannot be established from a path string or a successful
mkdir. On Linux reject a known NFS/CIFS/SMB mount with controlled input error using
read-only mount information; unknown/platform-specific detection is an explicit
`filesystem_verification_pending` warning, not local-WAL verified. The definitive
WAL/deployment check belongs to M1-02/M1-06/M6. No `--force-network-state` escape.

## CLI foundation behavior

Implement `facet --help`, `--version`, `python -m facet`, and actual offline
`facet config validate/show`. Config init/facet init parser declarations clearly
report `blocked` / `owner_unavailable` (exit 4) with zero writes until M1-03/M1-06
integration; no stub successful initialization. Help distinguishes implemented
reads from unavailable mutations/DB/OAuth/daemon integration. Parse global
selectors/output flags consistently before or after subcommands; ambiguous/duplicate
selectors, `--public` + `--private-metadata`, unsupported public config output and
nonfinite/nonpositive timeout fail with fixed input/guard codes. No root logger/Gmail
client/runtime is initialized during parsing, help, version or validation.

`--json` produces exactly one schema-version-1 document with fixed command/status/code,
allowlisted data and typed warnings. Metadata/help/version can use that envelope when
JSON is explicitly requested; ordinary help/version remain conventional text. Fixed
stderr messages never include argv, parser input excerpts, paths, addresses or stack
traces. Exit 0 means completed config/read result; input errors use 2, confirmation/
selection guards 3, ownership conflict 4 and persistence failure 7. Preserve all CLI
exit categories for future handlers; no fake accepted receipt on filesystem failure.

Future config init in non-TTY requires explicit source/target selectors, `--yes` and
stable request identity under the writer ADR; M1-01's unavailable mutation never
prompts or writes, even with these flags. Non-TTY persistent requests cannot silently
generate inaccessible keys. Private display is opt-in and still forbids credentials,
raw/body/headers/attachment names or provider errors. `--public` is limited to future
aggregate status/doctor DTOs, not a wrapper for config output. No implicit backfill,
OAuth, source/target reads, insert, label mutation, migration or spike state import.

## Packaging, dependencies, and CI

Keep the existing distribution name/version for this focused foundation (no PyPI
publish or release/version decision); adjust description, `requires-python >=3.12`,
Ruff target `py312`, both console entries and Hatch's explicit two-package wheel list.
Both production and spike install on 3.12/3.13; dropping whole-project 3.11 installation
follows the approved production floor, not removal of spike's entry or tests.

Add PyYAML with a bounded compatible 6.x constraint and exact version/artifact hashes
in `uv.lock`; inspect upstream supported runtimes/current release at implementation.
Do not broad-upgrade existing Google dependencies. IDNA is currently locked as a
transitive dependency; this package does not implement domain normalization using
an implicit transitive API. Direct IDNA/PSL dependency and an offline versioned PSL
snapshot belong to M1-06's reviewed rule plan; reserve interface/version fields now,
do not fetch PSL or contact providers on startup/config validation. If a rule helper
becomes an M1-01 prerequisite, extend/review this scope and lock it explicitly.

Local production checks use observed Python 3.13.5 at the available explicit
interpreter and uv 0.12.2, with `--no-python-downloads --offline` once dependencies
are cached. An offline cache miss is a dependency-install prerequisite, not a reason
to claim tests passed or silently download a runtime. Ordinary public package
resolution/download is permitted after implementation dispatch, with no credentials
or mail access; use `uv lock` without upgrade-all and inspect its diff.

Minimal `ci.yml` change replaces obsolete 3.11 with 3.13 while retaining 3.12; installs
locked dev dependencies and executes lint/format/full pytest, both CLI help checks and
a temporary synthetic config subprocess smoke. Keep contents-read permission and
existing pinned actions; no package writes, Gmail secrets, containers or image jobs.
CI's actual 3.12 success is required before integration; local 3.13 does not prove it.

## Acceptance and verification

| ID | Required actual offline evidence |
| --- | --- |
| M101-01 | Locked install and non-editable wheel installation include both packages/entries; import/help/version create no state and do zero network I/O; all existing spike tests and help still pass |
| M101-02 | Default table exact; required roles/obvious equal accounts fail correctly; unknown fields at each level, duplicate keys, YAML coercions/tags/aliases/merge/multidoc/oversize/overdepth are rejected with controlled output |
| M101-03 | Exact primitive/27-enum/10-value inventory and branch fields match frozen ADR; required-nullable omission, bad tag/extra field, partition/cursor/count/positive generation guards rejected; SourceEventKey equality retains label/change/history. No guessed storage/wire/public/provider records or forbidden import dependency |
| M101-04 | Pure template construction produces the exact schema/defaults only in memory; config init/facet init return controlled unavailable with zero writes even on existing/conflicting state; readonly validate/show do not chmod/create; symlink, ownership and permission failures are safe |
| M101-05 | Real console subprocesses test text/JSON, stdout one-document, fixed stderr/exit 0/2/3/4/7 where applicable, flag placement, selector mismatch, non-TTY guards and controlled unavailable mutation, help/version; no direct-handler-only evidence |
| M101-06 | Sensitive synthetic config keys/values/paths and exception text absent from default stdout/stderr/logs; opt-in private fields exactly allowlisted; tokens/body/raw/headers/attachment sentinels forbidden in every output and generated artifact |
| M101-07 | Managed reads unavailable until unified M1-03 view provider; concurrent bootstrap/restore/marker/inode changes cannot fall into unlocked reads; independent config parsing only claims structure. Known network FS refused, uncertain FS warning/pending; no WAL/live/OAuth/G1 claims; spike unchanged |
| M101-08 | CI actually succeeds on 3.12/3.13 with full regression/safety; shared-doc handoff states implemented versus offline-verified versus pending, and later init/auth/doctor/full CLI/G1/G6 are not advertised as done |

Tests use pytest-local temporary directories and synthetic configuration only. Our
tests do not modify root conftest, import future adapters, read real token paths or
store MIME to files. Subprocess network guards and file-tree/hash snapshots prove
zero side effects on help/validate/show/unavailable mutations/failure and preservation
of preexisting state. Inject read/permission/mount-inspection failures and concurrent
bootstrap/restore checks; no failure creates, truncates or repairs state. Assert
managed reads never proceed without the shared view provider, and initial config
apply registry rejects every field. M1-03/M1-06 later test init writes/fsync/races,
coordinated bundle reads and the complete registered config apply path.
P1-02's shared sentinel
helpers may later replace duplicate test mechanics by coordinated reviewed change,
not duplicate Facet business states.

After dispatch and implementation, run locked Python 3.13 sync, frozen Ruff lint and
format, full pytest, both CLI help checks, config subprocess matrix, wheel build/
isolated install checks, `git diff --check` and repository safety on staged/tracked
content. Exact commands/counts/versions and result go to the Issue/PR. Docs-only plan
preparation checks links/fences/whitespace/ownership, not production behavior.

## Sequence, risks, and stop gates

1. Save this plan, create only this ready-to-plan Issue, submit exact hash/base for
   independent review. No source/lock/CI edits while plan/ADR freeze is pending.
2. Record reviewed integrated core/writer revisions and typed-code ownership;
   preserve the resolved M1-03/M1-06 init boundary, update plan if necessary and
   re-review.
3. On coordinator dispatch, implement focused atomic units: dependency-free core
   types; package/config foundation; local CLI/tests/CI and coherent docs handoff.
   Subjects use `feat: impl ...` / `test: verify ...` / `ci: verify ...` as appropriate.
4. Publish a focused Draft PR after actual checks, with exact candidate/base and
   limits. Independent implementation/acceptance review and 3.12/3.13 CI precede
   root-authorized normal integration; do not inherit the plan's approval as code
   approval. Hand off exact type/interface commit to P1-02 and future M1 owners.

Stop and report if frozen ADR differs materially, config init is made to bypass
the reviewed writer/receipt/credential scheme, a type requires arbitrary content
persistence, path inspection cannot fail closed, another owner edits these files, the
dependency/runtime floor cannot install on required CI versions, or rule validation
would require premature live/PSL access. Resolve compatible engineering choices
through review; product/privacy/authority changes go to the user via root.

No live Gmail/OAuth, mailbox mutation, new scopes, host deployment, image workflow,
registry publish, license selection, tag/release, contact with people or automation
is needed or authorized by this package plan. G1-G6 remain open; full CLI, credential
ownership and Compose E2E are later gates even when this foundation is integrated.

## Primary references

Checked read-only on 2026-10-02; primitive documentation is not Facet test evidence.

- [PyYAML documentation](https://pyyaml.org/wiki/PyYAMLDocumentation) and
  [canonical source](https://github.com/yaml/pyyaml): safe parsing primitives; Facet
  must separately test duplicate-key, coercion/resource and schema rejection.
- [uv project configuration](https://docs.astral.sh/uv/concepts/projects/config/)
  and [locking/sync](https://docs.astral.sh/uv/concepts/projects/sync/): Python floor,
  locked versus frozen checks and preserving existing dependency resolution.
- [Hatch wheel builder](https://hatch.pypa.io/latest/plugins/builder/wheel/): build
  backend reference; verify actual two-package installed-wheel contents.
- [Python 3.12 OS interfaces](https://docs.python.org/3.12/library/os.html): file
  creation, no-follow/permission and durability primitives; test local race/failure
  behavior rather than assuming a multi-file operation is atomic.

## Execution appendix — dispatched foundation candidate

The r3 plan above (through Primary references) remains the exact independently
approved prefix, SHA-256
`feeabe53d454c931da343964aa7d0a923508d86d3710a03e7c69dc413d534101`.
Its preparation-only status/conditional freeze language is historical. Reviewer
`phase1_plan_review` approved it against integrated base `09031e7`; the coordinator
then explicitly dispatched implementation on 2026-10-02. This appendix records
execution without changing inventory, ownership, schema or product gates.

- Core atomic commit `78949ce374a5b27cdc1fc30f14bbb39f76dddde7` received independent
  bounded preliminary approval: 47 exports/closed branches, 42 core tests, and
  66 full tests in that core-only snapshot passed. This is not final package or
  CI/integration approval.
- The existing local Python 3.13.5 lacks `_sqlite3`. The coordinator authorized
  the QA owner to prepare an isolated official managed CPython 3.12.13 runtime;
  our separate locked venv verifies SQLite 3.53.1. No system interpreter/settings
  were changed or second runtime downloaded. Full local checks use this complete
  runtime; actual 3.13 coverage waits for CI, not a fake local-runtime claim.
- `uv lock` added only PyYAML 6.0.3 and adjusted supported artifacts for the Python
  floor; existing dependency versions are retained. Its
  [tagged primary source](https://github.com/yaml/pyyaml/blob/6.0.3/setup.py) and safe
  parser documentation were inspected; Facet's own hostile-YAML tests prove its
  stricter behavior. Authorized dependency bootstrap downloads are distinct from
  Gmail-free test execution.
- Current local candidate checks: 149 tests (24 retained spike plus 125 foundation),
  Ruff lint/format 55 files, production/spike help, wheel build and separate
  non-editable installed-wheel entry/import/config smoke. The isolated wheel
  environment is constrained to the production dependencies exported from `uv.lock`.
  The initial offline wheel install encountered a registry cache miss; normal
  dependency retrieval followed by locked dependency constraints succeeded.
- Implemented reads only claim `structural_only`. Default managed reads and all
  init/apply commands remain `owner_unavailable`, with zero writes, no spike
  reading or unfiltered exception output. The StrEnum invalid-value path has a
  subprocess privacy negative control. No credential, DB, owner/view protocol,
  admission, Gmail, image/deployment or complete CLI/G1 capability is claimed.
- Exact final candidate review/3.12+3.13 CI/integration results belong to
  [Issue #7](https://github.com/GhostFlying/facet/issues/7) and its focused PR;
  no self-referential report-only repository commit is necessary.
