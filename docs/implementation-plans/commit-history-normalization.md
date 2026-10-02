# Commit history normalization implementation plan

Date: 2026-10-02

Status: the independently approved one-time operation has been executed and
independently accepted. The original reviewed plan version had SHA-256
`eab928e34e440be59cd1dbdf16d3679503fcae2d2695246913bd2393a1e12288`.
The baseline/steps below describe that consumed authorization; the execution
appendix is report-only evidence, not authority for another history rewrite.

## Authority and scope

The user explicitly requested a one-time rewrite of the two existing `main`
commit subjects into the `feat: impl ...` / `fix: fix ...` convention. This is a
specific history-edit authorization, separate from approval of the overall
Phase 1 plan. The coordinator delegates the Git work to a single integration
agent after independent plan review and an explicit execution handoff.

This unit changes only historical commit messages and the parent links needed
to keep the existing Draft planning PR based on the rewritten `main`. It does
not merge PR #2, approve the Phase 1 plan, start production implementation, call
Gmail, publish images, deploy, create tags/releases, or change Git identity or
repository settings. G0 remains pending and PR #2 remains Draft.

The only document owned by this unit is this implementation plan. The separate
documentation owner is adding the maintenance CLI specification and updating
the other Phase 1 documents. Those substantive changes need their own review;
the previous technical review cannot cover them merely because a rebase occurs.

## Read-only baseline and exact subject mapping

The main checkout and existing planning worktree were initially clean. Their
branches, local remote-tracking refs, and actual remote branch tips agreed:

| Ref / object | Verified value |
| --- | --- |
| `main`, `origin/main`, remote `refs/heads/main` | `9d8595da789e6e450a5bdb0bfe391aab34244237` |
| Planning branch and PR #2 head | `af3b7933ad052b9a9484dc894e5e77ea84f287b9` |
| Planning branch | `docs/phase1-execution-plan` |
| PR #2 | Draft, base `main`; the only open PR |
| Main protection / repository rulesets | `protected: false`; protection endpoint returned 404; rulesets empty |
| Tags | No remote tags |
| Git identity | Configured name `GhostFlying`; email matches authorized account noreply |

Both historical commits have author and committer `GhostFlying` with
`4019569+GhostFlying@users.noreply.github.com`. There are exactly two commits on
`main`, with no merge or signed-commit headers in those objects. The complete
one-time `main` mapping is:

| Old commit | Old subject | New subject | Tree that must remain identical |
| --- | --- | --- | --- |
| `53ac21b10dc6f6d055d5b49e720e5a00ab29632b` | Bootstrap Facet Gmail spike, project contracts, and agent workflow | `feat: impl Facet Gmail spike and project foundations` | `45616f1adb46d428e7815f57f34b951e10d9ccea` |
| `9d8595da789e6e450a5bdb0bfe391aab34244237` | Record verified public repository bootstrap and CI results | `feat: impl bootstrap verification and development status` | `2f952181b98984f892299faa1e94bf193ecdf043` |

Preserve the root author's and committer's original timestamp and timezone,
`1790908179 +0800` (2026-10-02 10:29:39 +08:00), and the second commit's
`1790908284 +0800` (2026-10-02 10:31:24 +08:00). Preserve their empty message
bodies. The rewritten root has no parent; the rewritten second commit has only
the rewritten root as parent. New object IDs are calculated, not invented.

Existing planning commits are descendants of the old `main` tip:

| Old planning commit | Existing subject |
| --- | --- |
| `a8e87de8e02469f018a317efeea1be6493dafdc2` | docs: define Phase 1 execution and delegated review workflow |
| `7c68991ef5f47ba65cc61a0dcc2dfd80fdb0ca46` | docs: require Phase 1 user approval and correct dispatch dependencies |
| `af3b7933ad052b9a9484dc894e5e77ea84f287b9` | docs: record independent Phase 1 technical approval |

