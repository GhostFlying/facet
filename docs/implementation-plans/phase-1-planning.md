# Phase 1 execution planning implementation record

Date: 2026-10-02

Status: documentation drafting; product implementation has not started.

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
- Pending: draft PR/CI, then explicit user overall-plan review/approval.
  Production M1-M6 remain unimplemented; the overall planning PR stays unmerged
  while G0 is pending.
