# Facet

Facet creates controlled projections of user data for AI agents. The first
vertical slice is a selective Gmail projection into a separate Gmail account.

Repository: [GhostFlying/facet](https://github.com/GhostFlying/facet) (public).
License selection is pending; no production release is available yet.

This repository currently contains a Phase 0 spike, not the production sync
daemon. Its purpose and stop conditions are documented in
[`docs/phase-0-gmail-spike-plan.md`](docs/phase-0-gmail-spike-plan.md).
The redacted live findings are documented in
[`docs/phase-0-gmail-spike-results.md`](docs/phase-0-gmail-spike-results.md).

Phase 0 is complete: Gmail API behavior and target Gmail conversation/PDF access
were verified. Production implementation is planned, not yet available.

The user approved the complete Phase 1 plan on 2026-10-02 at
`caba7c73895a303d329cf3eba1c89557530c38c5`; [PR #2](https://github.com/GhostFlying/facet/pull/2)
is merged at that exact SHA. Agents now advance reviewed internal work packages
and qualified PR merges autonomously. Production capabilities are still
unimplemented; material product, privacy or authority changes return to the user.

## Development plan

- [Agent instructions](AGENTS.md): mandatory project boundaries, autonomous
  workflow, privacy, authority, and verification requirements.
- [Development status](docs/development-status.md): verified capabilities,
  remaining milestones, and the next resumable implementation unit.
- [Project plan](docs/project-plan.md): Phase 1 scope, milestones, acceptance,
  and later roadmap.
- [Complete Phase 1 execution plan](docs/phase-1-execution-plan.md): 36 stable
  work packages, dependencies, parallel dispatch waves, acceptance gates, risks,
  and external decisions.
- [Agent workflow](docs/agent-workflow.md): coordinator-only root role,
  delegated engineering, independent plan/code/acceptance review, model routing,
  worktree ownership, GitHub Issues/PRs, and evidence-bound handoffs.
- [Plan technical review](docs/reviews/phase-1-plan-review.md): reviewed candidate
  SHA, independent findings and corrections; separate from user plan approval.
- [Phase 1 Epic](https://github.com/GhostFlying/facet/issues/1): durable progress
  and the ready-work-package queue.
- [Phase 1 progress ledger](docs/phase-1-progress.md): the 36 package states,
  current readiness, shared-document ownership and evidence scope.
- [Product contract](docs/product-contract.md): thread disclosure, permission
  modes, BlackList, and consistency guarantees.
- [Gmail implementation specification](docs/gmail-projection-spec.md): planned
  configuration, storage, queues, recovery, and CLI.
- [Dashboard specification](docs/dashboard-spec.md): read-only sync status,
  progress, counts, issues, diagnostics, and privacy boundaries.
- [Complete maintenance CLI](docs/cli-spec.md): command/ownership contract,
  offline troubleshooting, JSON/exit codes, confirmations, bounded repair and
  recovery, backup/restore/migration, and Compose end-to-end acceptance.

Facet's acceptance boundary ends at correct target Gmail materialization and
readback. Each AI product owns its connector indexing and retrieval behavior.

Phase 1 includes a read-only Web dashboard with no email details. Facet serves
HTTP; a fronting Nginx owns HTTPS and user authentication. The production database
stores sync metadata and state, not complete messages or attachments. Raw payloads
are handled in memory without a disk spool.

Phase 1 will provide a non-root image and one-command Docker Compose startup
after the initial private configuration and Gmail OAuth setup. GitHub Actions
will publish main full-commit-SHA images to the user-approved public package
`ghcr.io/ghostflying/facet`; PRs build without publishing. Explicit image
versions/digests, backup/restore, upgrade/rollback, and anonymous pull verification
are delivery gates. Compose files and images are planned, not available yet.
Image workflow implementation and publication follow the approved package
dependencies and M6 gates; G0 approval alone does not start image work now.
Formal version tags/releases, live mailbox scope and deployment host remain
separate decisions.

The complete CLI is a required Phase 1 deliverable, not help-only scaffolding.
All maintenance commands will run from the image without host Python. Status,
doctor and stopped backup/restore/migration/inspection work offline when Gmail
or OAuth fails; queue retry cannot bypass unknown-insert recovery. This new CLI
contract has independent technical review evidence but remains unimplemented.

Commit subjects use atomic English `type: action summary` form: features use
`feat: impl ...`, fixes use `fix: fix ...`, and documentation/test/refactor/CI/
chore commits use a clear action verb. The user-authorized one-time main-history
normalization is a separately reviewed operation, not general rewrite authority.

## Local setup

```bash
uv sync --extra dev
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run facet-spike --help
bash scripts/check-repo-safety.sh
```

Before coding, write the scoped implementation plan to
`docs/implementation-plans/` and obtain independent plan review; implementation
then needs independent code and acceptance review. Offline CI uses the committed dependency lock and
checks lint, formatting, tests, CLI startup, and the repository safety baseline.
It never receives Gmail credentials. The safety check reads tracked/staged files;
ignored runtime data is not scanned or uploaded.

Private runtime files live in `.facet-spike/` and are ignored by Git. The CLI
creates token and state files with owner-only permissions.

## Google OAuth prerequisite

1. Create or select a Google Cloud project.
2. Enable the Gmail API.
3. Configure the Google Auth Platform audience and add both Gmail accounts as
   test users when the app is External and in Testing.
4. Create an OAuth client of type **Desktop app**.
5. Download its JSON and save it as:

   ```text
   .facet-spike/client_secret.json
   ```

6. Restrict the file locally:

   ```bash
   chmod 600 .facet-spike/client_secret.json
   ```

The source spike requests `gmail.readonly`. The target spike requests both
`gmail.insert` and `gmail.readonly`; target read access is required to measure
crash recovery and fidelity.

Google's device authorization flow does not support Gmail scopes. The supported
Desktop flow redirects the browser to a loopback address. On a remote host,
forward the selected local port to the same remote loopback port before opening
the authorization URL, for example:

```bash
ssh -N -L 8765:127.0.0.1:8765 <remote-host>
uv run facet-spike auth source --port 8765
```

Run source and target authorization separately, selecting the intended account
on each consent screen. Never send token JSON, authorization responses, or
refresh tokens through chat.

## First commands

```bash
uv run facet-spike auth source --port 8765
uv run facet-spike auth target --port 8765
uv run facet-spike doctor
uv run facet-spike search source --query 'has:attachment newer_than:1y'
```

Copy commands make external writes to the target Gmail account. Inspect their
help and use an intentionally disposable target account.
