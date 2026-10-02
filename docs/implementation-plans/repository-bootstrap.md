# Repository bootstrap implementation plan

Date: 2026-10-02

Scope: publish the existing Phase 0 spike and Phase 1 specifications to a public
`GhostFlying/facet` GitHub repository, with durable instructions for autonomous
implementation. This bootstrap does not implement or start the production daemon.

## Planned changes

1. Add root `AGENTS.md` with product and privacy invariants, milestone order,
   authority boundaries, implementation-plan requirements, and verification gates.
2. Add `docs/development-status.md` as the resumable development handoff; distinguish
   verified spike behavior from planned production capabilities.
3. Extend `.gitignore` for production state, credentials, databases, and artifacts.
4. Add an offline GitHub Actions workflow and a tracked-content safety check. Pin
   actions to verified upstream commit SHAs; CI receives no Gmail credentials.
   Test the guard against synthetic credential formats, private file paths, and
   staged-index/working-copy differences without printing matched content.
5. Correct the spike report's obsolete AI-connector acceptance requirement and
   add a regression assertion. No live Gmail calls or account changes.
6. Update README navigation and repository references without choosing a license
   or publishing a public release.

## Verification and publish gates

- Run the locked development environment, Ruff lint/format checks, offline pytest,
  and CLI help; check shell syntax and documentation links/whitespace.
- Stage only reviewed source, tests, docs, lockfile, and bootstrap configuration.
  Check the Git index for credentials/private runtime files without printing any
  matched secret values. Review the initial commit file list before publication.
- Use the user's account identity and authorized GitHub noreply email, with no
  agent co-author. Preserve global and repository Git configuration.
- Publish the public repository and push the initial `main` commit. Verify remote
  ownership, visibility, commit identity, and workflow results.
- Update the durable handoff with actual outcomes. Do not claim M1-M6 completion.

## Stop conditions

Stop for an unexpected remote/owner, unavailable GitHub authority, ambiguous
private-data matches, or an unapproved visibility change. Do not delete mailbox
contents, reuse spike state as production state, create releases, or deploy.

The content scan is a baseline guard, not proof that every possible privacy leak
is detectable. Production schema, logging, HTTP, and UI need behavioral privacy
tests in their own milestones.

## Authorized public-publication follow-up

On 2026-10-02 the user explicitly requested a PUBLIC repository and use of the
account's GitHub noreply email. The current Git identity already matches that
choice; no saved identity override is necessary.

1. Update `AGENTS.md`, README, project plan, and development handoff to reflect the
   public/noreply decision. Keep license selection unresolved, not implicit.
2. Recheck tracked/staged content before making anything publicly accessible.
3. Verify that the remote has no branch, then replace the unpublished root commit
   using the existing user's configured identity with `--reset-author`. Do not
   publish the rejected old commit or use a force push.
4. Change only `GhostFlying/facet` visibility to public, push `main`, then verify
   public visibility, remote commit SHA, author/committer noreply identity, and CI.
5. Record observed completion and any CI fixes in the durable handoff. No Gmail
   writes, release creation, deployment, or license choice are part of this work.

## Earlier attempt / handoff

- Local gates passed: 24 offline tests, Ruff lint/format, CLI help, shell syntax,
  documentation links/fences, staged safety baseline, and whitespace checks.
- Initial local commit created using the unchanged user identity.
- Private `GhostFlying/facet` was created and `origin` configured. The first push
  was rejected by `GH007` (author-email privacy protection). At that point the
  remote had no branch and CI had not run. No private email or credential is
  recorded in this handoff.
- Work stopped for the identity decision. The user subsequently authorized the
  public/noreply follow-up above; publication and CI verification remain pending.
