# Production Gmail domain-query capability

Date: 2026-10-10

## Goal

Make the already-approved rule-scoped domain backfill executable through the
production Google Gmail service factory. The source adapter already fails
closed unless its provider adapter advertises `gmail-from-domain-v1`; the
factory must provide that declaration for the Google Gmail API service instead
of relying on a test-only adapter monkeypatch.

## Scope and behavior

- Set the versioned capability on every service returned by
  `GoogleGmailServiceFactory._build()`.
- Remove the complete-sync test's `SourceAdapter` monkeypatch so its production
  factory path proves the capability wiring.
- Keep the bounded `from:(@<domain>)` query and local exact-domain admission;
  do not add an unfiltered fallback or widen OAuth scopes.
- Preserve the fail-closed `maintenance_required` behavior for adapters that do
  not advertise the capability.

## Acceptance

- Factory unit tests prove the production service carries the exact capability
  token without changing access-token-only construction or transport ownership.
- Complete CLI wire tests execute sender and domain rule-scoped backfill through
  `GoogleGmailServiceFactory`, issue only the bounded domain query, and persist
  mappings across restart.
- Focused tests, full offline checks, lint/format, repository safety, and an
  independent implementation review pass before the PR is merged.

## Boundary

This change does not authorize live Gmail writes, new rules, deployment, or
release. Real Gmail domain backfill remains a separately authorized validation
step after the production wiring is merged.
