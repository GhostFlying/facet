# Proposed test-only job materialization supplement r1

Status: design only, pending independent review and implementer plan alignment.
Owned authoring base: `1b7cd58b4846aab86edcbb781a999abb968d047c`. Consumer inspection
uses actual SQL foundation `eb7dde4ff33c349b3a5e7270c5ac480a292f425b` and the
committed finite read-case plan `e5ca928217b467c73f3fe88de3aa3a6621ce9aee`.
Moving helper files were read only to locate this interface gap, not approved.
DB21 r4 and the accepted isolated-reader safety/physical tests remain unchanged.

## Why a bounded exception is necessary

Actual get_job/list_jobs returns SyncJobRow whose resolve_event subject contains
an actual typed SourceEventKey, not its private SQL source_events.event_id. The
SQL encoder requires that durable event ID; SQL decoding also resolves actual
event and partition companions. Inventing an event ID, treating a key as its
foreign-key proof, or issuing arbitrary SQL merely to round-trip a test return
would weaken the original test boundary.

Allocate a TEST-ONLY same-value transport for exactly `row_job` and `page_jobs`.
The child still calls the actual production getter with its real ReadSession;
production SQL decoding/relationship validation finishes BEFORE transport.
Materialization serializes only the typed returned value, not a SQL row or an
instruction to write one. It never calls _encode_row/_decode_row for sync_jobs,
passes event_id, fetches another table or constructs a fake provider fact.
No production model, getter, schema, callback or general serializer is added.
All other 22 allocated getter families retain their existing registered SQL
codec/counts/schema handling. Existing child physical/guard cases are unchanged.

## Test-only file scope and functions

Allocate `tests/unit/db_view_job_values.py` with precisely private
`pack_job(row:SyncJobRow) -> list` and
`unpack_job(value:list, expected_projection:ProjectionId) -> SyncJobRow`.
This file is imported only by fixed test helpers AFTER the accepted child
bootstrap. It is not a wheel asset, public export, callable endpoint, product
RPC or configuration-selected codec. No reflection/asdict/class-name dispatch,
pickle, dynamic import, arbitrary field map or generic model argument.

Changes in `tests/unit/db_view_adapter.py` select pack_job only from the hardcoded
row_job/page_jobs case branches. `tests/unit/test_db_repositories.py`'s fixed
SnapshotProbe selects unpack_job from those same known cases; a response field
cannot choose another codec/table. Add focused tests under
`tests/unit/test_db_view_job_values.py`; preserve original repository assertions.
The implementer records this supplement in the owned bridge plan BEFORE coding.
No src/, shared conftest, core enums or production serialization edits are allowed.

## Exact positional grammar

One job is exactly the following 16-item JSON list, in order:

`[1, projection_id, job_id, kind, key_version, stable_key_hex, priority, state,
revision, created_at_us, updated_at_us, next_attempt_at_us_or_null,
attempt_count, last_error_code_or_null, origin_epoch_id_or_null, subject]`.

The leading exact integer 1 is this test transport version, not a schema/key
version. All fields are mandatory; optional means an explicit null only.
Reject wrong length, extra fields, unknown tag/version and wrong primitive type.
The subject is a fixed list chosen solely by its first literal tag:

| Tag | Exact remaining positional fields |
| --- | --- |
| project_message | source_message_id, source_thread_id, generation |
| repair_message | repair_operation_id, source_message_id, source_thread_id, generation |
| expand_thread | source_thread_id, epoch_id, generation |
| resolve_event | event_key |
| operation_read | operation_id, read_kind |
| recover_insert | attempt_id |
| scan_discovery | epoch_id, partition |
| scan_gap | epoch_id, partition |
| reconcile_source | epoch_id, partition |
| audit_target | epoch_id, partition |
| cleanup_action | action_command_id |

event_key is exactly one of:

- `["message_added", projection_id, history_record_id, source_message_id]`;
- `["message_deleted", projection_id, history_record_id, source_message_id]`;
- `["label_changed", projection_id, history_record_id, source_message_id,
  label_id, change]`, where change is the actual LabelChange added/removed enum.

partition is exactly `["source_window"]`, `["source_thread", source_thread_id]`,
`["target_catalog"]` or `["mapped_target_set"]`. There are NO event_id,
partition_key, partition_epoch_id, table-name, row-class or arbitrary companion
fields. These typed selectors remain values, not proof that any DB row exists.

## Scalar bounds, construction and equality

Both directions use a static branch for each exact concrete class/tag above.
Encoder accepts only actual SyncJobRow and its exact closed nested classes;
wrong/subclass/uninitialized objects refuse before custom repr/properties.
No generic object.value inspection. For each known primitive, check its exact
class and primitive content before using the fixed constructor/conversion.

