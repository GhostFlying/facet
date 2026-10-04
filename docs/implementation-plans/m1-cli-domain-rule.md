# CLI exact domain rule

Status: bounded maintenance-CLI unit on top of `origin/main` `055eae6`.
It does not change the authentication trust boundary or claim live Gmail
automatic admission.

## User-observable delivery

An operator can run `facet rules add-domain --domain <value> --yes
--request-id <id> --json` against initialized managed state. The command
normalizes one exact registrable domain using the existing PSL/IDNA policy,
publishes a new durable ruleset through the existing single writer, and safely
replays the same request. It rejects invalid/public-suffix inputs, pending
bindings, request collisions, and private output by default.

## Scope and reuse

- Extend the existing rules parser and sender-rule mutation with a closed
  `RuleKind.ALLOW_DOMAIN` path; reuse `normalize_rule`, policy publication,
  request-key collision guards, config-artifact verification, and owner lock.
- Add subprocess tests for valid normalization, replay, invalid/public-suffix
  input, pending binding, no provider/target access, and aggregate-only output.
- Do not add a new operation framework, schema table, Gmail call, label write,
  source-path attestation, blacklist/thread-stop behavior, or rules list/export.

## Acceptance and stop gates

The focused CLI tests, affected rule/policy tests, full offline suite, Ruff,
wheel smoke, safety scan, and Python 3.12/3.13 CI must pass. The candidate is
reviewed independently against this exact plan and SHA before engineering
merge. Any need to change rule persistence, disclosure semantics, or source
trust stops this unit for a revised plan.
