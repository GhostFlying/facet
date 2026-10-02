# Phase 1 execution planning implementation record

Date: 2026-10-02

Status: product-first reordering plan independently approved; overall user
approval G0 is pending. Earlier CLI/history approvals remain historical evidence;
the reordered candidate requires its own technical review. Product implementation
has not started.

## Scope and authority

The user requested a complete Phase 1 plan, root-agent coordination and reporting,
delegated engineering with `gpt-6-astra` high and `gpt-6.1-sol` xhigh as needed,
independent plan and implementation reviews, dependency-based parallel work,
multiple worktrees, and GitHub Issue/PR tracking with atomic commits. Docker
Compose deployment and GitHub Actions image publication are required deliverables.

This record authorizes documentation work for that request. It does not start the
production daemon, issue Gmail calls, copy mail, deploy a host, or publish an
image. The user subsequently authorized autonomous project PR merges after
independent plan/implementation reviews and CI, and public
`ghcr.io/ghostflying/facet` main full-SHA image publication. The current planning
PR requires the user's explicit overall Phase 1 plan approval and cannot merge
autonomously beforehand. Engineering PR merge authority takes effect inside the
phase only after that approval; formal version tags/GitHub Releases, live Gmail,
and host deployment remain separate decisions. GHCR publication scope is
approved, but implementation and its triggers begin only after the phase starts.

Baseline: clean `main` and `origin/main` both resolved to `9d8595d`. The isolated
planning worktree is the repository's sibling `../facet-worktrees/phase1-plan`,
branch `docs/phase1-execution-plan`. No existing user changes were moved or
overwritten.

## File scope

- Add `docs/cli-spec.md` for the user's complete maintenance-CLI requirement:
  command groups, effect/lock ownership, JSON/exit-code contract, confirmation,
  offline operation, privacy and local/Compose E2E acceptance.
- Add `docs/phase-1-execution-plan.md`: stable work-package IDs, dependency graph,
  interfaces, M1-M6 gates, evidence requirements, release/Compose scope, risks,
  decision ledger, and first dispatch wave.
- Add `docs/agent-workflow.md`: coordinator/worker/reviewer responsibilities,
  model routing, plan-review-implementation-review process, worktree ownership,
  Issue/PR lifecycle, atomic commits, review identity, and durable handoffs.
- Add `docs/reviews/phase-1-plan-review.md` after independent review: exact
  reviewed candidate SHA, findings, corrections, and verdict without private
  evidence. A report-only metadata commit must not conceal substantive plan
  changes; substantive corrections require a new candidate review.
- Update repository `AGENTS.md` to link this workflow and record this request's
  delegation/worktree/GitHub authority. This hand-maintained repository file is
  not the generated cross-repository instructions.
- Update `docs/project-plan.md`, `docs/development-status.md`, and `README.md`
  navigation, current planning state, and the required image delivery path.
- If needed, clarify implementation ambiguities in
  `docs/gmail-projection-spec.md` without changing the product contract: sender
  authentication trust boundary, unknown-insert attribution, and single-writer
  CLI coordination remain ADR design gates.

## Approach and review

1. Read the current instructions, development status, product contract, project
   plan, Gmail/Dashboard specifications, spike results, and prior bootstrap plan.
2. Obtain independent architecture and execution-design inputs from separate
   agents. Keep milestone acceptance sequential while allowing dependency-ready
   design and synthetic-test modules to proceed in parallel.
3. Draft the documents in this worktree. Root coordinator reviews the integrated
   structure; an independent reviewer assesses contract consistency, unresolved
   authority, dependency completeness, and measurable gates before publication.
4. Apply review corrections and record actual checks and remaining decisions.
   The coordinator authorized a local candidate commit for SHA-bound review.
   Stage explicit files, scan the index, check author/committer noreply identity,
   and provide the candidate SHA before pushing or creating the planning PR.
   No product source, dependency, or runtime state changes are in this unit.

## Scope clarification before the next revision

The user clarified that they review and explicitly approve the overall Phase 1
plan; autonomy applies to work inside the approved phase. Add a top-level user
approval gate, currently pending, consistently to the execution plan, workflow,
AGENTS, project plan, development status and README. The overall planning PR is
reviewable but must not merge before that user approval. Ordinary complex work
packages retain independent agent plan/code reviews without per-package user
approval; material product/privacy/authority changes return to the user.

Combine this clarification with the independent technical review of candidate
`a8e87de8e02469f018a317efeea1be6493dafdc2`, correct dispatch-wave dependency
issues, and commit a new local candidate for re-review. Do not push or create a
PR until the coordinator directs it, and do not implement product code or run
Gmail/publication/deployment actions.

## CLI and commit-subject extension before editing

The user added two requirements: a complete CLI for maintenance, and commit
subjects in the `type: action summary` form, specifically `feat: impl ...` and
`fix: fix ...`, with one-time normalization of existing main history. This
author only edits documentation; the separate history agent owns
`docs/implementation-plans/commit-history-normalization.md` and all later
approved reference/history operations. Do not edit or stage that agent's file.

