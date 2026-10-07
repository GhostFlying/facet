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

## Qualified main integration, 2026-10-08

Independent bounded review approved `2a8ff44d0e7c4b94a0da066c34df5c8575716723`'s
ten-to-twenty-minute job budget; its complete dual-Python CI succeeded. The
subsequent independently accepted parent action-retry fix was carried without
conflict into integration candidate
`b634d94c100b4de064cf35782923f753d0470ed8`; all other runtime conclusions remain.
Final candidate [full CI](https://github.com/GhostFlying/facet/actions/runs/37661831018)
and [PR image build](https://github.com/GhostFlying/facet/actions/runs/37661831081)
passed. Older same-head cancelled runs are superseded concurrency runs, not
assertion failures or skipped final checks.

The pinned local image `facet:b634d94`, ID
`sha256:6dfc0316680ce54c936c6deb58c9e980b9a12061ad05abc909edb1692b0cbce3`,
has that full OCI revision and UID `10001:10001`. Eight supported production CLI
cases passed: historical copying, preserved old unknown, interrupted historical
pagination, new unknown no-resend, normal gap/restart, interrupted gap source
page, interrupted H1 page and gap with old unknown. Tests ran with networking
disabled, read-only rootfs and external-only fakes. The first ad-hoc driver used
unsupported fault names and aborted; correcting the driver to the fixture's
`discovery`/`catchup` inputs passed the affected cases without any runtime change.

PRs #93–#96 merged in order; every main tree matched its accepted head. Final
runtime main commit `392fe31969d96c5be4e46dff0bce3fdb249c8fd3` has the exact
integration tree above. Main publication/host checks and the newly requested
live-window confirmation remain distinct from this acceptance. Offline retained
state status still shows nine mappings, one old unknown and 58 old attention
jobs; no new real Gmail write, recovery override or service resume occurred.

### Published-image and stopped-host preparation

Main [full CI](https://github.com/GhostFlying/facet/actions/runs/37663322229)
and [publication](https://github.com/GhostFlying/facet/actions/runs/37663322235)
passed. Anonymous registry checks verified the public index digest
`sha256:2f89d96338b7e6cafa421c5f58722a61681bffe8fc80e0285aaae014cfaa2054`,
amd64/arm64 manifests, SPDX SBOM and SLSA provenance for the exact main commit.
The imported amd64 config/image ID is
`sha256:8f979c5d1aeb64fb306a3de2b38eff26813f24ce2dfb3ca8c22fd3835eb6a841`;
its complete non-cache application source matches the accepted local image.
The published image also passed the external-only fake production CLI historical
copy/restart case. Publication has no OCI revision label; provenance evidence
comes from the registry attestations, runtime config and source comparison.

The authorized test host retains its original state volume and now has a stopped,
non-root/read-only container referencing the full main-SHA tag. Before replacement,
the stopped writer-locked backup used SQLite's backup API for both journals and
included owner-only configuration/credentials. No daemon or Dashboard startup
is claimed. Production account/scope checks and read-only target classification
passed: nine mapped copies, two permitted outbound SENT items, no other unmanaged
content. An empty old-unknown search result remains inconclusive.

Offline real-state CLI preview/stable-key replay passed with protected business
state unchanged, zero target writes, no new insert attempts and no new epochs.
The newer default preview window requires the separately requested user scope
confirmation before historical start/run. No bulk copying, old unknown retry,
cleanup, attention reopening, additional scope or live gap acceptance occurred.
