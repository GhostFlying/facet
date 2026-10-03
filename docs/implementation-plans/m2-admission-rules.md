# M2 Admission, Rules and Readonly Action Consumer

Status: amended after independent plan-review BLOCK; awaiting nonauthor
re-review. This plan is based on exact `origin/main`
SHA `a854cb61b282ad102f61f54be532128bdd21c0f5` and authorizes no code,
credential operation, Gmail request, deployment, publication or merge.

This is the policy slice for the first automatic discovery/backfill and normal
History path. It supplies deterministic sender/domain rules, blacklist
precedence, fixed offline PSL/IDNA normalization, an admission result that
routes untrusted or unknown authenticity to attention, and the concrete typed
consumer of the existing readonly `AI/AddSender`, `AI/AddDomain` and
`AI/BlackList` action producer. It does not add a per-thread product selector,
source mutation, convenience-label cleanup, or a generic provider/plugin
framework.

## 1. Exact dependency and trust boundary

The base already contains:

- `src/facet/projection/actions.py`, whose closed `ActionLabelProducer` returns
  `ActionActivation` or `ActionAttention` and selects the latest external
  sender from typed source-thread facts;
- `src/facet/projection/backfill.py`, whose `AdmissionEvaluator` seam receives
  one discovery item and epoch and returns `DiscoveryDecision`; and
- the typed `RuleKind`, `RuleOrigin`, `PolicyVersion`, `ProviderId`,
  `PrivateAddress`, `RuleValue`, source event and repository records.

The base does not contain `rules.py`, `authenticity.py`, or `admission.py`.
The historical M1-06 pure-rules work is a frozen plan/research record, not
shipping source. The planned `docs/implementation-plans/adrs/authentication-
trust.md` is absent. The progress ledger explicitly says that M1-06's actual
trusted source-path evidence and registry are pending. These are hard inputs,
not reasons to weaken the policy.

The current `DiscoveryItem` contains only source message/thread IDs. Automatic
admission cannot be wired from that ID-only shape: the adapter owner must first
release a reviewed typed discovery-candidate extension carrying the normalized
sender, source mailbox state, observation timestamp and producer-issued
authentication evidence. Until that extension and its exact source adapter
commit are released, the evaluator may expose a pure candidate seam and return
attention for ID-only inputs, but `BackfillProducer` must not claim automatic
admission or synthesize sender/auth facts.

Automatic admission therefore requires a narrow verified evidence object from
the M1-06 owner. It must be produced by the verified source Gmail path/profile
consumer and be bound to the source account and message, with an explicit
decision of trusted, rejected, or unknown. A raw `Authentication-Results`
header, an arbitrary authserv-id, a bare `dkim=pass`, a From header, a fake
profile, or a test-only boolean is not evidence. Until that producer exists,
the production admission adapter remains unavailable/attention-only; pure
normalization and offline decision tests may proceed without claiming M1-06 or
G1/G2 completion.

The implementation must not infer source-path trust from the target account,
host-wide credentials, current label snapshots, provider JSON, or spike
statistics. If evidence is missing, stale, account-mismatched, ambiguous, or
otherwise not verified by the M1-06 seam, the result is durable review/attention
and `admit` is false.

## 2. Owned files and interfaces

This worker owns only the following paths on the exact base. Shared status,
progress, migration, credential, adapter, and existing action-repository files
remain owned by their workers.

| Path | Responsibility |
| --- | --- |
| `docs/implementation-plans/m2-admission-rules.md` | This plan, review receipts, exact implementation handoff and evidence |
| `src/facet/projection/suffixes.py` | Fixed bundled PSL loader/evaluator and opaque policy metadata |
| `src/facet/projection/rules.py` | Sender/domain normalization, exact matching, blacklist precedence and learning candidate |
| `src/facet/projection/authenticity.py` | Closed verified source-path evidence values and trust assessment seam; no provider parser or network lookup |
| `src/facet/projection/admission.py` | Admission evaluator, typed attention/review result, effective-at and source-state gates |
| `tests/unit/test_projection_rules.py` | Pure normalization, matching, blacklist, boundary and learning tests |
| `tests/unit/test_projection_admission.py` | Auth/effective-at/mailbox-state admission decisions and privacy controls |
| `tests/unit/test_projection_actions_consumer.py` | Existing action producer integration with rule publication/admission/blacklist effect seam |
| `tests/integration/test_projection_rules_installed.py` | Optional fresh-wheel/resource/privacy smoke limited to this unit |