This `main`-only message rewrite preserves those existing planning subjects and
bodies; it reconstructs their parent links. Any requested expansion to rewrite
additional messages requires a revised mapping and plan review. New documentation
commits use the requested convention. Before execution, the documentation owner
must commit and hand off a clean, frozen candidate; enumerate any additional
descendants and retain every one without squashing or content editing.

The local Codex capture ref and GitHub-generated `refs/pull/2/*` refs are outside
the editable targets. Preserve the former locally; GitHub regenerates its own PR
refs. Never push backup, capture, pull, or unrelated refs.

## Single-writer and freeze gates

1. Obtain independent Astra high review of this plan and the coordinator's
   execution handoff. Until then, do not create replacement commit objects,
   change refs, commit, or push.
2. The documentation owner completes the CLI/document changes and their review,
   commits the candidate, stops editing, and reports the full frozen local head
   SHA. The coordinator gives one agent exclusive Git-writer ownership across
   both existing worktrees. No new worktree is needed.
3. Recheck all worktrees, including untracked and staged files. Any dirty state
   blocks ref movement. Do not stash, reset, discard, or absorb another owner's
   changes. Recheck the complete ref inventory, remote owner/URL, main protection,
   rulesets, tags, open PRs, configured identity, and all candidate identities.
4. Recheck actual remote main and planning branch. Remote main must still equal
   the full baseline SHA above. Record the current remote planning SHA as an
   exact lease after verifying any advancement was the coordinator-approved
   documentation handoff; unexpected advancement stops the operation. Freeze
   the local candidate independently, since it may include reviewed but not yet
   pushed documentation commits.
5. Use a cooperative Git-writer lock in the Git common directory during the
   ref-changing phase, with cleanup on exit. The coordinator's explicit writer
   ownership remains necessary; a lock alone cannot stop unrelated Git clients.

## Private rollback anchors and candidate construction

Before creating replacement commits, create local-only rollback refs in a
uniquely named `refs/facet-history-backups/<operation>/` namespace for old main,
the frozen local planning candidate, and the exact old remote planning head.
Verify their object IDs and that they retain the original reviewed candidates.
The backups stay in the Git common directory and are not public branches or
artifacts. An owner-only bundle containing exactly these reviewed public-history
anchors is an optional additional backup; do not include ignored runtime data,
unrelated refs, unreachable objects, or earlier private-email commits.

Build replacement objects using `git commit-tree` with the original tree and
per-command original author/committer names, authorized emails, timestamps, and
timezones. Do not change saved Git configuration. Verify identity/date metadata
after each construction rather than relying on ambient environment variables.
Unexpected signature/extra-header semantics require review before reconstruction.

Reconstruct both main commits using the exact subjects above. Then replay every
planning descendant in original topological order, using the exact old tree,
message, identity, and dates, replacing only its parent with the mapped new
parent. This gives rebase semantics while preserving original committer dates;
ordinary rebase's refreshed committer timestamps do not meet this plan. Do not
run `reset --hard`, `checkout --`, force-checkout, or a content merge.

Create an old-to-new full-SHA map for every reconstructed commit. Before moving
any branch, verify every mapped pair has exactly the same tree, author,
committer, author date, and committer date. Verify message equality except the
two approved main subject changes, correct parent chains, unchanged commit
counts, and identical base-to-planning diff. Each content comparison must be
empty, not merely visually similar or an equal final file count.

## Local ref update and exact remote publication

Run repository safety against the clean main and frozen planning indexes, check
all new-ancestry identities, and confirm the candidate contains no executable
Gmail/image/deployment workflow changes. Only then atomically compare-and-swap
the two local branch refs using `git update-ref --stdin` and exact old local
tips. Their checked-out trees and indexes already match the unchanged candidate
trees, so a destructive reset is neither required nor permitted. Immediately
check both worktrees remain clean and their trees are unchanged.

