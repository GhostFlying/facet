# M1-06 trusted source candidate seam

Status: implementation plan for the next independent unit. This plan is based
on the integrated main at `cf3004990dfe384a8d388ad98e4c33522274622e` and
authorizes no Gmail request, OAuth operation, target write, deployment, or live
account mutation.

## Goal and boundary

Release the smallest typed source-candidate boundary needed by the already
integrated M2 pure admission seam. The source adapter must provide normalized
sender, source mailbox state, draft status, observation time, source account,
and producer-owned authenticity evidence without retaining raw headers or
provider JSON. The boundary must be usable by a synthetic/fake provider and
must fail closed for the real Gmail path until an independently verified
provider attestation exists.

This unit does not claim G1/G3, automatic admission, or production Gmail trust.
Gmail `Authentication-Results`, `ARC-Authentication-Results`, `authserv-id`, a
bare DKIM/SPF/DMARC result, a From header, profile identity, or spike counters
cannot construct trusted evidence. A production adapter with no verified path
returns `unknown`/attention. The next worker may inject a separately reviewed
source-path attestation producer; this unit does not invent one.

## Owned files

| Path | Responsibility |
| --- | --- |
| `docs/implementation-plans/adrs/authentication-trust.md` | concise trust boundary, accepted/rejected evidence classes, policy/version and stop gates |
| `src/facet/gmail/source.py` | metadata-to-candidate conversion and a typed candidate discovery method; preserve the ID-only compatibility method |
| `src/facet/gmail/source_auth.py` | closed producer protocol and synthetic-only issuer adapter; no header parser can issue trusted evidence |
| `tests/unit/test_gmail_source_candidates.py` | sender/mailbox-state parsing and candidate/privacy controls |
| `tests/unit/test_gmail_source_auth.py` | trust-boundary negative/unknown/attestation tests |
| `docs/development-status.md` | handoff after exact review/CI, owned by the root for this unit |

No DB/repository, action registry, BackfillProducer, credential file, Gmail
network, OAuth, target adapter, or dashboard file is edited by this plan.

## Public typed boundary

`SourceAdapter.discover` remains the existing ID-only, fixed-window method for
adapter/history compatibility. Add a separate `discover_candidates` method
whose page items are a closed `CandidateResult` union. A successful item carries
the existing M2 `DiscoveryCandidate` shape: one valid From address,
`Visibility`, draft flag, source account, observation timestamp, and
`VerifiedSourceEvidence | None`. An attention item carries only source
message/thread IDs and a closed redacted reason (`missing_metadata`,
`multiple_from`, `malformed_from`, `unsupported_labels`, or
`provider_failure`). Exactly one candidate or attention item is present for
every discovered ID; the adapter never drops a selected item, guesses a
sender, or turns malformed data into trusted evidence. Provider failures that
prevent page enumeration remain a page-level controlled failure with the
checkpoint unchanged, not a partial-success claim.

The exact new shapes are `CandidateAttention(reason, message_id, thread_id)`,
`CandidateResult(candidate | attention)`, and
`CandidatePage(items, next_page_token)`. `CandidateResult` enforces exactly one
variant and all fields have redacted representations. `source_account` comes
from the verified M1-04 source binding, never from an untrusted profile string
returned by the message adapter. A malformed or missing provider timestamp does
not reuse the existing `_timestamp` fallback-to-now; it becomes a typed
`invalid_metadata` attention item (or a page-level controlled failure when the
page cannot be safely enumerated).

The source-auth module defines a producer-owned attestation protocol. Its only
trusted constructor is an owner-issued token held by the injected provider
implementation. The adapter can pass through a producer-issued evidence value
bound to the exact source account/message, binding revision, credential
revision, observation/freshness window, and `auth-v1`; it cannot create one
from raw headers. The default/no-provider implementation returns unknown.

The candidate method never returns raw headers, bodies, snippets, attachment
names, unfiltered provider errors, or credentials. `repr`/`str` remain redacted.
The candidate timestamp is captured once per page/message and evidence expiry
is exclusive, matching the M2 seam.

## Tests and acceptance

- synthetic metadata with one valid From produces the expected normalized
  candidate; case/domain normalization and local-part preservation follow the
  M2 policy;
- Spam, Trash, Draft, unknown labels, missing/duplicate/malformed From, and
  provider failures produce typed non-trusted/attention outcomes;
- raw `Authentication-Results`, ARC, authserv-id, bare pass tokens, profile
  account text, and fake booleans cannot issue trusted evidence;
- only a producer-issued synthetic attestation with matching account/message,
  lineage, policy and freshness can reach the M2 evaluator, and a missing
  producer remains unknown;
- no synthetic sensitive sentinel appears in repr/str, controlled exceptions,
  logs, files, or HTTP-facing values;
- existing source adapter/history/backfill tests remain unchanged and the
  ID-only discovery method keeps its prior provider request shape;
- run affected tests, full offline pytest, Ruff, wheel/import smoke and
  `bash scripts/check-repo-safety.sh` before handing the exact candidate to a
  nonauthor implementation reviewer.

## Stop gates

1. If the real Gmail API offers no independently verifiable source-path
   attestation beyond headers, keep the production result unknown and report
   the missing external evidence; do not weaken the contract.
2. If the typed candidate extension would require changing the M2 admission
   policy, DB schema, action effects, or BackfillProducer ID-only compatibility,
   stop and revise this plan before coding.
3. A synthetic attestation proves only the seam and offline routing. It does
   not close G1/G3 or authorize real Gmail operations.