Before implementation, specify the full CLI across config/init/validation,
OAuth/status/re-auth, daemon control and pause boundaries, rules/thread actions,
preview/backfill, queue/review, reconcile/audit, bounded repair/recovery, and
backup/restore/migrate/upgrade maintenance. Map commands to existing package
owners and G1-G6 gates, preserving the 36 package IDs. Status/doctor and stopped
maintenance inspection/backup/restore/migration must work offline and from the
image without installing host Python. Queue retry cannot bypass unknown-insert
recovery or stopped generations; one-off containers must honor locks.

Synchronize AGENTS, workflow, execution/project/Gmail specifications, development
status and README. Make clear that complete CLI is a Phase 1 deliverable, not
help-only scaffolding. Define private local metadata separately from public DTOs;
neither profile permits mail bodies/raw/credentials/unfiltered exceptions.
Set structured JSON, exit codes, non-TTY confirmations and explicit write scopes.

Acceptance: all requested maintenance paths have command/owner/effect/lock and
test coverage; offline/Compose E2E requirements are explicit; no send/delete/
purge, reset-cursor or force-bind shortcuts appear. Documentation checks and
independent review apply to the new revision, not the previously approved SHA.
Risks: unintended disclosure from generic retry/repair, a second writer in a
maintenance container, credential output, and reusing old review after substantive
CLI requirements change. Stop for those conflicts. Product implementation and
user overall-plan approval G0 remain pending.

The current baseline is published draft PR #2 at `af3b793`; this extension is
prepared as a reviewable working-tree diff. Do not commit, push, stage the history
agent's file or operate on refs until the coordinator assigns the single Git
writer after review.

The coordinator has now assigned this author candidate-only Git ownership:
after documentation/whitespace/safety checks, stage the owned documents and the
separately approved, unchanged history-plan file (SHA-256
`eab928e34e440be59cd1dbdf16d3679503fcae2d2695246913bd2393a1e12288`) and make one
local `docs: plan complete maintenance CLI and commit conventions` candidate.
No push, merge or reference rewrite is authorized by this candidate step. The
history agent's file is not edited by this author. Freeze the resulting SHA for
independent review; previous plan approval is historical only.

## Acceptance and checks

- Every implementation package has a stable ID, dependency, worker/model route,
  file scope, deliverable, and falsifiable acceptance criteria.
- The plan covers all M1-M6 scope, read-only Dashboard, raw-memory-only privacy,
  fault recovery, action labels, image publication, deployment, rollback, and
  the 72-hour dogfood gate without claiming those capabilities already exist.
- Bulk real Gmail backfill cannot precede durable consumption of its captured H0.
- Authentication trust, insert attribution, and single-writer command handling
  have explicit design/review gates and conservative unresolved behavior.
- User decisions distinguish existing authorization, engineering choices the
  coordinator can make, and external authority still needed.
- Check internal document links, Markdown structure, whitespace, cross-document
  consistency, and repository safety against the staged/tracked index before
  committing or pushing. Keep public content free of private mailbox evidence.
- This documentation-only change does not require new product tests; existing
  baseline checks can be reported separately if run, without treating them as
  validation of planned production behavior.

## Stop gates

Stop dependent work for a material contract conflict, unverifiable source
authentication trust, ambiguous insert provenance, private content in public
documents, or missing live/release/deployment authority. Continue independent
offline work and report a concrete decision packet to the user. Do not invent
bank allowlists, licenses, live accounts, host paths, delivery SLAs, or completed
milestone evidence.

## Verification record

- Revised draft contains 36 unique work-package cards. Mechanical checks of the
  implementation dependency references/ranges found no nonexistent package or
  cycle, and the independent reviewer manually checked the corrected waves.
  Reference extraction counts vary when live/adapter references are included;
  an edge count alone does not establish dependency semantics. Milestone/live
  gates remain separately reviewed acceptance conditions.
- Local links, balanced fences, heading separation, and absence of private host
  paths passed for all nine changed documentation files. Whitespace checks
  passed. No production test is claimed from these documentation checks.
- D1 phase-internal merges and D2 public GHCR/main full-SHA publication scope were
  explicitly approved by the user on 2026-10-02, conditional on overall plan
  approval/start G0. G0 is pending; the overall planning PR cannot merge or start
  implementation based on independent technical review/CI.
- Staged-index repository safety passed and the existing configured user/noreply
  identity matched the authorized identity; saved Git configuration was not
  changed. Candidate author/committer will also be inspected after committing.
- Initial independent review at `a8e87de8e02469f018a317efeea1be6493dafdc2`
  returned changes_requested. R1-R3 and optional C1 were corrected and preserved
  in the [review record](../reviews/phase-1-plan-review.md).
- Independent technical re-review approved candidate
  `7c68991ef5f47ba65cc61a0dcc2dfd80fdb0ca46`; R1-R3 closed and C1 implemented.
  The follow-up commit only records this verdict and actual baseline evidence,
  without changing task scope or product requirements.
- Locked local baseline passed on Python 3.13.5: `uv sync --locked --extra dev`,
  Ruff lint/format (31 files), 24 offline tests, and spike CLI help. No production
  or live Gmail behavior is claimed.
