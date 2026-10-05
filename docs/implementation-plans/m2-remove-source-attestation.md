# Remove source-path attestation from automatic admission

Status: implementation candidate; plan independently approved by
`/root/cli_sync_review`, implementation review pending.
Base: `origin/main` at `7e334efc31890ad5fb187c74fef1dbc7815adfe5`

## Product decision

The user explicitly removed source-path attestation and sender-authentication
verification as a Phase 1 admission gate. Gmail owns SMTP authentication and
mail classification. Facet projects messages that Gmail has placed in the
source mailbox when the configured exact sender/domain policy authorizes them.
Facet does not claim that the sender or message content is safe.

## User-observable delivery

The existing CLI vertical path remains:

```text
init -> fake/real role authorization -> exact rule -> preview (zero target writes)
-> explicit backfill start -> metadata discovery/History -> insert/readback
-> durable mapping -> restart continuation
```

Automatic admission no longer fetches raw mail for authentication, performs DNS
or DKIM verification, parses `Authentication-Results`, or routes an otherwise
rule-matching message to attention solely because authentication is unknown.

## Scope and reuse

- `src/facet/gmail/source.py`: use the existing metadata candidate boundary and
  keep message/thread binding, sender normalization, visibility and provider
  error checks; remove the raw-authentication call from normal candidate flow.
- `src/facet/gmail/source_auth.py`, `src/facet/projection/authenticity.py` and
  the DKIM dependency: remove production admission ownership. Keep no unused
  provider path or raw-auth shortcut. Delete the now-unconsumed evidence types
  and tests rather than leaving a dead trust seam.
- `src/facet/projection/admission.py`, `src/facet/projection/rules.py` and
  `src/facet/config.py`: make exact rule matching, source account binding,
  visibility and draft checks the complete admission decision. Remove the
  `rules.authenticity` configuration field and all AUTHENTICITY_* admission
  outcomes; a matching metadata candidate with no auth evidence is admitted.
  For existing private configs, accept the legacy key only when its old value is
  `require_trusted_auth`, ignore it, and omit it from newly serialized config;
  this avoids a state-artifact migration while making the old gate inert.
- `src/facet/projection/backfill.py` and admission-reference consumers: retain
  the existing durable `PolicyVersion("auth-v1")` token for backward
  compatibility with persisted rule revisions and admission references. It is
  reinterpreted as the stable projection-rule policy token; it no longer means
  sender authentication and no SQLite shape or migration manifest changes.
- `src/facet/sync.py`, `src/facet/runtime/foreground_runtime.py` and
  `src/facet/cli/bootstrap.py`: compose admission without a source-auth provider
  and keep action labels, insert/readback and recovery unchanged.
- `src/facet/gmail/synthetic.py` and `src/facet/projection/backfill.py`: remove
  the synthetic DKIM provider seam and update the consumer documentation/types
  to describe metadata/rule admission.
- `tests/cli/test_bootstrap.py`, source/admission/runtime tests and test fixtures:
  replace signed-raw prerequisites with metadata-only synthetic messages and
  prove a spoofed/absent authentication header has no effect on a matching rule.
- `docs/product-contract.md`, `docs/gmail-projection-spec.md`,
  `docs/project-plan.md`, `docs/phase-1-execution-plan.md`,
  `docs/implementation-plans/adrs/authentication-trust.md`,
  `docs/implementation-plans/m1-01-package-config.md`,
  `docs/implementation-plans/m2-admission-rules.md`,
  `docs/implementation-plans/m2-adapter-discovery-history.md`,
  `docs/implementation-plans/m2-automated-projection-core.md`,
  `docs/implementation-plans/m2-foreground-sync-cli.md`,
  `docs/implementation-plans/cli-sync-closure.md`, and
  `docs/development-status.md`: record the confirmed product boundary and
  remove the old trusted-auth gate from canonical requirements, while retaining
  a short note that Facet does not claim sender authenticity. Historical review
  records may retain their original conclusions, but must be marked historical
  where they otherwise look like active dependencies.
- `pyproject.toml` and `uv.lock`: remove the DKIM package only if no remaining
  production or test consumer requires it.

No database migration, new framework, provider scope, live Gmail operation,
deployment, or target mailbox mutation is included.

## Required invariants

- Exact sender/domain/blacklist/effective-time policy remains unchanged.
- New Spam/Trash/draft admission rules remain unchanged; tracked thread history
  semantics remain unchanged.
- Source and target account/scope/binding checks remain mandatory.
- H0, History events/cursor, insert intent, mapping and generation ordering
  remain unchanged.
- Unknown insert outcomes still enter recovery and are never blindly retried.
- Raw mail remains memory-only for projection; it is not fetched merely for
  admission and never enters DB, logs, CLI or Dashboard output.
- Preview still performs zero target writes and backfill still needs explicit
  start.

## Acceptance and stop gates

1. A real CLI subprocess command path, with only Gmail/OAuth calls replaced by
   the synthetic transport, completes init, role authorization, rule,
   write-free preview, explicit start, discovery, insert/readback, mapping and
   a second-process zero-duplicate continuation without a signed raw fixture,
   DNS call or `Authentication-Results` decision.
2. A matching message with absent, failed, forged, duplicate or conflicting
   authentication headers follows the same rule decision as any other matching
   metadata message; no authentication-specific attention is emitted.
3. Non-matching, draft, prohibited Spam/Trash, binding mismatch, provider
   failure, generation-stale and unknown-insert cases retain their existing
   outcomes.
4. Focused source/admission/runtime/config tests, full offline suite, Ruff/format,
   wheel/help, repository safety and candidate CI pass. The focused evidence
   includes legacy-config compatibility and proves no raw fetch, DNS lookup or
   source-auth provider call occurs during admission. No live Gmail authorization
   or deployment operation is performed.

The fake transport may replace only Gmail/OAuth interactions. Readiness,
bindings, rules, epochs and mappings must still be created through the real CLI
commands; no test may seed those rows directly to bypass command behavior.

Stop and revise this plan if implementation would change thread disclosure,
rule semantics, recovery ordering, privacy output, OAuth scope or target write
behavior beyond the explicit product decision above.
