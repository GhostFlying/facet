# ADR proposal: closed public output, errors and production logging

Date: 2026-10-02. Package M1-05. Revision r1, proposed `m1-output-v1`.
Status: independent design review required; not source or HTTP implementation.
Owner: delegated phase1_architecture_plan. This author cannot approve this ADR.
Actual owned base: `1b7cd58b4846aab86edcbb781a999abb968d047c`.

This extends the four record families in [core v1](core-state-contracts.md),
the [Dashboard](../../dashboard-spec.md) and [CLI](../../cli-spec.md) contracts.
It implements the independently approved [M1-05 plan](../m1-05-status-privacy.md),
original 274-line SHA256
`e88eadeec0773388f9bb4a6932343afc53d876c84f5d5dddc6deeb75bd55de02`.
Root reassigned its docs-only ownership from phase1_plan_author; the historical
plan prefix remains unchanged. SQL candidate QA takes priority over this lane.

Accepted design inputs, not claims of integrated implementation:

- M1-02 storage r3 SHA256
  `da2cfcd0081eaca8b102436186c9f5d034947fbf71ca2f0b95a14ee25840cfa0`;
  actual SQL code/DB-01..28 are in progress. Only its finite query contract may
  be consumed, never copied into a fake storage business engine.
- M1-04 credential r2 SHA256
  `bc1c6b993f27d2575d5759282fbbeb7fd67f125639e578ee31a63ee94ffba999`;
  independently approved design, not actual credential/CLI implementation.
- M1-03 owner/view/command registry is a separate reviewed extension. This ADR
  does not define an IPC envelope, authorize a connection or fake live readiness.

The owned writable files are this ADR and the plan execution appendix only.
No source, tests, HTTP, SQL, dependency, runtime/environment, credential, Git
publication or external data operation is part of this dispatch.

## Executable inventory and scalar rules

Implementation lives only in the plan's `src/facet/status/` files after dispatch.
No additions to `facet.contracts`. Import its actual Count, Timestamp, Role,
SourceMode, BindingState, JobState, EpochKind, EpochState, ErrorCode, ErrorClass,
Freshness, PublicPhase and PublicHealth. No duplicate business enum definitions.
All records below are frozen, slots dataclasses with exact field types, no extra
keys, no subclass acceptance and safe repr. Every nullable field is REQUIRED;
there is no implicit healthy/zero/default. Record fields are JSON keys verbatim.

Status-local scalars/enums are finite:

PublicCount, Seconds and BuildVersion are validated aliases of built-in int/int/
str, not new core wrappers. Conversions explicitly unwrap only exact registered
core values; field validation still requires exact built-in types as below.

| Name | Exact values or validation |
| --- | --- |
| PublicCount | Exact non-bool integer 0..9007199254740991; checked conversion from core Count, never float/rounded/saturated |
| Seconds | Same integer bounds as PublicCount; operational duration, never timestamp or mail Date |
| PermissionMode | `source_readonly`, `source_convenience`, `target_insert_readonly`, `target_insert_readonly_labels`; display facts, not scope authority |
| CheckState | `ok`, `failed`, `unknown`, `unavailable`; unknown means no evidence, unavailable means attempted check could not complete |
| Pressure | `normal`, `elevated`, `critical`, `unknown`; thresholds/measurements belong to runtime/M4, not inferred here |
| Component | `runtime`, `source`, `target`, `database`, `storage`, `memory`, `configuration` |
| LogEventKind | `lifecycle`, `dependency_state`, `work_summary`, `boundary_failure` |
| SafeLogLevel | `debug`, `info`, `warning`, `error`; all obey the same schema |
| Suggestion | Exact codes in the suggestion table below |
| BuildVersion | Exact trusted package build constant, ASCII `[0-9]+\.[0-9]+\.[0-9]+` optionally `aN`, `bN` or `rcN`, max 64 bytes; no local version, hash, path or hostname |