- Complete CLI/commit extension candidate
  `eca99118b46db765960c7439246b6a1c5f4e5ccb` received independent Astra high
  technical approval; preliminary findings were closed. Its eleven-file scope
  remains documentation only; no runtime CLI behavior is claimed.
- The separately approved history plan was executed under exclusive Git-writer
  ownership. All six reconstructed commits passed independent raw-header,
  identity/date/tree/parent mapping, backup and diff-equivalence acceptance.
  The substantive candidate maps to
  `5d623f201b4e4f8c701b196d3f017bf874f3e79a`; its tree is unchanged.
  Current main is `2f78fdf69cba786d2568689b0d0566d827d4285a`.
  See the [history execution appendix](commit-history-normalization.md) for
  full mappings and private local rollback ref names.
- Fresh [main CI](https://github.com/GhostFlying/facet/actions/runs/36965264011)
  and [planning candidate CI](https://github.com/GhostFlying/facet/actions/runs/36965268013)
  passed Python 3.11/3.12, including safety, locked install, lint, format,
  offline tests and spike CLI smoke. They validate their exact SHAs and do not
  stand in for CI on a later report-only commit.
- Pending: report-only evidence review/publication and its own CI, then explicit
  user overall-plan review/approval. PR #2 remains Draft and unmerged;
  production M1-M6 and the runtime maintenance CLI remain unimplemented.

## Product-first total-plan reordering before editing

The user authorized a presentation change, not overall-plan approval G0 or
product implementation. Start from clean planning branch
`be0c1020e026b66a67f28149a22cef539aa65f8b`; main is not edited. Preserve the existing
worktree and branch; do not rewrite history or change product/CLI contracts.

Scope is at most four documents: this record, `docs/phase-1-execution-plan.md`,
and only necessary current-state/review entries in `docs/development-status.md`
and `docs/reviews/phase-1-plan-review.md`. AGENTS, README, product/project/Gmail/
Dashboard/CLI specifications, source code, and history appendix are out of scope.

Proposed presentation order:

1. Overall goals: controlled ongoing thread authorization, the target view of
   Facet-managed material, long-running self-hosting, observability and maintenance.
2. User operating loop: install/configure/OAuth, preview and explicit start,
   incremental tracking, rules/action labels, CLI exception handling, and
   backup/restore/upgrade.
3. Eight overall acceptance groups: disclosure, fidelity, continuity/recovery,
   privacy, observation/maintenance, deployment/recovery, conditional P95 < 60 s,
   and final delivery including the actual 72-hour dogfood gate. Map each to
   required evidence and existing G/CLI/package owners; requirements are not results.
4. Scope and non-goals, including unmanaged target data and the AI-connector
   boundary; no new feature, hard metric or weakened gate.
5. Milestones: retain M1-M6/G0-G6, M4 alpha versus v0.1, engineering versus live
   dependencies, the existing DAG and gate evidence.
6. Work packages and execution: move the 36 cards, CLI ownership, review/model/
   concurrency rules, waves, risks and authority ledger after the product overview.

Before this edit, obtain independent plan review of this section. After approval,
use a minimal structural patch: simplify the title/opening and link the review
record rather than leading with historical SHAs. Move existing package card
bodies, dependencies/tests, DAG, wave and authority text without semantic changes;
compare extracted card bodies and preserved operational sections to the baseline.
New overview prose summarizes existing contracts only. Freeze latency measurement
definition/sample plan before live tests; unchanged normal API, valid auth and
no-backlog conditions apply, and no samples cannot pass. Do not invent results.

Acceptance/checks: the six-part order is visible; the eight acceptance groups are
traceable to existing requirements; all 36 IDs and original card bodies remain,
and no dependency/wave/authority meaning changes. Run local-link/Markdown/
whitespace/privacy and staged safety checks. Submit a local atomic
`docs: reorganize Phase 1 plan around product goals and acceptance` candidate for
exact-SHA independent review; pushing requires a separate coordinator instruction.

Risks/stop: duplicated overview could silently broaden disclosure, impose a new
measurement threshold or weaken recovery/privacy. Stop and escalate a material
contract conflict instead of resolving it in prose. G0 remains pending; neither
technical review nor this reordering authorizes plan merge, coding, Gmail calls,
image publication or deployment. The initial step is plan-only review before editing.

Independent Astra high plan review approved the above reordering scope/approach
at file SHA-256
`4eca92dd86dc9a84cfd435139dc53524984b64aafb322bf8feed0cbb66e99835` before
the total-plan edit. The coordinator then authorized the structural implementation
and local candidate commit only. Candidate technical review/CI will be tracked
against its exact SHA in draft PR #2/Epic #1; G0 remains pending.

Local structural checks passed for the reordered draft: six top-level parts,
eight acceptance groups, all 36 package card bodies and the seven preserved
operational sections (DAG/gates, CLI ownership, coordination, waves, authority,
handoff and references) match the baseline apart from heading level/separation.
Links, fences, heading separation, private-host-path and whitespace checks passed
for the four-document scope. These are documentation checks, not runtime proof.
