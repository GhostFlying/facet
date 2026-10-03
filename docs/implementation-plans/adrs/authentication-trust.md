# Authentication trust boundary (M1-06)

Status: design input for the typed source-candidate seam; it is not evidence
that real Gmail automatic admission is enabled.

Facet admits a new thread only when a producer-owned source-path attestation is
bound to the verified source account and exact message, has matching binding
and credential revisions, is fresh, and reports trusted source authentication
with aligned From. A default Gmail metadata read has no such attestation.

The following are observations only and never trusted evidence by themselves:

- `Authentication-Results`, `ARC-Authentication-Results`, an authserv-id,
  `dkim=pass`, `spf=pass`, or `dmarc=pass` text;
- From/Return-Path headers, source profile identity, Gmail labels, provider
  JSON, a target credential, or spike counters;
- a caller-provided boolean, policy version, or synthetic value outside the
  owner-issued test/provider seam.

Duplicate/conflicting results, forwarding/ARC ambiguity, malformed or multiple
From addresses, stale/future evidence, account/message/lineage mismatch and
unknown provider state are `unknown`/attention. The policy version is the
sealed `auth-v1` value consumed by M2; expiry is exclusive. Any future real
accept branch must identify the provider path and its independently reviewed
evidence source before changing this ADR or enabling automatic admission.
