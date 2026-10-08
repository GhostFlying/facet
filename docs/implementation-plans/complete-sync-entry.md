# Complete sync entry

2026-10-08. Base: `c4e3181680910fdc73b700ea617890cfc0b415e0`.
Root implements; independent Sol xhigh reviews. Existing authorized live trial
continues in its unchanged qualified image; this unit has no live authority.

## User delivery and minimal reuse

`facet sync --once --yes` prepares/starts the default six-month scope and runs
one production cycle without separate preview/start IDs. `facet sync --yes`
then uses the existing foreground owner/Dashboard loop. Granular commands keep
their existing semantics; Compose defaults remain `run`. No new sync engine,
IPC, runtime framework, schema or application-owned authentication UI.

Refactor the existing preview/start/cycle/service operations to accept an already
held owner/config; their ordinary CLI wrappers continue to acquire that owner.
The complete entry holds one writer from selecting scope through execution.
It verifies binding/scopes and uses the same credential manager and provider
factory. Missing authorization gives the existing normalized role-specific
error and guidance to existing setup/auth commands; never auto-select accounts
or expand scopes. Validate runtime options and confirmation before mutation.

An optional caller request ID identifies an intentional operation. Without it,
derive stable internal preview/start keys from persisted owner namespace,
binding/config/ruleset revisions plus the default calendar
window start. A matching invocation in that calendar window resumes the same
durable preview/start; selected-rule/scope changes create a distinct intentional
operation. Preview's persisted window/end and selected rules are authoritative,
not recomputed on replay. Ordinary `run`/container restart never creates a scope.
Do not include generation-sum invalidation in default keys: normal admissions
change it. Retain that guard in preview/start validation and stopped workers.
Explicit request IDs derive children only from owner namespace and caller ID;
lookup their saved operations before selecting current rules/window, so replay
after rules/calendar changes keeps the original scope, not a new epoch.
Only existing DB operation records store progress; deterministic child keys
exist before submission and no additional plaintext journal is needed. A stale
unstarted preview fails existing guards rather than silently replacing scope.

## Files, acceptance and stop gates

- `src/facet/cli/bootstrap.py` and a small CLI-local orchestration module if
  helpful: parser, confirmation, stable key selection and shared owner operation
  reuse. Public result is aggregate counts/state/disclosure, not keys/mail IDs.
- `runtime/foreground_runtime.py`: share its existing two-role credential
  preparation with the complete entry before scope mutation; no new policy.
- `tests/cli/`: real subprocess init/auth/rules -> complete sync historical/
  History/action -> insert/readback/mapping -> restart without duplicate intent;
  external-only Gmail/OAuth fakes, no readiness/binding/rule/epoch DB seeds.
  Cover interrupted preview/start replay, stale preview, changed selected rules,
  normal admission/generation changes keeping no-key replay in the same epoch,
  explicit same-key replay after rules/calendar changes retaining saved scope,
  unknown insert no resend, stopped generation, writer conflict, missing OAuth,
  confirmation and runtime-option rejection before mutations, privacy sentinels.
  Keep granular zero-write preview and plain-run non-expansion regressions.
- `README.md`, CLI usage/current status: concise actual evidence and unfinished
  Phase 1 gates; replace obsolete foundation-only descriptions, not the contract.

Develop affected tests first; exact final source gets independent implementation
acceptance, prescribed full offline checks and non-root image CLI external-fake
E2E before focused PR/required CI. Keep prior source/image evidence for unchanged
components. No live new scope, unknown retry, cleanup, deployment, Release or
continuous service startup. Stop for a material product/authority conflict;
ordinary engineering remains authorized.
