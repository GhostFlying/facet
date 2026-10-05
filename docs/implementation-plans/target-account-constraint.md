# Dedicated target-account deployment constraint

Date: 2026-10-05. Revision: 3. Status: awaiting independent plan review.
Base: `1398549` (current `origin/main`).

## Goal

Make the production deployment precondition explicit: the configured target
must be a newly created, dedicated Gmail account/mailbox, and the operator
must attest/configure that Facet is the only application authorized to write
to it. Gmail metadata and OAuth scopes cannot prove that sole-writer claim or
identify every other writer's activity. AI products may read the target as the
intended disclosure consumer, but no other application, forwarder, human
workflow, or legacy projection may write there. This is a deployment and
setup contract, not permission to mutate a mailbox. The user has explicitly
authorized this stricter product-contract change for this documentation unit.

The existing defensive boundary remains mandatory. Any pre-existing,
unexpected, or unmanaged target mail (including messages, drafts, Spam, or
Trash) is a fail-closed condition for setup/deployment. Facet must not claim,
adopt, relabel, delete, purge, or silently clean that content. The documents
must distinguish the new-account precondition from later audit/recovery
behavior, where unmanaged content is still reported and never auto-claimed.

This unit is documentation-only. It does not change Python, CLI behavior,
OAuth scopes, Gmail state, credentials, Compose, deployment, or live sync. No
real account or mailbox is inspected.

## Scope and files

- `docs/product-contract.md`: replace the advisory “target should be
  dedicated” wording with the required production precondition: a new,
  dedicated target account and an operator-attested/configured Facet-only
  application writer. Distinguish that attestation from observable Gmail
  checks. Define the permitted AI read-only consumer boundary, the
  fail-closed result for unexpected/unmanaged mail, and the continuing
  no-delete/no-claim promise. Clarify that this requirement does not authorize
  target cleanup or mailbox mutation.
- `docs/gmail-projection-spec.md`: make target admission/setup verify, after
  target OAuth and through read-only Gmail calls but before any projection or
  insert, the empty, dedicated mailbox and account identity. Cover all
  relevant Gmail categories (normal mail, drafts, Spam, and Trash), and the
  operator-attested operational rule that no other writer is configured; do
  not claim Gmail APIs can prove it. Keep existing insert-attribution, recovery, audit, and
  unmanaged-content rules intact: an unexpected item stops setup/deployment
  and enters a report/attention state rather than being mapped or removed.
  State that existing deployments cannot be made compliant by automatic
  cleanup or retroactive claiming.
- `docs/oauth-setup.md`: add a pre-OAuth deployment gate for the operator's
  new-account/dedicated-account declaration and explicit Facet-only-writer
  attestation. After target OAuth, document the read-only mailbox/account
  discovery across normal mail, drafts, Spam, and Trash; before the first
  projection/insert, unexpected content or account/binding mismatch stops the
  flow. OAuth consent is not a Gmail mailbox write. Document that setup has no
  delete/claim/cleanup path. Synthetic examples only; do not add real
  addresses or account evidence.
- `docs/cli-spec.md`: add the matching setup/doctor/deployment contract only
  where command behavior is described: setup/preflight and deployment checks
  fail closed on an unexpected target, while target audit reports unmanaged
  content and repair remains explicit and bounded. Do not invent a new
  mutation command, auto-cleanup flag, or mailbox ownership mechanism.

## Contract details to preserve

1. “Sole writer” means the operator attests/configures Facet as the only
   application/service intentionally authorized to perform target Gmail
   writes. Gmail metadata and OAuth scopes cannot prove that claim or identify
   every other writer's activity. AI products remain read-only consumers;
   provider-generated metadata is not treated as a Facet mapping or as
   permission for another writer.
2. The operator's new-account declaration and sole-writer attestation happen
   before OAuth. After target OAuth, read-only mailbox/account checks happen
   before first projection/insert. A target with any unexpected or unmanaged
   item, legacy/spike copy, prior forwarding, or observable evidence of another
   writer fails closed. No content is adopted, deleted,
   relabeled, or moved to make the check pass.
3. Existing production deployments are not silently migrated. The operator
   must attest to the prerequisite at the next documented deployment/setup
   gate; until verified, the safe state is blocked/report-only. Existing
   mappings and audit evidence remain intact.
4. The target account identity must remain bound to the configured target
   role. A role/account mismatch, account reuse, or evidence of another
   writer is a deployment failure, not a reason to broaden OAuth scopes.

## Acceptance tests

- `product-contract.md` explicitly requires a newly created, dedicated target
  account and operator-attested Facet-only application writes, distinguishes
  that attestation from unobservable Gmail writer activity, allows AI
  read-only consumption, and forbids automatic delete/claim/cleanup.
- `gmail-projection-spec.md` defines the pre-projection empty-mailbox and
  sole-writer gate across normal mail, drafts, Spam, and Trash, and keeps
  unmanaged/unknown content in fail-closed report/attention paths.
- `oauth-setup.md` places the operator attestation before OAuth, the
  read-only target mailbox/account check after target OAuth and before the
  first projection/insert, and states the stop behavior using synthetic
  examples only; it does not call OAuth consent a mailbox write.
- `cli-spec.md` (if updated) matches the same fail-closed setup/deployment and
  report-only audit semantics without introducing a cleanup or claim command.
- Documentation review finds no contradictory instruction that allows
  automatic target deletion, adoption, relabeling, or silent cleanup. Links,
  headings, and Markdown formatting remain valid; `git diff --check` and the
  repository safety script pass. No code or live Gmail test is claimed.

## Migration boundary and stop gates

- This constraint applies to new production setup and documented deployment
  acceptance. It does not authorize mailbox cleanup, account recreation,
  token revocation, target deletion, or retroactive remapping of an existing
  deployment.
- If the existing target lacks a new/dedicated operator attestation, or its
  observable contents/account binding conflict with the prerequisite, stop the
  deployment and report the conflict. Do not claim that Gmail APIs prove sole
  writer status, and do not use audit/recovery evidence to convert unmanaged
  mail into managed mappings.
- If wording conflicts with the product contract, projection recovery rules,
  or the no-delete/no-claim privacy boundary, stop and revise this plan before
  editing the affected documents.
- No live OAuth, Gmail API calls, mailbox reads, sync, backfill, deployment,
  real account identifiers, or real secrets are permitted in this unit.