ProjectionId is the actual 1..64 ASCII `[A-Za-z0-9_-]` grammar. LocalId is actual
32-lowercase-hex RFC4122 variant UUIDv4, not arbitrary hex. ProviderId is actual
nonempty <=512 UTF-8 bytes without Cc/Cs characters; History values remain strings,
not numeric counters. Numbers are exact JSON integers (never bool/float/string):
Count/Revision are 0..2^63-1, key_version is exactly 1, subject Generation is
1..2^63-1. Stable key is exact lowercase even hex representing 1..8192 bytes;
no permissive whitespace/case normalization. Last error is null or an exact
existing ErrorCode value; origin is null or actual LocalId.

Kind/Priority/JobState/ReadTaskKind/LabelChange are exactly their existing core
enum wire values. No enum aliases, new variant or reflective class lookup.
created/updated/deadline use the actual DB integer-microsecond conversions
timestamp_to_sql/timestamp_from_sql and their MIN_TIMESTAMP/MAX_TIMESTAMP bounds;
negative representable timestamps remain legal, no float or host timezone.
Decode int bounds BEFORE datetime construction. Child DB timestamps are actual
UTC datetime values; reject forged content rather than calling foreign tzinfo
hooks. Null deadline stays null, not zero or a synthesized retry time.

Reconstruct each nested value through its actual existing constructor, then
construct SyncJobRow with all fields. Preserve required tags and enforce its
kind==subject.tag, key_version and production job_key equality. Require row and
any event_key projection equal expected_projection. Positive generation and
actual subject/partition restrictions remain: discovery only source_window;
gap/reconcile source_window or source_thread; audit target_catalog or
mapped_target_set. No constructor is bypassed using object.__new__/setattr.

Do NOT invent additional job-state/deadline transitions, alter timestamps,
recompute a different key or retrieve claimed/attempt/epoch rows here. Relational
proof came from the child's actual getter/DB decoder. Parent reconstruction proves
same-value materialization ONLY; it cannot replace that production evidence.

## Envelopes and page handling

Keep the already reviewed outer test envelopes. row_job None is distinct from
a job value and from the actual child StorageFailure code. page_jobs retains
exact items list and next cursor/null; items use only the grammar above. It has
at most min(requested PageLimit,500) jobs, all in the requested projection, in
the getter's original `(created_at,job_id)` order. Never sort/truncate to make a
test pass. Decode the same bounded hex cursor and construct the actual
ReadPage(tuple(rows), next_key), preserving its family/projection checks. Keep
existing cursor rejection tests in the actual child, not at the facade.

Unchanged request bound is 32768 UTF-8 bytes; response bound is 2 MiB. An oversized
test result fails the harness, not a partial page, implicit smaller limit or fake
StorageFailure from the repository. Integer/string/list checks reject unexpected
JSON forms; no arbitrary dictionary nesting occurs in this job representation.
All values are synthetic metadata used by tests. Never capture real private
state into this response or add it to public serializers/artifacts.

Packing/unpacking errors are fixed test-harness failures, distinct from an actual
get_job/list_jobs StorageFailure. Do not mask a child exception as a parent
constructor failure or claim parent rejection tested the production API. Keep
fixed errors without SQL, paths, traceback contents or hostile object rendering.

## Paired acceptance (planned)

JM01: real stored resolve_event jobs for all three SourceEventKey variants and
both label changes; actual isolated getter→typed transport→parent equality.
Use durable event IDs deliberately different from every message/history/job ID;
no fake ID or additional lookup is passed to the SQL encoder/decoder.
JM02: all eleven actual subject constructors and four PartitionRef variants;
actual allowed combinations round-trip, unsupported tag/arity/partition/generation
or mismatched event projection refuse in the codec without issuing SQL.
JM03: every row field survives unchanged, including nullable error/deadline/origin,
nonzero revisions/attempt count, distinct creation/update times and stable keys.
Literal independent positional vectors detect dropped/reordered fields.
JM04: corrupted stable key, kind/tag mismatch, bool/float counts, overflow,
invalid timestamps/IDs/hex, extra/missing fields, subclass/hostile objects and
cross-family results refuse without repr/property side effects or private output.
JM05: actual list_jobs 500+1 case retains order, next cursor and expected typed
job equality; empty page/None/error envelopes remain distinct. Parent transport
success does not replace actual child read-lifetime/no-write/keyset tests.
JM06: other 22 families and fixed physical tests keep their prior codec and actual
assertions; full regression passes. Production wheel contains no test codec or
dispatch hook. No source/public API/SQL table changed to accommodate the harness.

This is a narrowly reviewed exception to the original test-family SQL-codec rule,
not a runtime protocol or permission to serialize other core records. Independent
design approval, exact implementer plan alignment and later source/test acceptance
are separate gates; genuine M103 producer/RV11 and full M1 readiness stay pending.