Publish exactly the two approved remote branches in one atomic push. The push
must use explicit full old SHAs, not a bare `--force`, an implicit tracking-ref
lease, `--all`, or `--mirror`:

```text
git push --atomic \
  --force-with-lease=refs/heads/main:9d8595da789e6e450a5bdb0bfe391aab34244237 \
  --force-with-lease=refs/heads/docs/phase1-execution-plan:<verified-old-remote-plan-sha> \
  origin \
  <verified-new-main-sha>:refs/heads/main \
  <verified-new-plan-sha>:refs/heads/docs/phase1-execution-plan
```

The placeholders are replaced only with verified full SHAs. Recheck remote refs
immediately before the push; server-side leases handle later races. If the
server rejects atomic pushes, a lease fails, protection/rules change, or the
outcome is unclear, stop and inspect remote state. Do not silently fall back to
sequential forced pushes, delete branches, weaken protection, or retry against
a newly observed SHA.

After success, query both actual remote refs and PR #2. Verify new main has
exactly the rewritten two-commit chain, the plan is based on that main, PR #2
remains Draft/open with base `main`, and unrelated remote refs/tags are unchanged
apart from GitHub's own regenerated PR refs. Refresh only the two remote-tracking
refs after verifying they have not advanced unexpectedly.

## Review provenance and CI acceptance

Keep original review records tied to the exact old reviewed SHAs. Publish a
redacted old-to-new mapping and the tree-equivalence result; do not rewrite an
old review record to falsely imply its reviewer inspected a new SHA.
`7c68991...` was reviewed before the subsequent maintenance CLI changes. Its
review can describe only that historical plan tree. The revised CLI, workflow,
authority, and documentation candidate needs its own independent review and
candidate binding, irrespective of identical-tree reparenting.

For a reviewed candidate that changes only parent/message metadata, an
independent reviewer may explicitly verify the map and exact tree equality and
record that provenance. No automatic inheritance is allowed for a candidate
with substantive differences. The documentation owner records the actual map,
new review evidence, and historical status after integration ownership returns.

Acceptance evidence required before handoff:

- Main mapped trees and each planning descendant tree match exactly; identities,
  original dates/timezones, messages and parent topology meet the rules above.
- Full-SHA backup anchors exist locally; original reviewed objects remain
  readable. No private backup refs were published.
- Both worktrees are clean; main and plan remote SHAs match the verified new
  targets; PR #2 is still Draft, open, and unmerged; G0 remains pending.
- Repository safety and whitespace checks pass on the staged/tracked index.
  The unchanged spike baseline remains distinct from planned product behavior.
- Fresh offline CI for both rewritten `main` and the current PR head completes
  successfully. Old-SHA CI is retained as historical evidence, not relabeled as
  validation of a new SHA. Observe final job conclusions; pending is not failed.
- Public handoff records actual hashes, content equivalence, CI links, review
  scope and any remaining limits without credentials or private runtime data.

## Failure, recovery, and stop conditions

Before a successful remote push, local refs can be restored by exact
compare-and-swap to the saved anchors if current refs are still the expected
replacement tips and both worktrees remain clean. Retain backups even after a
successful operation; never use broad reflog/garbage-collection cleanup.

After a successful push, any remote rollback is itself another visible rewrite.
Do not automatically undo published history or overwrite later work. Report the
verified remote state and proposed rollback to the coordinator for a new
explicit, lease-bound execution decision. A network failure requires querying
remote state before declaring success, failure, or considering rollback.

Stop for missing execution/review handoff, another writer, dirty worktrees,
unexpected remote/ref/protection/tag/PR drift, non-noreply or agent-owned
identity, signatures not addressed by the plan, non-linear/unexpected history,
tree or date mismatch, safety failure, atomic-push rejection, lease failure,
unclear remote outcome, or failed required CI. Preserve the state and evidence;
do not hide failure, weaken checks, merge the plan, or start product work.

## Executed operation and independent acceptance

