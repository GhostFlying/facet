# P1-00 execution baseline implementation plan

Date: 2026-10-02

Revision: r2. Status: revised for independent plan review; no baseline edits yet.

## Objective and already completed integration

Record the approved Phase 1 start and establish its focused execution ledger.
The user explicitly approved overall plan G0 on 2026-10-02 for
`caba7c73895a303d329cf3eba1c89557530c38c5`, then requested multi-agent execution
under the plan and previous requirements. Independent technical review and
mechanical QA approved that exact candidate; they did not replace user approval.

[PR #2](https://github.com/GhostFlying/facet/pull/2) is actually MERGED at the
same SHA via normal fast-forward, preserving the six atomic user/noreply commits.
No new merge commit, force push, history rewrite or rule change was needed.
[Candidate CI](https://github.com/GhostFlying/facet/actions/runs/36968387054) and
[main push CI](https://github.com/GhostFlying/facet/actions/runs/36969107636)
both succeeded at that SHA on Python 3.11/3.12. G0 approval/integration has also
been recorded in the merged PR and [Epic #1](https://github.com/GhostFlying/facet/issues/1).
Production capabilities and G1-G6 remain unimplemented/unverified.

## Base, ownership and bounded file scope

Base: clean local/remote main at `caba7c73895a303d329cf3eba1c89557530c38c5`.
Owned worktree: `../facet-worktrees/p1-00-execution-baseline`; branch:
`docs/p1-00-execution-baseline`. This delegated integration/document worker owns
shared status/coordination documents; other agents propose changes through
handoffs rather than edit them concurrently. Root coordinates, reviews evidence
and reports; it does not author this implementation. Independent reviewer is
separate from this plan/document author.

- Update current G0/start/next-step statements in `AGENTS.md`, `README.md`,
  `docs/development-status.md`, `docs/agent-workflow.md`,
  `docs/phase-1-execution-plan.md` and `docs/project-plan.md` only. Replace stale
  current-state pending/Draft wording, not historical evidence or approval rules.
- In `docs/cli-spec.md`, update only its top current G0 status metadata to approved
  with the date/exact approved SHA or a reference to the ledger. Production CLI
  stays unimplemented; command/option/privacy/writer/acceptance body is unchanged.
- Add `docs/phase-1-progress.md`: 36 stable package rows linked to Epic/canonical
  cards, with current state, engineering readiness, owner/reviewer and Issue/PR/
  evidence references. Do not duplicate or modify their dependencies/contracts.
- This plan records scope/revision and checks. Reuse existing workflow Issue/PR/
  review/handoff templates; add no new template system unless a concrete gap is
  found and independently reviewed.
- Product/Gmail/Dashboard contracts and the CLI specification body, code,
  dependencies, workflows, historical
  SHA mappings, rollback refs and other agents' owned files are out of scope.

## Implementation after independent plan approval

1. Recheck base/clean state and file ownership. Record G0 approved/date/exact SHA,
   actual merged PR and CI evidence consistently in current-state locations.
   D1 engineering merge and D2 GHCR scope are now phase-active, but their existing
   review/CI/milestone/permission requirements remain unchanged.
2. Add the 36-row ledger from existing card IDs. Start P1-00 at its actual review
   state, P1-01 at its actual design/plan state, and P1-02 waiting for reviewed
   frozen typed interfaces; later packages remain planned. Planned/design-ready,
   implementation-ready, integrated and milestone/live-verified are distinct.
3. Create only P1-00, P1-01 and P1-02 Issues with dependencies, role/worktree owner,
   written plan/revision, owned scope, acceptance, authority and blocking/ready
   conditions; link them to Epic #1. P1-02 explicitly waits for P1-01 output.
   No outside assignee/mention, bulk later Issues or fabricated GitHub approvals.
4. Commit a focused documentation candidate with explicit staging, safety and
   user/noreply identity; obtain independent exact-SHA implementation/acceptance
   review and CI. Publish a focused PR linked to P1-00/Refs #1 only as directed.
   Integrate normally without force, then update durable handoff/Issue state
   using actual evidence. Fresh GitHub rules govern each integration.

## Acceptance and checks

- Current instructions/status agree that G0 is approved at the exact user-reviewed
  SHA and the phase has started; G1-G6 or production CLI are not called complete.
- All 36 IDs match canonical cards, without missing/duplicate/new packages or
  changed card bodies, dependency graph, waves, acceptance or external authority.
- Ledger records actual readiness, independent reviewer and evidence scope;
  three initial Issues trace to Epic, and P1-02 cannot start implementation before
  P1-01 interfaces pass review. Existing handoff templates are usable.
- Only approved shared-file paths change. Local links, Markdown structure,
  whitespace, privacy and tracked/staged safety checks pass. New candidate
  review/CI cannot be inferred from the earlier plan candidate's successful runs.
- Docs-only verification suffices here; baseline runtime tests/CI remain offline
  and are not proof of planned Gmail, Compose or maintenance functionality.

## Risks, external actions and stop gates

Do not turn G0 into blanket Gmail/host/extra-scope/license/tag/release/automation
authority, implement image workflows early, or weaken independent package review.
Live and deployment decisions remain separate; raw/spike state is never copied.
Normal Issue/PR metadata, commits and non-force integration are authorized within
this package's reviewed workflow. Stop for dirty/unowned changes, changed branch
rules, candidate drift, private public-tracking content or substantive contract
changes; report evidence to root. At this handoff only this plan is drafted;
wait for independent plan review and root scheduling before the implementation.

## Plan review response

Independent review of r1 requested one scope correction: the mandatory CLI
specification still has a current G0-pending header. Revision r2 permits only
that approval-state metadata update; its product/command/acceptance body remains
out of scope. All other scope, gates and planned execution remain unchanged.
