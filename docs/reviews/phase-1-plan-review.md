# Phase 1 plan independent technical review

Date: 2026-10-02

Status: complete CLI/commit extension independently technically approved at
`eca99118b46db765960c7439246b6a1c5f4e5ccb`, with independently accepted
tree-equivalent reparenting to `5d623f201b4e4f8c701b196d3f017bf874f3e79a`.
Earlier review records below retain their original historical SHAs.
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
the earlier reviewed candidate. The changes received their own technical
review. Preliminary reading identified missing thread/review/recovery preview
producers, lookup when the first mutation response is lost, and maintenance versus
credential-refresh ownership. The author's preliminary response specified these
paths and their CLI-02/06/08 acceptance; that response was not itself a verdict.

The existing unknown-History-gap recovery decision also has an explicit scoped
range preview/approve path and CLI-04 guards, not a direct DB edit or cursor reset.

- Reviewed candidate SHA: `eca99118b46db765960c7439246b6a1c5f4e5ccb`;
  parent `af3b7933ad052b9a9484dc894e5e77ea84f287b9`.
- Reviewer: independent Astra high agent, separate from the CLI/document author.
- Scope: the eleven changed documentation files, complete CLI and maintenance
  ownership/acceptance, commit convention and history-operation plan.
- Verdict: `approved`; preliminary preview-producer, lost-first-response lookup
  and maintenance/refresh-ownership findings closed; no blocking findings remain.
- This approval belongs to the substantive CLI candidate, not the earlier
  `7c68991` review. It does not claim runtime CLI, Gmail or deployment validation.

## History normalization and candidate traceability

The original history plan was independently approved at SHA-256
`eab928e34e440be59cd1dbdf16d3679503fcae2d2695246913bd2393a1e12288` before
execution. The integration agent reconstructed the two main commits and four
planning descendants; an independent reviewer accepted all six raw-object pairs,
header/date/identity/tree preservation, parent mapping, rollback anchors,
unchanged base-to-plan diff and the remote Draft PR state.

The reviewed `eca99118b46db765960c7439246b6a1c5f4e5ccb` maps to
`5d623f201b4e4f8c701b196d3f017bf874f3e79a`, tree
`8f3884ea158dd9ddf8eb8da2eb5e1a0f02c141e1`. Only its parent changed; the
independent equivalence acceptance explicitly establishes this traceability.
Original reviewed SHAs remain in the historical records above. Full mappings
are in the [execution appendix](../implementation-plans/commit-history-normalization.md).

[Main CI at `2f78fdf`](https://github.com/GhostFlying/facet/actions/runs/36965264011)
and [CLI candidate CI at `5d623f2`](https://github.com/GhostFlying/facet/actions/runs/36965268013)
completed successfully for Python 3.11/3.12. An earlier same-head PR run was
superseded and cancelled under workflow concurrency; the latest run succeeded.
These results apply to those exact SHAs. This report-only update needs its own
publication/CI evidence and does not relabel the candidate runs as its checks.

Overall user approval G0 remains pending; PR #2 remains Draft and unmerged.
No product implementation, CLI runtime, Gmail operation, image publication or
deployment was introduced by these documentation/history units.
