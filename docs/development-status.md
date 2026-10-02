# Facet development status

Updated: 2026-10-03 (PRC; historical UTC receipts retain their original dates)

This is the durable handoff for autonomous development. Update it with evidence
at the end of each coherent implementation unit. Do not store account addresses,
mail identifiers, private fixtures, tokens, or raw diagnostics here.

## Current state

| Unit | Status | Evidence / remaining gate |
| --- | --- | --- |
| Phase 0 Gmail spike | Complete within its scope | See [redacted results](phase-0-gmail-spike-results.md); production behavior not implied |
| Repository bootstrap | Complete | Public `main` published with account noreply identity; Python 3.11/3.12 offline CI passed |
| Phase 1 execution planning | User G0 approved; plan integrated | Exact approved/merged `caba7c7`; independent review/QA and candidate/main CI passed; not milestone completion |
| P1-00 execution baseline | Integrated | PR #6 exact `2618eaf`; independent plan/implementation review, candidate/main CI passed |
| P1-01 core/writer ADRs | Reviewed and integrated design freeze | PR #8 exact `09031e7`; core-v1/writer-v1, independent review and candidate/main CI passed; no runtime/G1 claim |
| P1-02 test foundations | Reviewed and integrated, including mandatory CT | PR #12 exact `1b7cd58`; independent review, candidate/main CI and 92 core-compatibility cases passed; Issue #5 closed, later feature-consumer tests remain |
| M1-01 package/config/CLI foundation | Reviewed and integrated | PR #11 exact `b1e4ae0`; 287 offline tests, independent whole/closure reviews, 3.12/3.13 candidate/main CI and installed-wheel checks passed; not complete init/CLI/G1 |
| M1-02 persistence | Finite SQL/DB21/action library and combined input accepted, unmerged; whole gate open | Corrected `c0bb4b0` and normal carry `a9c4e36` independently accepted with fresh exact CI; combined 1625 full tests and wheel passed; PR #15 remains Draft/open/unmerged, historical `62d75c0`/`2466834` HOLDs retained; actual provider/RV11, released migration source, restore and whole DB-01..28 remain |
| M1-03 writer/runtime/CLI | Bounded OS foundation and corrected Thread harness integrated; full runtime open | PR #20 exact `ea80db2` and PR #22 exact `befe278` actually merged after nonauthor review and candidate/main dual-Python CI; corrected harness retains production OS bytes, 150 focused/758 full tests; no-state bootstrap source separately released, not accepted provider/actor/receipt/credential integration or running daemon |
| M1-04 OAuth/binding | Early pure values/codec/client parser integrated; full package open | PR #18 actually merged exact `ff77e63`; 120 OP/608 full tests, independent source/head review, wheel and candidate/main 3.12/3.13 CI passed; actual OAuth/profile/files/publication remain |
| M1-05 public status/privacy | Early pure/logging library integrated; full consumer gate open | PR #16 actually merged exact `f209fbe`, independent review and candidate/main CI passed with 488 offline tests; actual DB/auth/runtime/HTTP/DOM/Compose consumers still pending |
| M1-06 authentication/initialization | r2 design approved; not implemented | Trusted production source-path evidence/registry, actual dependencies and complete init/doctor/G1 remain; all-unknown is not final acceptance |
| M1 foundation as a whole | Incomplete | Full persistence, process/view/credential ownership, init/doctor/config apply, authenticated bindings and real status consumers remain; G1 has not passed |
| M2 durable projection | Not implemented | Production workers, fidelity, insert intent, recovery, bounded memory |
| M3 admission/backfill | Not implemented | Rules/authenticity, preview, fixed six-month discovery, durable backfill |
| M4 sync + Dashboard alpha | Not implemented | History/gap recovery, reconcile, aggregate read-only Web UI |
| M5 action labels | Not implemented | Learning, legacy handling, idempotent commands, BlackList cancellation |
| M6 self-hosted v0.1 | Not implemented | One-command Compose, Actions GHCR image, Nginx, backup/restore, bilingual docs, live/deployment/72-hour gates |

Both `facet` and the isolated `facet_spike` are now packaged for Python 3.12+.
Production imports/CLI never adopt spike cursors/tokens. The foundation tests cover
closed types, strict YAML, no-follow private reads and real CLI subprocess
JSON/exit/privacy/zero-effect behavior, alongside all existing spike tests. They
do not verify a production daemon, trusted admission, backfill or rendered Dashboard.