PublicCount's JSON-safe bound prevents browser rounding of large exact counts.
Overflow is consistency_failure, never a fabricated lesser count. Core storage
retains its wider integer contract. Times are actual Timestamp values persisted
as UTC instants and encoded with the sync server's local offset (six fractional
digits) at public and structured-log boundaries; no arbitrary string timestamps.
Non-finite/coerced metric values, bool-as-number and unsupported enum values
refuse before output. Counts can be null only where listed as unavailable.

`facet.status.__all__` exports exactly: PublicEnvelope, Status, Progress, Issues,
Diagnostics, RoleStatus, EpochSummary, QueueCounts, RateMetric, LatencyMetric,
IssueGroup, PermissionMode, CheckState, Pressure, Component, Suggestion,
serialize_public, public_json, catalog_entry, present_error, emit_safe,
configure_production_logging. No private input/model/log context reexports.
The named scalar validators, local presentation/error/log records and enums not
listed there remain explicit submodule imports for owned consumers/tests.

## Four public record families

`PublicEnvelope(data: Status|Progress|Issues|Diagnostics, schema_version:
Literal[1], sampled_at: Timestamp, freshness: Freshness, age_seconds: Seconds|None,
scope: Literal['projection'])`. The endpoint/CLI consumer knows the record family;
there is no arbitrary discriminator or projection selector in the wire format.
The exact data class selects one of four serializers. No `data=None`, dictionary,
row, exception, private diagnostic, extra extension bag or mutation receipt.

| Record | Exact fields |
| --- | --- |
| RoleStatus | role:Role, mode:PermissionMode\|None, auth_state:BindingState\|None, last_verified_at:Timestamp\|None, freshness:Freshness |
| Status | phase:PublicPhase\|None, health:PublicHealth, source:RoleStatus, target:RoleStatus, last_poll_at:Timestamp\|None, last_verified_insert_at:Timestamp\|None, heartbeat_at:Timestamp\|None |
| EpochSummary | kind:EpochKind, state:EpochState, started_at:Timestamp |
| QueueCounts | queued:PublicCount\|None, claimed:PublicCount\|None, retry_wait:PublicCount\|None, blocked:PublicCount\|None, needs_attention:PublicCount\|None, completed:PublicCount\|None, cancelled:PublicCount\|None, source_missing:PublicCount\|None, failed:PublicCount\|None |
| RateMetric | value:float\|None, unit:Literal['messages_per_second'], window_seconds:Seconds, sample_count:PublicCount |
| LatencyMetric | p50:float\|None, p95:float\|None, unit:Literal['milliseconds'], window_seconds:Seconds, sample_count:PublicCount |
| Progress | epoch:EpochSummary\|None, discovery_complete:bool, scanned_threads:PublicCount\|None, discovered_threads:PublicCount\|None, completed_threads:PublicCount\|None, known_message_total:PublicCount\|None, confirmed_messages:PublicCount\|None, jobs:QueueCounts, oldest_runnable_job_age_seconds:Seconds\|None, verified_last_hour:PublicCount\|None, verified_last_day:PublicCount\|None, rate:RateMetric, latency:LatencyMetric |
| IssueGroup | code:ErrorCode, error_class:ErrorClass, role:Role\|None, count:PublicCount, first_at:Timestamp, last_at:Timestamp, retryable:bool, next_retry_at:Timestamp\|None, suggestion:Suggestion |
| Issues | groups:tuple[IssueGroup,...] |
| Diagnostics | app_version:BuildVersion, schema_version:PublicCount\|None, sync_owner_count:PublicCount\|None, db_readable:CheckState, db_writable:CheckState, source_mode:SourceMode\|None, source_scope_ready:CheckState, target_scope_ready:CheckState, memory_pressure:Pressure, disk_pressure:Pressure, heartbeat_at:Timestamp\|None, checked_at:Timestamp\|None |

These fields instantiate the existing allowed families; no account, epoch ID,
custom label/rule text, receipt or mail selector is added. Operational epoch
kind/state/start describes the selected scope as permitted by core v1. Extra
reconcile/audit/rule/action summary variants require their owning reviewed M4/M5
extension within the canonical Dashboard contract; they are not invented here,
nor removed from the final Dashboard gate.