The CLI/document owner froze clean candidate
`eca99118b46db765960c7439246b6a1c5f4e5ccb` after independent Astra high
technical approval. The original approved history-plan hash above was verified
unchanged before execution. The coordinator then assigned exclusive Git-writer
ownership and explicitly handed off this one-time operation. Fresh checks found
main/remote at the planned old SHA, remote plan at `af3b793`, four local planning
descendants, clean worktrees, unchanged identity and no protection/rules/tag drift.

| Old full SHA | New full SHA |
| --- | --- |
| `53ac21b10dc6f6d055d5b49e720e5a00ab29632b` | `34818fe9f5d2d7bcb30353939b146418b2d5a814` |
| `9d8595da789e6e450a5bdb0bfe391aab34244237` | `2f78fdf69cba786d2568689b0d0566d827d4285a` |
| `a8e87de8e02469f018a317efeea1be6493dafdc2` | `ba664a2e6fc2e1877cbf9cd026b6282ef51faa30` |
| `7c68991ef5f47ba65cc61a0dcc2dfd80fdb0ca46` | `ad0ed79aeeedbc8c3a5678cd95bd6b3d9a9fe1f1` |
| `af3b7933ad052b9a9484dc894e5e77ea84f287b9` | `cf1a69116d6097eee87ec7e2b83a263565808314` |
| `eca99118b46db765960c7439246b6a1c5f4e5ccb` | `5d623f201b4e4f8c701b196d3f017bf874f3e79a` |

The two main messages became exactly the approved subjects. All four planning
messages remained unchanged. `git commit-tree` preserved original tree,
author/committer identities, timestamps and timezones. Raw reconstructed objects
matched the expected original headers/messages byte-for-byte after only approved
parent/main-subject substitutions. Commit counts/topology and the entire
base-to-plan diff were unchanged. An independent reviewer accepted all six pairs
and explicitly confirmed review traceability from the substantive `eca99118`
candidate to tree-identical `5d623f2`; older review SHAs remain historical.

Private local rollback refs were created and verified:

| Local-only ref | Retained commit |
| --- | --- |
| `refs/facet-history-backups/20261002-normalization/main-before` | `9d8595da789e6e450a5bdb0bfe391aab34244237` |
| `refs/facet-history-backups/20261002-normalization/plan-before` | `eca99118b46db765960c7439246b6a1c5f4e5ccb` |
| `refs/facet-history-backups/20261002-normalization/remote-plan-before` | `af3b7933ad052b9a9484dc894e5e77ea84f287b9` |

Local branch changes used one atomic compare-and-swap transaction. The remote
push used `--atomic` and exact full-SHA leases for old main `9d8595d` and old
remote plan `af3b793`; both updates succeeded together. There was no fallback,
branch deletion, content reset or identity-config change. Post-push remote tips
were main `2f78fdf69cba786d2568689b0d0566d827d4285a` and planning branch
`5d623f201b4e4f8c701b196d3f017bf874f3e79a`. No backup/capture refs or tags
were published; both worktrees remained clean. Independent acceptance included
the backups, remote tips, unchanged diff and Draft/open PR #2 based on main.

[Fresh main CI](https://github.com/GhostFlying/facet/actions/runs/36965264011)
and [fresh plan-candidate CI](https://github.com/GhostFlying/facet/actions/runs/36965268013)
completed successfully for Python 3.11/3.12. Every safety, locked dependency,
lint, format, offline test and CLI-smoke step passed. Earlier same-head PR run
`36965267744` was superseded/cancelled under existing workflow concurrency;
the latest run succeeded without a manual rerun. These CI results validate the
listed SHAs; this report-only appendix does not claim CI for its later commit.

The one-time history gate is complete. G0 remains pending, PR #2 remains Draft
and unmerged, and maintenance CLI/product runtime remain planned. No product
code, Gmail operation, image publication, deployment or release occurred.
