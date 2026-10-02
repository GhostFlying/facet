# Facet development status

Updated: 2026-10-02

This is the durable handoff for autonomous development. Update it with evidence
at the end of each coherent implementation unit. Do not store account addresses,
mail identifiers, private fixtures, tokens, or raw diagnostics here.

## Current state

| Unit | Status | Evidence / remaining gate |
| --- | --- | --- |
| Phase 0 Gmail spike | Complete within its scope | See [redacted results](phase-0-gmail-spike-results.md); production behavior not implied |
| Repository bootstrap | Complete | Public `main` published with account noreply identity; Python 3.11/3.12 offline CI passed |
| M1 foundation | Not implemented | Config, bindings, schema/migrations, locks, rule storage, public status models |
| M2 durable projection | Not implemented | Production workers, fidelity, insert intent, recovery, bounded memory |
| M3 admission/backfill | Not implemented | Rules/authenticity, preview, fixed six-month discovery, durable backfill |
| M4 sync + Dashboard alpha | Not implemented | History/gap recovery, reconcile, aggregate read-only Web UI |
| M5 action labels | Not implemented | Learning, legacy handling, idempotent commands, BlackList cancellation |
| M6 self-hosted v0.1 | Not implemented | Compose/image, Nginx example, backup/restore, bilingual docs, live/dogfood gates |

The executable package is currently `facet_spike`, not `facet`. Existing tests
cover MIME payload analysis/comparison, private atomic file permissions, RFC-ID
query validation, and aggregate spike reports. They do not test a production
daemon, trusted sender admission, bulk backfill, or a rendered Dashboard.

## Active implementation record

- [Repository bootstrap](implementation-plans/repository-bootstrap.md).
- Repository: [GhostFlying/facet](https://github.com/GhostFlying/facet), verified
  PUBLIC with default branch `main`; `origin` points to it. On 2026-10-02 the user
  explicitly requested public visibility and their account's GitHub noreply email.
- Local verification: 24 offline tests passed; Ruff lint/format, spike CLI help,
  shell syntax, tracked/staged safety scan, documentation links/fences, and staged
  whitespace checks passed. No live Gmail requests were used for this bootstrap.
- The first push was rejected by `GH007`. The unpublished root commit was
  replaced using the current configured user/noreply identity, without changing
  saved Git configuration or email privacy protection. GitHub confirmed both
  author and committer use the account's noreply identity and attribution is
  `GhostFlying`. The rejected old commit is not in public history.
- Initial published commit: `53ac21b`. Its [offline CI run](https://github.com/GhostFlying/facet/actions/runs/36955887359)
  completed successfully on both Python 3.11 and 3.12: 24 tests in each job,
  tracked-content safety baseline, locked install, lint, formatting, and CLI smoke.
- Published GitHub tree checked: source/tests/docs/configuration only; no private
  runtime directory or credential files. The baseline scan is not a substitute
  for the production privacy tests still required by later milestones.
- Runtime credentials/evidence are ignored local files. No live Gmail writes are
  part of this bootstrap, and no experimental state is adopted as production data.

## Next authorized development unit

When asked to implement the next phase, start M1 from the [project plan](project-plan.md).
Write a concrete M1 implementation record before coding. Its minimum scope is:

1. Establish the production Python package/CLI without breaking the spike.
2. Validate configuration and explicit source/target bindings; refuse identity
   swaps or identical accounts, and separate private internal configuration from
   allowlisted public diagnostics.
3. Implement schema v1, migrations, durable repositories, process/writer locks,
   rule effective times, and metadata-only typed payloads.
4. Establish private OAuth/token handling and synthetic tests; require separate
   authorization for real account setup or additional scopes.
5. Define Dashboard response models and privacy sentinels before exposing HTTP.
6. Establish conservative authentication-evidence parsing/tests. Do not enable
   automatic admission using the spike's pass counters.

No automatic production backfill or deployment is authorized by a repository
bootstrap request. Complete each requested unit's acceptance gate and record
results before moving into broader live verification.

## Known limits and decisions still needed

- Gmail insert is not exactly once; target search timing is not an SLA. Production
  crash/recovery and ambiguous-ID tests remain necessary.
- Default raw processing is memory-only with no disk spool; source loss may
  prevent recovery. DB contains only necessary metadata and state.
- Target may contain unmanaged or old experiment mail. Initialization reports it
  without deleting, adopting mappings, or assuming All Mail is empty.
- AI connector retrieval is an AI-product responsibility, not a Facet gate.
- Real bank domains/credible authentication samples, dogfood host and local
  volume, license, and release/image destination remain undecided. Public source
  repository visibility is decided and does not authorize a production release.