Null count means unavailable, not zero. QueueCounts is either all nine exact
counts or all nine null; partial queries cannot silently drop a category. Zero
is valid only for an actually observed empty set. All tuple/list items are exact
declared classes; no generator/property can perform a read during serialization.

RoleStatus source/target positions must match their role; source accepts only
source modes and target only target modes. Null mode/auth means unknown, never
the configured default. A stale historical VERIFIED may be retained as history
only with stale freshness; it cannot establish present healthy. A failed current
dependency may keep the last verification time but cannot claim fresh VERIFIED.
None phase means no reliable phase fact; it is not uninitialized. Uninitialized
requires actual no-state evidence from the proper read provider.

The M104 scope-policy-to-display mapping is closed: source_readonly maps to
source_readonly, source_convenience to source_convenience, target_default to
target_insert_readonly, target_labels to target_insert_readonly_labels. Read the
accepted policy enum through M104's adapter, never interpret arbitrary scope URI
strings here. Config alone can establish configured mode, not auth/scope readiness.

Discovery incomplete requires known_message_total=None. Missing current epoch
has epoch=None, discovery_complete=false and no scoped thread/known-total counts.
completed_threads <= discovered_threads where both are known; scanned is not a
denominator and may include rejected candidates. Total and confirmed messages
share one selected scope; no comparison mixes global mappings with an epoch.
Outside an epoch confirmed_messages and jobs describe the projection, while the
explicit epoch field is null. Thread counts stay null without actual producers.
No percent/ETA field exists. Terminal issues never become all-success by omitting
their jobs; existing epoch state preserves completed_with_issues.

Window_seconds is 1..86400; finite rate/latency values are nonnegative. Zero samples
requires null metric values; positive samples require both corresponding values,
with p50<=p95. An unavailable metric uses null values and sample_count=0, retaining
its intended window, not fake zero latency/rate. M4 owns timestamp/sample capture,
scope, estimator and rate definitions in a separate reviewed metrics extension;
this model accepts no histogram/raw sample stream and implements no estimator.
Hourly/daily successes count unique sources first verified in the rolling window;
repair history/retry cannot re-count one source. A data source unable to establish
that definition supplies null, not current attempt or target mailbox totals.

Issues has at most 96 groups: one per 32 ErrorCode values times role=None/source/
target, ordered by code.value then role order None/source/target. Counts >=1;
first_at<=last_at; no duplicate group. Error class and suggestion equal the catalog.
Role-specific auth/rate codes require the corresponding role. Retryable may be
true only when the catalog allows automatic dependency recovery AND the real work
policy has allowed retry; next_retry_at exists only in that case and comes from
the queue, not a guessed timer. Empty fresh groups means the selected aggregation
observed none; empty unavailable groups means nothing was established.

Diagnostics is factual: owner count zero is stopped, >1 is an error, unknown is
null. Reading a DB successfully does not imply writable: read-only doctor cannot
probe write by creating a row/sidecar. Scope readiness requires accepted credential
evidence/current owner readiness, not mode/config or has_scopes. No collector
threshold or filesystem path enters Pressure. App version comes solely from the
build constant; unsupported build syntax causes controlled unavailable output,
not a pass-through arbitrary version string.

## Freshness, sources and absent adapters

Sampled_at is the original completed aggregation attempt time, not serialization
or page refresh time. Freshness is supplied by the real cache/runtime policy;
M1-05 does not invent a stale threshold/SLA. A pure helper may calculate elapsed
whole seconds by exact UTC subtraction at an explicitly supplied observation time,
never call a clock, I/O or provider. Negative elapsed time produces unavailable
with age_seconds=None; never clamp into fresh zero. Stale keeps the original
sample time and historical data. Serializer may reject contradictory input but
cannot refresh/fix its timestamps. An unavailable envelope has age=None and no
healthy claim; previously measured facts may remain visibly unavailable history.
Fresh/stale envelope requires non-null age. A healthy Status requires fresh
envelope, both fresh VERIFIED roles and non-null operational phase; this is a
necessary condition, not an inference that all other components are healthy.

