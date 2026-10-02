# Phase 1 plan independent technical review

Date: 2026-10-02

Status: earlier candidate technically approved; complete CLI/commit extension
awaits new SHA-bound review. Earlier approval does not cover the extension.
Overall user Phase 1 plan approval G0 is separately pending. This technical
record cannot authorize merging the overall plan or starting implementation.

## Initial review

- Base SHA: `9d8595da789e6e450a5bdb0bfe391aab34244237`.
- Reviewed candidate SHA: `a8e87de8e02469f018a317efeea1be6493dafdc2`.
- Reviewer: independent `phase1_plan_review` agent, `gpt-6-astra` / high;
  not an author of the architecture input, execution input or documentation.
- Verdict: `changes_requested`.
- Scope: eight documentation files; contract/authority, work-package dependencies,
  milestone evidence, AUTH/insert attribution/writer design gates, privacy,
  Compose/Actions delivery and dogfood. No product or live behavior was tested.

| Finding | Evidence and requested correction | Author response in revised draft |
| --- | --- | --- |
| R1 / P1 | User clarified that the overall plan requires their review/explicit approval; initial D1 language allowed the planning PR to merge automatically | Added top-level G0/D0 pending gate across AGENTS, execution plan, workflow, status, README, project plan and planning record. Internal D1 merge/D2 image implementation take effect after G0; total planning PR waits for user approval |
| R2 / P2 | Wave table omitted P1-02 implementation, paired M2-01 with its dependent M2-02, advanced M4-01 implementation before M3-02, and paired M6-03 with required M6-01 | Replaced ambiguous waves with explicit design/implementation sub-waves and ordered arrows; P1-02 implementation is present and simultaneous pairs only use satisfied implementation dependencies |
| R3 / P2 | M4-06 used full G3 as implementation dependency, indirectly blocking offline Runtime/Compose on live authentication scope | M4-06 depends on M3/M4 offline-verified outputs; G3 and D3 apply to final G4/live acceptance. Clarified M2-05, M5-03, M6-02/03/06 references as engineering outputs and PR integration versus milestone live acceptance in workflow |
| C1 / optional | M6-08 mentioned token refresh/generic faults but did not explicitly require real authorization loss and re-OAuth | Added real authorization failure→CLI OAuth→pending jobs resume evidence, distinct from token refresh, with explicit fault-scope permission and user participation; missing permission keeps that gate pending |

The initial reviewer otherwise found the product coverage, privacy, AUTH/insert
attribution design gates, Compose, Actions and supply-chain direction acceptable.
The initial verdict remained changes_requested until the separate re-review.

## Revised candidate

- Reviewed candidate SHA: `7c68991ef5f47ba65cc61a0dcc2dfd80fdb0ca46`.
- Base SHA: `9d8595da789e6e450a5bdb0bfe391aab34244237`.
- Reviewer: the same independent `phase1_plan_review` agent, Astra high.
- Verdict: `approved` for technical pre-review only; no new blocking findings.
- R1/R2/R3 closed; C1 implemented. The reviewer confirmed consistent pending G0,
  no overall-plan auto-merge, corrected wave prerequisites, separation of offline
  inputs from final live gates, and permission/user participation for re-auth.
- Independent package extraction found 36 unique packages, no missing nodes or
  cycles; manual wave review and `git diff --check` passed. Extracted edge totals
  vary by reference classification and are not themselves semantic proof.
- Local locked baseline subsequently passed: environment sync, lint, format,
  24 offline tests and spike CLI help on Python 3.13.5. It verifies the unchanged
  spike baseline, not planned production or Gmail/deployment behavior.

The following report-only metadata commit records this reviewed SHA/verdict and
check results. It does not change the substantive plan. Overall G0 is pending;
the draft planning PR must remain unmerged. No product code, Gmail operation,
image publication or deployment occurred.

## Complete CLI and commit-contract extension

The user added complete maintenance CLI and commit-subject requirements after
the earlier reviewed candidate. Current changes require their own technical
review. Preliminary reading identified missing thread/review/recovery preview
producers, lookup when the first mutation response is lost, and maintenance versus
credential-refresh ownership. The draft now specifies these paths and their
CLI-02/06/08 acceptance; this response is not a review verdict.

The existing unknown-History-gap recovery decision also has an explicit scoped
range preview/approve path and CLI-04 guards, not a direct DB edit or cursor reset.

Pending: precise candidate SHA and independent integrated review. Overall user
approval G0 remains pending; no product implementation or overall-plan merge.
