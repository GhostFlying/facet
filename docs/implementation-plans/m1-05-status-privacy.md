# M1-05 public status models, controlled errors and logging

Date: 2026-10-02. Revision: r1, plan-only candidate.

Status: drafted for independent plan review. Only this plan and bounded Issue
tracking are currently authorized. No status/source/test implementation, HTTP/UI,
environment change, commit, push or PR is included. M1-02 storage and M1-04
credential interfaces remain unaccepted proposals; their names are not frozen APIs.

## Assignment, inputs and readiness

- Package M1-05; [Issue #14](https://github.com/GhostFlying/facet/issues/14),
  parent [Epic #1](https://github.com/GhostFlying/facet/issues/1).
  Delegated owner `phase1_plan_author`, 6.1 Sol xhigh; root assigns independent
  Astra high plan and implementation/acceptance review. No self-approval.
- Owned worktree `../facet-worktrees/m1-05-status-privacy`; branch
  `docs/m1-05-status-privacy-plan`, created from exact clean actual main
  `1b7cd58b4846aab86edcbb781a999abb968d047c`. Fresh remote and existing author/
  committer noreply identity were checked; no saved Git configuration changed.
- Frozen P1-01 core/writer design is integrated at `09031e7`; core SHA-256
  `795f80ab672ed4e0130eafc330bc0403981360f2e70bf935579973065c64f2f6`, writer
  SHA-256 `5f0e5af9cc238f7967a88590fb53acc91c4697ffa27d19773cc66cf5ccc41368`.
  Public/private field classes, four DTO records, controlled enums/error codes
  and CC-12/13 are normative inputs, not runtime evidence.
- Actual M1-01 foundation at `b1e4ae08` and complete P1-02 helper/core CT at the
  starting HEAD are reviewed/integrated. Exact
  [main CI 36982879970](https://github.com/GhostFlying/facet/actions/runs/36982879970)
  passed 3.12/3.13. Existing config/CLI fixed errors and spike isolation remain.
- M1-02's approved implementation plan and still-unaccepted storage proposal were
  inspected during engineering preparation. Its CountsSnapshot/error/audit names
  are proposed inputs, not a licence to invent an adapter or read raw SQL rows.
  M1-02 schema revision is being reviewed/changed; consume only its final accepted
  executable surface on later dispatch.
- M1-04's proposed OAuth/credential plan exposes the need to isolate library URL/
  callback/provider logging and classify invalid_grant. Its credential manager,
  envelope/phase/grant evidence and logger integration are not frozen here.

Applicable AGENTS and ordered product/project/Gmail/Dashboard/CLI/execution/workflow
documents, the M1-05 card, frozen core public inventory and actual M1-01/P1-02
outputs were read. Older shared status is a handoff snapshot; actual integrated
receipts above supersede its then-pending package prose. No ignored credential,
mailbox data or live service was read. All acceptance below is future evidence.

| Gate | Current state | Required release evidence |
| --- | --- | --- |
| Plan preparation | Authorized | Independent r1 hash review only |
| P1-01 / actual M1-01 / complete P1-02 | Integrated | Preserve actual exports/default/private behavior and use actual helpers |
| M1-02 storage/aggregates | Pending design acceptance and implementation | Actual reviewed schema/repository output; exact typed adapter alignment |
| M1-03 owner/view/CLI | Approved plan only, no implementation | Real offline read provider and canonical status/doctor consumer tests |
| M1-04 credential diagnostic/logging input | Proposed | Its reviewed role-state/error/library boundary, no raw envelope consumption |
| Model implementation | Not dispatched | Final closed schema/export/adapter field matrix, review for material drift, explicit root dispatch |
| G1 / G4 / G6 | Incomplete | Complete CLI/runtime consumers, HTTP/DOM/browser and container gates remain separate |

## Deliverable and owned file scope

Provide independent immutable public allowlist models, strict serialization,
controlled code/message/suggestion/exit catalog and production logging primitives.
Define meaningful unknown/stale/count/unit semantics and private doctor presentation
separately. This package supplies a model/presentation boundary, not a Dashboard,
cache store, scheduler, Gmail health probe or remote diagnostics service.

Current editable scope is this file only. Proposed implementation scope:

| Future owned files | Responsibility and boundary |
| --- | --- |
| `src/facet/status/__init__.py`, `models.py` | Closed public envelope and four record families, explicit nested status/metric/issue types; no inheritance from DB/internal/private models |
| `src/facet/status/serialization.py` | Explicit field-by-field JSON primitives and closed local presentation; reject wrong/unknown types before output, no generic object dumping |
| `src/facet/status/errors.py` | Catalog over actual ErrorCode/ErrorClass, fixed messages/suggestions and canonical CLI exits; safe unknown-boundary fallback |
| `src/facet/status/logging.py` | Closed safe log event/handler/bootstrap policy and third-party logger containment, no arbitrary message/exception sink |
| `tests/unit/test_status_models_*.py`, `test_status_errors_*.py`, `test_status_logging_*.py` | All closed schema/enum/type/nullability/count/unit/error catalog and leak counterexamples |
| `tests/integration/test_status_privacy_*.py` | Real serialized output/stdout/stderr/log-file subprocess and accepted DB adapter boundary tests, synthetic private values only |
| This plan | Actual input alignment and complete evidence/limits handoff |

Exact public exports and every field/type/required-nullability/bound/provenance/
serialization key must be recorded before coding, using the frozen inventory below.
The final aligned plan may contain that matrix or reference an independently reviewed
owned schema extension if needed; no source precedes its review. Adding an arbitrary
optional field is not forward compatibility. Storage/public schema/digest versions
remain independent, and all unsupported versions/extra fields refuse safely.

No current permission to change CLI registry/commands, M1-02 tables/rows, core enums,
M1-03 runtime/view, M1-04 credentials, test foundations/conftest, spike, dependencies,
CI, shared root docs or deployment files. Consumer changes go to their owner and
reviewed integration unit. This worker remains next M1-02 implementation owner;
ready storage work takes priority over this plan preparation.

## Public inventory, field provenance and metric semantics

Consume the frozen [core public contract](adrs/core-state-contracts.md) and
[Dashboard specification](../dashboard-spec.md), not an internal model copy.
Public schema-1 envelope contains only schema_version, sampled_at, freshness,
nullable age_seconds, scope fixed to projection, and one of the four closed data
records. It does not identify that projection/account by private selector.

| Closed family | Allowed field sources and required semantics |
| --- | --- |
| Status | Actual PublicPhase/PublicHealth; source/target role records containing approved mode/auth state and last verification time, plus operational last-poll/verified-insert/heartbeat times; no email address/identity and no per-mail original Date |
| Progress | Discovery complete and scoped scanned/discovered/completed thread counts, nullable known message total, unique confirmed mappings, exclusive current JobState counts, nullable oldest runnable job age, hourly/daily verified counts, bounded rate/latency measures with explicit unit/window/sample count |
| Issues | Bounded aggregate groups of actual code/class/role, count, first/last time, retryability, nullable next retry and fixed suggestion code; no per-item selector, arbitrary detail or remote error |
| Diagnostics | Build-supplied app version and reviewed schema version, owner count, typed DB readable/writable/mode/scope readiness, pressure enums and heartbeat/check timestamps; no host/path/PID/config dump/process arguments or OAuth material |

Nested schema closure must explicitly allocate role health, component availability,
pressure, units/windows, suggestions and issue-group bounds; reuse actual core enums
where defined rather than duplicate them. New status-local enums have a finite
reviewed inventory and no free-text escape. Only trusted build source produces an
app version; an arbitrary config/provider string cannot be relabelled as version.
Times are operational aware-UTC values; units/ranges are validated, bool is not a
count, non-finite values and coerced/unknown enums are refused with fixed errors.

Unique success counts current verified source mappings, not insert attempts,
receipts, mapping-history rows or target mailbox size. Repeated History events,
verification retries and repair history cannot inflate it. Target missing/visibility
is a separate audit issue, not deletion of historical confirmed facts. Job categories
are exclusive and retain blocked/retry/attention/cancelled/missing/failed outcomes.
No hidden category removal may manufacture all-success.

Progress is one explicit epoch/window; no epoch UUID is public. During discovery
known total remains null, even if a provider reports an estimate. No fake percentage
or ETA. A later known total retains message versus thread units and ongoing additions;
terminal exceptions yield processed-with-issues, not all-success. Aggregate counts
and epoch membership must come from actual accepted repositories; synthetic model
tests do not prove query correctness. No ghost CountsSnapshot or speculative SQL.

Unavailable metric has null value and zero samples, not numeric zero/healthy. Rates/
latency retain scope, unit, window and actual sample count; stored sums/histograms,
P95 calculation and measurement definitions remain their owning reviewed metric
extension. This plan adds no performance threshold, sample minimum or measurement.
Do not derive sync latency from old raw RFC Date or include AI indexing delay.

Fresh/stale/unavailable is explicit at envelope/component level. Re-serializing an
old sample cannot renew its sampled_at or mark cached green healthy. Unknown auth,
DB or pressure is not pass. Poll/heartbeat/role ages and snapshot age are different
signals. The cache/runtime owner later supplies reviewed freshness policy; do not
invent a new public SLA or expiry threshold here. Clock anomalies must remain
explainable unknown/unavailable, not silently clamp them into fresh/zero-age.

Model and serializer work is pure and has no DB/Gmail/credential/command capability.
Actual aggregation/caching/HTTP belongs to M4-04; model instances are not a new
persistent snapshot store. Future HTTP GET consumes cached public values only and
cannot trigger refresh, audit, mutation or Gmail through a serializer/property.

## Default/private CLI versus public output

Default CLI permits minimum fixed operating state and opaque local request/operation/
preview selectors needed to act, as selected by the frozen writer/core contract.
Mail IDs, bindings, rule values, fingerprints and full paths require explicit local
`--private-metadata`. A local private diagnostic type is separate from all four
public DTO families and never their subclass/base or optional private fields.
Private opt-in cannot include body/raw/snippet/HTML/full headers/per-message sender
or recipient/subject/attachment names or bytes/credentials/provider responses.

Doctor checks and their normalized facts may be shared with future consumers;
presentation is not shared by casting the private result. A private doctor fact
can contain an allowed local selector, while its public equivalent constructs only
aggregate role/component/code/count/time. Public status/doctor has no receipts,
addresses (even masked), rules/custom label values or routes to individual work.
`--public` does not turn an arbitrary command result into a safe export; unsupported
public commands refuse. No copying dict/repr/asdict/exception attributes into data.

Keep canonical CLI schema-1 and exits 0/2/3/4/5/6/7; accepted remains distinct from
completed and displaying blocked work can still be a successful read. Fixed code
catalog must cover every actual ErrorCode and correct class/exit/suggestion without
interpolating user input. Dependency failures retain work; persistence failures
never return a success receipt or encourage empty initialization/blind insert retry.
Unknown exception/type/enum maps to a fixed boundary failure, never str(exc), repr,
traceback, errno path, SQL text/parameters, request URL or provider JSON.

Status/doctor command registration, offline owner/view, invalid_grant operation,
request receipts and genuine CLI E2E remain M1-03/04/06 integration. This package's
output subprocess probes are evidence of the actual serializers/logging boundary,
not a claim that full doctor/runtime commands already work.

## Logging, third-party libraries and typed audit

Production logging accepts a closed safe event with fixed registered event/code/
role/component/class plus allocated counts/operational times. It has no arbitrary
message, extra dict, mail selector, account/rule/path, exception, stack or SQL slot.
Log levels including DEBUG use the same field policy. Prefer preventing unsafe data
at construction over regex masking after raw was already formatted or emitted.

The app-owned production startup path configures containment before importing/
constructing credential/transport code that can log. Freeze the actual locked
library logger inventory and propagation/handler policy on implementation alignment;
test google OAuth/auth/client/HTTP, requests/urllib3/httplib2 and loopback callback
logging actually used. Untrusted third-party records must not reach a console/file/
public diagnostic by root propagation, alternate handlers, DEBUG or exc_info.
Do not invoke an unsafe object's str/repr/getMessage merely to scrub it afterward.
Missing/unknown third-party records produce at most a fixed code, not raw fallback.

Do not mutate global logging on module import or weaken the isolated spike's
exploratory tool behavior. Production startup/runtime/CLI owners integrate the
explicit logging bootstrap and fixed uncaught-exception boundaries. A third-party
direct print/callback handler is not protected by Python logging filters alone:
M1-04 must use its reviewed library calls and private interactive terminal path,
and M2-01 later repeats transport failures under capture. No monkeypatching global
stdout, TLS/OAuth checks or reclassifying the one-time auth URL as public telemetry.

M1-04 supplies only closed role-state/time/error facts and explicitly handles its
interactive authorization URL exception; M1-05 receives no credential envelope,
client secret/token/code/state/URL or arbitrary library exception. Credential phase,
manager revision and logging handshake is reviewed before registration. Real reauth
and its Compose terminal setup remain separately scoped; fake redaction is not live
OAuth or backup evidence.

DB audit/error inputs stay typed IDs/state/revisions/codes/counts/times in their
private storage-owned schema, not rendered message/suggestion text or JSON notes.
M1-05 catalog presentation occurs at the boundary, not a covert content column.
Allowed DB IDs/rules/bindings can survive private storage while forbidden content/
credentials are rejected before persistence. Public/log policy is stricter than
metadata storage; no overly broad test that rejects all legitimate DB metadata.

## Required acceptance and privacy counterexamples

Use actual serializers/error catalog/log handlers in-process and in isolated
subprocesses, with P1-02 detecting positive/negative controls. No real mail/private
state, uploads or uncontrolled external network. Public JSON, default/private CLI,
log stdout/stderr/files and storage are separate sink classifications.

| ID | Future required evidence |
| --- | --- |
| ST-01 | Exact public schema/exports and every nested field/type/nullability/bound/version; extra dict fields, wrong enum, bool counts, arbitrary subclass/object and non-finite metrics refuse |
| ST-02 | Every ErrorCode has fixed class/message/suggestion/CLI exit; malformed/unknown codes map to fixed fallback; attacker __str__/repr/exception/SQL/URL never runs or appears in output |
| ST-03 | Replay/retry/duplicate History and repair-history scenarios against actual accepted mapping/epoch queries count unique confirmed sources, not attempts/receipts/target totals |
| ST-04 | Exclusive counts across every JobState; blocked/cancelled/missing/attention/partial failure retained; no double categorization or false all-success |
| ST-05 | Discovery incomplete with estimate/unknown/zero/later-changing total, thread/message units, nullable oldest-job age; no fake percent/ETA or epoch selector leak |
| ST-06 | Zero-sample latency/rate null with actual sample count/unit/window; no false zero/P95 claim, numeric bounds/coercion rejected |
| ST-07 | Stale green cache, unavailable source/target/DB/pressure, clock drift and retained sampled_at; serializer cannot refresh timestamp/health or invoke a check |
| ST-08 | Synthetic addresses/masked addresses, subject/From/To/Cc/body/snippet/HTML/raw/attachments/names/Content-ID, mail/auth URLs injected into every reachable public source; absent from all JSON/text keys and values |
| ST-09 | Gmail/RFC/local operation/epoch/request IDs, fingerprints, rule/domain/custom label values, hostnames/full paths/proxy credentials injected; public excludes all, default/private rules enforced separately |
| ST-10 | Token/client secret/code/state/provider exception/response/traceback/SQL/params injection on ordinary and failed serialization/error paths; no stdout/stderr/log/public leak at DEBUG or normal level |
| ST-11 | Actual third-party logger propagation/alternate handlers/exc_info/callback-request records and unsafe message object's __str__/repr; positive leak controls detect failure before containment pass |
| ST-12 | Isolated subprocess capture of real serializer/error/logger stdout/stderr plus explicit temporary log files; one JSON document where applicable, no crash traceback/value/argv leak or global spike logger regression |
| ST-13 | Actual accepted DB/audit/error rows plus active DB/WAL/journal/file scans: legitimate private metadata retained, content/credentials rejected before write; fixed presentation does not create free text/JSON storage |
| ST-14 | Private doctor fact with IDs/path/account versus independently built public component aggregate; no inheritance/dict/asdict/repr/property traversal or public mutation wrapper |
| ST-15 | External-network-denied model/output tests, injected DB/credential/command callbacks cannot be reached from serialization; no side effects or hidden snapshot/Gmail store |
| ST-16 | Accepted M104 role facts/provider failures with closed handoff; no credential envelope/URL reaches M105; actual startup/refresh/callback logging integration separately recorded |
| ST-17 | Exact-candidate locked supported-Python full regression/lint/format/safety/wheel, independent model/privacy review and 3.12/3.13 CI; no skipped pending inputs count as passed |

ST-03/13 require actual reviewed M1-02 output and its repository calls, not a second
fake DB business engine. ST-16 uses M1-04's accepted implementation when available;
an early synthetic boundary slice does not close its consumer integration. Consumer
tests for CLI-01/08 and CC-12/13 remain mandatory. M4-04/05 repeat sentinel injections
across real HTTP responses, DOM/frontend/URL/network/export and rendered stale states;
M6 repeats image/container/Compose logs and maintenance. None of those HTTP/browser/
deployment checks is claimed by model tests. Sensitivity checks inspect escaped JSON
and encoded forms with detecting controls, not column/field-name scans alone.

## Sequence, risks and stop gates

1. Save plan/base/hash and obtain independent review. No implementation is released
   by this preparation or by fulfilling another package's dependency.
2. After actual M1-02 review/integration, record exact typed query adapter and actual
   model export/field/serializer matrix; align M1-03 and M1-04 owned inputs. Material
   changes need plan review. Do not implement a guessed Snapshot/credential type.
3. On root dispatch, implement pure model/catalog/serializer and their tests, then
   safe logging/subprocess/sink tests, then actual available consumer adapters.
   Capture third-party library versions/logger entry points before relying on a
   containment policy. Missing consumer tests remain pending rather than skipped.
4. Complete locked checks in a separate accepted runtime environment, full offline
   regression, actual output/sentinel negative controls and staged safety. On later
   Git authorization use user/noreply atomic action subjects; exact candidate review
   plus CI precedes root-delegated integration. No self-referential report commits.

Stop for field-source/private-model leakage, unclosed schema/helper variants,
incorrect count/freshness interpretation, any raw/credential/provider data offered
as telemetry, unsafe third-party print/log behavior, unavailable actual DB/owner
provider or scope expansion. Report concrete counterexamples to root/feature owner;
do not weaken policy, delete a test or log raw detail to debug it. Privacy/product/
authority decisions return to the user; routine interface closure is engineering.

This plan introduces no Dashboard/frontend/HTTP/authentication/TLS/login/export,
Gmail/OAuth interaction, host service/credential/environment change, deployment,
image/release/license or automation. G0 is approved; G1/G4/G6 and actual M1-05
functionality remain unverified. M1-02 ready coding takes precedence when dispatched.

## Execution appendix: delegated output extension design

Root confirmed independent approval of the original 274-line r1 plan, SHA256
`e88eadeec0773388f9bb4a6932343afc53d876c84f5d5dddc6deeb75bd55de02`, and reassigned
the docs-only lane to phase1_architecture_plan. That approved prefix is unchanged.
Actual owned base remains `1b7cd58b4846aab86edcbb781a999abb968d047c`.

The design artifact is [public-output-logging-v1.md](adrs/public-output-logging-v1.md),
proposed m1-output-v1 r1. It closes four public families, nested finite fields,
types/units/nullability, source/freshness semantics, exact exports/serializers,
all actual ErrorCode catalog entries and safe logging/process boundaries. M102 r3
storage design and M104 r2 credential design have independent approvals, but
their actual implementation/composer interfaces are not fabricated by this ADR.

The ST-16 dependency sequence is early reviewed/integrated M105 model/logging
slice, then actual AUTH consumer implementation, then genuine ST-16/OA-16/17
integration. Early synthetic output evidence cannot close M105/G1 or claim those
future consumers passed. The existing explicit controlling-terminal OAuth URL
exception is retained with a mandatory positive PTY control and separate clean
stdout/stderr/log sinks.

Only this appendix and the new ADR were edited. No source/tests/SQL/HTTP/private
credential/runtime change or Git publication occurred. Design was paused for
independent SQL value-slice review and resumed only after root dispatch; subsequent
ready SQL candidates keep priority. Exact hashes/scope checks go to root and
another independent reviewer; this author cannot approve the output extension.

## Sequencing amendment: independent pure-output engineering slice

Date: 2026-10-02. Proposed for independent review; no source dispatch yet.
The original 274-line approved prefix remains byte-for-byte unchanged. This
amendment supersedes the original sequence step 2's wait-for-M102 requirement
ONLY for the bounded early slice below, not adapters or the complete package.
Root authorized this proposal to enable dependency-ready parallel engineering;
it changes neither product scope nor privacy or final acceptance requirements.

Early-slice inputs are actually integrated M1-01 b1e and complete P1-02 1b7,
frozen core/writer contracts, and independently approved output ADR SHA256
`466f8abf7814fb38f7df99c94880785a6032fd481932d03a5b3b630acca92617`.
The ADR body is unchanged. After this amendment's independent approval AND root
implementation dispatch, phase1_architecture_plan may implement and integrate a
coherent partial unit containing only the plan-owned `src/facet/status/` pure
models, catalog, serializers and explicit logging primitives, their
`tests/unit/test_status_models_*.py`, `test_status_errors_*.py`,
`test_status_logging_*.py` and isolated output/logging subprocess cases in
`tests/integration/test_status_privacy_*.py`. Evidence goes in this plan appendix.
No shared CLI entrypoint, M1-03 bootstrap, DB schema/query/adapter, credential
manager/adapter, runtime cache, HTTP or container change belongs to this slice.
No imports/callbacks acquire an owner, DB connection, credential or network.

Use exact closed DTO values and detecting synthetic privacy controls, not fake
storage/owner/Auth business engines. Missing production sources stay explicitly
unavailable/null/unknown; zero or healthy requires real consumer evidence. The
pure test fixtures exercise validation only and are never registered as live
snapshots. Logging bootstrap is explicit, not invoked by module import; spike
process behavior remains isolated. Test ordinary logs AND pre-buffered stdlib
MemoryHandler records at normal shutdown/atexit and controlled startup refusal:
removeHandler/disable/NullHandler alone cannot prevent later buffer flush. No
raw record may be formatted/emitted during setup, failure, close or exit. Preserve
the approved TTY-only AUTH URL exception, with its actual consumer PTY gate later.

Early evidence can cover applicable ST-01/02/04..12/14/15/17 pure-boundary portions
and explicit logging subprocess regressions. It does not mark their future real
consumers as passed. Actual accepted-and-integrated M1-02 remains a hard input for
DB adapter work and complete ST-03/13; actual AUTH/M1-03 integration remains a
hard input for ST-16, OA-16/17 and production bootstrap/TTY verification. Full
M105 closure, Issue #14 closure, G1, runtime/CLI, HTTP/browser and container gates
remain unchanged and pending until their real evidence exists. No skip/xfail of
a missing consumer substitutes for that evidence.

Another agent independently reviews this exact amendment before code and the
early candidate implementation/acceptance afterward. Candidate CI and root-
delegated integration remain mandatory; partial integration is not full-package
acceptance. Ready SQL candidate review keeps priority and pauses this lane.

## Execution dispatch: early pure-output implementation

Root dispatched the independent pure/logging slice after another reviewer
approved the sequencing amendment (SHA256
`bdaae6750c4a4d0e611e2054770bc7566c5e0dce95196cb5ca97c3a6801a4bcb`)
and unchanged ADR `466f8abf7814fb38f7df99c94880785a6032fd481932d03a5b3b630acca92617`.
Implementation owner is phase1_architecture_plan; independent implementation QA
is phase1_plan_review. Base remains actual integrated 1b7cd58. Source is confined
to the preceding early-slice file scope; every deferred consumer gate remains
pending. SQL review takes priority, without editing its author's worktree.
Normal focused commits, push and a draft PR are authorized; integration requires
independent exact-candidate review and CI. No live/provider authority is added.

### First source slice: models, catalog and explicit serializers

The first source candidate implements the closed model families, local-only
doctor/AuthRoleFact values, exact fixed 32-code catalog, separate private renderer
and field-by-field public serialization. It supplies no producer or DB adapter.
Actual checks on task-local CPython 3.12.13: 70 focused status tests and 449 full
offline tests passed; lint, format, whitespace and repository safety passed.
The original 379-test baseline remains present. These checks cover pure model
portions only; full sink/subprocess privacy, logging containment and the final
package export inventory are still being implemented separately. This is an early
reviewable source slice, not full M105 acceptance or an Issue14 closure.

### Early pure/logging unit evidence

The model/catalog/serialization slice received independent approval at
608022a236c03c10c330ff6ab9fb7d5f223310e8. The subsequent logging slice adds the
exact 22 package exports, explicit production bootstrap, typed stderr events,
sealed warning/exception hooks and subprocess regressions. Import has no policy
side effect. Setup retires stdlib's shutdown handler registry after discarding
pending buffers/targets; merely detaching handlers was insufficient. Unsupported
custom handlers/factories or changed policy refuse without invoking close/format
hooks. Runtime thread admission/notification and actual transport checks still
need their consumer integration; this is not a general Python sandbox.

| Gate | Actual early evidence and remaining boundary |
| --- | --- |
| ST-01 | Fixed golden field inventory, exact 22 exports, all-family/type/null/count/version guards; no generic model dumping |
| ST-02 | 32 actual error-code entries, fixed exits/retry classification, hostile object and unknown-code fallback |
| ST-03 | Pending actual accepted-and-integrated M102 aggregate adapter; no duplicate-count query claim |
| ST-04/05/06 | Pure exclusive nine-category values, absent-source/null/discovery and unit/sample-count guards; actual counts/metrics producers pending |
| ST-07 | Fresh/stale/unavailable and healthy prerequisites; serialization preserves timestamps; runtime/cache policy pending |
| ST-08/09/10 | Pure wrong-field/private-value rejection and synthetic content/credential/metadata/output sentinels across JSON/error/stdout/stderr/file sinks, detecting negative controls |
| ST-11/12 | Real subprocess MemoryHandler normal exit, explicit shutdown, setup refusal/custom close, policy change, all sensitive logger prefixes/DEBUG, warning/main/thread/unraisable/async hooks, fixed sink failure; actual entrypoints/transport/callback consumers pending |
| ST-13 | Pending actual accepted DB/audit/adapter/WAL evidence; output tests do not inspect or certify a fake DB |
| ST-14 | Separate local doctor private opt-in positive and default/public negative controls; no public inheritance |
| ST-15 | Pure serializers and separately installed child-process network guard, including an actual denied-connect control; not an OS sandbox |
| ST-16 | Pending actual AUTH/owner integration. Synthetic PTY proves logging leaves an explicit terminal channel intact, not OAuth/Compose/TTY consumer acceptance |
| ST-17 | Task-local Python 3.12.13/SQLite 3.53.1: 95 focused and 474 full offline tests passed; Ruff check/format (81 files), both CLI help probes, safety and whitespace passed. Built wheel imported under isolated interpreter with exact status modules/exports and no runtime artifacts. New candidate independent review and 3.12/3.13 CI still required |

No DB, owner, Auth adapter, shared CLI, cache producer, HTTP, dependency, CI or
container file changed. No real account/credential/mail data was accessed. The
first 274-line plan prefix and closed ADR remain unchanged. Issue14, complete
M105, ST-03/13/16, OA-16/17, G1 and future runtime/HTTP/container gates remain open.
