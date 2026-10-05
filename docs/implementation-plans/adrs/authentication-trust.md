# Authentication trust boundary (M1-06) — superseded

This historical design is superseded by the user's explicit 2026-10-05
decision. Facet no longer performs source-path attestation or sender-authentication
verification as an automatic-admission gate. Gmail owns SMTP authentication and
classification; the active contract is documented in `product-contract.md` and
`gmail-projection-spec.md`. The former implementation and its tests were deleted.

The remainder of this file is retained only as historical review evidence and is
not an active requirement or Phase 1 acceptance gate.

Status: implemented source-provider contract; live Gmail evidence is still
required before the Phase 1 trust gate can be closed.

Facet admits a new thread only when a producer-owned source-path attestation is
bound to the verified source account and exact message, has matching binding
and credential revisions, is fresh, and reports trusted source authentication
with aligned From. A default Gmail metadata read has no such attestation. The
reviewed production provider may issue this evidence only after cryptographic
DKIM verification over the exact in-memory Gmail raw message and the
`auth-alignment-relaxed-v1` rule: IDNA/PSL-normalized From and signing domains
must be exactly or registrable-domain equal. Public suffixes, IP literals,
malformed domains and dot-boundary lookalikes are rejected.

The following are observations only and never trusted evidence by themselves:

- `Authentication-Results`, `ARC-Authentication-Results`, an authserv-id,
  `dkim=pass`, `spf=pass`, or `dmarc=pass` text;
- From/Return-Path headers, source profile identity, Gmail labels, provider
  JSON, a target credential, or spike counters;
- a caller-provided boolean, policy version, or synthetic value outside the
  owner-issued test/provider seam.

Duplicate/conflicting results, forwarding/ARC ambiguity, malformed or multiple
From addresses, stale/future evidence, account/message/lineage mismatch and
unknown provider state are `unknown`/attention. ARC headers, `Resent-From`,
`Resent-Sender`, malformed/conflicting DKIM signatures and DNS/provider
failure are never positive evidence, even when another signature verifies.
The policy version is the sealed `auth-v1` value consumed by M2; expiry is
exclusive. Raw message bytes remain memory-only and are discarded at the
adapter boundary. Live Gmail evidence is still required to close the trust
gate.