The approved M2 resolver choice is `tldextract==5.3.2` with the Public Suffix
List snapshot bundled by that exact dependency, plus `idna==3.20`. The
dependency owner must record both versions and their exact artifact hashes in
`pyproject.toml`/`uv.lock`; this worker does not edit those shared files
concurrently. Runtime PSL update/fetch and a second copied PSL resource are
forbidden. The locked dependency artifact, its bundled snapshot and the
resolver policy version recorded in rule metadata are the sole runtime source
of truth. A different resolver requires a new reviewed plan with its exact
digest/license and dependency owner; no silent substitution with the historical
M1-06 custom resource is allowed.

The resolver must be constructed with runtime fetching and mutable cache
updates disabled. Tests must verify it can load the locked bundled snapshot
offline and that no network/cache path is consulted.

The public pure boundary is intentionally small and closed:

```text
load_rule_policy() -> RulePolicy
normalize_domain(value: str) -> CanonicalDomain
normalize_sender(value: str) -> CanonicalSender
normalize_rule(kind: RuleKind, value: str, *, policy: RulePolicy) -> NormalizedRule
normalize_rules(config: RulesConfig, *, policy: RulePolicy) -> RuleSet
domain_matches(domain: CanonicalDomain, rule: CanonicalDomain) -> bool
match_sender(sender: CanonicalSender, rules: RuleSet) -> RuleMatch
learn_domain(sender, *, source_primary, own, policy) -> LearnResult
```

The exact fields, bounds, policy version and closed error behavior must follow
the released M1-06 pure-rules plan. Values are frozen/slotted/private-repr and
must never carry raw headers, body, subject, attachments, provider JSON or
unfiltered exceptions. Domain comparison is exact equality or a whole-label
dot descendant (`domain == rule` or `domain.endswith("." + rule)`); substring,
glob, suffix-appending attacker and public-suffix rules are rejected.

The authenticity seam is an immutable, metadata-only value with no public
constructor that can assert trust on its own. Its minimum shape is:

```text
VerifiedSourceEvidence {
  source_role: Role  # must be Role.SOURCE
  source_account: PrivateAddress
  source_message_id: ProviderId
  source_binding_revision: Revision
  source_credential_revision: Revision
  source_path: SourcePathStatus  # trusted | rejected | unknown
  from_alignment: FromAlignment  # aligned | misaligned | unknown
  evidence_policy: PolicyVersion
  observed_at: Timestamp
  expires_at: Timestamp
}
```

The M1-06 producer owns construction and validation of this value. It must
stamp `observed_at` and a bounded `expires_at`, reject stale/future-invalid
windows, and bind the evidence to the source profile's verified account,
`binding_revision` and `credential_revision` lineage. Admission checks the
same source binding/credential lineage and freshness window against its
observation time; callers cannot construct a trusted value by setting a status
field. The producer may add bounded typed provenance fields after review, but
it may not expose raw headers or accept arbitrary caller claims. Admission
accepts only evidence issued by that producer for the same source account and
message. In all other cases it returns an attention result.

The admission boundary must consume a typed discovery candidate containing
source message/thread IDs, normalized sender, source mailbox state, candidate
observation time, the configured ruleset revision/effective-at context, and the
verified evidence above. The adapter-owned extension must be released before
the automatic `BackfillProducer` path is connected; pure tests may pass this
closed candidate directly. It returns the existing `DiscoveryDecision` shape for
the backfill seam plus a private reason/review value for attention paths:

```text
AdmissionEvaluator.evaluate(candidate, epoch)
  -> AdmissionResult(admit, rule, attention_reason?)
```

The adapter-owned dependency is resolved as this closed in-memory candidate
shape before automatic wiring (the source adapter worker owns the concrete
class and exact source commit; this worker owns only its admission consumer):

```text
DiscoveryCandidate {
  message_id: ProviderId
  thread_id: ProviderId
  sender: PrivateAddress
  source_visibility: Visibility
  is_draft: bool
  observed_at: Timestamp
  authenticity: VerifiedSourceEvidence | None
}

DiscoveryPage.items: tuple[DiscoveryCandidate, ...]
```

