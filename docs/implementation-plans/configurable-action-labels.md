# Configurable source action labels

Date: 2026-10-05. Revision: 1. Status: awaiting independent plan review.
Base: `a888655` (current `origin/main`).

## Goal

Replace the source action-label adapter's hard-coded names with an explicit
configuration block while preserving the existing behavior by default:

```yaml
source:
  action_labels:
    add_sender: AI/AddSender
    add_domain: AI/AddDomain
    blacklist: AI/BlackList
```

Operators may use another exact set, for example `Facet/AddSender`,
`Facet/AddDomain`, and `Facet/BlackList`. Facet only reads the configured source
labels and consumes their History events. It does not create, rename, delete,
clear, or otherwise write source labels, and it does not request or expand
OAuth scopes. Existing source/target bindings continue without reauth because
the scope policy and credential ownership are unchanged.

## Scope and files

- `src/facet/config.py`: add a typed `source.action_labels` configuration
  model with the three exact keys. Missing `source`/`action_labels` keeps the
  default names above for backward compatibility with existing config files.
  Validate each name as a bounded, non-empty, control-free string and reject
  duplicate names so one provider label cannot represent multiple actions.
  Preserve strict unknown-key, YAML, depth/size, and round-trip validation.
  Include the resolved values in deterministic config serialization without
  storing credentials or message data.
- `src/facet/gmail/source.py` and `src/facet/runtime/foreground_runtime.py`:
  pass the resolved source label names into `action_label_map()` and match
  exact configured names while retaining provider duplicate/malformed response
  failures and the missing-label opt-in behavior. Keep the adapter read-only:
  only `users.labels.list` and existing History reads are allowed; no label
  create/update/delete calls or scope changes.
- `tests/unit/test_config.py`, `tests/unit/test_gmail_source_candidates.py`,
  `tests/integration/test_foreground_runtime.py`, and relevant action-label
  tests: cover default compatibility, custom `Facet/*` names, missing labels,
  duplicate configured names, duplicate provider labels, malformed names,
  round-trip serialization, and assertions that the fake transport receives
  no label-writing calls. Existing binding fixtures must pass without reauth.
- `docs/gmail-projection-spec.md`, `docs/cli-spec.md`, and the configuration
  example in the applicable runbook: document the optional `source` block,
  defaults, exact-name/unique validation, read-only lookup, no-label-creation
  boundary, and no-reauth compatibility. Do not add a new write command or
  imply that labels are created automatically.

## Compatibility and migration

1. An old config with no `source` key or no `action_labels` resolves to the
   existing `AI/AddSender`, `AI/AddDomain`, and `AI/BlackList` names. Existing
   bindings, tokens, scopes, DB mappings, and action history remain valid; no
   OAuth reauth or migration of label IDs is required.
2. A custom configuration affects only future source-label resolution. Existing
   durable events store provider label IDs and remain interpretable by the
   resolved map for the current config; no historical event rewrite or bulk
   replay is introduced. A config artifact update must use the existing
   ownership/configuration path and preserve its digest/lock protocol; direct
   file replacement is not added.
3. Missing configured labels retain the current optional behavior: ordinary
   sync continues, while matching action work remains explicit attention. A
   provider response containing duplicate IDs/names or invalid label fields
   fails with the existing typed error; it is never resolved by choosing one.
4. Label names are exact provider names, not substrings, globs, or aliases.
   Renaming a configured label does not rename or delete anything in Gmail and
   does not infer the old label as an alias.

## Acceptance tests

- Minimal legacy config loads the three default names and serializes
  deterministically; custom `Facet/*` config loads and round-trips exactly.
- Unknown/missing action-label keys, empty/control/oversize names, duplicate
  configured names, malformed YAML, and unsafe resource inputs fail closed with
  the existing sanitized configuration error.
- Source label lookup resolves custom names exactly, preserves missing-label
  optional behavior, and rejects duplicate/malformed provider entries.
- Foreground runtime passes the configured map without creating, modifying,
  deleting, or clearing source labels; fake transport call logs prove no label
  write methods or additional OAuth scopes are used.
- Existing binding/credential fixtures load and run without reauth or token
  replacement. Docs state the default/custom names, read-only/no-create
  boundary, and migration behavior consistently.
- Focused tests, full offline pytest, Ruff/format, and
  `bash scripts/check-repo-safety.sh` pass. No live Gmail or mailbox data is
  used or claimed.

## Risks and stop gates

- Do not broaden OAuth scopes, create labels, add aliases/globs, rewrite
  historical events, or silently mutate existing config artifacts. If the
  current ownership/configuration writer cannot safely persist the new block,
  stop and revise the plan rather than bypassing its lock/digest protocol.
- If adding `source` conflicts with a current schema/fixture or would require
  reauth, DB migration, or source mailbox mutation, stop and report the
  smallest contract decision needed.
- This unit is offline/synthetic only. Do not copy real label names tied to a
  private account, run Gmail API calls, perform sync/backfill, or deploy.