| Field source | Accepted boundary / missing evidence behavior |
| --- | --- |
| confirmed_messages and exclusive jobs | M102 actual `counts(view, projection_id, epoch_id)` result, explicit field reads and enum-exhaustive conversion; no private row serialization |
| discovery_complete/known_message_total | Same selected M102 count scope; incomplete/absent source gives false/null, not Gmail estimates |
| EpochSummary | Actual accepted `get_epoch` values kind/state/created_at; consume private ID only to select, do not export it |
| thread totals, age, hourly/day counters, rates/latencies | M3/M4 reviewed aggregate query/metrics extension; M102 v1 does not promise these fields; no worker writes speculative SQL to fill them |
| role modes/auth facts/scopes | Accepted M104 role-fact handoff below, accepted binding/config source; no envelope/token, library Credentials or profile response enters output layer |
| poll/insert/heartbeat/phase/health/pressure | M103/M2/M4 runtime observations and reviewed aggregation policy; no inference from file existence, old last_error or process ID |
| issue groups | Actual bounded M102 error rows plus owning M4 grouping query; this ADR does not add list_errors or a parallel table; until that extension, no fake complete group aggregation |
| schema/DB read state | Actual M102 inspect result under M103 read view; no_create is the opener's verified property, not inferred from query_only |

Models can be tested with explicit synthetic values now; they are not persistent
snapshots. ST-03/13 require actual accepted SQL implementation. M105 owns no DB
connection, SQL text, cache store or network callback. A downstream adapter must
be written in its assigned integration scope against exact reviewed types; missing
fields remain unavailable or the consumer explicitly refuses. No guessed Snapshot,
provider protocol or shadow CountsSnapshot is an implementation dependency.

## Strict serialization and separate local presentation

`serialize_public(envelope: PublicEnvelope) -> dict[str, JSONPrimitive]` and
`public_json(envelope: PublicEnvelope) -> str` explicitly enumerate every key and
enum mapping. JSONPrimitive here is built-in null/bool/int/finite-float/string plus
lists/dictionaries created solely by those four fixed serializers, not an accepted
input type. public_json uses UTF-8-safe ensure_ascii JSON, allow_nan=false and
deterministic sorted keys, no custom default handler. Maximum encoded size is
262144 bytes; failure emits no partial data and raises sealed OutputBoundaryError
with fixed consistency_failure. Errors never include offending object/value/type.
OutputBoundaryError has only code:Literal[ErrorCode.CONSISTENCY_FAILURE]; its
str/repr/args are fixed and it stores no rejected object or original exception.
Build the whole result before the caller writes one document; output is not a
streaming best-effort scrubber. Exact supported types are checked before reading
fields; never vars/asdict/__dict__/getattr fallback, repr, str(exception), property
traversal, generic encoder or inheritance cast from private records.

Default/private CLI still uses its existing schema-1 command envelope. M1-03/06
owns registration and command-result validation; M105 does not wrap arbitrary
command data as public. `--public` status/doctor consumer uses the relevant public
family, without CLI receipts. Text public rendering, if selected, is generated
from the same validated keys/catalog rather than a separate permissive formatter.

Owned local-only models in serialization.py are distinct classes, never PublicData:

- `PrivateDoctorDetail(kind:Literal['binding','state_root'], role:Role|None,
  binding_address:str|None, state_root:str|None)`: binding branch requires role
  and canonical normalized config address, null path; path branch requires null
  role/address and the verified local state-root path (max4096 UTF-8 bytes, no
  NUL/control/surrogates). These are necessary private config facts, not mail From
  copies. Only actual owner/config integration supplies them. No free detail text.
- `LocalDoctorFinding(component:Component, role:Role|None, code:ErrorCode|None,
  state:CheckState, checked_at:Timestamp|None, detail:PrivateDoctorDetail|None)`.
  An exact local renderer accepts `private_metadata:bool`; false omits detail
  entirely. Public construction selects component-state/count/time facts afresh;
  passing this class to a public serializer always fails even when detail=None.
  Mail/object selectors for other commands remain their own reviewed CLI schemas.