`DiscoveryItem` ID-only pages remain valid for adapter tests and normal History
identity, but `BackfillProducer` must reject them as an automatic-admission
input until this extension is released. The adapter must obtain sender,
visibility/draft and evidence through the verified source path and must not
place raw headers or provider JSON in this value. A missing `authenticity`
field is an unknown/review result, never an implicit trust claim.

`admit=True` requires: source state is not Spam, Trash or draft for a new
automatic admission; the candidate time is at/after the selected rule's
`effective_at`; blacklist exact sender does not match; an allow sender/domain
rule matches; and M1-06 evidence is trusted and From-aligned. Existing tracked
threads are handled by the surrounding worker's thread authorization and may
continue when later senders change. The evaluator never creates rows, calls
Gmail, or silently backfills old matching threads after a rule change.

## 3. Action-label consumer semantics

The consumer uses the existing `ActionLabelProducer` and its
`PrivateActionLabelMap`, `ActionSourceReader`, `ActionActivation` and
`ActionAttention` values. It must not replace History events with a current
label snapshot. The producer registry owner is
`src/facet/projection/actions.py`, specifically the fixed
`registered_action_producer_types()` tuple released at base commit
`5a95c0873769cdea24cd792f1bbb88d8b67864d3`; the durable effect owner is
`src/facet/db/repositories/actions.py` on base `a854cb6`. This worker does not
register a producer or modify either owner path. Action integration is deferred
until those owners provide an exact released producer/repository contract;
pure tests may consume the current closed values without creating DB rows.
For an added configured label:

- `AddSender` normalizes the producer-selected latest external sender and
  publishes an exact sender allow rule with `RuleOrigin.ACTION_LABEL`,
  `effective_at` equal to command execution, then admits the selected thread
  under `AdmissionRefActionLabel` and schedules its expansion only once.
- `AddDomain` derives the sender's normalized registrable domain under the
  fixed PSL/IDNA policy, refuses public/unknown suffixes and the source
  primary/own domains, publishes a dot-boundary domain allow rule, and admits
  only the selected thread. The new rule is prospective and does not rescan
  historical threads.
- `BlackList` publishes an exact sender blacklist, stops only the selected
  thread by incrementing its generation and cancelling unstarted jobs. Other
  senders and threads remain active; dispatched/unknown inserts are retained
  and recorded. Removing the blacklist does not reactivate the stopped
  generation.

The existing repository transaction remains the authority for action
registration, deduplication, rule publication, admission/stop and job
creation. The consumer supplies typed selections and facts; it does not write
ad-hoc JSON, arbitrary payloads or a second action table. Deduplication remains
`(projection, history record, label, source thread)`, so remove/re-add creates a
new activation key. A removed label is an observation with no new command.
Readonly mode leaves source labels unchanged. Convenience cleanup and
`gmail.modify` are outside this unit.

## 4. Test and acceptance gates

All tests use synthetic addresses, IDs, headers and mailbox state. No Gmail,
OAuth, target write, spike state or private fixture is used.

Pure rule controls must cover:

- exact sender matching, local-part preservation, case/domain normalization,
  subdomain dot boundaries, near-match/hyphen/substring/glob/IP/URL refusals;
- IDNA and the locked `tldextract==5.3.2` bundled-PSL positive/negative
  vectors, public suffix and unknown suffix rejection, wildcard/exception
  behavior, dependency artifact/version validation, and no runtime
  network/cache update;
- blacklist precedence over sender/domain allow, `effective_at` boundary,
  configured primary/own-domain protection, no alias inference, bounded rule
  counts, malformed/foreign typed values and caller-input immutability; and
- neutral privacy failures: synthetic sensitive values do not appear in
  repr/str/errors/logs/stdout/stderr or persisted records.

Admission controls must prove:

- trusted evidence with aligned From plus an exact allow match admits;
- rejected, unknown, stale, account-mismatched, or ambiguous evidence always
  yields attention and never `admit=True`, including a spoofed
  `Authentication-Results: dkim=pass` fixture;
- producer-enforced `observed_at`/`expires_at`, source binding revision and
  credential revision are checked at the candidate boundary; future-invalid,
  expired, lineage-mismatched and role-mismatched evidence cannot be injected
  by constructing a status-like value;
