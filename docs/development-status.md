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
| Phase 1 execution planning | Complete CLI/commit extension technically approved; user G0 pending | Reviewed `eca99118` maps by verified tree equivalence to `5d623f2`; 36 packages, complete CLI acceptance, passing candidate CI; no product implementation |
| M1 foundation | Not implemented | Config, bindings, schema/migrations, locks, rule storage, public status models |
| M2 durable projection | Not implemented | Production workers, fidelity, insert intent, recovery, bounded memory |
| M3 admission/backfill | Not implemented | Rules/authenticity, preview, fixed six-month discovery, durable backfill |
| M4 sync + Dashboard alpha | Not implemented | History/gap recovery, reconcile, aggregate read-only Web UI |
| M5 action labels | Not implemented | Learning, legacy handling, idempotent commands, BlackList cancellation |
| M6 self-hosted v0.1 | Not implemented | One-command Compose, Actions GHCR image, Nginx, backup/restore, bilingual docs, live/deployment/72-hour gates |

The executable package is currently `facet_spike`, not `facet`. Existing tests
cover MIME payload analysis/comparison, private atomic file permissions, RFC-ID
query validation, and aggregate spike reports. They do not test a production
daemon, trusted sender admission, bulk backfill, or a rendered Dashboard.

## Active implementation record

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
  passed Python 3.11/3.12. Overall user approval G0 remains pending. These runs
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
  remains Draft and unmerged, with G0 pending. Complete mappings and rollback
  anchors are recorded in the history-normalization execution appendix.
- Published GitHub tree checked: source/tests/docs/configuration only; no private
  runtime directory or credential files. The baseline scan is not a substitute
  for the production privacy tests still required by later milestones.
- Runtime credentials/evidence are ignored local files. No live Gmail writes are
  part of this bootstrap, and no experimental state is adopted as production data.

## Next authorized development unit

Finish review/publication of the report-only evidence update and its own CI,
then present the technically approved plan for the user's review and
explicit G0 approval. Do not merge the overall plan or start product code before
that decision. Ordinary phase-internal plans/engineering PRs can advance under
the approved autonomous gates after G0; material product/privacy/authority
changes return to the user. When implementation starts,
dispatch P1-01/P1-02 interface/ADR/test work, then the M1 packages from the
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
- Overall Phase 1 plan approval/start is pending. Internal engineering merge and
  GHCR scope approvals do not substitute for that decision. Final milestone live
  gates remain separate from dependency-ready offline engineering outputs.
