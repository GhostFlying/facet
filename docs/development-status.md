# Facet development status

Updated: 2026-10-02

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
| M1-02 persistence | Implementing; multiple finite SQL slices accepted, whole gate open | Draft PR #15 exact `c03e62f`: 879 offline tests and independent slice/3.12+3.13 CI passed; mapping/action/migration/restore and whole DB-01..28 remain; actual DB-21 sidecar-creation counterexample unresolved |
| M1-03 writer/runtime/CLI | Plan and wire/storage r3 design approved; no runtime source | Actual owner/view/receipt/credential participants and reviewed storage integration pending; design approval is not a running daemon |
| M1-04 OAuth/binding | Early pure values/codec/client parser accepted; this delivery candidate | PR #18 source exact `b94b610`: 120 OP cases/608 full tests, independent source review, wheel and 3.12+3.13 CI passed; this docs/head review and actual integration remain tracked in PR #18; full OAuth/binding open |
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
open. This snapshot does not predict PR #18 integration or its post-merge main CI.

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
  acceptance and exact Python 3.12/3.13 CI. The latest submitted SQL snapshot passed
  879 full offline tests; [exact CI](https://github.com/GhostFlying/facet/actions/runs/37000255749)
  succeeded. These are storage-library facts, not Gmail invocation/fidelity or
  scheduler acceptance. SIGKILL is not physical power loss; a DB snapshot is not
  a complete credential/config bundle or migration receipt. Typed sessions are not
  real process locks; fresh-owner publication belongs to M1-03's reviewed extension.
  A real DB-21 probe found that `mode=ro` followed by the current supplied-connection
  view adapter creates WAL/SHM for a clean stopped database. Full no-create acceptance
  is held pending a reviewed view/provider closure; no immutable-live shortcut or
  automatic sidecar repair is enabled. Mapping confirmation, actions, migration/
  restore and complete DB-01..28 evidence remain incomplete. PR #15 remains Draft.
- M1-03 [Issue #13](https://github.com/GhostFlying/facet/issues/13) has an approved
  implementation plan and independently approved r3 wire/command-storage design,
  but no runtime source. Actual owner/view/bootstrap/receipts and storage/credential
  participant integration remain pending. M1-06 r2, M2-01 r2 and M6-01 r2 designs
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
  [Draft PR #18](https://github.com/GhostFlying/facet/pull/18) early pure source
  `b94b610aec070617a4bd3c1249b58437cc9bfbae` received independent implementation/
  acceptance review; 120 OP cases/608 full tests, Ruff, both CLI help entries,
  installed-wheel privacy/export checks and
  [exact CI](https://github.com/GhostFlying/facet/actions/runs/37000045729) passed.
  This delivery adds only a coherent update of these two current-state documents;
  its exact-head affected review/CI and eventual integration receipt belong to
  PR #18. No file/network/OAuth/profile/token publication or full binding gate
  was exercised. SQL's unmerged state is not silently imported into this branch.

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

Continue M1-02's reviewed finite repository and real-file fault/privacy work;
its value/schema slices do not close whole persistence or G1. Close the M1-05
early delivery's exact-head docs/CI gates before coordinator-authorized integration,
then retain its actual DB/auth/runtime consumer gates. Resolve the M1-03 wire
design findings before any writer implementation; M1-04 actual ownership/schema
integration remains pending. M1-01 and P1-02 are actually integrated. Ordinary
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
