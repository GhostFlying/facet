# P1-02 synthetic Gmail, fault, and privacy test foundations

Date: 2026-10-02

Revision: draft r3, exact P1-01 r2 candidate alignment and ownership handoff.
No test implementation has started. P1-01 at
`09031e723af1ef6590dc6746744ee52894501e38` passed independent review and exact-head
PR CI and actually merged in PR #8 at 2026-10-02 06:42:04 UTC. This is the ADR
freeze input, not an executable implementation. This new plan revision requires
independent review and an explicit implementation dispatch, not inherited r1/r2
approval. Post-merge main CI passed both existing Python lanes at this exact SHA;
that baseline success is not verification of unimplemented P1-02 tests.

## Assignment and exact baseline

- Package: P1-02; tracking: [Issue #5](https://github.com/GhostFlying/facet/issues/5),
  under [Epic #1](https://github.com/GhostFlying/facet/issues/1).
- Current design/implementation owner: delegated worker `phase1_architecture_plan`.
  The coordinator transferred this lane from `phase1_execution_plan` on
  2026-10-02; its complete r2 draft was preserved as the starting input with
  SHA-256 `83994114adb67ae980362be6a2d57fd79f1e16537354af94c93a0d346b03939c`.
  The new owner is not its independent reviewer.
- Independent reviewer: appointed by the coordinator, not this author; use
  Astra high for the privacy, concurrency, and recovery-facing plan review.
- Owned branch: `test/p1-02-test-foundations`; owned sibling worktree:
  `../facet-worktrees/p1-02-test-foundations`. No ignored files are copied.
- Exact starting main and fresh remote main:
  `2618eafad817aee4e491aa87ebede0f44f27a20b`.
  P1-00 is integrated in [PR #6](https://github.com/GhostFlying/facet/pull/6);
  coordinator-verified [main CI](https://github.com/GhostFlying/facet/actions/runs/36971068807)
  passed. Current-state documents at that commit retain their candidate snapshot;
  the actual merged SHA, not an older snapshot's wording, determines this base.
- Current implementation base after coordinator-authorized normal fast-forward:
  `09031e723af1ef6590dc6746744ee52894501e38`, the actual P1-01 merge commit.
  Original r2 was the only untracked file and was preserved; no other changes,
  reset, forced update or unrelated branch integration occurred.
- Overall G0 is approved at `caba7c73895a303d329cf3eba1c89557530c38c5`.
  This approval does not close G1-G6 or grant live Gmail/deployment authority.
- Input inspected: P1-01 plan, independently approved at SHA-256
  `68015c0dfffe72068b0e8b02ff678e8db44e17cf47d407ebefaac436adc0aeaf`.
  The separately reviewed ADR candidate and hashes are recorded below. Neither
  the plan nor an ADR document is executable type implementation.
- Current writable scope: this document only. No tests, source, dependencies,
  shared documents, commits, pushes, or PRs in this drafting dispatch.

Requirements come from the repository instructions, development status, product
contract, project plan, Gmail specification, Dashboard specification, CLI
specification, execution plan, agent workflow, and package ownership ledger.
Only tracked synthetic tests and implementation files were inspected; no ignored
spike state, credentials, real mail, or private runtime evidence was read.

## Outcome, non-goals, and dependency release

Deliver a reusable, falsifiable offline test harness: provider-shaped in-memory
Gmail facts, deterministic scheduling/fault controls, bounded inspection helpers,
and storage/output-specific privacy sentinels. Test tools must themselves fail
when their scripts, guards, or assertions are ineffective.

The fake does not implement admission, authenticity, queue policy, retry policy,
generation cancellation, checkpoints, mapping, receipt replay, or recovery. Those
are production behaviors tested by their package owners, not a second business
state machine inside fixtures. A fake passing its own tests is not production
fault/privacy coverage, real Gmail fidelity, or a milestone acceptance result.

| Work slice | Inputs that must be ready | What can proceed or be released |
| --- | --- | --- |
| This plan draft | Integrated P1-00 and approved P1-01 design plan | Write and independently review this draft; no implementation |
| Provider-fact/self-test foundation | P1-01 reviewed, frozen, integrated ADRs; final aligned P1-02 plan review; explicit coordinator dispatch | In-memory fake API, clock/fault/barrier/privacy helpers and self-tests; parallel with M1-01 |
| Mandatory P1-02 core-type compatibility | Above, plus M1-01's independently reviewed merged minimum domain types and package configuration | P1-02 owns and passes CT-01 through CT-04 against actual production types before package completion or M1-02 dependency release; no duplicate test enums/classes |
| Later business/CLI/Web integration | Each owning package's merged implementation and reviewed plan | That owner adds consumer tests using the harness; no P1-02 dependency on future M2 adapters |

M1-01 is the sole owner of minimum executable production domain types. The
provider-fact slice deliberately depends only on provider wire shapes and
test-controller objects, so P1-02 and M1-01 do not form a dependency cycle.
P1-02 may integrate a reviewed provider/self-test slice while M1-01's types are
pending, but that is a partial delivery: the package stays incomplete, its Issue
stays open, and it does not release M1-02's P1-02 dependency. P1-02's own mandatory
core-type compatibility is distinct from later business/CLI/Web consumer tests.
Only the latter may remain pending after P1-02 completion, until their feature
owners implement them. Core compatibility must pass against merged M1-01 types,
with independent candidate review and actual CI, before P1-02 is released.

Before implementation, actual P1-01 integration/base carry and this aligned plan's
independent review must be recorded. Before the CT slice, M1-01's accepted export
mapping and actual merged executable commit must also be recorded. A missing CT
dependency does not block the independently dispatched provider/self-test slice,
but does block package completion. Do not resolve interface drift during coding.

| Required frozen input | Current state | Alignment required |
| --- | --- | --- |
| `adrs/core-state-contracts.md` | Independently approved and actually merged `09031e7`, `p1-core-v1` | Exact inventory, required-nullable tagged values, guard constraints, stable keys and deferred owners mapped below |
| `adrs/writer-command-protocol.md` | Same integrated freeze, `p1-writer-v1` | Stable request/receipt/lineage, durable acceptance/effect order, serialized dispatch entry, owner/view/credential locks; runtime tests remain owner-specific |
| M1-01 minimum domain types | Export plan r3 independently approved; executable implementation/review/merge pending | `facet.contracts` public exports with primitive/enum/record modules; CT implementation waits for actual accepted constructors, not copied types |
| Test-controller hook vocabulary | Defined below, test-only | Provider/helper self-tests exercise these controls; no production fault endpoint |
| Production fault-hook locations | Deferred to each implementing package's reviewed test integration | Missing future source locations are feature-consumer-pending, not ghost wrappers or a hidden M2 prerequisite for P1-02 |

Exact reviewed ADR input hashes at `09031e723af1ef6590dc6746744ee52894501e38`:

- Core: `795f80ab672ed4e0130eafc330bc0403981360f2e70bf935579973065c64f2f6`.
- Writer: `5f0e5af9cc238f7967a88590fb53acc91c4697ffa27d19773cc66cf5ccc41368`.
- Candidate [CI run 36974129495](https://github.com/GhostFlying/facet/actions/runs/36974129495)
  passed both existing Python lanes; this verifies that documentation candidate,
  not runtime protocols or this untracked plan.

The worktree carried normally from starting `2618eaf` to actual merged `09031e7`
on coordinator dispatch. [Main CI run 36974823051](https://github.com/GhostFlying/facet/actions/runs/36974823051)
completed successfully for Python 3.11 and 3.12 at that exact SHA, independently
checked after actual merge, not inferred from PR CI. Further base changes need
coordinated inspection/carry and must preserve this owned draft.

## Future file ownership

These paths are proposed implementation scope, not files written by this draft.
Exact names may be refined before the final aligned plan review.

| Owned path | Responsibility |
| --- | --- |
| `tests/fakes/__init__.py` | Small explicit test-helper exports; no production/spike startup imports |
| `tests/fakes/gmail.py` | In-memory mailboxes, minimal Google-style service/request surface, provider response scripts and controller-only setup |
| `tests/fakes/clock.py` | UTC wall time and separate monotonic time; explicit deterministic advancement |
| `tests/fakes/faults.py` | Named one-shot/repeating failures and bounded barrier controls |
| `tests/fakes/transport.py` | Per-worker fake transport factory, concurrent-use probe and bounded call metadata |
| `tests/fakes/mime.py` | Synthetic MIME builders returning bytes in memory only |
| `tests/fakes/privacy.py` | Classified sentinels and bounded assertions for metadata stores and output surfaces |
| `tests/fakes/network.py` | Scoped deny-network guard for supported Python networking paths and its negative controls |
| `tests/conftest.py` | Sole shared fixture registry: function-scoped factories and explicit guards; no global real credentials/profile loading |
| `tests/unit/test_fakes_gmail.py` | Provider shapes, scripts, duplicates, delayed visibility and source loss self-tests |
| `tests/unit/test_fakes_faults.py` | Clock, barrier, fault consumption, timeout and transport self-tests |
| `tests/unit/test_fakes_privacy.py` | Positive/negative sentinel and network-guard controls; allowed private metadata is not falsely rejected |
| `tests/unit/test_fakes_contract_compatibility.py` | Mandatory P1-02 CT-01 through CT-04 against M1-01's real merged core values; not future feature/adapter integration |
| `docs/implementation-plans/test-evidence-matrix.md` | Separate helper, mandatory core-compatibility and future feature-consumer evidence with contract/candidate revisions and completion gates |
| This plan | Review findings, final frozen-input alignment and package handoff |

P1-02 alone edits root `tests/conftest.py` and the shared fake/evidence registry.
M1-01 owns package/config/CLI source, lockfile and its config/CLI unit tests; it
uses existing fixtures or local helpers without editing root conftest. Later
workers own their consumer tests, request new fixtures through P1-02's owner, and
do not change helper semantics independently. Shared current-state documents
remain the delegated integration/docs owner's files. No `src/`, `pyproject.toml`,
`uv.lock`, existing spike tests, CI workflow or product contract edit is in scope.

The M1-01 author confirmed disjoint planned tests: `tests/unit/test_contracts.py`,
`test_config.py`, `test_private_paths.py` and `tests/cli/test_bootstrap.py`.
Its planned modules are `src/facet/contracts/__init__.py`, `primitives.py`,
`enums.py`, and `records.py`. P1-02 imports canonical exports from `facet.contracts`
and the explicitly documented union constructors from `facet.contracts.records`,
checks their module ownership, and never constructs substitute values. The
concrete export/constructor mapping below is M1-01-owned. Its r3 plan received
independent approval at SHA-256
`feeabe53d454c931da343964aa7d0a923508d86d3710a03e7c69dc413d534101`,
base `09031e723af1ef6590dc6746744ee52894501e38`; that is interface-plan approval,
not evidence that its executable types exist or that CT can start yet.

## Provider-facing fake design

### Separate controller knowledge from application observations

A function-scoped controller seeds two different synthetic mailboxes, messages,
threads, profile facts, labels, History pages, responses, and visibility times.
Consumers receive only the fake service/transport view, not the controller or a
mailbox dictionary. Controller-only knowledge may label fixture setup as an old
unmanaged copy or another writer's insert; neither flag is returned by Gmail
responses. No response contains `belongs_to_intent`, a local attempt ID, origin
oracle, artificial idempotency key, or production mapping/generation state.

Never trust equal content, a unique RFC Message-ID, old Date/internalDate, or
controller insertion order as production provenance. Supporting future target
History/fence experiments means returning only ordinary scripted History facts;
it does not preselect or prove the separate M2-04 attribution ADR.

### Minimal Google-shaped surface, not a general Gmail emulator

Implement the used subset of `users().getProfile()`, `messages().list/get/insert`,
`threads().get`, `history().list`, and `labels().list` as request objects with an
explicit `execute` operation. Keep optional label mutations scripted and guarded
by separately supplied test credential/role facts, never profile response fields;
they are not needed to operate a readonly source. Unsupported
methods/arguments fail explicitly instead of silently returning empty success.
There is no send, forward, delete, purge, OAuth, discovery download, or real HTTP
operation. The fake never imports `facet_spike` services or discovers profiles.

Provider facts use test-only wire dictionaries/validation, not a duplicate
`facet` domain model. Keep request construction separate from execution; record
that insert execution was requested once, without automatic SDK retries.
Successful repeat inserts create different target message IDs even for identical
raw bytes, so a blind retry visibly produces duplicates in self-tests.

| Operation | Observable contract and controllable counterexamples |
| --- | --- |
| Profile | Exactly the documented `emailAddress`, `messagesTotal`, `threadsTotal`, `historyId` wire shape; no scopes, role, binding or live-verification flag |
| Labels | Scripted synthetic label IDs/names and legacy-label facts; separate from profile/credential state |
| Message list/search | ID/thread references, optional next page and estimated count; empty response may omit messages; bounded supported query matching, unknown query refuses; includeSpamTrash affects scripted candidates |
| Message get | Separate raw versus metadata responses; base64url raw from immutable in-memory bytes, string IDs/internalDate and labels; 404 can occur after a previous list |
| Thread get | Message collection in provider-supported formats; raw bytes require message get, not a fabricated thread raw endpoint; participants/drafts/Spam/Trash are facts, not admission decisions |
| History list | String non-contiguous IDs, typed add/delete/label events plus potentially overlapping generic messages, opaque page tokens, final historyId, empty polls, replay and explicit 404/token expiry |
| Target insert | Raw/date-source/optional thread/label inputs; success, confirmed rejection, uncertain response and scripted actual returned thread facts; no automatic fidelity verdict or map update |

OAuth scope and source/target role facts belong to the controller's explicit
credential/binding test boundary, not `getProfile`. The application gets those
facts only through the separately reviewed credential interface when it exists.
Profile success is not proof of live scopes or correct role. Profile self-tests
assert the exact response field set/types and reject an attempt to seed scopes,
role or binding state as profile fields. No real OAuth/scope checks occur here.

Responses are defensive copies so consumer mutation cannot alter mailbox facts.
Search visibility is independent of existence/direct retrieval: an inserted
message can exist while search returns zero, indefinitely until explicitly made
visible. Get/list/History visibility may be scripted separately. Result estimates
can be wrong or absent. Page scripts are bounded and reject unexpected tokens or
calls; no hidden Gmail search-language implementation is necessary.

Provider HTTP failures use synthetic status/reason/header/body facts shaped for
the locked official client's error path, where needed, without network calls.
Production code remains responsible for classifying 401, 403 reasons, 429,
Retry-After, 5xx and result certainty. Script transport exceptions separately.
Both an effect followed by response loss and response loss without an effect
must produce indistinguishable consumer uncertainty; the fake cannot resolve
that uncertainty for the application. Unfiltered sentinel-bearing error bodies
stay in test memory and exercise sanitization later, not the fake call trace.

### Raw data and transport constraints

Synthetic MIME is built as Python bytes in memory: plain/HTML, multipart,
attachment and inline image, non-ASCII headers, missing/duplicate RFC IDs,
valid/invalid Date, replies and conflicting authentication headers. MIME parsing
or fingerprint comparison is not part of the provider fake's business behavior.
No `.eml`, mailbox dump, raw temporary file, spool, DB cache or serialized fixture
is written. Fake target content is retained only in its in-memory mailbox.

Use a separate fake transport instance per worker, sharing only synchronized
mailbox facts. A probe detects overlapping use of the same transport while
allowing legitimate cross-thread calls on different transports. Call evidence
contains bounded operation names, ordinals, fake transport IDs, timing and
controlled status/byte counts; no raw/body/headers/addresses/error response dump.
Budget/release/ordering policy is production behavior, not implemented here.

## Deterministic fault and interleaving controls

Clock helpers provide aware UTC wall time and independent monotonic time with
explicit advancement, including wall-clock rollback without monotonic rollback.
Never use History IDs as clock values or increment contiguous cursor counters.
There are no multi-minute sleeps or retry timing measured from elapsed wall time.

Fault scripts select a boundary and occurrence, then fail once, repeat a bounded
number of times, or wait at a barrier. All reached barriers and joins have bounded
test timeouts and guaranteed cleanup. An unreached expected hook or unconsumed
script is a test failure; no silent successful no-op injection. Safe assertion
messages report case/hook/category, not captured sensitive values.

The following selects the exact test-controller hook labels. They are closed
test vocabulary, not production function names or a runtime/debug API. Each
helper scenario registers an expected occurrence and must explicitly reach it;
an unused registration fails teardown. Provider hooks are called by the fake;
all other hooks are self-tested with synthetic callbacks until the listed owner
connects a reviewed real implementation boundary. Neither an absent future
module nor a no-op production wrapper counts as a passing consumer test.

| Boundary family | Exact test-only hook labels | Later behavior owner |
| --- | --- | --- |
| Provider calls | `provider.before_execute`, `provider.before_effect`, `provider.after_effect`, `provider.before_response` | P1-02 fake/self-tests; real transport consumers M2 |
| Event/cursor | `event.before_commit`, `event.after_commit`, `cursor.before_final_commit`, `cursor.after_final_commit` | M1-02, M4-01; later-page failure uses provider hook occurrence |
| H0/H1 and scans | `fence.before_commit`, `fence.after_commit`, `scan.before_start`, `scan.after_page` | M3-02, M4-02; scenarios distinguish H0/H1, no cursor counters |
| Intent/dispatch | `intent.before_commit`, `intent.after_commit`, `dispatch.before_guard`, `dispatch.entry` | M2-03/04, M5-03 |
| Insert/map | `result.before_commit`, `result.after_commit`, `mapping.before_commit`, `mapping.after_commit` | M2-02/03/04; remote effect/response use independent provider hooks |
| Stop/restart | `stop.before_effect`, `stop.after_effect`, `claim.before_reentry`, `owner.before_restart`, `owner.after_restart` | M1-03, M2-03/04, M5-03; actual restart belongs to subprocess/crash tests |
| CLI request | `request.before_journal`, `request.before_submit`, `request.before_accept_commit`, `request.after_accept_commit`, `request.before_effect_commit`, `request.after_effect_commit`, `request.before_first_response`, `request.before_lookup` | M1-03, M6-02; lookup scenarios include restored namespace |
| Credentials/maintenance | `credential.before_refresh`, `credential.before_replace`, `credential.after_replace`, `maintenance.before_lock`, `maintenance.after_lock`, `backup.before_snapshot`, `backup.after_snapshot`, `bundle.before_replace`, `bundle.after_replace` | M1-04, M6-01/02 |

The controller accepts only these labels and bounded occurrence/action settings.
Scenario data remains in caller-owned memory, not label text or trace payloads.
For dispatch-versus-stop tests the later owner must map `dispatch.entry` to the
writer actor's serialized admission/committed dispatch marker, not worker queue
submission or a claim timestamp. Test both orderings: stop first forbids provider
execution; admitted invocation first preserves its eventual factual result.
`request.before_lookup` alone cannot prove authoritative negative lookup: M1-03
must also test its serialized ordering and restored-namespace branch. A Python
exception at any hook is only interruption simulation, never a kill/fsync proof.

P1-02 supplies callback/failure/barrier machinery, not production DB wrappers or
an invented schema. Repository/transaction adapters belong to their production
owners. A test connection probe can detect an open SQLite transaction at a fake
network callback; it does not own transaction policy. Inject persistence errors
at real reviewed repository/commit hooks later, not by substituting a fake DB that
pretends to prove durability.

Helper self-tests prove scripts and exception-based interruption work. Actual
process crash/reopen, fsync/disk failure, maintenance locking and CLI subprocess
tests are future consumer cases against real local metadata SQLite/state. A
raised Python exception is not claimed as proof of kill/crash durability.

## Two-layer privacy assertions and offline safety

Use distinct synthetic marker classes so allowed metadata is not conflated with
forbidden content. No real token/address/mail sample is used. Markers are long,
distinctive test values; fixtures can derive the ordinary base64/escaped forms
needed to catch common representation leaks without printing matches.

| Surface/profile | Forbidden | Explicitly permitted exception |
| --- | --- | --- |
| Production metadata DB, WAL/journal, command journal and runtime files | Raw/body/HTML/snippet/attachment bytes/full headers; per-message Subject/From/To/Cc copies; arbitrary provider responses and credentials | Necessary IDs, digest+version, account binding/rule values and typed state in their approved locations; not a free-form payload store |
| All logs and all CLI output | Content, attachment names, credentials, full header/per-message address or subject copies, unfiltered provider errors/stack traces | Controlled categories and necessary explicitly allowlisted local operation/metadata fields only |
| Public CLI, HTTP/UI/URL/network/export | Above plus all addresses including masked, rule/custom-label values, Gmail/RFC IDs, fingerprint, receipt, token/auth link, hostname/path/SQL/internal errors | Independent aggregate DTO fields and fixed text only |
| Private credential/state/config/backup files | Any raw/body/content cache; credentials outside the specific approved credential file | Synthetic credential markers only in explicit owner-only credential locations and coherent private backups, never console/artifacts |

Assertions inspect only explicitly passed, test-owned sinks under the test's
temporary metadata directory: logical SQLite values plus DB/WAL/journal bytes,
captured logs/stdout/stderr, request-journal entries, files and serialized output
buffers. Check active journals before checkpoint/cleanup as well as afterward.
Do not scan real ignored directories, account files, environment secrets or host
logs. Read-only examination of consumer-controlled test files is not permission
to collect private runtime data.

Positive controls deliberately place marker-only violations into test-owned
metadata buffers/files/SQLite cells and verify detection; they do not write raw
MIME or real content fixtures to disk. Negative controls preserve legitimate
binding/rule/ID metadata and private credential files while proving those values
are rejected from public output. Allowed locations are explicit, not a blanket
directory exclusion that could conceal a content cache. Assertion diagnostics
use fixed IDs/categories and never echo matched bytes, paths or provider text.

Sentinel checks are behavioral regression probes, not proof against every
encoding/covert store. Complement them with reviewed field-source allowlists,
file/sink inventory and no-content data-flow review. P1-02 self-tests check the
helpers; M1-02/05, CLI and Web owners must apply them to actual production paths.
Browser DOM/network/export tests belong to M4/M6, not an invented P1-02 UI.

The fake itself has no network implementation or credentials. An explicit
function-scoped network-denial fixture guards supported Python Internet socket,
DNS and client connection paths in foundation self-tests; positive controls
prove a forbidden connection attempt fails before external I/O. Test imports
must not load real OAuth or discovery. Do not make root conftest blanket-disable
every socket: approved local Unix IPC and later local browser traffic require
their own exact test-scoped allowance. Subprocesses do not inherit monkeypatches;
their owners must provide a separately verified offline child isolation/guard,
not assume this parent fixture proves subprocess safety. No live-test enable
flag, secret fixture, mailbox access or reusable real credentials in P1-02.

## Falsifiable acceptance and consumer evidence matrix

Each case gets a stable ID, contract revision, synthetic setup, precise injected
point/interleaving, observed facts, expected production invariant, forbidden
action, helper self-test reference, consumer owner/test, actual command/result
and reviewed candidate SHA. The evidence file separates `helper_verified`,
`core_compatibility_pending`/`core_compatibility_verified` and
`feature_consumer_pending`/`feature_consumer_verified`. A core-pending row blocks
P1-02 completion/M1-02 release; a future feature-pending row alone does not.
Absent modules are not skipped tests reported as passes. The CC references below
originate in the P1-01 plan.

| Case | Foundation self-test/control | Downstream counterexample and owner |
| --- | --- | --- |
| TF-01 / CC-01 | Replayed/overlapping typed History pages and non-contiguous string IDs | Event/message/action/repair uniqueness remain distinct; M1-02/M4-01/M5-01 |
| TF-02 / CC-07 | Later page fails; final cursor/fence hooks independently observable | No premature cursor advance or discovery before durable H0/H1; M3-02/M4-01/02 |
| TF-03 / CC-08 | Insert creates target fact, then loses response; no-effect timeout also supported | Unknown remains recoverable, not blind retry; M2-04 |
| TF-04 / CC-08 | Same raw inserted twice gives different target IDs; delayed search returns zero | Zero search is not proof of no insert or exactly once; M2-04 |
| TF-05 / CC-08 | Old identical unmanaged copy, other-writer copy, multiple/mismatching candidates | No provenance oracle/implicit binding or cleanup; M2-04 |
| TF-06 / CC-01/08 | Missing/reused RFC ID, equal content with different source IDs, Spam/Trash candidates | Source identity/attribution/normal visibility are independent; M2-02/04 |
| TF-07 | 401/403-reason/429-header/5xx and transport failure scripts | Classification retains work, sanitizes errors, no unconditional insert retry; M2-01/04 |
| TF-08 / CC-06 | Barriers expose claim→intent→dispatch→result versus stop ordering | Unsent stale generation blocked; in-flight actual facts retained; M2-03/M5-03 |
| TF-09 | Source disappears after listing or after unknown insert; thread raw unavailable | Re-fetch/recovery or explicit source_missing, never cached raw spool; M2-03/04 |
| TF-10 / CC-02/03/11 | Journal/acceptance/effect/first-response/lookup hooks can fail independently | Same client key lookup, changed-payload refusal, restore lineage fencing; M1-03/M6-02 |
| TF-11 / CC-04/14 | Transport factory uniqueness and shared-transport overlap negative control | One writer, no SQLite transaction across network; actual process tests M1-03/M2-03 |
| TF-12 / CC-07/10 | Persistence failure hook interrupts without consuming later success script | Durable rollback/old cursor/intents retained, not empty DB recovery; M1-02/M4-01/M6-02 |
| TF-13 | Fake estimate differs from actual pages; empty poll and stalled indexing | No fabricated total/ETA/success or fake zero/healthy; M1-05/M4-04 |
| TF-14 / CC-12 | Content markers detected in logical rows and active DB/WAL/journal/files/logs | No forbidden persistence in production, including failure paths; M1-02/M2/M6 |
| TF-15 / CC-12 | Allowed binding/rule/ID markers survive approved internal metadata locations | Not a blanket metadata ban; same markers absent from all public surfaces; M1-05/M4-04/05 |
| TF-16 / CLI-08 | Credential/provider-error/attachment-name markers rejected from all output | Private CLI is not content/token output; subprocess consumer checks all command owners |
| TF-17 / CC-09/10 | Credential/file-replacement barriers and failure actions are deterministic | Coherent backup/restore/cache revisions and offline maintenance; M1-04/M6-01/02 |
| TF-18 | Network and unconsumed-script negative controls intentionally fail safely | Offline harness cannot silently use network or claim an unreached injection passed; P1-02 |
| TF-19 | MIME bytes stay in memory and call trace excludes body/headers/errors | Actual fidelity/raw-budget behavior tested by M2-02/03, not fake success claims |
| TF-20 | Legacy label facts and add/remove/re-add events can be scripted without rules | Readonly zero source mutation, durable action dedupe/cleanup; M5-01/02/03 |
| TF-21 | Profile response contains only documented fields; scope/role injection is rejected | Credentials/scopes/binding verification have a separate boundary; M1-04/06 |

No G1-G6 closure follows from this matrix. AUTH spoof/alignment fixtures are
synthetic input only; real admission trust and bank-domain evidence remain
M1-06/M3 responsibilities. Date/thread/fidelity responses are scripted, not
evidence of actual Gmail behavior or a calibrated upper bound on indexing delay.

### Mandatory P1-02 core-type compatibility acceptance

P1-02 owns the following tests in `test_fakes_contract_compatibility.py` and their
evidence rows. They wait for M1-01's accepted merged minimum types, not M2-01 or
any future Gmail adapter. The exact ADR-level inventory below is the compatibility
target; M1-01 supplies its accepted Python export/constructor mapping before CT
coding. Missing assigned exports fail rather than skip. Tests construct/import
production values directly, without fallback dataclasses, copied enums or a
test-owned core model. A static expected export/field manifest in a test is an
assertion, not a second implementation of the production type.

#### Exact minimum inventory and structural assertions

Import the following public symbols from `facet.contracts`. Its proposed public
`__all__` is exactly 10 primitives, 27 enums and 10 record/union names; CT-01 checks
this inventory and that ownership matches primitives/enums/records submodules.
No protocol under an unlisted name is added. M1-01's independently approved plan
owns this Python mapping; implementation review and actual merge still precede CT.

| Group | Exact required symbols | CT coverage |
| --- | --- | --- |
| Primitives | `ProjectionId`, `LocalId`, `ProviderId`, `Timestamp`, `Count`, `Generation`, `Revision`, `Sha256Hex`, `PolicyVersion`, `ProviderPageToken` | CT-01 inventory/owner; CT-02 valid/invalid bounds and wire-to-value conversion |
| Core enums | `Role`, `SourceMode`, `BindingState`, `RestoreState`, `RuleOrigin`, `RuleKind`, `AdmissionOrigin`, `EpochKind`, `EpochState`, `JobKind`, `JobState`, `Priority`, `InsertState`, `OutcomeCertainty`, `Visibility`, `DatePolicy`, `OperationState`, `PreviewPurpose`, `ErrorClass`, `ErrorCode`, `Freshness`, `PublicPhase`, `PublicHealth` | CT-01 exact values from core ADR; CT-03 privacy; CT-04 distinct independent state types |
| Supporting enums | `LabelChange`, `ReadTaskKind`, `PartitionState`, `ClaimPhase` | CT-01 exact values; CT-02/04 structural cases |
| Value records/unions | `RuleRef`, `AdmissionRef`, `EpochDecisionRef`, `PartitionRef`, `PartitionProgress`, `SourceEventKey`, `SourceEvent`, `JobSubject`, `ThreadGenerationGuard`, `Claim` | CT-01 exact field/tag inventory; CT-02 guards; CT-03/04 helper integration |

The six union names are aliases of their closed frozen-dataclass branches. Public
branch constructors in `facet.contracts.records` follow the M1-01 author's exact
mapping `<UnionName><PascalCaseTag>`; underscore-separated tags become PascalCase.
For example `SourceEventKeyMessageAdded`, `AdmissionRefManualThread`,
`JobSubjectOperationRead`, `ThreadGenerationGuardTracked`. The full variant sets
in the tables below determine every constructor name; no introspective fallback
or best-effort naming is allowed. Each constructor requires its literal `tag`
argument plus exactly the declared payload fields, including nullable fields.
The four non-union records `RuleRef`, `PartitionProgress`, `SourceEvent`, `Claim`
use same-name constructors. Branch classes implement already allocated union
variants; they are not new independent core-record inventory or test-owned types.

CT-02 must check primitive edge cases, not just successful construction:

- Projection selector length 1/64 accepted and 0/65 or unsafe characters refused;
  local IDs use UUID4 lowercase 32-hex, not arbitrary 32-character text.
- Provider IDs preserve string values including non-contiguous History IDs,
  reject empty/control/NUL or over-512-byte values; strings are never converted
  into History arithmetic. Page tokens have their separate 16384-byte/no-NUL
  bounds and never become identity keys.
- UTC-aware timestamps and integer units remain explicit; naive/non-UTC values
  fail as specified by M1-01's accepted UTC constructor. Count/generation/revision
  enforce signed-64-bit nonnegative bounds and reject bool. Positive-generation
  guards are record constraints, not a ban on initialization generation zero.
- SHA-256 syntax is 64 lowercase hex; policy-version syntax/length does not imply
  that AUTH/attribution policy is enabled. No fingerprint record is invented.

All fields below are required, including nullable fields; omitted fields must
not silently default. Closed tagged variants reject unknown tag/extra fields.
Exercise every variant with at least one valid synthetic value and each stated
cross-field guard with a rejecting counterexample:

| Value | Exact fields/tags to check | Structural counterexample |
| --- | --- | --- |
| `RuleRef` | `rule_id: LocalId`, `revision: Revision` | Wrong primitive type/bound refused; no copied private rule value |
| `AdmissionRef` | `initial_backfill(epoch_id, rule: RuleRef, policy_version)`, `future_rule(rule, policy_version)`, `manual_thread(preview_id)`, `action_label(action_command_id)` | Missing policy/rule in automatic variant fails; manual/action variants reject invented authentication payload |
| `EpochDecisionRef` | `backfill_start(operation_id, preview_id, ruleset_revision)`, `gap_approval` with same fields, `scheduled_reconcile(ruleset_revision)`, `requested_reconcile(operation_id, ruleset_revision)`, `scheduled_target_audit()`, `requested_target_audit(operation_id)` | Empty variant rejects payload; no rule-set values or arbitrary decision text |
| `PartitionRef` | `source_window()`, `source_thread(source_thread_id)`, `target_catalog()`, `mapped_target_set()` | Unknown tag/extra field rejected; progress changes do not change partition identity |
| `PartitionProgress` | `partition`, `state`, `completed_pages: Count`, `observed_items: Count`, required-nullable `page_token`, required-nullable `after_source_message_id` | Tokens only source_window/target_catalog; local after-ID only mapped_target_set; other nullable fields None; not_started counts zero/cursors None; complete token None |
| `SourceEventKey` | `message_added`/`message_deleted(projection_id, history_record_id, source_message_id)`; `label_changed` adds `label_id`, `change: LabelChange` | Added/removed distinct; no generic provider messages converted into an extra event; duplicate key equality survives replay |
| `SourceEvent` | `key`, `observed_at: Timestamp`, required-nullable `source_thread_id` | Missing thread represented as None, not guessed; enrichment preserves key; no body/header/provider payload |
| `ThreadGenerationGuard` | `untracked()`, `tracked(generation)` | tracked zero rejected; untracked has no synthetic generation field |
| `Claim` | `claim_id`, `owner_run_id`, `acquired_at`, required-nullable `thread_generation`, `job_revision`, `phase: ClaimPhase` | Omitted nullable generation refused; no timer-created ownership, transport call or claim-recovery transition |

The exact `JobSubject` tags and field order/names mirror all 11 `JobKind` values:

```text
project_message(source_message_id, source_thread_id, generation)
repair_message(repair_operation_id, source_message_id, source_thread_id, generation)
expand_thread(source_thread_id, epoch_id, generation)
resolve_event(event_key: SourceEventKey)
operation_read(operation_id, read_kind: ReadTaskKind)
recover_insert(attempt_id)
scan_discovery(epoch_id, partition: PartitionRef)
scan_gap(epoch_id, partition: PartitionRef)
reconcile_source(epoch_id, partition: PartitionRef)
audit_target(epoch_id, partition: PartitionRef)
cleanup_action(action_command_id)
```

IDs use their core ADR types. The first three variants require generation at
least 1. scan_discovery accepts source_window only; scan_gap/reconcile_source
allow source_window/source_thread; audit_target allows target_catalog/
mapped_target_set. `ReadTaskKind` has exactly thread_preview, review_preview,
backfill_preview, repair_preview, recovery_preview, gap_preview and doctor_live.
A generation-less recovery/read subject conveys no insert authority.

Cross-record projection/reference resolution, contradictory thread references,
atomic key uniqueness and rule-snapshot ownership require repositories and remain
M1-02 consumer tests. CT checks value equality/structure, not a fake SQL identity
encoder. In particular resolve_event keeps the complete SourceEventKey,
operation_read preserves operation ID across helper retries, and recover_insert
preserves attempt ID; no helper creates a replacement operation/attempt on a
fault. Their actual durable dedupe/concurrency and no-second-insert assertions
remain TF-01/03/04/10 consumer cases under CC-01/02/08.

#### Deferred types are not compatibility prerequisites

Do not instantiate Projection/Binding/Rule/TrackedThread/Epoch/HistoryCheckpoint,
full JobRecord/attempt/mapping rows (M1-02); CommandEnvelope/payload/receipt/
Preview or wire serializer (M1-03); credential envelope (M1-04); ErrorRecord/audit
payload/public DTOs (M1-02/05); provider result/error protocol (M2-01); fingerprint
or recovered-attribution records (M2-02/04). These are separately reviewed owner
extensions, not missing CT exports. CT-03 uses actual minimal RuleRef/SourceEvent/
JobSubject/Claim and scalar values, not nonexistent binding/DTO records. Permitted
binding/rule-value markers can test the privacy helper's synthetic input buffers,
but that does not claim a current production storage model.

| Case / owner | Minimum compatibility proof | Required evidence / completion gate |
| --- | --- | --- |
| CT-01 / P1-02 | Import the actual M1-01 minimum primitives/enums/records allocated by the frozen registry; verify owner/module, contract revision and exact applicable fields/closed variants | Exact M1-01 merged SHA and ADR version/hash; all assigned exports present; missing/drifted type negative control fails |
| CT-02 / P1-02 | Build actual core ID/time/generation/key values from synthetic wire/controller inputs; keep string non-contiguous History IDs, timestamp units and distinct frozen key variants intact | Value/type/constructor assertions at the final frozen boundary, including specified invalid-input guards; no fake adapter or fabricated production keys |
| CT-03 / P1-02 | Exercise actual allocated core metadata records/closed enums with the helper privacy assertions; legitimate binding/rule/ID metadata and disallowed content/public markers stay distinct | Positive/negative controls using actual production values, with field-classification alignment; not evidence of an as-yet-unimplemented production DTO or DB |
| CT-04 / P1-02 | Exercise fault/trace/assertion helpers with actual allocated core selectors/values, preserving independent frozen state axes and excluding forbidden payloads from helper evidence | Exact input types and safe trace/assertion results; no business transitions, provider result protocols or copied outcome state machines |

For CT-03, derive only explicit metadata fields from actual SourceEvent,
RuleRef, JobSubject and Claim values into test-owned inspection buffers; do not
serialize their entire records to a pretend public DTO. Check that permitted
internal IDs pass the metadata profile and the same ID markers fail the public
profile. Inject separately classified content markers to prove rejection without
adding forbidden fields to production records. Buffer construction here is a
helper control, not an approved persistence/public serialization path.

For CT-04, caller closures hold actual `JobSubjectRecoverInsert`,
`JobSubjectOperationRead`, `ThreadGenerationGuardTracked`, `Claim` and the separate
`JobState`, `InsertState`, `OutcomeCertainty` enum values. Invoke test-only hooks
twice under a bounded retry script and assert identity/value preservation, without
mutating or resolving those states. Trace output is limited to hook/ordinal/
controlled outcome/time counts and does not serialize these selectors, IDs,
claim contents or private payloads. Safe failure diagnostics must likewise omit
them. This proves helper compatibility, not production dedupe or state transitions.

This is compatibility with the minimum executable core values, not an invented
production Gmail request/result protocol. Deferred provider result protocols and
adapter signatures belong to M2-01 and must not be implemented as ghost types in
M1-01, P1-02, or a fake. The final plan maps each CT case to only the concrete
types allocated to M1-01 in the accepted registry; deferred feature types remain
explicit future feature-consumer evidence, not a hidden CT prerequisite.

P1-02 is complete only when provider/helper self-tests and all mandatory CT cases
are implemented, pass against the accepted merged M1-01 types, receive independent
implementation/evidence review on the exact candidate, and pass that candidate's
CI. Until then, any integrated provider-only slice remains partial and cannot
close Issue #5 or unblock M1-02. Future feature-consumer tests retain their own
owners/gates and may remain pending without creating an M2 dependency cycle.

## Implementation sequence after the release gates

1. Independently review this r3 alignment against integrated P1-01 `09031e7`.
   Review readiness is not implementation dispatch; this unit has no code yet.
2. Record approval on the exact new plan hash and coordinator release. Current
   input registry, test-hook labels, versions/units/classifications and ownership
   are explicit above. Any further base/contract drift needs inspected carry and
   review; M1-01's accepted export plan and merged code remain the CT-only gate.
3. On explicit implementation dispatch, create in-memory MIME/wire-fact helpers,
   service/request scripts and test-controller separation. Add TF-01 through
   TF-07/09/13/19/20 self-tests without importing nonexistent domain types.
4. Add deterministic clocks/faults/barriers/transport controls and negative
   controls. Verify all failures and cleanup are bounded and observable.
5. Add privacy/network helpers and the sole root fixture registry. Add positive
   controls and legitimate-private-metadata negative controls; no raw files.
6. Populate distinct helper, mandatory core-compatibility and future feature
   evidence rows. A reviewed provider-only slice may integrate while core types
   are pending, without completing P1-02 or releasing M1-02. After M1-01 is merged
   and the concrete alignment/dispatch is reviewed, implement and pass P1-02's
   CT-01 through CT-04; no substitute types or future M2 prerequisite.
7. Run locked offline validation; send candidate diff/SHA and evidence for
   independent implementation/acceptance review. Correct findings and re-review
   changed candidates. Commit/push/PR/integration require coordinator dispatch.
8. Hand the integration/docs owner accurate helper/core evidence and pending
   feature-consumer cases. Release P1-02 only after mandatory core compatibility,
   accepted exact-candidate review/CI/integration; a partial provider delivery,
   dirty worktree or plan approval alone cannot release M1-02.

Future atomic units should be small coherent helper changes with their self-tests
and evidence, for example `test: add synthetic Gmail provider fixtures`,
`test: add deterministic failure controls`, and `test: add privacy sentinel checks`.
Do not split one invariant across unrelated unchecked commits, alter production
interfaces to make tests pass, or weaken an assertion after it exposes a defect.

## Verification environment and honest evidence boundaries

Read-only host checks found `uv 0.12.2` and an already installed Python 3.13.5
usable by `uv python find --no-project --system --no-python-downloads --offline
'>=3.12'`. There is no interpreter download or system/identity configuration
change. This is local Python 3.12+ availability, not actual Python 3.12 CI evidence.

After implementation dispatch, use the owned worktree and installed interpreter
with an offline locked environment, e.g.:

```text
uv sync --locked --extra dev --python /usr/local/bin/python3.13 --offline --no-python-downloads
uv run --frozen --offline --no-python-downloads ruff check .
uv run --frozen --offline --no-python-downloads ruff format --check .
uv run --frozen --offline --no-python-downloads pytest tests/unit/test_fakes_gmail.py tests/unit/test_fakes_faults.py tests/unit/test_fakes_privacy.py
uv run --frozen --offline --no-python-downloads pytest tests/unit/test_fakes_contract_compatibility.py
uv run --frozen --offline --no-python-downloads pytest
uv run --frozen --offline --no-python-downloads facet-spike --help
bash scripts/check-repo-safety.sh
git diff --check
```

Run production `facet --help` only after M1-01 makes that entrypoint available.
The core-compatibility pytest command likewise runs only after its merged types
and dispatched tests exist; otherwise the required CT gate is pending, not pass.
If an offline dependency is not cached, stop and report the exact missing locked
requirement; do not download an interpreter, alter the lockfile or silently use
an unlocked environment. Record Python/package/base/candidate/contract revisions,
test count, failures and commands. Existing spike tests must remain unchanged
and passing; their success is not production coverage. PR CI must apply to the
actual candidate, not the starting main CI cited above.

Current drafting validation is document-only: scope/status, whitespace, relative
links, balanced fences, no private data and dependency/ownership consistency.
The index safety script checks tracked/staged content, so an untracked plan also
needs explicit content review; no plan draft is force-added to expand coverage.
No proposed helper, runtime fault, production privacy or subprocess test has been
executed in this drafting step.

## Risks, stop gates, and handoff

| Risk | Required containment or counterexample |
| --- | --- |
| ADR/type drift or duplicate domain models | Exact integrated `09031e7` inventory; independently review this new hash and later M1-01 export alignment; M1-01 sole executable type owner |
| Fake too helpful, masking recovery bugs | Non-idempotent inserts, unlimited search delay, ambiguous old copies, no provenance oracle; strict unexpected-call scripts |
| Fake implements production policy | Only provider facts and controls; consumer invariants and real repositories remain their owners' code/tests |
| False privacy failure or broad exclusion | Separate content/public markers and explicit allowed locations; both positive and negative controls |
| Sentinel false confidence | Field-source/data-flow review plus file inventory; disclose representation/scope limits |
| Global fixture collision or hidden network | Single root registry owner, function-scoped guards, no real service startup; separately guarded child tests later |
| Flaky concurrency or unobserved crash point | Explicit barriers/clock, bounded cleanup, mandatory hook consumption; exceptions not mislabeled kill/crash durability |
| Main/type changes during parallel work | Exact base/input revision and coordinator-managed carry; no unauthorized refs integration or shared-file edits |

Stop and report if frozen contracts require forbidden persistence, unreviewed
production types/IPC changes, hidden retry/provenance shortcuts, access to real
credentials/mail, fixture ownership overlap, or unavailable offline dependencies.
Ordinary compatible details return to independent technical review; material
product/privacy/authority changes require the coordinator's user decision packet.

No live Gmail/OAuth/scope expansion/mail mutation, deployment, image publication,
release/tag, contact with other people or recurring automation is required or
authorized by this package dispatch. This handoff makes no external writes; the
coordinator receives the plan/hash and maintains current Issue status.

Handoff remains plan-only: actual base `09031e7`, owned file/worktree/branch and
new SHA-256 supplied to the coordinator; r3 independent review and implementation
dispatch pending. P1-01 is integrated, while M1-01 executable types/CT remain
pending. No tests or production types were implemented by this drafting step.

## Independent r1 review responses

The independent review of r1 at SHA-256
`e2077ca2744e30244ca9ec1c26e559896ec460be137b5fc0b5853e14d1ec8ba7`
requested changes. The former owner's r2 at
`83994114adb67ae980362be6a2d57fd79f1e16537354af94c93a0d346b03939c`
received independent conditional approval with R1/R2 closed, subject to final ADR
alignment; this does not approve the current r3 revision automatically:

- R1: restrict Profile to the actual Gmail shape; scopes/role/credential facts
  now have a separate boundary, with TF-21 enforcing the distinction.
- R2: define P1-02-owned mandatory CT-01 through CT-04; core-pending blocks package
  completion/M1-02 release, unlike future feature consumers. Sequence/evidence
  and partial-integration semantics now agree.

R3 preserves those fixes and adds actual P1-01 integration/base evidence, the exact
47-symbol core inventory, closed value/tag/field/nullability/generation tests,
M1-01-owned union-constructor mapping, and test-hook versus future-runtime-hook
ownership. It explicitly excludes deferred provider/SQL/command/DTO interfaces
from CT prerequisites. Provider/self-tests may run alongside M1-01 only after this
plan's approval/dispatch; CT completion still requires the reviewed actual M1-01
merge. This author does not independently review their own plan.

## Primary-source API checks

Checked read-only on 2026-10-02. These define wire behavior or library constraints,
not proof that the proposed fake or production service works:

- [Gmail profile](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users/getProfile):
  response fields are email address, message/thread totals and string History ID;
  OAuth scopes and source/target role are not profile response fields.
- [Gmail message list](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list):
  ID/thread-only list items, optional pagination, estimates and Spam/Trash query
  behavior; no list-body shortcut.
- [Gmail message get](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get)
  and [Message resource](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages):
  format-specific retrieval, base64url raw, string metadata and documented thread
  prerequisites; the fake does not independently prove actual threading.
- [Gmail thread get](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads/get):
  supported thread formats do not provide a raw-thread endpoint.
- [Gmail insert](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/insert):
  insertion without sending, Message request/response and date-source option;
  no provider intent/provenance response field is assumed.
- [Gmail History list](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.history/list):
  non-contiguous string IDs, typed events/generic overlap, pagination and expired
  cursor 404; no fixed lifetime is encoded into tests.
- [Official Python client thread safety](https://googleapis.github.io/google-api-python-client/docs/thread_safety.html):
  separate HTTP instances for concurrent workers; helpers probe this constraint.
