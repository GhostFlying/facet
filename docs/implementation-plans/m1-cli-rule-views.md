# Persisted rule inspection commands

Status: bounded maintenance-CLI unit on top of main `535e096`.
This unit exposes the currently published ruleset for local maintenance without
changing admission, Gmail access, or the rule publication protocol.

## User-observable delivery

Add two offline commands:

- `facet rules list --json` returns aggregate rule counts and the current
  ruleset revision without rule values, addresses, or local identifiers.
- `facet rules show --json --private-metadata` returns the selected persisted
  rule's normalized value, current revision, effective time, enabled state and
  origin. The exact grammar is `facet rules show --rule-id <local-id>`;
  `--rule-id` is required and the selector must belong to the configured
  projection's sealed current ruleset. Rule values and rule IDs are private
  local metadata and are rejected from public output.

Both commands read the managed SQLite snapshot without Gmail/OAuth calls or the
writer lease. They read the sealed current ruleset and its referenced rule
revisions, never reconstructing rules from standalone config or an unsealed
revision.

## Scope and reuse

- Extend the existing `rules` parser/dispatch and use the existing readonly
  state/config ownership checks.
- Add subprocess coverage for empty and populated rulesets, missing/foreign
  `--rule-id` selectors, projection ownership validation, public-output
  rejection, offline provider guards, and unchanged state files. A missing or
  malformed selector returns `invalid_input`; a well-formed rule ID that is not
  present in the configured projection's current ruleset returns
  `owner_unavailable` without disclosing whether it exists elsewhere.
- Do not add schemas, mutation paths, new rule kinds, target/source calls,
  public identifiers, or rule deletion/blacklist behavior in this unit.

## Acceptance and stop gates

Focused CLI/status tests, affected tests, full offline suite, Ruff/format,
wheel smoke, repository safety, independent implementation review, and
supported-Python CI must pass. If the command would need to publish a rule,
show an identifier in public output, or add removal/blacklist semantics, stop
and leave that operation for a later reviewed unit.