- Spam, Trash and drafts cannot newly trigger automatic admission; a tracked
  thread's later sender change is left to the existing authorization path;
- dynamic rules apply prospectively, newly learned rules do not expand history,
  and exact blacklist blocks new admission without affecting unrelated senders;
- action producer output is consumed once, duplicate History/replayed action is
  a no-op, remove/re-add is a new command, latest external sender excludes all
  explicitly configured own addresses, and unknown/ambiguous action facts go to
  attention; and
- no test-only producer registration, direct DB row fabrication, source-label
  mutation, Gmail call, or target-side effect is needed for pure evidence.

Before implementation release, the independent reviewer must verify this plan
against exact `origin/main` and the current M1-06 plan/research, especially the
authentication evidence blocker, resource custody, action repository contract,
and no-new-framework boundary. After implementation, a different reviewer must
inspect the exact candidate SHA, focused tests, full offline suite, Ruff,
installed-wheel/privacy checks and repository safety. Reviewers must not approve
their own plan or source.

## 5. Stop gates and unresolved blockers

Stop implementation and report to the coordinator if any of the following is
observed:

1. M1-06 cannot provide a typed producer-issued source-path evidence object
   tied to the verified source account/message. Do not substitute header parsing,
   DNS, authserv-id text, profile identity, or spike counters.
2. The exact locked `tldextract==5.3.2`/`idna==3.20` artifacts or bundled PSL
   snapshot cannot be reproduced offline, their digest/version differs, or
   supported runtimes produce different canonical decisions without a reviewed
   policy update. Do not add a second PSL resource.
3. The adapter owner has not released a typed `DiscoveryItem`/candidate
   extension carrying sender, mailbox state, observation time and producer-
   issued evidence. Do not broaden the provider API, synthesize facts or use
   raw JSON; automatic admission remains disabled while the pure attention-only
   seam is allowed.
4. The action producer registry/repository owners have not supplied the exact
   released contract named above, or action publication would require bypassing
   the shipping writer/repositories, adding an action registry/plugin callback,
   mutating source labels, or persisting content/private payloads.
5. A requested behavior would imply per-thread product selection, implicit
   historical backfill, send/delete/forward, two-way sync, new OAuth scope,
   or a change to the disclosure/privacy contract.

Until the first blocker is closed by an actual M1-06 consumer and the shipping
credential/writer/migration owners are integrated, this worker may deliver only
pure deterministic rule/authenticity value tests and a reviewable typed seam;
it must not claim automatic admission, G2, or production completeness.

## 6. Implementation release sequence

1. Obtain independent nonauthor plan review and root release against exact
   `a854cb6`.
2. Confirm the actual M1-06 evidence interface, its freshness/lineage checks,
   and the exact source adapter candidate extension with the owners; update this
   plan before coding if fields or ownership change.
3. Implement suffix/policy and rules plus focused pure tests, then implement the
   attention-first authenticity/admission seam and action consumer using only
   typed inputs.
4. Run focused tests, full offline checks, Ruff, installed-wheel/privacy checks
   and `bash scripts/check-repo-safety.sh`; record measured evidence here.
5. Hand the exact candidate SHA to an independent implementation/acceptance
   reviewer. Integration into main, real Gmail validation, deployment and image
   publication remain coordinator-owned gates.

## 7. Implementation handoff (root direct unit)

The first implementation slice is intentionally limited to the currently
available pure boundary. It adds `suffixes.py`, `rules.py`,
`authenticity.py`, and `admission.py`, plus synthetic unit coverage. The
resolver is constructed with the locked bundled `tldextract` snapshot and no
network/cache update path. The admission evaluator accepts only a typed
candidate and returns attention for absent, stale, rejected, mismatched, or
otherwise untrusted evidence; it does not call Gmail, write SQLite, register
action producers, or wire the ID-only `BackfillProducer`.

The action-label repository/registry and automatic M1-06/adapter wiring remain
deferred under stop gates 1, 3, and 4. This candidate therefore does not claim
automatic admission, G2, or production sync completion. Candidate evidence is
bound to the source account/message, role, credential/binding revisions, and
both candidate/current freshness checks. All test inputs are synthetic.
