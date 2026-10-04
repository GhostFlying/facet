# M1-06 real source-path attestation

Status: independently reviewed and approved for implementation. Base candidate is
`origin/main` at
`2558b17453a2add8cf840b567c98e87d1e059d6d`.

## User-observable delivery

The existing production Gmail path will be able to make an automatic admission
decision for a newly discovered message only when it can verify, in memory, a
cryptographic sender-authentication result for that exact Gmail message. An
unknown, malformed, unsigned, unaligned, conflicting, or DNS/provider-failed
message remains `attention` and never reaches target insert.

The proposed provider is deliberately narrow: fetch the exact message with
Gmail `messages.get(format=raw)`, verify a DKIM signature cryptographically
against DNS, require an unambiguous `From` address and aligned signing domain,
and issue the existing owner-bound `VerifiedSourceEvidence`. It will never
trust `Authentication-Results`, `ARC-Authentication-Results`, a textual
`dkim=pass`, a profile address, or a caller boolean. Raw bytes exist only in
memory and are discarded before the candidate result crosses the adapter
boundary.

The alignment policy is frozen for this unit as `auth-alignment-relaxed-v1`:
normalize both domains with the pinned IDNA/PSL policy already used by Facet,
then accept exact equality or equality of their registrable domains. Public
suffixes, IP literals, malformed domains, and dot-boundary lookalikes are
rejected. The policy is relaxed organizational-domain alignment, not arbitrary
substring matching.

Forwarding/ARC ambiguity remains fail-closed. Any ARC set, `Resent-From`, or
`Resent-Sender` header, a malformed/conflicting signature set, or a forwarding
state that cannot be distinguished from the original delivery produces
`unknown`/attention, even when a DKIM signature still verifies. The provider
does not use ARC or `Authentication-Results` text as positive evidence.

## Files and behavior

- `src/facet/gmail/source_auth.py`: add a production provider with injected raw
  fetch/DNS verification seams, bounded raw input, typed unknown/failure
  outcomes, exact account/message/binding/credential lineage, and no raw/error
  serialization.
- `src/facet/gmail/source.py`: fetch metadata and raw only for the candidate
  under evaluation, pass raw to the provider, and retain the existing redacted
  candidate/attention boundary. Do not persist or return raw.
- `pyproject.toml`, `uv.lock`: add a pinned, maintained DKIM verification
  dependency only if the plan review accepts this route; no general mail-auth
  framework.
- `docs/implementation-plans/adrs/authentication-trust.md`: record the exact
  accepted evidence class, `auth-alignment-relaxed-v1` rule, forwarding/ARC
  ambiguity behavior, DNS timeout/failure behavior, and why textual provider
  headers remain rejected.
- `tests/unit/test_gmail_source_auth.py` and
  `tests/unit/test_gmail_source_candidates.py`: signed/unsigned, valid/invalid
  signature, aligned/misaligned From, multiple/conflicting signatures, DNS
  failure, size bound, raw/privacy, and exact-message/lineage tests. DNS and
  provider calls are deterministic test doubles; no live Gmail or DNS is used
  in CI.
- `docs/development-status.md`: update only after exact candidate review and
  CI, and distinguish cryptographic offline evidence from live Gmail evidence.

## Reuse and non-goals

Reuse `VerifiedSourceEvidence`, `assess_evidence`, `SourceAdapter`, the existing
normalized sender/domain policy, `GoogleGmailServiceFactory`, and the current
foreground admission/worker path. Do not add a daemon, attestation service,
spool, database content cache, OAuth scope, target behavior, or live-account
test. Do not make DKIM verification imply that an arbitrary sender is safe;
it only closes the sender-authentication gate before the existing disclosure
policy evaluates a candidate.

## Acceptance and stop gates

1. A deterministic signed synthetic raw message reaches the existing admission
   seam only when its signature verifies and its signing domain satisfies the
   documented `auth-alignment-relaxed-v1` rule.
2. Every negative/unknown case remains attention and performs no target write;
   DNS/network/auth failures do not become trusted evidence or blind retries.
3. Forwarded/ARC-indicated, malformed, conflicting, and otherwise ambiguous
   delivery cases remain unknown/attention, including a valid aligned DKIM
   signature that cannot be attributed to the original delivery.
4. Raw sentinels are absent from DB, logs, exceptions, CLI output, and typed
   candidate values; the provider releases raw after verification.
5. Existing fake CLI closure remains green, but is still labelled synthetic;
   no live Gmail, OAuth, DNS, deployment, or release action is performed.
6. If the product contract does not accept cryptographic DKIM plus aligned
   From as the real source-path evidence, stop before implementation and return
   the missing evidence decision; do not silently weaken the current ADR.
