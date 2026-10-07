# Production History gap recovery: review and local evidence

Date: 2026-10-07. Base: `b29543ae331619950eb3ce866dbc21b1735e8f69`.
Root authored the plan/code; independent reviewer used authorized Sol xhigh.

## Review

Initial bounded plan passed independent review. The user subsequently approved
processing-time rules, with pre-rule messages allowed only inside the known
downtime window. The revised plan passed independent review at SHA256
`49acf9b5b0d1fb67fd268d2691cac9c8ce40d444c013615ebf3953c3733f20c1`.
No strict reconstruction of rule/mail chronology or schema migration is needed.

Implementation review of `de6c0e82136fa393f9bec88accded81dabd88154` found one
P2: a strict provider `before` bound could omit the inclusive integer-second
window end. Fixed source candidate
`75093dce1737f3427dff04e9908f746a177e1720` passed focused independent rereview;
unaffected conclusions were retained. The provider query rounds outward while
metadata enforces the exact local window. A strict fake verifies endpoint
inclusion and exclusion of endpoint-plus-1ms from admission. Current ruleset
membership/removal, stopped generations, H1 ordering and unknown-job reuse had
no other concrete blocker in the reviewed delta.

## Observable offline capability

Actual CLI subprocesses create configuration, OAuth bindings, rules and epochs
through production commands. Only external Gmail/OAuth interactions are fake;
no DB readiness/binding/rule/epoch/gap seeds shortcut the command path.
History 404 preserves the cursor and records H1 without target insert. Subsequent
processes scan the known window and active threads, finish H1 pages, insert,
read back and map eligible messages; another restart does not insert them again.
Pre-rule gap candidates are admitted, out-of-window candidates are excluded,
source/catchup page failures resume, and old unknown attempts do not resend.
Typed-policy unit fixtures separately cover removal between failed pages,
unknown-coverage refusal and downtime longer than six months.

The unchanged pinned Dockerfile built on the authorized sgbox build host. Image
`facet:75093dc`, ID
`sha256:c30eb1228406d207d88ed5d8974cb2ab419a88de258c6da2ff9d8a46601c7227`,
has OCI revision equal to that source candidate and user `10001:10001`. It passed
all four gap CLI cases with networking disabled and a read-only root filesystem.
Only the read-only test driver/external fake was mounted; application source,
real state and real credentials were not overlaid. Synthetic content/error
sentinels are checked against persisted files and command output.

The local full-suite run completed with 2771 passing cases and one failing legacy
CLI dispatch fixture (620.73 seconds); that fake omitted the new warnings field.
This is not an all-green full-suite result. Test-only candidate
`a02236d7179b987382fa9230cbe96c6692c6c5bd` replaces that fake result with the actual
typed receipt and verifies no-warning/fixed-warning output. Its independent
focused review passed; seven affected cases passed. Runtime/image inputs are
unchanged. This does not claim a passing final full suite; mandatory candidate CI
must pass before merge. Ruff/format, locked sync, spike help and repository safety
checks passed. CI, integration, live Gmail gap evidence
and deployment remain separate gates. Complete `sync`, unknown-range approval
CLI, daily reconcile, target audit and other Phase 1 maintenance/acceptance are
not claimed here. No real mailbox operation, scope expansion, old unknown retry,
state reset, service resume, deployment or Release occurred.