- `AuthRoleFact(role:Role, mode:PermissionMode|None, binding_state:BindingState|None,
  scope_ready:CheckState, verified_at:Timestamp|None, expires_at:Timestamp|None,
  freshness:Freshness, error:ErrorCode|None)`: closed M104→M105 handoff, no secrets,
  account, grant URI, revision, credential change, file path or operation ID.
  M104 constructs from accepted state, not arbitrary response dictionaries.
  Public RoleStatus excludes expiry/error and uses catalog issue aggregation;
  Diagnostics selects scope_ready. Local auth-status may show expiry separately
  without calling it current health. No time/profile check runs in a projection.

The M104 author and M103 logging/CLI owner must align these exact value imports
before source consumers. A foreign class with matching names is not accepted.
ST-14 separately injects legitimate private addresses/paths and rejects every
private model at public boundary. Subprocesses prove no private value appears in
default text, public JSON or failure diagnostics.

The local-only function `render_local_doctor(finding:LocalDoctorFinding, *,
private_metadata:bool) -> dict` constructs only component/role/code/state/checked_at
plus detail when explicitly enabled; detail is then the exact selected branch
above. It does not return a CLI envelope or support public=True. Its dict is a
closed output, never accepted as input to public serializers. The pure internal
`role_status_from_fact(fact:AuthRoleFact) -> RoleStatus` performs only the explicit
field selection above; role-specific errors must match role, and unavailable
facts cannot produce fresh VERIFIED. Other integration entrypoints stay with
their owner rather than importing a speculative callback/DB/provider protocol.

## Complete controlled error catalogue

errors.py owns immutable `CatalogEntry(code:ErrorCode,error_class:ErrorClass,
message:str,suggestion:Suggestion,failure_exit:Literal[2,3,4,5,6,7],
automatic_dependency_retry:bool)` values. Strings are the exact literals below,
never constructor/user/provider input. `catalog_entry(code:ErrorCode)` accepts
the exact enum only. `present_error(code:ErrorCode) -> ErrorPresentation` returns
code/class/fixed message/suggestion/fixed suggestion_text/failure_exit, no args.
Unknown object/enum/type becomes the consistency_failure entry without invoking
its str/repr/attributes. Catalog coverage asserts exact equality with all 32
actual ErrorCode members; adding/removing a member fails tests until reviewed.
ErrorPresentation fields are exactly code:ErrorCode, error_class:ErrorClass,
message:str, suggestion:Suggestion, suggestion_text:str and
failure_exit:Literal[2,3,4,5,6,7]. Its constructor is private to the catalog;
message strings must be identical to its fixed entry, not arbitrary caller text.

| Suggestion code | Exact fixed suggestion text |
| --- | --- |
| correct_input | Correct the local input and run validation. |
| inspect_request | Inspect the existing request before submitting work. |
| repeat_same_request | Resubmit only the confirmed unaccepted request with its original key and payload. |
| confirm_scope | Review the selected scope and provide the required confirmation. |
| verify_binding | Verify the configured account roles without changing the binding. |
| refresh_preview | Create a fresh scoped preview before continuing. |
| inspect_owner | Inspect the owner state; do not start a second writer. |
| wait_receipt | Look up the retained request receipt before taking further action. |
| authorize_source | Reauthorize Source on the deployment host. |
| authorize_target | Reauthorize Target on the deployment host. |
| wait_dependency | Retain queued work and wait for the dependency to recover. |
| inspect_target_storage | Inspect Target storage without deleting mailbox data. |
| inspect_recovery | Inspect recovery evidence; do not blindly repeat an insert. |
| inspect_work | Inspect the selected work through the scoped local CLI. |
| inspect_maintenance | Stop affected writes and use offline maintenance; do not initialize an empty database. |