The integrated M1-05 early library adds independent allowlisted public models, a closed
error catalogue/serializer and fail-closed structured logging. It does not expose
HTTP or read actual DB/auth/runtime state. Real snapshots and raw third-party
OAuth/provider logger consumers, browser/DOM and Compose remain later gates;
Issue #14 stays open. M1-04's current pure slice contains closed credential value
models, an in-memory byte envelope codec and a strict Desktop-client parser. It
does not open private files, create capabilities, invoke OAuth/Gmail, fetch profiles,
refresh or publish credentials, or make a production binding ready. Issue #17 stays
open. PR #18's actual integration and successful main CI are recorded below.

The user's latest model policy on 2026-10-02 permits only Sol high/xhigh or Luna
for prospective tasks. Complex design and high-risk independent review use Sol
xhigh; Astra receives no new work or reactivation. Earlier authorized reviews
retain their actual model/reviewer/SHA attribution. G1-G6 remain incomplete.

## Active implementation record

- On 2026-10-02 the user explicitly approved G0 at
  `caba7c73895a303d329cf3eba1c89557530c38c5` and requested multi-agent execution.
  [PR #2](https://github.com/GhostFlying/facet/pull/2) is actually MERGED at that
  SHA via normal fast-forward. Independent technical review/QA and
  [candidate CI](https://github.com/GhostFlying/facet/actions/runs/36968387054)
  passed; [main push CI](https://github.com/GhostFlying/facet/actions/runs/36969107636)
  also passed Python 3.11/3.12. No force, platform merge commit or rule change.
- [P1-00 plan](implementation-plans/p1-00-execution-baseline.md) r2 received
  independent approval at SHA-256
  `b77d4f90d44ea61aad286851454e9db7d98cef0e1c703ad5968470e4d7242bae` before
  implementation. [PR #6](https://github.com/GhostFlying/facet/pull/6) actually merged
  at `2618eafad817aee4e491aa87ebede0f44f27a20b` after independent implementation/
  acceptance approval and [candidate CI](https://github.com/GhostFlying/facet/actions/runs/36970748778);
  [main CI](https://github.com/GhostFlying/facet/actions/runs/36971068807) succeeded.
  The shared current-state
  docs owner and 36 actual package states are in [the ledger](phase-1-progress.md).
  Initial Issues: [P1-00 #3](https://github.com/GhostFlying/facet/issues/3),
  [P1-01 #4](https://github.com/GhostFlying/facet/issues/4),
  [P1-02 #5](https://github.com/GhostFlying/facet/issues/5).
- Independent startup baseline QA on main `caba7c7` passed Python 3.11.2,
  24 offline tests, Ruff lint/format (33 files), spike CLI help and safety.
  This preserves the spike baseline; it is not production Python 3.12/runtime,
  Gmail, Compose or maintenance verification.
- P1-01 [PR #8](https://github.com/GhostFlying/facet/pull/8) actually merged exact
  `09031e723af1ef6590dc6746744ee52894501e38`, after independent reviewer
  `phase1_plan_review` approved the corrected candidate and
  [candidate CI](https://github.com/GhostFlying/facet/actions/runs/36974129495) passed.
  [Main CI](https://github.com/GhostFlying/facet/actions/runs/36974823051) passed
  Python 3.11/3.12. Frozen core `p1-core-v1` and writer `p1-writer-v1` are engineering
  inputs, not evidence that storage/writer/recovery runtime exists or G1 is closed.
- M1-01 [plan](implementation-plans/m1-01-package-config.md) r3 received independent
  approval at SHA-256 `feeabe53d454c931da343964aa7d0a923508d86d3710a03e7c69dc413d534101`
  before coordinator dispatch. The integrated foundation implements 47 canonical core
  exports, strict bounded YAML/config defaults, safe standalone config reads and
  actual `facet config validate/show`, with empty mutable-field registry. Init/apply
  and managed reads are controlled unavailable; no temporary writer/view protocol.
  Local locked checks passed CPython 3.12.13 with SQLite 3.53.1: 149 foundation-snapshot
  tests (24 retained spike plus 125 new), then 287 full tests after the normal merge
  of reviewed P1-02 partial inputs, Ruff lint/format (69 files), both entrypoint help and wheel
  build/non-editable install smoke. Dependency bootstrap used authorized network;
  production tests made no Gmail calls and subprocess guards forbid network/spike/DB
  imports. The preexisting local 3.13.5 lacks `_sqlite3`; it is not a full-runtime
  verification substitute. [PR #11](https://github.com/GhostFlying/facet/pull/11)
  actually merged exact `b1e4ae08f7e361518eaa4f7fb1ae9f7f0b278f28` after independent
  whole/affected-boundary approval and [revised candidate CI](https://github.com/GhostFlying/facet/actions/runs/36980149544).
  [Main CI](https://github.com/GhostFlying/facet/actions/runs/36980646059) passed
  Python 3.12/3.13 at the same SHA. [Issue #7](https://github.com/GhostFlying/facet/issues/7)
  is closed only for this foundation, not Gmail/deployment/G1 or the full CLI.
  The earlier combined candidate `f00cf27` independently passed whole review and
  3.12/3.13 CI, but the coordinator held merge for two parser/help corrections.
  Current revised candidate adds specific child text/JSON help and canonical
  `config apply --file` parsing; apply still reads/writes nothing and returns
  unavailable. Twelve additional subprocess regressions and the required revised
  exact-SHA review/CI passed before integration; the earlier hold is historical.
- P1-02 provider/helper partial [PR #10](https://github.com/GhostFlying/facet/pull/10)
  actually merged exact `c18bfbee09b985ee7b9bb5c230ee2a70427c7edc` after independent
  reviewer `phase1_plan_review` approved the metadata-format correction and
  [candidate CI](https://github.com/GhostFlying/facet/actions/runs/36978399171) passed.
  [Main CI](https://github.com/GhostFlying/facet/actions/runs/36978909460) passed
  at the same SHA. This partial slice supplies synthetic API/fault/privacy helpers,
  not, by itself, a completed P1-02 compatibility gate. M1-01 preserves its atomic core/config
  commits and normally merges that reviewed input without history rewriting;
  the combined tree requires a new whole-candidate review and 3.12/3.13 CI.
- P1-02 mandatory compatibility [PR #12](https://github.com/GhostFlying/facet/pull/12)
  actually merged exact `1b7cd58b4846aab86edcbb781a999abb968d047c`, consuming reviewed
  merged M1-01 types. Independent review, 92 CT cases/379 full offline tests,
  [candidate CI](https://github.com/GhostFlying/facet/actions/runs/36981977390) and
  [main CI](https://github.com/GhostFlying/facet/actions/runs/36982879970) passed.
  Issue #5 closed and the engineering dependency for M1-02 released; this does
  not validate future Gmail/repository/runtime feature consumers.
- M1-02 [Issue #9](https://github.com/GhostFlying/facet/issues/9) / [Draft PR #15](https://github.com/GhostFlying/facet/pull/15)
  is in actual implementation against independently approved schema r3. Values
  and 32-table STRICT/WAL initializer/session slices received independent review,
  including real SQL sealed-snapshot/NUL negative controls. Exact `56eaac6` passed
  450 full offline tests and [3.12/3.13 CI](https://github.com/GhostFlying/facet/actions/runs/36987351921).
  The initial finite-repository candidate `bf0bf0b` was held for audit relationships
  and caught-error rollback defects; corrected `e3eb14b` received independent
  acceptance and exact CI. Subsequent independently accepted/exact-CI slices are
  epochs `397282f`, History lifecycle `a6235f8`, events `a4cf745`, reviewed r4
  private getters/poll revision `07b452c`, expansion epoch work `d7874f3`, and
  History origin-epoch work `0fb0f10`. Known holds were corrected, not waived.
  Insert preparation/dispatch `32c4c66`, recovery claim allocation `f5279c7`, bounded
  SQLite WAL snapshot `c589b4c`, own-child SIGKILL tests `bb27213`, actual result/
  recovery-work recording `d1a89d8`, fact-only target audit `d2fb6a1`, and SQLite
  row-stepping/caught-failure rollback `c03e62f` also received independent slice
  acceptance and exact Python 3.12/3.13 CI. That earlier SQL snapshot passed
  879 full offline tests; [exact CI](https://github.com/GhostFlying/facet/actions/runs/37000255749)
  succeeded. These are storage-library facts, not Gmail invocation/fidelity or
  scheduler acceptance. SIGKILL is not physical power loss; a DB snapshot is not
  a complete credential/config bundle or migration receipt. Typed sessions are not
  real process locks; fresh-owner publication belongs to M1-03's reviewed extension.
  A real DB-21 probe found that `mode=ro` followed by the current supplied-connection
  view adapter created WAL/SHM for a clean stopped database. This is a retained
  historical failure, superseded for the finite library by independently accepted
  exact `16bcd0b99bf1118924b214bf9ded3976813f5e1a`: 1188 full offline tests and
  8 ownership controls passed; the prior d6 single-owner finding was closed by
  reviewed source before the model-policy change.
  [Exact CI](https://github.com/GhostFlying/facet/actions/runs/37014341329) passed
  Python 3.12/3.13. Production provider/runtime registries remain empty: actual
  managed-read/RV11, action consumers, migration/restore and whole DB-01..28 are
  incomplete.
  No immutable-live shortcut or sidecar repair is enabled. PR #15 stays Draft/open
  and unmerged. Later bounded action/policy persistence source
  `62d75c0253a6d66710a9d4d4a4b4346b8b55c6db` passed 164 AP/1352 full tests,
  installed-wheel checks and
  [exact CI](https://github.com/GhostFlying/facet/actions/runs/37023546672), but
  independent acceptance placed it HOLD on two required findings. At that
  snapshot R1 correction and independently approved R2 plan60333e9 strategy were
  released for bounded repair, not accepted corrected source. Later R3 and
  combined acceptance are recorded in the Oct3 handoff below; this historical
  HOLD is not relabelled. Production action/read registries remain empty; no
  actual M5 producer was enabled. The independently approved migration
  entry plan has SHA-256
  `2116d042a8065ba44b818eb7f832414e883cf7ebec27ba4c51ab4e3717746af4`;
  at that snapshot source still awaited accepted actual action input, qualified
  OS input, exact dependency CI and explicit root dispatch. The later finite
  release below is not a complete backup provider, migration/restore
  implementation or whole-package acceptance.
- M1-03 [Issue #13](https://github.com/GhostFlying/facet/issues/13) has an approved
  implementation plan and independently approved r3 wire/command-storage design,
  and a separately independently approved bounded OS root/lock plan. Root released
  that finite source slice against main `ff77e63` after the qualified SQL library
  and exact CI above. The policy pause ended after PR #19 integration. Historical
  OS `183dc6d` independently remains HOLD despite green CI: ordering failed across
  two opaque handles for the same physical root. The reviewed C1 terminal-metadata
  refinement was independently approved before code at full-plan SHA-256
  `4b7895159612699a05f7278652e9c45c884a914478ff61490a63f3358dcc898f`.
  Corrected `ea80db286fe110a69450076581b0b25810dcaf91` received nonauthor Sol
  acceptance: 123 focused/731 full offline tests, paired actual kernel/descriptor
  ordering and 256-cycle live/terminal controls, fork/Thread/uncertain-close checks,
  fresh noneditable-wheel/privacy/import controls passed. R1/C1 are resolved at
  this exact source, not waived for the historical candidate.
  [Candidate CI](https://github.com/GhostFlying/facet/actions/runs/37025751696)
  passed Python 3.12/3.13. [PR #20](https://github.com/GhostFlying/facet/pull/20)
  actually merged at that exact SHA via authorized normal fast-forward; no force,
  bot merge commit or settings change.
  [Main CI](https://github.com/GhostFlying/facet/actions/runs/37026826339) also
  succeeded on Python 3.12/3.13 at that exact SHA. Only low-level Linux
  root/owner/view/key resources are integrated: actual managed provider, actor,
  bootstrap/receipts, storage/credential participants and second real daemon
  refusal remain pending. Arbitrary mounts, NFS/SMB and native descriptor/fork
  paths outside the declared discipline are not qualified. M1-06 r2, M2-01 r2
  and M6-01 r2 designs
  are also independently approved preparation only, not implemented consumers or
  permission to skip their dependencies. Production authentication remains
  unknown/review until the declared trusted source-path evidence gate closes.
- M1-05 [Issue #14](https://github.com/GhostFlying/facet/issues/14) / [PR #16](https://github.com/GhostFlying/facet/pull/16)
  early pure-model/catalogue/serializer/logging unit received independent source
  acceptance at `c455f71ae63fa435c9bb02b82767aff4a032c30c`. Local verification passed
  488 full offline tests (including 33 logging subprocess cases), Ruff, CLI and
  installed-wheel export/privacy smoke; [exact source CI](https://github.com/GhostFlying/facet/actions/runs/36989013627)
  passed Python 3.12/3.13. The two-doc handoff also received independent affected
  review at `f209fbe616dc65c70bbcdc4a104cf82b0d5dad27`, which actually merged via
  normal fast-forward. [Main CI](https://github.com/GhostFlying/facet/actions/runs/36989986570)
  succeeded at the same SHA. The full package stays open for actual consumers.
- M1-04 [Issue #17](https://github.com/GhostFlying/facet/issues/17) /
  [PR #18](https://github.com/GhostFlying/facet/pull/18) early pure source
  `b94b610aec070617a4bd3c1249b58437cc9bfbae` received independent implementation/
  acceptance review; 120 OP cases/608 full tests, Ruff, both CLI help entries,
  installed-wheel privacy/export checks and
  [exact CI](https://github.com/GhostFlying/facet/actions/runs/37000045729) passed.
  Its coherent docs/head candidate received independent review and actually merged
  exact `ff77e63a823dc8bcb130836243746c067778b94f`;
  [main CI](https://github.com/GhostFlying/facet/actions/runs/37001014793) succeeded
  on Python 3.12/3.13. No file/network/OAuth/profile/token publication or full
  binding gate was exercised. Issue #17 stays open; SQL remains unmerged.
- Prospective model-policy [PR #19](https://github.com/GhostFlying/facet/pull/19)
  actually merged exact `a57dd77116ea79b44c177d03bb6b9815a5913795` after independent
  nonauthor source acceptance and candidate CI.
  [Main CI](https://github.com/GhostFlying/facet/actions/runs/37018290223) succeeded
  on Python 3.12/3.13. The temporary OS pause was an ownership handoff, not
  cancellation. At that handoff `m103_os_source` retained OS source and sole
  shared-status/integration ownership; `phase1_sol_policy_review` owned bounded
  SQL corrections and migration plan-only work and independently reviewed OS
  source it did not author. `phase1_os_acceptance_sol` independently reviewed
  SQL source and approved the C1 OS and bounded status-handoff plan. Current
  ownership transfers are recorded below. Historical model attribution,
  package dependencies, external authority and milestone gates are unchanged.

## Oct3 source and main-health handoff

- The [PR #21](https://github.com/GhostFlying/facet/pull/21) status snapshot actually
  merged exact `36b5a303856f00876c697f712ee98c9012c497c7`. Its
  [main CI37028856572](https://github.com/GhostFlying/facet/actions/runs/37028856572)
  failed on Python 3.12 while Python 3.13 passed: OL07 assumed 64 sequential
  Threads would reuse a retired Python thread ID. This is retained failure
  evidence, not observed runtime ownership bypass. The first harness candidate
  `a410ca1dab1e0f0a8980f77d0443f88a92e7b982` separately received independent H1
  HOLD despite full/CI success: legitimate sibling activity changed ancestor
  directory metadata included in its test oracle. Neither finding is waived.
- Corrected [PR #22](https://github.com/GhostFlying/facet/pull/22) actually merged
  exact `befe278285cfbd77798ffa58e8ef5d35b12e203a` at 2026-10-02T16:59:36Z after
  independent nonauthor acceptance, concurrent 150 focused/758 full tests,
  twenty complete nine-scenario child batches, real sibling-positive and
  descriptor/invalid-phase negatives, and fresh installed-wheel controls.
  [Candidate CI37036616826](https://github.com/GhostFlying/facet/actions/runs/37036616826)
  and [main CI37037683010](https://github.com/GhostFlying/facet/actions/runs/37037683010)
  succeeded on both Python jobs. Actual main logs show CPython 3.12.3 and 3.13.16,
  758 full tests and 40 CLI smoke tests each. All production OS and complete
  approved OS/C1-plan bytes remain the qualified `ea80db2` input; only bounded
  test-harness/main-health evidence changed, not runtime/provider qualification.
- SQL `2466834f79c41dbbf95e2919072ea9f57f36e7cc` remains historical R3 HOLD for
  foreign UoW exit invalidating the genuine creator lifecycle. Corrected
  `c0bb4b02277942f335ce278d359b60c16a46fd48` received independent acceptance with
  1598 full/73 R3-focused tests, eight actual WAL controls, installed-wheel
  checks and [CI37032060497](https://github.com/GhostFlying/facet/actions/runs/37032060497)
  both-success. Its actual ACTION plan is 546 lines with unchanged full hash;
  the earlier review's 535-line description was a clerical count error, not
  different source or retrospective acceptance of either held candidate.
- Normal combined carry `a9c4e36de6ad70294002a83e678a2a7cf1b012d6`, parents c0bb
  then befe, now has independent nonauthor combined acceptance: 1625 full tests,
  73 R3-focused/150 OS-focused/eight actual WAL controls, byte-preserved SQL/
  OS/harness inputs and fresh noneditable wheel. Author full 1625 also passed.
  [Fresh CI37038807962](https://github.com/GhostFlying/facet/actions/runs/37038807962)
  succeeded on both jobs. Actual checkout logs identify PR merge commit
  `8e703daf8a8739411324457dec98cc34c0dff036`, whose tree
  `b33a7679c0ed4e3f2cc6885d084ac3c0eb479cab` exactly equals candidate a9c's tree;
  run head metadata alone is not the tested-revision proof.
  [PR #15](https://github.com/GhostFlying/facet/pull/15) remains Draft/open/unmerged.
  This docs branch remains based on accepted main befe, not that SQL branch.
- Root explicitly transferred the approved migration plan/tree and released its
  finite source allocation to `m103_os_source`; source work starts only after
  this docs freeze/CI start.
  The preserved 217-line plan is SHA-256
  `2116d042a8065ba44b818eb7f832414e883cf7ebec27ba4c51ab4e3717746af4` and the
  232-line design is `3a9fedfcb3cf2fbaa410c982383fd459d8f1f1b73f58992e96883c9ad50042cf`.
  Source implementation/independent acceptance/CI are not yet complete. The
  approved 229-line restore-fence plan hash
  `1cee159f355ef6df39ec781cc75cf31ad43e26966c47d9c34ad306dd7c29c0ba`
  and 307-line design hash
  `3e8bd09eb9d6068d29d2e1bdf2eba617dcc20be695a65ba8b38f2e26f70aadf8`
  remain plan-only without source release. Neither supplies a complete
  config/binding/credential bundle, installation/provenance issuer or restore
  recovery/clearance consumer.
- `phase1_sol_policy_review` separately owns the source-released no-state
  read-bootstrap foundation under approved 217-line plan SHA-256
  `87321fe4ae703356a7aee8eb8c2f4a80a372f3bfc2ef8ba86c27e1c142029094` and preserved
  229-line design `9d28e18cee3dbaed00c939838686a6b715cefb569c268a4f3e73a0d1cc6c660e`.
  Its bounded launcher/latch/in-memory probe allocation is not accepted source,
  a state opener, managed-read producer, qualified runtime, daemon or RV11.
  Shipping action/read-provider/runtime inventories remain empty. Source
  authors do not approve their own design or implementation; root dispatches
  exact independent acceptance and separate integration gates.

`m103_os_source` remains the sole shared-status/integration writer. This separate
three-document handoff needs its own exact-source nonauthor review and fresh CI
before root-qualified integration. Whole M1-02/M1-03, actual M5 consumers,
credential ownership, complete backup/restore/migration, full maintenance CLI,
G1-G6, live Gmail, Dashboard and Compose remain incomplete.

## Historical planning and bootstrap record

The following records describe their then-current candidates. Current approvals,
engineering integration and remaining gates are in the sections above.

- Historical planning/normalization records below retain their original SHA/
  verification scope. Their then-pending G0/Draft states were superseded by the
  explicit approval and actual integration recorded above, not retroactively
  relabelled as approval or runtime proof.
- User authorized product-first reordering of the total plan, not G0 approval:
  goals → operating loop → overall acceptance → scope/non-goals → milestones →
  work packages/execution. Eight acceptance groups summarize existing contracts;
  the 36 card bodies, DAG, waves, CLI ownership and authority ledger are preserved.
  The file-based reordering plan received independent Astra high approval before
  editing. Exact candidate review and CI belong to this revision and are tracked
  in [draft PR #2](https://github.com/GhostFlying/facet/pull/2); earlier approvals
  do not imply approval of the new overview. No production work has started.
- [Repository bootstrap](implementation-plans/repository-bootstrap.md).
- User requested a complete maintenance CLI and atomic English commit subjects
  (`feat: impl ...`, `fix: fix ...`, other types with action verbs), plus one-time
  main-history normalization. [CLI specification](cli-spec.md) now covers full
  command families, offline/Compose maintenance and CLI-01 through CLI-08 gates.
  Stable request keys before submission, explicit preview producers and coordinated
  DB/credential ownership address preliminary review feedback. This substantive
  extension received its own independent Astra high technical approval at
  `eca99118b46db765960c7439246b6a1c5f4e5ccb`; preliminary findings were closed.
  [History normalization](implementation-plans/commit-history-normalization.md)
  was separately reviewed, executed and independently accepted. The reviewed
  CLI candidate maps to `5d623f201b4e4f8c701b196d3f017bf874f3e79a` with an
  identical tree, identity and original dates; this traceability does not extend
  the old `7c68991` review to the substantive CLI changes.
- [Phase 1 planning record](implementation-plans/phase-1-planning.md),
  [complete execution plan](phase-1-execution-plan.md), and
  [agent workflow](agent-workflow.md). [Epic #1](https://github.com/GhostFlying/facet/issues/1)
  tracks this planning unit and later ready work-package Issues. The planning
  worktree is isolated. Local document links/fences/headings, whitespace, private
  host-path checks, 36-package dependency references/acyclicity and staged-index
  repository safety passed for the initial candidate. Independent review of
  `a8e87de` requested changes. Independent technical re-review approved
  `7c68991ef5f47ba65cc61a0dcc2dfd80fdb0ca46`, closing R1-R3 and C1; 36-package
  uniqueness/missing-node/cycle checks and manual wave review passed. Prior
  [draft PR CI at `af3b793`](https://github.com/GhostFlying/facet/actions/runs/36960852657)
  passed Python 3.11/3.12; it does not cover this new CLI extension. The new
  CLI candidate received separate review and
  [new candidate CI at `5d623f2`](https://github.com/GhostFlying/facet/actions/runs/36965268013)
  passed Python 3.11/3.12. At that planning handoff G0 remained pending. These runs
  validate their exact candidate SHAs, not a later report-only commit. The
  [review record](reviews/phase-1-plan-review.md) preserves historical and current verdicts and
  responses. No
  production package, daemon, Gmail request, deployment, or image is
  introduced by this unit.
- This planning unit's locked local baseline passed on Python 3.13.5: environment
  sync, Ruff lint/format (31 files), 24 offline tests and spike CLI help. These
  checks preserve the existing spike baseline; they do not validate planned
  production behavior. No mailbox credentials or live Gmail calls were used.
- On 2026-10-02 the user authorized delegated Phase 1 work, multiple worktrees,
  Issue/PR tracking, atomic commits, Astra high / 6.1 Sol xhigh as needed, and
  root coordination/reporting only. Complex plans need independent review before
  implementation, then independent implementation and acceptance review.
- The user also authorized autonomous merges of engineering/work-package plan
  PRs inside the approved phase after those review and CI gates, and public
  `ghcr.io/ghostflying/facet` main full-SHA image publication through Actions once
  the phase starts. They clarified that the overall Phase 1 plan itself needs
  their review and explicit approval; the draft planning PR must not merge
  beforehand, and technical review/CI cannot start implementation. PRs only
  build; formal version tags/GitHub
  Releases, live Gmail operations and host deployment are not included. No
  image has been built or published yet.
- Repository: [GhostFlying/facet](https://github.com/GhostFlying/facet), verified
  PUBLIC with default branch `main`; `origin` points to it. On 2026-10-02 the user
  explicitly requested public visibility and their account's GitHub noreply email.
- Local verification: 24 offline tests passed; Ruff lint/format, spike CLI help,
  shell syntax, tracked/staged safety scan, documentation links/fences, and staged
  whitespace checks passed. No live Gmail requests were used for this bootstrap.
- The first push was rejected by `GH007`. The unpublished root commit was
  replaced using the current configured user/noreply identity, without changing
  saved Git configuration or email privacy protection. GitHub confirmed both
  author and committer use the account's noreply identity and attribution is
  `GhostFlying`. The rejected old commit is not in public history.
- Initial published commit: `53ac21b`. Its [offline CI run](https://github.com/GhostFlying/facet/actions/runs/36955887359)
  completed successfully on both Python 3.11 and 3.12: 24 tests in each job,
  tracked-content safety baseline, locked install, lint, formatting, and CLI smoke.
- The user-requested one-time main-subject rewrite now maps that root to
  `34818fe9f5d2d7bcb30353939b146418b2d5a814` and old `9d8595d` to current
  `main` `2f78fdf69cba786d2568689b0d0566d827d4285a`. All six reconstructed
  commits passed independent tree/header/identity/date/topology acceptance;
  the base-to-plan diff is unchanged. Private local rollback refs are retained
  and were not published. [Fresh main CI](https://github.com/GhostFlying/facet/actions/runs/36965264011)
  passed Python 3.11/3.12. [PR #2](https://github.com/GhostFlying/facet/pull/2)
  was then Draft/unmerged with G0 pending; the later approval/integration is above.
  Complete mappings and rollback
  anchors are recorded in the history-normalization execution appendix.
- Published GitHub tree checked: source/tests/docs/configuration only; no private
  runtime directory or credential files. The baseline scan is not a substitute
  for the production privacy tests still required by later milestones.
- Runtime credentials/evidence are ignored local files. No live Gmail writes are
  part of this bootstrap, and no experimental state is adopted as production data.

## Next authorized development unit

Freeze and independently verify this bounded Oct3 docs handoff on actual main
befe. Then implement only the root-released migration-entry allocation on the
accepted unmerged combined SQL input a9c, preserving its approved plan/design
and binding new exact-source acceptance/CI before any integration. The separate
no-state bootstrap worker follows its own finite source/review gate; restore
remains plan-only. Preserve the integrated OS foundation's finite kernel/
mount/consumer limits. Its low-level resources and the qualified
finite M1-02 library do not close whole persistence, RV11, canonical M1-03 or G1;
actual runtime/provider/credential and backup/restore consumers remain pending.
M1-05 and M1-04 early pure deliveries are actually integrated; their real DB/auth/runtime
consumer gates remain open. M1-01 and P1-02 are actually integrated. Ordinary
phase-internal plans/engineering PRs advance under the approved autonomous gates;
material product/privacy/authority changes return to the user. Continue with the
P1 interface/ADR/test work, then dependency-ready M1 packages from the
[execution plan](phase-1-execution-plan.md). Write and review a concrete package
implementation record before coding. M1's minimum scope is:

1. Establish the production Python package/CLI without breaking the spike.
2. Validate configuration and explicit source/target bindings; refuse identity
   swaps or identical accounts, and separate private internal configuration from
   allowlisted public diagnostics.
3. Implement schema v1, migrations, durable repositories, process/writer locks,
   rule effective times, and metadata-only typed payloads.
4. Establish private OAuth/token handling and synthetic tests; require separate
   authorization for real account setup or additional scopes.
5. Define Dashboard response models and privacy sentinels before exposing HTTP.
6. Establish conservative authentication-evidence parsing/tests. Do not enable
   automatic admission using the spike's pass counters.

Production live copying, bulk backfill and deployment require their recorded
scope/target decisions. Dependency-ready offline engineering can proceed while
an external gate remains pending; keep final milestone gates in order and record
actual verification scope instead of marking a partial gate complete.

## Known limits and decisions still needed

- Gmail insert is not exactly once; target search timing is not an SLA. Production
  crash/recovery and ambiguous-ID tests remain necessary.
- Default raw processing is memory-only with no disk spool; source loss may
  prevent recovery. DB contains only necessary metadata and state.
- Target may contain unmanaged or old experiment mail. Initialization reports it
  without deleting, adopting mappings, or assuming All Mail is empty.
- AI connector retrieval is an AI-product responsibility, not a Facet gate.
- Real bank domains/credible authentication evidence, live account/test scope,
  dogfood host/local volume/Nginx entry, license and formal version release remain
  undecided. GHCR/package public visibility and main full-SHA publication scope
  are decided; actual package visibility and anonymous pulling still need M6
  verification. Source publication does not substitute for those checks.
- Authentication trust, unknown-insert attribution (excluding old unmanaged/spike
  copies), and daemon/CLI single-writer coordination are required early ADRs.
  Unique fingerprint matches alone do not establish this insert's provenance.
- Overall Phase 1 G0 is approved at the exact reviewed SHA; production milestone
  completion is not implied. Internal merge/GHCR scope does not authorize new
  live Gmail or host actions. Final milestone live
  gates remain separate from dependency-ready offline engineering outputs.