| ErrorCode | Class | Failure exit | Auto dependency retry | Suggestion | Exact message |
| --- | --- | --- | --- | --- | --- |
| invalid_input | input | 2 | false | correct_input | Input is invalid. |
| unsupported_version | input | 2 | false | correct_input | This version is not supported. |
| request_conflict | guard | 3 | false | inspect_request | The request key conflicts with existing work. |
| request_not_received | ownership | 4 | false | repeat_same_request | The owner confirmed that the request was not accepted. |
| request_outcome_unknown | attention | 6 | false | inspect_request | The request outcome is unknown. |
| request_lineage_mismatch | guard | 3 | false | inspect_request | The request belongs to a different restored lineage. |
| confirmation_required | guard | 3 | false | confirm_scope | Explicit confirmation is required. |
| scope_required | guard | 3 | false | confirm_scope | The required approved scope is unavailable. |
| binding_mismatch | guard | 3 | false | verify_binding | Account binding verification failed. |
| binding_pending | guard | 3 | false | verify_binding | Account binding verification is pending. |
| preview_invalid | guard | 3 | false | refresh_preview | The selected preview is no longer valid. |
| generation_stale | guard | 3 | false | refresh_preview | The selected work generation is stale. |
| owner_unavailable | ownership | 4 | false | inspect_owner | The required owner is unavailable. |
| owner_busy | ownership | 4 | false | inspect_owner | The owner is busy. |
| maintenance_incomplete | ownership | 4 | false | inspect_maintenance | Maintenance has not completed. |
| wait_timeout | ownership | 4 | false | wait_receipt | The bounded wait ended before completion. |
| source_auth_required | dependency | 5 | false | authorize_source | Source authorization is required. |
| target_auth_required | dependency | 5 | false | authorize_target | Target authorization is required. |
| source_rate_limited | dependency | 5 | true | wait_dependency | Source rate limiting is active. |
| target_rate_limited | dependency | 5 | true | wait_dependency | Target rate limiting is active. |
| network_unavailable | dependency | 5 | true | wait_dependency | A network dependency is unavailable. |
| target_storage_full | dependency | 5 | false | inspect_target_storage | Target storage is full. |
| insert_result_unknown | attention | 6 | false | inspect_recovery | The insert outcome is unknown. |
| duplicate_candidates | attention | 6 | false | inspect_recovery | More than one recovery candidate exists. |
| attribution_unknown | attention | 6 | false | inspect_recovery | Recovery attribution is unverified. |
| fidelity_mismatch | attention | 6 | false | inspect_recovery | Message fidelity verification failed. |
| source_missing | attention | 6 | false | inspect_work | Required source data is missing. |
| target_missing | attention | 6 | false | inspect_work | A managed target message is missing. |
| database_unavailable | persistence | 7 | false | inspect_maintenance | The local database is unavailable. |
| persistence_failure | persistence | 7 | false | inspect_maintenance | Durable persistence failed. |
| consistency_failure | persistence | 7 | false | inspect_maintenance | A consistency check failed. |
| maintenance_required | ownership | 4 | false | inspect_maintenance | A supported maintenance step is required. |

These are failure exits, not the exit of a successful read displaying issues.
Successful status output is exit0; successful durable acceptance is exit0 but not
remote completion; wait timeout is exit4 with retained receipt. Doctor failed
checks use deterministic severity precedence 7,6,5,4,3,2, then0, not iteration order.
Retryable classification never authorizes Gmail retry or bypasses unknown intent,
generation, ownership or scope. Actual M104/M2 adapters normalize exceptions via
their reviewed allowlisted response facts and pass only ErrorCode; this module
does not inspect arbitrary exceptions or HTTP payloads to guess a provider code.
M1-01's limited catalog is replaced through its CLI owner's integration, not a
concurrent edit or silent divergence from schema-1/exit behavior.

## Closed safe logging and process containment

logging.py defines exact internal value `SafeLogEvent(kind:LogEventKind,
level:SafeLogLevel, at:Timestamp, component:Component, role:Role|None,
code:ErrorCode|None, count:PublicCount|None)`. boundary_failure requires code and
count=None; work_summary requires count and code=None; dependency_state requires
code and count=None; lifecycle requires code/count=None. Source/target components
require matching role; other components require role=None. No message, extra,
logger name, input, path, exception, request or private selector field.

`emit_safe(event:SafeLogEvent) -> None` validates exact fields, then writes one
bounded JSON line (max4096 bytes) to the production-bound stderr sink, with only
the named fields and catalog-derived error_class when code exists. No raw stdlib
LogRecord is accepted. A process-local mutex protects line atomicity across app
threads. No logging file/path option exists here; deployment captures stderr.
Tests may supply a private in-memory/file sink through a test-only factory, never
runtime configuration. Serialization failure emits only the fixed literal
`facet: consistency_failure`; sink OSError is swallowed without recursive logging
and signals controlled runtime logging-unavailable through a fixed owner callback
when integrated. It never prints handler failures, repr or traceback.

`configure_production_logging() -> None` is an explicit one-time pre-network
production startup action, never an import side effect. It does not configure
facet-spike. M103 calls it before importing credential/transport modules and before
starting threads; M105 exports primitives, not a new CLI entrypoint. Repeated calls
validate the installed policy, not reset foreign changes behind a running worker.

Policy is deliberately not a regex redactor or root-logger filter:

1. Before third-party imports, disable ordinary stdlib logging through its public
   global disable threshold for every standard level, set raiseExceptions=false,
   remove existing root/named logger handlers and install a drop-only NullHandler
   on root; lastResort is also drop-only. No handler is flushed/formatted with a
   pending untrusted record. SafeLogEvent output uses its independent writer, not
   the disabled stdlib logger. Existing nonstandard custom Logger/Handler/factory
   or external logging configuration is unsupported and refuses startup before
   secrets/network; it is not trusted merely because its name begins with facet.
2. Inventory loaded/new loggers after imports and before network admission. Fixed
   sensitive prefixes: google_auth_oauthlib, oauthlib, requests_oauthlib, google.auth,
   google.oauth2, googleapiclient, requests, urllib3, httplib2, asyncio and py.warnings.
   Remove alternate handlers and install drop-only sinks without calling
   getMessage/str/repr/formatException; global disabling covers ordinary future
   loggers too. No library raw record is re-emitted even when DEBUG is requested.
   No runtime logger reconfiguration is supported. A changed handler/disable/
   factory invariant detected at operation admission refuses new I/O; it never
   attempts best-effort formatting first. This is supported-process containment,
   not a sandbox against arbitrary code able to write fd2 itself.
3. Install sealed warnings.showwarning, sys.excepthook, threading.excepthook and
   sys.unraisablehook at production bootstrap. They discard message/exception/
   traceback/object/context without formatting and emit only a fixed boundary
   failure. Do not use logging.captureWarnings, default exception printers or
   traceback formatting. An uncaught main error exits7; background failures notify
   M103's fixed shutdown/degraded callback without carrying the exception. M103
   registers the same sealed asyncio exception handler before task admission;
   its context dictionary is never serialized. Process signal/power failure is
   not claimed recoverable by these Python hooks.
4. Direct stdout/stderr paths require owner-specific prevention, not stream
   monkeypatching. HTTPConnection.debuglevel and httplib2.debuglevel must be zero;
   each actual transport is checked with wire debug disabled. Reject unsupported
   interpreter/HTTP debug configuration before secret operations; do not change
   TLS/proxy/OAuth validation to suppress errors. M104 uses its reviewed thin
   loopback adapter, no run_local_server printer, default callback access logger
   or server handle_error traceback. Only its explicit controlling terminal URL
  path is permitted. Runtime forbids diagnostic stack dumping/SQL trace and raw
   crash reports; normal Python exception hooks are covered, native crash output
  remains a separate container/runtime hardening check, never claimed sanitized.

The logging bootstrap does not close or intercept the controlling terminal or
redirect stdout/stderr, and does not prohibit M104's explicitly selected one-time
TTY URL output. A positive PTY control must observe that URL only on that terminal
while simultaneous captured stdout JSON, stderr and log sinks remain clean; absent
TTY still refuses. That is an AUTH consumer test, not permission for another module
to print OAuth material or for diagnostics to expose the terminal transcript.

No general arbitrary application `print(exception)` is supported. CLI parse/output
owners retain their fixed-code outer catch before any result is written. Normal
JSON commands write exactly one stdout document; logs remain stderr. An uncaught
failure before result write uses the same fixed boundary result through the CLI
owner, not a second partial JSON document. This needs actual entrypoint integration;
unit serializer tests alone cannot prove it. No public logs/download endpoint.

## Acceptance slices, dependencies and stop gates

This removes the ST-16/AUTH sequencing cycle without declaring it passed early:

1. After this exact ADR review and root dispatch, M105 pure models/catalog/
   serializers and explicit safe logging bootstrap can be implemented and
   independently reviewed as an early engineering slice. M103 integrates the
   real process bootstrap before AUTH consumers; its subprocess tests prove
   containment without needing a working credential manager. No fake OAuth
   implementation or duplicated business model is needed to test the sink.
2. Actual accepted M102 code enables ST-03/13 adapter/storage evidence. A missing
   aggregate query stays missing until its owner extension; M105 cannot fake SQL
   or mark an entire downstream aggregation gate passed from model fixtures.
3. AUTH implementation consumes integrated M105 logging/value imports and actual
   M103 startup lifecycle. Its real callback/refresh/error paths then execute
   OA-16/17 and M105 ST-16 together. Until those actual consumers pass, M105 final
   integration remains pending; early slice does not close Issue14/G1.
4. M4 actual cache/HTTP/browser and M6 container outputs repeat privacy gates.
   This ADR defines no endpoint, serializer side-effect, persistent snapshot,
   stale threshold, resource threshold, network client or new schema table.

Carry all ST-01..17 from the approved plan. Required focused counterexamples:

- Exact exports/types/keys and all required nullable fields; subtype/dict/custom
  property/exception with trapping str/repr never runs; unknown version/enum and
  oversized/overflow/nonfinite input refuses before any partial output.
- Actual duplicate mapping/repair/history observations do not inflate confirmed
  success; all nine JobState counts are exclusive or explicitly all unknown.
  Missing metric source never becomes zero, estimate never becomes total.
- Stale historical VERIFIED/green state retains its sample but is not current
  healthy. Backward clock is unavailable, not zero-age fresh. Fresh output cannot
  be obtained by calling the serializer repeatedly.
- Public/local/log sinks independently inject synthetic private address/path/ID/
  subject/raw/token/code/auth-URL/error/SQL sentinels with detecting negative
  controls across JSON escaping. Private detail remains allowed only in its local
  opt-in path, never by a public class inheriting private fields.
- Real subprocesses configure initial and alternate library handlers, DEBUG,
  exc_info, warnings, main/thread/unraisable/async failures and direct HTTP debug
  toggles. No raw formatting or stderr leak; unsupported reconfiguration refuses
  before provider entry. Compare a deliberately uncontained subprocess negative
  control. Spike logger/import behavior remains unchanged in its separate process.
- ST-16 specifically uses actual accepted AUTH manager/callback/refresh paths,
  not a dataclass shaped like its future output. No credential envelope reaches
  M105; wrong RoleFact type/freshness fails. Record early and final slice separately.

Stop for unclosed source provenance, raw third-party print path, unsupported logger
reconfiguration, unavailable real owner/view, new DTO field, scope change or a
required non-owned edit. Return technical seams to root/owner; product/privacy
changes require the user. Source publication/CI/integration and later independent
implementation acceptance need their separate root dispatch. Nothing here proves
G1, live OAuth/Gmail, DB/WAL correctness, Dashboard, deployment or dogfood.

## Read-only references and limits

Python's [logging propagation and handlers](https://docs.python.org/3.12/library/logging.html),
[warning hooks](https://docs.python.org/3.12/library/warnings.html), and
[exception hooks](https://docs.python.org/3.12/library/sys.html#sys.excepthook)
were checked against the supported Python design. Parent logger filters alone
do not filter child records delivered to ancestor handlers. The locked library
source was also inspected read-only: google_auth_oauthlib.flow has URL printing/
logging in run_local_server, and httplib2 has direct print paths when debuglevel
is enabled. These observations explain prevention at the actual call/startup
boundaries; they are not evidence that this proposed policy has been implemented.

No real client JSON, token, mail, ignored spike state or live endpoint was read.
All fixtures/tests described here are prospective synthetic verification.
