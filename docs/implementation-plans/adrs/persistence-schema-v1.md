# ADR proposal: metadata persistence schema and repositories v1

Date: 2026-10-02. Package: M1-02. Proposal revision: storage-proposal-r3.
Status: proposed for independent design review; not frozen or implementation-ready.
No SQL/source/test implementation accompanies this file.

## Authority, inputs and owner

This is the storage extension commissioned by the independently approved
[M1-02 plan](../m1-02-persistence.md), original approved prefix SHA-256
`abc9f87b813cb510205deab5e350c04ab5fa4a24498cceb43f44349125979e4f`.
The delegated author is `phase1_plan_review`, not this ADR's independent reviewer.
The coordinator assigns another reviewer before a schema freeze or implementation.
Original design base is `09031e723af1ef6590dc6746744ee52894501e38`.
The owned branch normally fast-forwarded to actual integrated base
`1b7cd58b4846aab86edcbb781a999abb968d047c`, preserving both untracked documents.

Normative inputs are [p1-core-v1](core-state-contracts.md) and
[p1-writer-v1](writer-command-protocol.md). M1-01's complete corrected implementation
`b1e4ae08f7e361518eaa4f7fb1ae9f7f0b278f28` is independently accepted and actually
merged, with main CI 36980646059 passed. P1-02's CT candidate
`1b7cd58b4846aab86edcbb781a999abb968d047c` has independent acceptance and exact
CI 36981977390 passed, in addition to previously merged provider/helper c18.
PR #12 actually merged at that exact SHA on 2026-10-02 08:14:00 UTC and
post-merge main CI [36982879970](https://github.com/GhostFlying/facet/actions/runs/36982879970)
passed; Issue #5 closed after root verified the complete package gates.
These actual inputs satisfy the M1-01/P1-02 dependency requirement, not independent
review of this storage proposal or root dispatch of SQL implementation.

Task-local Python 3.12.13 / SQLite 3.53.1 is now available, with actual import and
memory SELECT checks supplied by the runtime owner and verified by the coordinator.
This resolves the missing-module preparation issue, not DB-01..28, real WAL,
process-crash, production mount or image acceptance. This author neither modifies
that runtime nor downloads another one.

## Design boundaries and notation

The proposed implementation uses stdlib sqlite3, one writer connection owned by
M1-03, no ORM and no generic payload columns. This document owns storage records
and codecs; it does not add public `facet.contracts` exports. All listed tables
are private metadata. Public serialization remains an independent allowlist.

Every family below is enabled as a structural storage library except explicitly
deferred registries and production integration paths. There are no placeholder
JSON or arbitrary text objects. Tables and method signatures are proposed schema
design, not installed DDL or a freeze.

Notation for the field matrices:

- Every field is required and NOT NULL unless suffixed `?`. Nullable fields have
  no guessed business default. SQL defaults are limited to deliberately specified
  singleton/check constants; creation methods pass all other values explicitly.
- `P` is ProjectionId as TEXT; `L` is LocalId as TEXT; `V` is ProviderId as TEXT;
  `T` is Timestamp as signed INTEGER microseconds from the Unix UTC epoch;
  `N` is Count as nonnegative signed-64-bit INTEGER; `G` and `R` retain distinct
  Generation and Revision codecs; `H` is Sha256Hex TEXT; `K` is PolicyVersion TEXT.
- `B` is INTEGER constrained to 0 or 1, rejecting Python bool coercion anywhere
  a Count/Generation/Revision is required. Named core enums use exact frozen text
  values. Storage-only enums require an explicit exhaustive inventory here.
- A SQL TEXT value always has a named semantic codec and bound. No `detail`,
  generic exception, body, header, raw, token, provider JSON or extensible notes
  column is permitted. IDs are not parsed as numbers. Key encoding uses UTF-8
  byte lengths rather than delimiter concatenation.
- Every entity belongs to one projection. A child stores `projection_id` and
  references a composite parent key `(projection_id, id)` even when IDs are
  randomly generated. The nullable suffix of a composite FK is all-null/all-present;
  the always-present projection_id is not itself made nullable.
- Codecs reject unregistered fields before SQL. STRICT tables, fixed CHECKs,
  bound parameters and FKs independently protect structural invariants. Repository
  queries enforce relational conditions that CHECK cannot express; tests bypass
  repositories to prove all constraints actually promised at SQL level.
- No field-source decision is delegated to a permissive dictionary serializer.
  Persistent records are immutable closed dataclasses; callers receive values,
  not a connection, cursor, arbitrary query builder or unbounded row iterator.

## Enabled versus deferred extension boundary

The enabled foundation must cover projection/binding metadata, immutable rules,
tracking, epochs/partitions, events/checkpoints, jobs/claims, attempts/mappings,
action activation and closed audit facts. Its structural storage does not perform
AUTH, domain normalization, Gmail I/O or recovered-attribution decisions.

The following complete registries are explicitly not invented by this ADR:

| Deferred registry | Owner / activation requirement |
| --- | --- |
| Command envelope/payload, operation receipt/result, preview payload and canonical digest | M1-03 reviewed registry extension and same-transaction integration |
| Actual credential scopes and credential envelope | M1-04 reviewed manager extension; declared config is not verification |
| Public aggregate DTOs and error presentation | M1-05/M4 reviewed allowlists; a private query row is not an HTTP response |
| Canonical fingerprint and recovered-attribution evidence | M2-02/M2-04 reviewed codecs and policy; only direct invocation facts before then |
| Metrics histogram persistence | Owning metrics extension supplies exact versioned buckets; no arbitrary histogram JSON |

References to a not-yet-enabled command/preview registry cannot authorize a
production insert into an admission/epoch/repair record. The storage library can
validate closed values and use explicitly synthetic test fixtures, but the future
production integration must add real same-projection reference checks before
enabling those paths. No UUID alone represents authority.

## Ownership and transaction integration (proposed)

M1-02 does not acquire flock, discover a state root, refresh credentials or expose
a standalone open/create API. M1-03 constructs the private owner/view sessions and
opens connections under its existing lock protocol. M1-02 validates connection
configuration and supplies short transaction methods over that lifecycle.

The exact session adapter signatures are specified below; their implementation
must not introduce a callable network plugin inside a SQL
transaction or pretend that an in-memory token proves an OS lock. Missing real
production provider remains owner_unavailable. Tests explicitly own newly created
temporary connections and cannot register their fixture provider in production.

One transaction boundary composes repository changes; repository helpers never
commit behind a caller's back. M1-03 will compose its own durable receipt and local
effect in the same unit of work. DB-07 in M1-02 proves typed transactional effect
replay for storage-owned identities, not first-response-loss/IPC/request-journal
behavior. Those latter claims remain mandatory M1-03 consumer tests. A fabricated
receipt table or fake CLI client is not used to break the dependency order.

Read sessions receive only an already locked, validated read-only view. DB-21
will cover an existing clean stopped DB, an active readable WAL view, and refusal
when SQLite would need to create sidecars or perform crash recovery. Read-only
inspection cannot create root/locks/DB/WAL/SHM, migrate or checkpoint. Never mark
a changing live DB immutable to bypass this requirement. Unknown/unsafe state
returns a controlled category without copying files or silently repairing them.

## Proposed storage codecs and closed auxiliary values

These are storage-local value types, not new core exports:

| Type | Representation / validation |
| --- | --- |
| SchemaVersion | INTEGER 1..2147483647; unknown newer version is unsupported, never downgraded |
| MigrationName | TEXT matching `v[0-9]{4}` exactly; source registry supplies checksum |
| PrivateAddress | TEXT 1..320 UTF-8 bytes, no control/NUL/surrogate; already normalized by its configuration/rule owner, not per-message address storage |
| RuleValue | TEXT 1..512 UTF-8 bytes, no control/NUL/surrogate; exact kind-specific normalization remains M1-06 |
| RfcMessageId | nullable TEXT 1..998 UTF-8 bytes, no controls/NUL/surrogate; evidence hint only, not unique and never parsed from headers by SQL |
| KeyBytes | BLOB 1..8192 bytes, versioned encoding of a closed identity tuple; never raw message bytes or an arbitrary digest input |
| EventProcessing | `pending`, `resolved`, `consumed`, `needs_attention`, `source_missing` |
| PollState | `reading`, `completed`, `abandoned` |
| PollOrigin | `checkpoint`, `initial_epoch`, `recovery_epoch`; selects a constrained durable start relation, never arbitrary cursor reset |
| ExpansionItemKind | `project_job`, `verified_mapping`; metadata work accounting, not a new admission decision |
| ThreadStopReason | `manual_stop`, `blacklist`, `queue_cancel` |
| ActionKind | `add_sender`, `add_domain`, `blacklist` |
| ActionState | `pending`, `executed`, `needs_attention` |
| CleanupState | `not_requested`, `queued`, `completed`, `blocked` |
| AttributionKind | `none`, `direct_response`; recovered variants require the M2-04 extension |
| AuditKind | `initialized`, `rule_changed`, `thread_admitted`, `thread_stopped`, `epoch_started`, `page_ingested`, `cursor_advanced`, `job_state_changed`, `attempt_state_changed`, `mapping_verified`, `binding_changed`, `restore_fenced`, `maintenance_completed` |
| AuditObjectKind | `projection`, `rule`, `thread`, `epoch`, `event`, `job`, `attempt`, `mapping` |

Count/code/ID CHECKs are structural, not a claim that strings meeting a syntax
cannot carry secrets. Input field provenance, closed repository records and
sentinel checks supply the semantic boundary. In particular arbitrary caller text
cannot be relabeled ProviderId or RuleValue to obtain a persistent notes field.

Timestamp codecs use exact integer arithmetic, not floating Unix timestamps.
Round trips preserve microseconds across dates before and after 1970. Values
outside Python's supported aware-UTC datetime range are refused on decode.
Generation and revision arithmetic checks signed-64-bit overflow before mutation.
An enum's unrecognized SQL value yields controlled consistency_failure, never the
raw value or an exception containing it. No serializer uses repr/asdict on an
unvalidated general object.

## Proposed table catalogue: foundation and policy

All entity tables below use STRICT mode. `PK(...)` and `UQ(...)` denote exact
ordered keys. FKs use RESTRICT on delete/update: there is no cascade that erases
audit or unknown work. Referential joins include projection_id. No table grants
permission to delete remote data. The field, scalar-check, branch-predicate,
reference and index manifests below define the proposed DDL; implementation must
expand them literally, without inventing an additional column or permissive codec.

| Table | Exact columns | Keys and additional constraints |
| --- | --- | --- |
| `schema_metadata` | singleton:N, schema_version:SchemaVersion, registry_digest:H, created_at:T | PK(singleton), singleton=1; registry digest matches trusted source manifest, not a caller-provided checksum |
| `schema_migrations` | version:SchemaVersion, name:MigrationName, checksum:H, applied_at:T | PK(version), UQ(name); immutable; exact contiguous trusted registry prefix, verified before normal opening |
| `projections` | projection_id:P, singleton:N, state_instance_id:L, request_namespace:L, config_revision:R, ruleset_revision:R, source_mode:SourceMode, binding_state:BindingState, restore_state:RestoreState, daemon_paused:B, last_owner_run_id:L?, created_at:T | PK(projection_id), UQ(singleton), singleton=1; UQ(state_instance_id), UQ(request_namespace); immutable projection identity; future restore explicitly rotates lineage rather than opening a second projection |
| `bindings` | projection_id:P, role:Role, declared_address:PrivateAddress, verified_address:PrivateAddress?, credential_revision:R, binding_revision:R, state:BindingState, verified_at:T? | PK(projection_id,role), FK projection; verified_address/time both null or both present; verified state requires both; source/target inequality enforced by repository transaction plus insert/update trigger; credential bytes/scopes absent |
| `rules` | projection_id:P, rule_id:L, kind:RuleKind, normalized_value:RuleValue, current_revision:R | PK(projection_id,rule_id), UQ(projection_id,kind,normalized_value); kind/value identity immutable; FK current revision to `rule_revisions` is deferred until commit |
| `rule_revisions` | projection_id:P, rule_id:L, revision:R, enabled:B, effective_at:T, origin:RuleOrigin, policy_version:K | PK(projection_id,rule_id,revision), FK rule; immutable rows, same effect replay does not replace effective_at |
| `rulesets` | projection_id:P, revision:R, created_at:T, sealed:B | PK(projection_id,revision), FK projection; immutable snapshot identity; sealed only changes 0→1 and never back; publishing requires sealed=1 |
| `ruleset_members` | projection_id:P, ruleset_revision:R, rule_id:L, rule_revision:R | PK(projection_id,ruleset_revision,rule_id), FK ruleset and exact rule revision; members immutable once publishing the projection's pointer |

The projection's current ruleset FK is deferred to commit so explicit initialization
can create its initial empty snapshot atomically. The rule/current-revision cycle
uses deferred FKs, not foreign_keys OFF or inconsistent committed placeholder rows.
Bindings have exactly two roles after initialization; all normal mutation methods
reject a missing role. Database inspection can still describe an interrupted or
damaged database without treating it as valid or silently inserting missing rows.

Ruleset member INSERT/UPDATE/DELETE triggers require the parent sealed=0. A
sealed ruleset never becomes mutable when it stops being the current projection
pointer. Publication seals before swapping that pointer in the same transaction;
an empty sealed ruleset is valid and is not confused with an absent snapshot.

Scope values and live profile interpretation remain M1-04's closed extension.
M1-02 can represent verification_pending but cannot mark a declared address as
verified merely because the two input addresses differ. The production update
adapter remains unavailable until that owner supplies its verified result type.

## Proposed normalized value encoding

For the core closed unions, use discriminator plus dedicated nullable columns,
not JSON. A branch's required fields are NOT NULL under the branch predicate;
all other columns are NULL. Empty variants carry the tag only. These encoding
records are immutable; updates replace the owning fact only where explicitly
permitted, never change a committed identity key.

| Stored value | Dedicated columns after the tag | Exact branch predicate |
| --- | --- | --- |
| AdmissionRef | epoch_id:L?, rule_id:L?, rule_revision:R?, policy_version:K?, preview_id:L?, action_command_id:L? | initial_backfill requires epoch/rule/revision/policy; future_rule requires rule/revision/policy; manual_thread requires preview; action_label requires action command; every unused field null |
| EpochDecisionRef | operation_id:L?, preview_id:L?, ruleset_revision:R? | backfill_start/gap_approval require all three; scheduled_reconcile requires ruleset; requested_reconcile requires operation/ruleset; scheduled_target_audit none; requested_target_audit operation only |
| PartitionRef | source_thread_id:V? | source_thread requires source_thread_id, other three tags require null |
| SourceEventKey | history_record_id:V, source_message_id:V, label_id:V?, change:LabelChange? | message_added/message_deleted have null label/change; label_changed requires both; projection is inherited from its owning row |

Exact nullable key encoding is essential: uniqueness is not enforced by a SQL
UNIQUE constraint containing nullable label/change columns alone. Source events
also carry a non-null KeyBytes identity and collision/conflict checks against all
original columns; SQL uniqueness over normalized per-variant partial indexes is
required independently. The event encoding contains the actual event tag, not the
provider's general messages array. History IDs remain opaque strings.

AdmissionRef rule and epoch/action references must be resolved in the same
projection. The future manual-preview branch has an explicit disabled production
path until M1-03 supplies its validated preview relation. This draft does not add
an unvalidated preview ID allowlist or accept a scope-free seed operation.

## Proposed table catalogue: authorization, scans and events

`AdmissionColumns`, `DecisionColumns`, `PartitionColumns` and `EventKeyColumns`
below expand exactly to the preceding tagged-column matrices, including each tag
column. They are notation for concrete columns, never a BLOB/TEXT payload field.

| Table | Exact columns | Keys and additional constraints |
| --- | --- | --- |
| `tracked_threads` | projection_id:P, source_thread_id:V, active:B, generation:G, admitted_at:T, stopped_at:T?, stop_reason:ThreadStopReason?, admission_revision:R | PK(projection_id,source_thread_id), FK projection; generation>=1; active requires null stopped_at/reason; inactive requires both; FK current admission to thread_admissions deferred until commit |
| `thread_admissions` | projection_id:P, source_thread_id:V, admission_revision:R, generation:G, admitted_at:T, AdmissionColumns | PK(projection_id,source_thread_id,admission_revision), FK thread; immutable; generation>=1; valid referenced rule/epoch/action in same projection; old admissions retained over stop/re-track |
| `epochs` | projection_id:P, epoch_id:L, kind:EpochKind, state:EpochState, revision:R, created_at:T, window_start:T?, window_end:T?, discovery_cutoff:T?, DecisionColumns, gap_id:L?, recovery_margin_us:N?, fence_history_id:V?, fence_recorded_at:T?, catchup_history_id:V?, discovery_complete:B, known_message_total:N? | PK(projection_id,epoch_id), FK projection and optional history_gaps; window endpoints both null or both present and start<end; fence ID/time both present or both null; kind/decision compatibility below; immutable decision/window/cutoff/margin/fence after publication |
| `history_gaps` | projection_id:P, gap_id:L, failed_poll_id:L, failed_cursor:V, checkpoint_cursor:V?, checkpoint_revision:R, observed_at:T, reliable_coverage_at:T?, h1:V, h1_recorded_at:T | PK(projection_id,gap_id), FK projection/failed poll; immutable observation; checkpoint cursor/coverage both null or present; failed_cursor is actual poll start, not necessarily committed cursor; no approval or cursor-reset field |
| `epoch_partitions` | projection_id:P, epoch_id:L, partition_key:KeyBytes, PartitionColumns, state:PartitionState, completed_pages:N, observed_items:N, page_token:ProviderPageToken?, after_source_message_id:V?, revision:R | PK(projection_id,epoch_id,partition_key), FK epoch; exact core PartitionProgress predicates; unique normalized partition identity in addition to encoded key; original source-thread field immutable |
| `source_events` | projection_id:P, event_id:L, event_key:KeyBytes, EventKeyColumns, observed_at:T, source_thread_id:V?, processing:EventProcessing, revision:R, error_code:ErrorCode? | PK(projection_id,event_id), UQ(projection_id,event_key), FK projection; immutable key/observed_at, null thread may enrich once; contradictory non-null thread fails; error optional only for needs_attention/source_missing |
| `history_checkpoints` | projection_id:P, cursor:V?, reliable_coverage_at:T?, revision:R, active_poll_id:L? | PK(projection_id), FK projection; cursor/coverage both null or both present; active poll FK, at most one active poll per projection |
| `history_polls` | projection_id:P, poll_id:L, origin:PollOrigin, origin_epoch_id:L?, start_cursor:V, start_checkpoint_revision:R, started_at:T, state:PollState, completed_pages:N, next_page_token:ProviderPageToken?, final_history_id:V?, finished_at:T?, revision:R | PK(projection_id,poll_id), FK projection/optional epoch; checkpoint origin requires null origin_epoch_id, other origins require it; completed requires final ID/finished time and no next token; reading has null finished time; abandoned requires finished time and null final ID; immutable origin/start cursor |
| `history_pages` | projection_id:P, poll_id:L, ordinal:N, response_history_id:V, input_page_token:ProviderPageToken?, next_page_token:ProviderPageToken?, received_at:T, metadata_digest:H, expected_event_count:N, complete:B | PK(projection_id,poll_id,ordinal), FK poll; ordinal>=1; first page input token null, later input equals previous next token via repository guard; immutable page facts except complete false-to-true |
| `history_page_events` | projection_id:P, poll_id:L, ordinal:N, event_id:L | PK(projection_id,poll_id,ordinal,event_id), FK exact page and event; repeats across pages allowed but not repeated business effects |

An epoch of initial_backfill/historical_expansion requires backfill_start and a
fixed nonempty window/cutoff; source_reconcile allows scheduled/requested_reconcile;
target_audit allows scheduled/requested_target_audit and has no admission window.
history_gap requires gap_id and a fixed window; all other kinds require null
gap_id. A scheduled_reconcile decision for history_gap requires a referenced gap
with reliable_coverage_at present. Every known-gap epoch, even if explicitly
confirmed via gap_approval, uses the known-coverage boundary below rather than a
narrower selected range. Its immutable recovery_margin_us is exactly
300000000 (five minutes, schema-v1 scan overlap, not a Gmail retention/search
guarantee). window_start is max(minimum supported Timestamp, reliable_coverage_at
minus recovery_margin_us), computed with checked integer arithmetic; window_end
is gap.h1_recorded_at. A nonpositive resulting window or a future reliable
coverage timestamp is a controlled consistency_failure, not cursor advancement.
The margin is persisted, never enlarged on retry or recomputed from a moving now.
Scanning this overlap does not move any rule effective_at backwards: candidate
admission is still filtered against its original immutable policy timeline.
If coverage is absent, only gap_approval is accepted. The matching user range is
stored in the immutable epoch with its operation/preview references; those paths
remain production-disabled until M1-03 validates the actual decision. Repository
checks require the exact known-gap overlap boundary, not equality to coverage
itself or a fixed 24-hour window. Unknown-gap approval has recovery_margin_us=NULL
and exactly its explicitly approved range; no automatic margin broadens that
decision. Non-gap epochs likewise have recovery_margin_us=NULL.
The initial gap observation commits H1 even while approval is unavailable; no
epoch or scan job is created by that observation alone. The epoch fence equals
its gap's H1 and h1_recorded_at. No current-label snapshot fabricates expired
activation events. An unapproved gap remains an explainable observation, not an
epoch with invented authorization.

H0/H1 are committed before scanning. `fence_history_id` is the kind-appropriate
immutable fence, never overwritten by a later scan token. `catchup_history_id`
records completion of the later History consumption, not a replacement fence.
The final checkpoint is committed only with all page work durable. A page's
response_history_id does not advance the global cursor on its own; no lexical or
numeric comparison of provider History IDs is used to choose a maximum.

`begin_history_poll` resolves exactly one of three durable starting relations:

| PollOrigin | Required relation and starting point |
| --- | --- |
| checkpoint | Existing checkpoint cursor/coverage present, no unresolved recovery gate; start_cursor equals that cursor; origin_epoch_id null |
| initial_epoch | Checkpoint cursor/coverage both null and no unresolved recovery gate; referenced initial_backfill epoch was explicitly started with committed H0/fence and fixed cutoff; start_cursor equals that H0. No preview-only epoch or alternate H0 bypass is accepted |
| recovery_epoch | Checkpoint cursor is null-safely equal to referenced gap.checkpoint_cursor; referenced history_gap epoch has its approved/known-gap decision, committed H1, discovery_complete and all required source-window/active-thread partitions complete with work durable; start_cursor equals that H1 |

All three require no active poll and exact checkpoint revision CAS. Starting the
poll does not assign its start_cursor to the checkpoint or fabricate reliable
coverage. In the initial case H0 can be consumed concurrently with discovery;
epoch completion still requires discovery and catch-up. In recovery, H1 may only
be consumed once required gap recovery work is durable, while original expired
cursor remains inspectable. Unknown unapproved gap cannot choose recovery_epoch.
`record_gap` requires failed_poll_id identify the just-abandoned poll, failed_cursor
equal that poll.start_cursor, and saved checkpoint cursor/revision/coverage equal
the actual current checkpoint. The abandoned poll's start_checkpoint_revision+1
must equal the observation's checkpoint_revision, excluding a stale earlier poll.
Any unresolved gap suspends both checkpoint-origin and initial_epoch polling until
its authorized recovery finishes, including when committed cursor is still null.
Only recovery_epoch matching the latest unresolved failed-poll lineage may start;
creating another initial epoch/H0 cannot bypass an unknown/unapproved gap.
Another expired H0/H1 produces another durable gap/epoch against the still-null
or old checkpoint, never a generic set-cursor operation. A recovery origin is
refused if a later unresolved gap supersedes its failed-poll lineage; matching is
by explicit poll/epoch references, never numerical ordering of History IDs.

Only `finish_history_poll` changes committed cursor/coverage, after the complete
page chain and event/jobs checks. It revalidates origin+checkpoint revision and
active_poll_id; final_history_id must equal the last complete page's response ID.
Coverage records the poll's request-start Timestamp, not response-completion time
or scan start, and may not regress a previous reliable coverage timestamp. If the
wall clock regresses the poll remains explainably blocked; do not invent time.
Completion of an initial/recovery poll also sets its epoch.catchup_history_id in
the same transaction. For recovery this clears the old gap polling gate only as
a durable consequence of that matching completed poll; the gap observation stays.
Even an empty successful poll has one complete response page with zero events.

On interrupted pagination the runtime can abandon a poll and begin another from
the same validated origin (including initial H0 or recovery H1 while checkpoint
is still null/expired). Previously stored SourceEventKey rows and effect keys
dedupe replay. Poll/page facts remain inspectable; a token-expiry restart does not
erase selected work. A new poll's first page has no stale page token.

## Proposed job identity layout

`sync_jobs` is the canonical Gmail-spec jobs table; do not create a second queue.
Its proposed common columns are:

`projection_id:P, job_id:L, kind:JobKind, key_version:N, stable_key:KeyBytes,
priority:Priority, state:JobState, revision:R, created_at:T, updated_at:T,
next_attempt_at:T?, attempt_count:N, last_error_code:ErrorCode?, origin_epoch_id:L?`.

PK(projection_id,job_id), UQ(projection_id,key_version,stable_key), FK projection
and optional epoch. key_version=1 for this codec. Branch-specific subject columns
are separate concrete nullable columns in the same table:

`source_message_id:V?, source_thread_id:V?, generation:G?, repair_operation_id:L?,
event_id:L?, operation_id:L?, read_kind:ReadTaskKind?, attempt_id:L?,
subject_epoch_id:L?, partition_epoch_id:L?, partition_key:KeyBytes?, action_command_id:L?`.

| Kind | Required subject columns; all other subject columns null | Identity after projection+kind |
| --- | --- | --- |
| project_message | source_message_id, source_thread_id, generation | source_message_id, generation |
| repair_message | repair_operation_id, source_message_id, source_thread_id, generation | repair_operation_id, source_message_id, generation |
| expand_thread | source_thread_id, subject_epoch_id, generation | source_thread_id, subject_epoch_id, generation |
| resolve_event | event_id | original complete SourceEventKey, not a newly generated event ID |
| operation_read | operation_id, read_kind | operation_id; changed immutable read_kind is conflict |
| recover_insert | attempt_id | original attempt_id |
| scan_discovery | subject_epoch_id, partition_epoch_id, partition_key | subject_epoch_id, exact PartitionRef; only source_window |
| scan_gap | subject_epoch_id, partition_epoch_id, partition_key | subject_epoch_id, exact PartitionRef; source_window/source_thread |
| reconcile_source | subject_epoch_id, partition_epoch_id, partition_key | subject_epoch_id, exact PartitionRef; source_window/source_thread |
| audit_target | subject_epoch_id, partition_epoch_id, partition_key | subject_epoch_id, exact PartitionRef; target_catalog/mapped_target_set |
| cleanup_action | action_command_id | action_command_id |

`origin_epoch_id` is optional work provenance, separate from the required
`subject_epoch_id` used by the five epoch-identity variants. Both reference epochs
in the same projection. Core JobSubject.epoch_id maps to subject_epoch_id only.
For partition jobs, partition_epoch_id=subject_epoch_id is enforced by CHECK;
partition_epoch_id and partition_key are both present or both null. This storage
FK companion prevents a partial-null composite reference for expand_thread,
whose subject epoch is present but whose partition pair is null. It is derived
from the same validated subject, never an independently selectable epoch.
Adding provenance on replay cannot change a job key; multiple originating epochs
are represented by a normalized `epoch_jobs(projection_id:P, epoch_id:L, job_id:L)`
table, PK over all three, FKs to epoch/job. origin_epoch_id records the first
origin; later selected epochs gain an epoch_jobs row, not duplicated work.

SQL per-kind partial unique indexes protect the same source fields as the encoded
key. resolve_event may index event_id because source_events already enforces one
row per immutable event key; the codec still uses original event components.
Claims are a separate one-to-one table keyed by projection+job, holding the exact
core Claim fields plus job ID, and inserted/deleted only with job state/revision
transitions. Claim identity and owner-run are immutable for that acquisition.

Dispatch permission is not a SQL lease timeout. A claim cannot prove that an OS
owner died; restart classification follows real ownership acquisition and intent
inspection. At most one claim exists per job and no network wait occurs while
its CAS transaction is open. Thread-generation matching and stale-run rejection
are checked at prepare and again at invocation-entry admission.

### Generation-bound thread expansion proof

Thread expansion is not completed by an epoch partition's state. An
expand_thread job has no PartitionRef and its identity includes generation;
its own bounded source-thread snapshot is accounted for by these enabled tables:

| Table | Exact columns | Keys and constraints |
| --- | --- | --- |
| `thread_expansion_runs` | projection_id:P, run_id:L, job_id:L, source_thread_id:V, epoch_id:L, generation:G, current:B, state:PartitionState, snapshot_digest:H, expected_messages:N, started_at:T, completed_at:T?, revision:R | PK(projection_id,run_id), FK job/thread/epoch; generation>=1; same thread/epoch/generation as immutable expand_thread subject; state scanning/complete/needs_attention only; complete iff completed_at present; immutable identity/snapshot/count/start, current only 1→0 |
| `thread_expansion_items` | projection_id:P, run_id:L, source_message_id:V, kind:ExpansionItemKind, project_job_id:L?, mapped_source_message_id:V?, mapping_revision:R? | PK(projection_id,run_id,source_message_id), FK run/optional project job/optional exact mapping history; project_job requires project_job_id and null mapped_source_message_id/mapping_revision; verified_mapping requires the reverse with mapped_source_message_id=source_message_id; immutable membership/fact |

Each run represents one fetched available non-draft message-ID set, sorted by
UTF-8 byte ordering and encoded with the same length framing as stable keys
under the literal identity class `expansion-snapshot-v1`; digest is SHA-256 of
that closed metadata sequence. This is not a MIME/fidelity digest. Expected count
is the number of distinct IDs; no raw/header/body/Subject fields enter storage.
Chunked items either reference durable project_message jobs with this run's
source thread/generation/message or already verified mapping history for exactly
that source. Membership creation validates those relationships transactionally.

A partial unique index permits one current run per job. On restart, a new fetch
with the same set may resume its same run. A changed set creates a new run and
atomically marks the old current=false, retaining all old items and already
enqueued work; it never silently drops selection or mutates a previous snapshot.
The caller's current job claim/generation guards both choices. Marking a run
complete requires current=true, exact expected distinct count and matching digest,
all item references still valid, and the parent job's thread/generation still
active. New messages arriving after this snapshot are handled through the
History/reconcile routes, not falsely included in this proof.

Stopping/re-tracking produces a distinct expand_thread job/generation; its
completion cannot use any run belonging to the old job, even in the same epoch
and thread. Old factual results remain stored but cannot reactivate scheduling.

## Proposed table catalogue: claims, insert facts and mappings

The tables store observations separately from permission to schedule another
remote effect. A known target ID is not a verified-success flag; a stopped
generation does not prevent retaining facts from its already dispatched attempt.

| Table | Exact columns | Keys and constraints |
| --- | --- | --- |
| `job_claims` | projection_id:P, job_id:L, claim_id:L, owner_run_id:L, acquired_at:T, thread_generation:G?, job_revision:R, phase:ClaimPhase | PK(projection_id,job_id), UQ(projection_id,claim_id), FK job; thread-generation presence/equality follows its job/attempt; only a claimed job has a claim, repository-checked at transaction completion |
| `insert_attempts` | projection_id:P, attempt_id:L, job_id:L, claim_id:L, source_message_id:V, source_thread_id:V, generation:G, binding_role:Role, binding_revision:R, prepared_at:T, dispatch_started_at:T?, result_at:T?, requested_target_thread_id:V?, raw_digest:H, semantic_digest:H?, semantic_version:K?, rfc_message_id:RfcMessageId?, date_policy:DatePolicy, state:InsertState, certainty:OutcomeCertainty, target_message_id:V?, target_thread_id:V?, attribution:AttributionKind, visibility:Visibility, verified_at:T?, error_code:ErrorCode?, recovery_checks:N, next_recovery_at:T?, revision:R | PK(projection_id,attempt_id), FK job, FK tracked thread, FK(projection_id,binding_role,binding_revision) to binding_revisions; binding_role='target', generation>=1; claim_id is immutable acquisition provenance, not FK to ephemeral job_claims; exact axes constraints below |
| `message_mappings` | projection_id:P, source_message_id:V, source_thread_id:V, mapping_revision:R, attempt_id:L, target_message_id:V, target_thread_id:V, verified_at:T, visibility:Visibility, last_audit_at:T?, target_present:B? | PK(projection_id,source_message_id), UQ(projection_id,target_message_id), FK attempt/thread, FK(projection_id,source_message_id,mapping_revision) to mapping_history; target_present/last_audit_at both null or both present; only verified attempt establishes row |
| `mapping_history` | projection_id:P, source_message_id:V, mapping_revision:R, source_thread_id:V, attempt_id:L, target_message_id:V, target_thread_id:V, verified_at:T, superseded_at:T? | PK(projection_id,source_message_id,mapping_revision), FK attempt/thread; immutable verified identity/facts; old target ownership retained; mapping revision starts at 1 and increments only authorized repair |
| `target_ownership` | projection_id:P, target_message_id:V, source_message_id:V, first_attempt_id:L, recorded_at:T | PK(projection_id,target_message_id), FK first_attempt_id to attempts; repository checks its source/target facts equal the stored IDs; immutable; an old repaired target cannot later be assigned to a different source |
| `thread_targets` | projection_id:P, source_thread_id:V, target_thread_id:V, anchor:B, first_attempt_id:L, created_at:T | PK(projection_id,source_thread_id,target_thread_id), FK tracked thread/attempt; partial UQ(projection_id,source_thread_id) WHERE anchor=1; actual fallback thread set retained |

Retention of binding identity is necessary when credentials refresh or the binding
is reverified. The bindings current-pointer table has a normalized immutable
`binding_revisions` history: columns
`projection_id:P, role:Role, binding_revision:R, declared_address:PrivateAddress,
verified_address:PrivateAddress?, state:BindingState, verified_at:T?`;
PK(projection_id,role,binding_revision), FK projection, same verification checks.
`bindings` remains the current pointer with current credential revision, and must
reference the exact historical binding revision with a deferred FK. Attempt
binding_revision refers specifically to role=target. Account identity is immutable
across all rows; a new revision records verification, never an implicit rebind.
Credential revision history/file recovery is M1-04's separately reviewed extension.

Attempt SQL axis matrix (every other combination is invalid):

| InsertState | Required OutcomeCertainty | Times and target facts |
| --- | --- | --- |
| prepared | not_attempted | dispatch/result/verified times and both target IDs null; attribution none |
| cancelled_before_dispatch | not_attempted | dispatch and verified null; result_at present; target IDs null; attribution none |
| dispatch_started | unknown | dispatch present; result/verified null, target IDs null; attribution none |
| definite_not_inserted | definitely_not_inserted | result present; verified/target IDs null; attribution none; dispatch may be absent for confirmed pre-call failure |
| pending_recovery | unknown | dispatch and result present; verified/target IDs null; attribution none |
| known_inserted | inserted | dispatch/result and both target IDs present; verified null; attribution direct_response |
| verified | inserted | dispatch/result/verified and both target IDs present; semantic digest/version present; attribution direct_response before recovered evidence extension |
| needs_attention | unknown or inserted | dispatch/result present, verified null; inserted requires both target IDs/direct_response; unknown requires target IDs null/none |

The positive target result is factual and retained even if later verification
fails or the thread stops. Unknown candidate search observations do not fill these
target fields: M2-04 supplies its reviewed candidate/evidence tables later, without
turning search into a direct_response. `visibility` can remain unknown until a
readback/audit; unknown visibility cannot be reported as normal. Semantic digest
and version are both present or both null; the values are supplied by M2-02's
reviewed codec, not computed by SQL from raw. Raw digest never contains raw bytes.

Two partial unique constraints on attempts enforce one unresolved effect per
source message and one per source thread. The exact predicate for both is
`state IN ('dispatch_started','pending_recovery','known_inserted','needs_attention')`.
The axis CHECK already constrains their certainty. The known_inserted case blocks
successor prepare/insert until readback is resolved; needs_attention remains
conservatively thread-blocking until an explicit reviewed resolution changes its
state. No timer removes these blockers. Definite non-insertion and verified
facts are retained but do not satisfy this blocking predicate.

Prepared attempts need an independent unique guard over `(projection_id,
source_message_id)` WHERE state='prepared', plus writer-actor per-thread ordering
and a dispatch CAS. Never rely on only one unresolved-insert index to make two
prepared writes safe. A job retry after definite_not_inserted may create a new
attempt; replay of an existing prepare request returns its same attempt ID when
facts agree. Unknown cannot take that branch.

The storage operation transition allowlist, independent of the axis CHECK, is:
prepared→dispatch_started/cancelled_before_dispatch/definite_not_inserted;
dispatch_started→pending_recovery/known_inserted/definite_not_inserted/needs_attention;
pending_recovery→needs_attention; known_inserted→verified/needs_attention;
needs_attention(inserted)→verified only through verify_mapping after actual
direct-response fidelity checks. Same-state factual replay must agree with every
already-recorded non-null fact; it cannot erase a target or downgrade certainty.
All other transitions refuse in v1, including unknown→definite_not_inserted and
unknown→known_inserted based on a caller assertion. Recovered evidence transitions
require the independently reviewed M2-04 extension, not this direct-response API.
Verified/cancelled/definite-not-inserted facts are terminal; a separately permitted
new attempt has a new ID. Once dispatch exists, result classification comes only
from the future reviewed adapter's invocation facts; arbitrary HTTP status text
or search absence is not accepted as non-insertion evidence.

## Proposed table catalogue: action, error and audit facts

| Table | Exact columns | Keys and constraints |
| --- | --- | --- |
| `action_commands` | projection_id:P, action_command_id:L, event_id:L, history_record_id:V, label_id:V, source_thread_id:V, kind:ActionKind, state:ActionState, cleanup:CleanupState, observed_at:T, executed_at:T?, error_code:ErrorCode?, revision:R | PK(projection_id,action_command_id), UQ(projection_id,history_record_id,label_id,source_thread_id), FK source event; label-added key/history/label/thread must agree; executed iff executed_at present; cleanup only queued/completed/blocked after executed |
| `error_events` | projection_id:P, error_id:L, code:ErrorCode, error_class:ErrorClass, role:Role?, observed_at:T, job_id:L?, attempt_id:L?, count:N | PK(projection_id,error_id), FK projection/optional job/attempt; count>=1; attempt/job relationship if both present; no raw error/string/SQL/URL |
| `audit_events` | projection_id:P, audit_id:L, kind:AuditKind, object_kind:AuditObjectKind, local_object_id:L?, source_thread_id:V?, source_message_id:V?, before_revision:R?, after_revision:R?, before_state:TEXT?, after_state:TEXT?, error_code:ErrorCode?, observed_at:T | PK(projection_id,audit_id), FK projection; object-specific closed state/selector predicates below; no arbitrary delta/payload |

`audit_events` is not a general change dictionary. object_kind picks exactly one
selector: projection has none; rule/epoch/event/job/attempt use local_object_id;
thread uses source_thread_id; mapping uses source_message_id. Other selector
columns are null. The before_state/after_state columns are restricted by
object_kind to the corresponding frozen enum: projection BindingState, epoch
EpochState, job JobState, attempt InsertState. Rule/thread/mapping/event audits
have null state columns and record before/after revision only. AuditKind must
match that object kind according to its name; initialized/binding_changed/
restore_fenced/maintenance_completed address projection; page_ingested and
cursor_advanced address projection without arbitrary provider page details.
Exact allowed AuditKind/object pairs are: initialized/projection;
rule_changed/rule; thread_admitted/thread; thread_stopped/thread;
epoch_started/epoch; page_ingested/projection; cursor_advanced/projection;
job_state_changed/job; attempt_state_changed/attempt; mapping_verified/mapping;
binding_changed/projection; restore_fenced/projection; maintenance_completed/
projection. Unlisted pairs fail. event is reserved as a codec selector and has
no enabled AuditKind in v1; it cannot be inserted until a reviewed extension.

Legacy action labels are observations only and do not create an activation row.
M5 can add a reviewed legacy-observation table. A real remove/re-add History event
has a new immutable activation key. Cleanup retries change only cleanup metadata;
an executed row cannot reapply its rule/track/blacklist changes. Source readonly
mode never queues cleanup. No label name/header/learned sender is copied to this
row; normalized rule values live only in the rules table under their rule owner.

## SQL manifest, constraints and indexes

Every field matrix expands to an explicit named CREATE TABLE manifest in
`db/migrations/v0001.py` only after design approval. Implementation compares the
catalog to that trusted manifest; it does not infer/repair schema from current
rows. No runtime SQL generator consumes arbitrary configuration.

The SQL scalar CHECK templates are fixed here:

- P: TEXT, byte length 1..64, no character outside `[A-Za-z0-9_-]`.
- L: TEXT, length 32, lowercase hex only, character 13 is `4`, character 17 is
  one of `8,9,a,b`. H: length 64, lowercase hex only.
- N/G/R: INTEGER, 0..9223372036854775807. Required-positive guards add `>=1`.
  T: INTEGER, -62135596800000000..253402300799999999, with exact UTC codec.
- K: TEXT, byte length 1..64, first character `[a-z0-9]`, remaining characters
  only `[a-z0-9_.-]`. Core/storage discriminators use literal IN lists.
- V/PrivateAddress/RuleValue/RfcMessageId: TEXT, byte length within the stated
  bound, no codepoint U+0000..001F or U+007F..009F. The literal DDL expands fixed
  `instr(column,char(n))=0` checks for those codepoints; no custom SQL function,
  regex extension or `trusted_schema` exemption. Python rejects surrogates before
  UTF-8 binding. SQL cannot establish sender/domain/auth semantics by syntax.
- ProviderPageToken: TEXT, byte length 1..16384, NUL absent. KeyBytes: BLOB,
  byte length 1..8192. These are different codecs, never interchangeable.
- B: INTEGER IN(0,1). The Python boundary requires exactly bool for B and exactly
  integer wrappers for N/G/R; STRICT storage does not itself prevent coercion.

Use nullable CHECKs explicitly (`column IS NULL OR predicate`) and the closed
branch disjunction plus nullness predicates, not equality against NULL. FK
enforcement is enabled/verified on every connection before a transaction.
Referential integrity tests exercise direct SQL cross-projection violations.

The exact FK suffix manifest follows. Every entry implicitly prepends
`projection_id` on both sides; every entity table except projections also has
`projection_id -> projections(projection_id)`. Schema singleton/ledger tables
are the only projection-free tables. All use ON DELETE/UPDATE RESTRICT; only
the four pointer cycles marked deferred use DEFERRABLE INITIALLY DEFERRED.
References not listed here are not fabricated FKs into future registries.

| Child and columns after projection | Parent and columns after projection |
| --- | --- |
| projections(ruleset_revision), deferred | rulesets(revision) |
| bindings(role,binding_revision), deferred | binding_revisions(role,binding_revision) |
| rules(rule_id,current_revision), deferred | rule_revisions(rule_id,revision) |
| rule_revisions(rule_id) | rules(rule_id) |
| ruleset_members(ruleset_revision) / (rule_id,rule_revision) | rulesets(revision) / rule_revisions(rule_id,revision) |
| tracked_threads(source_thread_id,admission_revision), deferred | thread_admissions(source_thread_id,admission_revision) |
| thread_admissions(source_thread_id) / (epoch_id) / (rule_id,rule_revision) / (action_command_id) | tracked_threads(source_thread_id) / epochs(epoch_id) / rule_revisions(rule_id,revision) / action_commands(action_command_id) |
| epochs(gap_id) / (ruleset_revision) | history_gaps(gap_id) / rulesets(revision) |
| history_gaps(failed_poll_id) | history_polls(poll_id) |
| history_polls(origin_epoch_id) | epochs(epoch_id) |
| epoch_partitions(epoch_id) | epochs(epoch_id) |
| history_checkpoints(active_poll_id) | history_polls(poll_id) |
| history_pages(poll_id) | history_polls(poll_id) |
| history_page_events(poll_id,ordinal) / (event_id) | history_pages(poll_id,ordinal) / source_events(event_id) |
| sync_jobs(origin_epoch_id) / (subject_epoch_id) / (partition_epoch_id,partition_key) | epochs(epoch_id) / epochs(epoch_id) / epoch_partitions(epoch_id,partition_key) |
| sync_jobs(source_thread_id) / (event_id) / (attempt_id) / (action_command_id) | tracked_threads(source_thread_id) / source_events(event_id) / insert_attempts(attempt_id) / action_commands(action_command_id) |
| thread_expansion_runs(job_id) / (source_thread_id) / (epoch_id) | sync_jobs(job_id) / tracked_threads(source_thread_id) / epochs(epoch_id) |
| thread_expansion_items(run_id) / (project_job_id) / (mapped_source_message_id,mapping_revision) | thread_expansion_runs(run_id) / sync_jobs(job_id) / mapping_history(source_message_id,mapping_revision) |
| epoch_jobs(epoch_id) / (job_id) | epochs(epoch_id) / sync_jobs(job_id) |
| job_claims(job_id) | sync_jobs(job_id) |
| insert_attempts(job_id) / (source_thread_id) / (binding_role,binding_revision) | sync_jobs(job_id) / tracked_threads(source_thread_id) / binding_revisions(role,binding_revision) |
| message_mappings(attempt_id) / (source_thread_id) / (source_message_id,mapping_revision) | insert_attempts(attempt_id) / tracked_threads(source_thread_id) / mapping_history(source_message_id,mapping_revision) |
| mapping_history(attempt_id) / (source_thread_id) | insert_attempts(attempt_id) / tracked_threads(source_thread_id) |
| target_ownership(first_attempt_id) | insert_attempts(attempt_id) |
| thread_targets(source_thread_id) / (first_attempt_id) | tracked_threads(source_thread_id) / insert_attempts(attempt_id) |
| action_commands(event_id) | source_events(event_id) |
| error_events(job_id) / (attempt_id) | sync_jobs(job_id) / insert_attempts(attempt_id) |

Source events/action rows can describe not-yet-admitted threads, so their thread
IDs deliberately have no tracked_threads FK. Likewise a source_thread partition
can preserve a stopped/deleted historical selector; its epoch owner validates
scope rather than manufacturing admission. Audit polymorphic selectors have
transactional existence checks using their closed object kind, not an impossible
FK shared among multiple tables. All optional FK suffixes are all-or-none;
the separate partition_epoch_id companion keeps this true for expand_thread.

Immutable rows/columns use explicit BEFORE UPDATE/DELETE triggers raising only
fixed consistency_failure. No arbitrary RAISE text includes values. Immutable
rows: migration ledger, rule revisions, rulesets/members after sealing,
thread admissions, history gaps/page-events, target ownership, audit/error
events and epoch_jobs. An audit event is append-only. Rule identity, thread key,
epoch scope/decision/fence, event key/observed time, job identity/subject and
attempt identity/source/digest/prepare facts are immutable columns. Mapping
history may change only superseded_at from NULL to one timestamp; everything
else is immutable. Binding account identities cannot change through revisioning.
History pages may change only complete from 0 to 1, with all declared work durable.
History poll fields for an already completed/abandoned poll are immutable.
Expansion item rows are immutable. Expansion run job/thread/epoch/generation,
snapshot/count/start facts are immutable; completion is scanning→complete only,
attention is a controlled stopped/error result, and current can only change 1→0.

Besides PK/UQ constraints listed in the tables, install these named indexes:

| Index | Exact key / predicate |
| --- | --- |
| `events_plain_identity` | UQ(projection_id,tag,history_record_id,source_message_id) WHERE tag IN('message_added','message_deleted') |
| `events_label_identity` | UQ(projection_id,history_record_id,source_message_id,label_id,change) WHERE tag='label_changed' |
| `events_pending` | (projection_id,processing,observed_at,event_id) |
| `partitions_simple_identity` | UQ(projection_id,epoch_id,tag) WHERE tag<>'source_thread' |
| `partitions_thread_identity` | UQ(projection_id,epoch_id,source_thread_id) WHERE tag='source_thread' |
| `partitions_pending` | (projection_id,epoch_id,state,partition_key) |
| `jobs_project_identity` | UQ(projection_id,source_message_id,generation) WHERE kind='project_message' |
| `jobs_repair_identity` | UQ(projection_id,repair_operation_id,source_message_id,generation) WHERE kind='repair_message' |
| `jobs_expand_identity` | UQ(projection_id,source_thread_id,subject_epoch_id,generation) WHERE kind='expand_thread' |
| `jobs_resolve_identity` | UQ(projection_id,event_id) WHERE kind='resolve_event' |
| `jobs_read_identity` | UQ(projection_id,operation_id) WHERE kind='operation_read' |
| `jobs_recover_identity` | UQ(projection_id,attempt_id) WHERE kind='recover_insert' |
| `jobs_scan_identity` | UQ(projection_id,kind,subject_epoch_id,partition_key) WHERE kind IN('scan_discovery','scan_gap','reconcile_source','audit_target') |
| `jobs_cleanup_identity` | UQ(projection_id,action_command_id) WHERE kind='cleanup_action' |
| `jobs_eligible` | (projection_id,state,next_attempt_at,priority,created_at,job_id) |
| `jobs_thread_generation` | (projection_id,source_thread_id,generation,state,job_id) |
| `attempts_message_unresolved` | UQ(projection_id,source_message_id) WHERE state IN('dispatch_started','pending_recovery','known_inserted','needs_attention') |
| `attempts_thread_unresolved` | UQ(projection_id,source_thread_id) WHERE same unresolved predicate |
| `attempts_message_prepared` | UQ(projection_id,source_message_id) WHERE state='prepared' |
| `attempts_recovery_due` | (projection_id,state,next_recovery_at,attempt_id) |
| `expansion_current` | UQ(projection_id,job_id) WHERE current=1 |
| `expansion_job_runs` | (projection_id,job_id,started_at,run_id) |
| `jobs_inspection` | (projection_id,created_at,job_id) |
| `attempts_inspection` | (projection_id,prepared_at,attempt_id) |
| `events_inspection` | (projection_id,observed_at,event_id) |
| `mappings_audit` | (projection_id,source_message_id) with keyset pagination; no offset full export |
| `actions_pending` | (projection_id,state,cleanup,observed_at,action_command_id) |
| `audit_recent` | (projection_id,observed_at,audit_id) |

Thread-target anchor uniqueness is its named partial unique index above. Every
foreign-key child gets an ordinary index beginning with its exact FK columns if
no existing PK/index already has that prefix; this is a deterministic manifest
rule, not arbitrary runtime index creation. Query-plan tests enforce bounded
lookups. Index priority ordering is not a fairness scheduler; M2-03 picks among
bounded priority-specific batches using the frozen priority values.

All plain table scalar predicates plus reference predicates are enforced at SQL
level except explicitly described cross-table policy/authorization/CAS checks,
which belong to the repository transaction. In particular SQL valid IDs alone
do not claim a preview was authorized, a Google profile was verified or a semantic
digest was correctly computed. Those consumers must supply reviewed decisions.

## Stable-key codec v1

Encode an ordered tuple as the ASCII prefix `facet-key-v1`, one zero byte, then
each component's 4-byte unsigned big-endian byte length and exact UTF-8 bytes.
Integers use ASCII canonical base-10 without sign or leading zeroes (zero=`0`).
Every key begins with a fixed identity class (`event`, `partition`, `job`) and
projection selector. Components are chosen only from the closed tables above;
there is no public `encode_arbitrary_payload` persistence endpoint. Nesting is
flattened with the inner tag and its exact declared fields, not repr/JSON.

Event components after class/projection are tag/history/message, then label/change
only for label_changed. Partition components after class/projection are tag, then
source_thread_id only for source_thread; the owning epoch remains the SQL parent
key rather than part of the reusable PartitionRef value. Job components after
class/projection/kind follow the identity column table; resolve_event flattens
the complete event tag/history/message/optional-label/change (the already checked
projection is not silently changed); scan jobs flatten partition tag/thread after
their subject epoch. Generated event row IDs and page tokens never enter keys.

Required fixed vectors include empty-tag payload partitions, `ProviderId('a:b')`
versus tuples containing `a`/`b`, UTF-8 multibyte lengths, label add versus remove,
non-contiguous and nonnumeric History IDs, generation 1 versus 10, and each of the
11 JobKinds. A simple framing vector is component `é`: length bytes
`00 00 00 02`, value bytes `c3 a9`. `('a','bc')` differs from `('ab','c')` even
though concatenated values match. Encoded keys are compared together with original
typed columns. Same key with contradictory immutable source/thread/read-kind is
request_conflict/consistency_failure, never success-by-DO-NOTHING or REPLACE.

## Storage-only records and operation surface

Each table maps to one frozen storage-only `XRow` dataclass named by PascalCase
table singularization: SchemaMetadataRow, SchemaMigrationRow, ProjectionRow,
BindingRow, BindingRevisionRow, RuleRow, RuleRevisionRow, RulesetRow,
RulesetMemberRow, TrackedThreadRow, ThreadAdmissionRow, EpochRow, HistoryGapRow,
EpochPartitionRow, SourceEventRow, HistoryCheckpointRow, HistoryPollRow,
HistoryPageRow, HistoryPageEventRow, SyncJobRow, EpochJobRow, JobClaimRow,
InsertAttemptRow, MessageMappingRow, MappingHistoryRow, TargetOwnershipRow,
ThreadTargetRow, ActionCommandRow, ErrorEventRow, AuditEventRow,
ThreadExpansionRunRow and ThreadExpansionItemRow.

Fields and required-nullability are exactly the expanded table columns, using
their specified primitive/enum/storage codec wrappers. The normalized union
columns are decoded into the exact core union value for the corresponding row.
The replacements below remove all named SQL columns from the in-memory row;
every other table column is retained once with the same name/type:

| Row member | Replaced SQL columns |
| --- | --- |
| ThreadAdmissionRow.admission:AdmissionRef | tag plus all AdmissionColumns payload fields |
| EpochRow.decision:EpochDecisionRef | tag plus all DecisionColumns payload fields |
| EpochPartitionRow.progress:PartitionProgress | tag, source_thread_id, state, completed_pages, observed_items, page_token, after_source_message_id |
| SourceEventRow.event:SourceEvent | tag, history_record_id, source_message_id, label_id, change, observed_at, source_thread_id; event.key.projection_id must equal retained row projection_id |
| SyncJobRow.subject:JobSubject | all 12 nullable subject columns; resolve_event reconstructs its exact event key through the mandatory event FK; partition jobs reconstruct the exact PartitionRef through the partition FK; retained kind must equal subject.tag |
| JobClaimRow.claim:Claim | claim_id, owner_run_id, acquired_at, thread_generation, job_revision, phase |

In-memory rows contain these typed values instead of nullable SQL branch columns.
No additional shared enum,
wire/provider type or dynamic row dictionary is introduced.

The following finite helper records are also storage-local, all fields required:

- `PageLimit(value: int)` exactly 1..500, bool rejected.
- `RevisionGuard(expected: Revision)`; conditional mutation never means last-write-wins.
- `WriteReceipt(disposition: Literal['created','replayed','updated'], object_id:
  LocalId | ProviderId | ProjectionId, revision: Revision)`; not a CLI request
  receipt, never persisted as authority or confused with M1-03's protocol.
- `StorageFailure(code: ErrorCode)` with sealed repr/error text and no SQL/params.
- `OwnerSessionInfo(owner_run_id: LocalId, state_instance_id: LocalId,
  request_namespace: LocalId)`; immutable current connection lineage metadata,
  not proof of lock ownership and not a substitute for the M1-03 provider.
- `BootstrapInitContext(owner: OwnerSessionInfo, bootstrap_nonce: LocalId)`;
  identifies the already durable M1-03 bootstrap journal request
  `rq1_<owner.request_namespace>_<bootstrap_nonce>`. Private storage metadata only,
  not a new wire request type or proof of filesystem lock/journal completion.
- `ReadPage[T](items: tuple[T,...], next_key: bytes | None)` where T is one
  explicitly allocated row type and next_key is the registered bounded keyset
  codec for that query, never an arbitrary serialization cursor.
- `CountsSnapshot(confirmed_mappings: Count, by_job_state: tuple[JobStateCount,...],
  unresolved_attempts: Count, discovery_complete: bool, known_total: Count | None)`;
  `JobStateCount(state: JobState, count: Count)` contains exactly one ordered row
  for every JobState. Internal snapshot only, not a public DTO or latency model.

The exact repository call inventory is below. `uow` is the internal active write
unit of work, `view` a validated read session. Repository methods require
`projection_id:ProjectionId`;
it is never inferred from an arbitrary object's ID. Listed new-row parameters
use the exact closed row shapes above, not partial dictionaries. Unknown fields
are rejected before starting SQL. Every mutation returns WriteReceipt or a
controlled StorageFailure; read methods return the listed closed row/None/page.

| Method | Additional required typed parameters | Preconditions / output |
| --- | --- | --- |
| inspect_schema | view | Trusted SchemaMetadataRow plus ordered tuple[SchemaMigrationRow,...]; mismatch refuses normal reads |
| get_projection | view | ProjectionRow or None; no creation |
| get_binding | view, role:Role | BindingRow or None; history separately available by revision |
| get_binding_revision | view, role:Role, revision:Revision | BindingRevisionRow or None |
| get_rule / get_epoch / get_event / get_job / get_attempt / get_action | view, id:LocalId | Corresponding exact Row or None within the selected projection |
| get_thread / get_mapping | view, id:ProviderId | TrackedThreadRow / MessageMappingRow or None within the selected projection |
| get_checkpoint | view | HistoryCheckpointRow or None, no creation/cursor inference |
| record_binding_revision | uow, row:BindingRevisionRow, credential_revision:Revision, guard:RevisionGuard | M1-04 production adapter required; immutable identity, revision CAS |
| publish_rules | uow, rules:tuple[RuleRow,...], revisions:tuple[RuleRevisionRow,...], snapshot:RulesetRow, members:tuple[RulesetMemberRow,...], guard:RevisionGuard | Each collection <=500; M1-06 normalization input, immutable scope/effective times; current pointer CAS |
| admit_thread | uow, thread:TrackedThreadRow, admission:ThreadAdmissionRow, jobs:tuple[SyncJobRow,...], guard:ThreadGenerationGuard | Explicitly validated origin/ref; active replay compares identity, re-track increments exactly once within caller's durable effect |
| stop_thread | uow, thread_id:ProviderId, expected_generation:Generation, stopped_at:Timestamp, reason:ThreadStopReason | Increment generation, deactivate, cancel unsent jobs/attempts atomically; already-stopped generation returns classified conflict, not second increment |
| record_gap | uow, gap:HistoryGapRow | Persist H1/known-or-unknown coverage without creating authorization/work |
| start_epoch | uow, epoch:EpochRow, partitions:tuple[EpochPartitionRow,...] | Decision validation, fixed window/fence commit, <=500 initial partitions |
| extend_partitions | uow, epoch_id:LocalId, partitions:tuple[EpochPartitionRow,...], guard:RevisionGuard | Newly discovered active-thread partitions under same fixed epoch, bounded batch; immutable identity dedupe |
| advance_partition | uow, row:EpochPartitionRow, jobs:tuple[SyncJobRow,...], guard:RevisionGuard | Progress/work atomic, frozen scope and allowed cursor kind; <=500 jobs |
| advance_epoch | uow, epoch_id:LocalId, state:EpochState, discovery_complete:bool, known_total:Count\|None, guard:RevisionGuard | Immutable scope and catchup_history_id untouched; complete requires all partitions complete, this epoch's actual complete-poll evidence where required, all epoch_jobs terminal; issues produce completed_with_issues, never false success |
| begin_history_poll | uow, row:HistoryPollRow, guard:RevisionGuard | One active poll; exact checkpoint/initial_epoch/recovery_epoch branch above; checkpoint revision CAS, never writes start_cursor into checkpoint |
| begin_history_page | uow, page:HistoryPageRow, guard:RevisionGuard | Next contiguous ordinal; immutable metadata digest/count/token facts, complete=false; does not advance any cursor |
| ingest_history_chunk | uow, poll_id:LocalId, ordinal:Count, events:tuple[SourceEventRow,...], jobs:tuple[SyncJobRow,...], guard:RevisionGuard | <=500 events/jobs; page-event membership and required event/resolution work atomic; stable keys dedupe replay; may not advance page/poll cursor |
| finish_history_page | uow, poll_id:LocalId, ordinal:Count, metadata_digest:Sha256Hex, guard:RevisionGuard | Matching normalized metadata page identity, exact distinct membership count and all work durable; complete=true plus poll page/token progress atomic |
| finish_history_poll | uow, poll_id:LocalId, final_history_id:ProviderId, guard:RevisionGuard | Complete contiguous chain, exact final-page response ID; coverage derived from stored poll.started_at, checkpoint/poll/epoch CAS atomic; no caller-chosen coverage |
| abandon_history_poll | uow, poll_id:LocalId, finished_at:Timestamp, guard:RevisionGuard | reading→abandoned, release matching active_poll_id only; checkpoint cursor/coverage unchanged, retain all pages/events/jobs |
| enrich_event | uow, event_id:LocalId, source_thread_id:ProviderId, guard:RevisionGuard | Null-to-value or same-value replay; conflicting context attention, no key replacement |
| classify_event | uow, event_id:LocalId, processing:EventProcessing, error:ErrorCode\|None, jobs:tuple[SyncJobRow,...], guard:RevisionGuard | <=500 jobs, classification and derived work atomic; consumed requires durable effect or explicit no-admission decision, not disappearing unfinished selection |
| enqueue | uow, row:SyncJobRow | Stable identity and immutable columns agree; mapped/unknown/stopped preconditions checked by kind |
| begin_expansion | uow, run:ThreadExpansionRunRow, guard:RevisionGuard | Current claimed expand_thread job revision/generation; reuse identical current snapshot or atomically supersede it, retain old work |
| ingest_expansion_items | uow, run_id:LocalId, items:tuple[ThreadExpansionItemRow,...], jobs:tuple[SyncJobRow,...], guard:RevisionGuard | <=500 each, guard run.revision plus current parent claim/generation; membership and derived work in same UoW |
| finish_expansion | uow, run_id:LocalId, completed_at:Timestamp, guard:RevisionGuard | Guard run revision and current parent claim/generation; complete exact snapshot count/digest and reference checks; no other job's proof |
| claim | uow, job_id:LocalId, claim:Claim, guard:RevisionGuard, now:Timestamp | Exact runnable state/time/generation/owner; one CAS winner |
| defer_job | uow, job_id:LocalId, state:Literal['retry_wait','blocked','needs_attention','failed','source_missing'], error:ErrorCode, retry_at:Timestamp\|None, guard:RevisionGuard | retry_wait alone requires retry_at; unknown/known unverified insert cannot become safe-retry/failed/source_missing; explainable durable state/claim release |
| complete_noninsert_job | uow, job_id:LocalId, guard:RevisionGuard | Excludes project_message/repair_message; exact per-kind durable completion prerequisite below; no caller bool claiming remote effect |
| prepare_attempt | uow, row:InsertAttemptRow, guard:RevisionGuard | Current claim/binding/generation, no mapping or unresolved blocker; no raw |
| mark_dispatch | uow, attempt_id:LocalId, claim_id:LocalId, dispatched_at:Timestamp, guard:RevisionGuard | Actual M2 actor-entry caller; recheck pause/restore/binding/generation then commit marker, no network callback here |
| record_attempt_result | uow, row:InsertAttemptRow, guard:RevisionGuard | Preserve prepared immutable facts; allowed state/certainty update and recovery job atomically, including stopped generation results |
| verify_mapping | uow, attempt_id:LocalId, mapping:MessageMappingRow, history:MappingHistoryRow, ownership:TargetOwnershipRow, thread_target:ThreadTargetRow, guard:RevisionGuard | M2 verified decision, exact IDs/digest/version/direct-response facts; no generic recovered candidate acceptance |
| record_target_audit | uow, source_message_id:ProviderId, present:bool, visibility:Visibility, audited_at:Timestamp, guard:RevisionGuard | Fact only; absence cannot enqueue repair |
| register_action | uow, row:ActionCommandRow | Actual resolved label-added event and tuple dedupe; no legacy activation |
| complete_action | uow, row:ActionCommandRow, guard:RevisionGuard | Same uow includes business effects; replay reads executed row before repeating effects |
| record_cleanup | uow, action_id:LocalId, cleanup:CleanupState, error:ErrorCode\|None, guard:RevisionGuard | Only cleanup state after executed, readonly forbids queueing source mutation |
| append_audit / append_error | uow, row:AuditEventRow / ErrorEventRow | Exact closed predicates, append-only |
| list_jobs / list_attempts / list_events / list_audit | view, limit:PageLimit, after:bytes\|None | ReadPage of exact corresponding row, registered keyset only |
| counts | view, epoch_id:LocalId\|None | CountsSnapshot; unique mappings and exclusive job states, no fake total |

Keyset list order is `(created_at,job_id)` for jobs, `(prepared_at,attempt_id)` for
attempts, `(observed_at,event_id)` for events and `(observed_at,audit_id)` for audit.
The cursor is framed `read.<table>`, projection, canonical signed timestamp
microseconds and local ID; bounds/field types and table/projection must match the
query. It is not opaque arbitrary JSON or a capability. Actual eligible-queue
selection uses a separate internal fixed priority/state query, not these operator
inspection pages. Databases changing between read calls may add rows; a cursor
is an ordering hint, not a retained cross-request snapshot or claimed completeness.

RevisionGuard targets the row being changed: thread admission_revision, epoch
revision, partition revision, event revision, job revision or attempt revision.
begin_expansion guards the parent job; ingest/finish_expansion guard run.revision
and additionally validate the parent job's current claim, owner and generation.
Rule publication guards projection.ruleset_revision; binding update guards its
binding_revision. Begin-poll guards checkpoint.revision; page/chunk/finish/abandon
guard history_polls.revision, incremented at each accepted mutation. Final poll
also requires checkpoint.revision=start_checkpoint_revision and active_poll_id
matching. A conflicting batch re-reads/reconciles; it cannot accept stale effects.
Begin-poll first validates its supplied checkpoint guard; setting active_poll_id
does not change cursor/coverage or checkpoint revision. Its poll stores that exact
start_checkpoint_revision. Finishing or abandoning increments checkpoint revision
when clearing active_poll_id, so a stale abandoned poll cannot later finish.
prepare_attempt uses the current job revision rather than the not-yet-existing
attempt revision. Claim CAS increments job.revision and records the resulting
value as Claim.job_revision; phase-only claim updates retain that acquisition.
mark_dispatch changes Claim.phase to dispatching together with its attempt marker;
recording an inserted result changes phase to verifying while retaining the claim.
Recovery deferral releases the old claim; actual restart-owner reconstruction and
replacement claims belong to M1-03/M2, not a lease-expiry storage method.
record_target_audit guards mapping_revision (factual repeated audits additionally
reject audited_at older than last_audit_at). Action/cleanup guards action.revision.
M1-03 composes its own receipt in the same UoW rather than overloading these guards.

Epoch.catchup_history_id has no caller-setter. Only finish_history_poll derives
it from the last complete response of that same poll's origin_epoch_id, in its
checkpoint/epoch completion transaction. advance_epoch validates the referenced
actual completed poll's origin/epoch/final-ID evidence and cannot fill or replace
the field. A different epoch's poll, unfinished page, or arbitrary ProviderId
never establishes catch-up completion, even if other counts appear complete.

For counts(epoch_id=None), confirmed_mappings is the current mapping row count,
never mapping_history or attempts; by_job_state counts each current job once.
Unless a single explicitly selected epoch is supplied, discovery_complete=false
and known_total=None express unknown global total. For a selected epoch,
membership is epoch_jobs and success
counts distinct source_message_id with a verified current mapping and a completed
project/repair job in that epoch. Known total is published only when that epoch's
discovery is complete; mixed incomplete/failed work is never reported all-success.

Bulk methods reject oversized input before SQL; callers use multiple bounded
transactions without advancing a cursor past unfinished work. Large History pages
use begin/chunk/finish rather than truncation or a single unbounded transaction.
The metadata digest is SHA-256 of the versioned, ordered normalized SourceEvent
tuples plus declared page token/history facts, using the same length framing as
keys; it never hashes headers/raw into a stored page response. A changed response
for an incomplete page causes poll abandonment and restart from the committed
cursor, retaining already accepted events/work. Final-page completion alone does
not advance the global checkpoint; finish_history_poll performs that final CAS.

For complete_noninsert_job, expand_thread requires its own current complete
ThreadExpansionRunRow with the identical job/thread/epoch/generation, not an
epoch partition or another generation's run. resolve_event requires resolved/source_missing/
attention classification (attention is not completed success); scan jobs require
the exact partition complete; cleanup requires cleanup=completed; recover_insert
requires referenced attempt resolved into verified or definite_not_inserted,
while attention retains attention. operation_read remains disabled until M1-03's
operation-result registry supplies its durable result check. A policy or source
failure does not manufacture completed. All these checks run inside the same uow.

Explicitly absent APIs: execute SQL, write arbitrary row, delete mapping/attempt,
reset cursor, force binding, clear uncertainty, import spike state, choose a
new account, accept command payload, retry remote insert, and resolve attribution.
Helpers that transition internal job state are private to these transactions,
not arbitrary public `set_state` mutators.

## Connection/session API and transaction lifetime

New-state initialization has exactly one private entry point, separate from
repositories attached to an existing schema:

```text
_initialize_database(
  connection: sqlite3.Connection, *, bootstrap: BootstrapInitContext,
  initial_projection: ProjectionRow, source_binding: BindingRow,
  target_binding: BindingRow, initial_ruleset: RulesetRow
) -> WriterSession
```

It receives no path and never opens another connection. M1-03 has already taken
the real owner and view/bootstrap locks, durably recorded the matching bootstrap
journal identity, and opened a new connection using its controlled private root.
The request namespace/instance/run, projection IDs and two role bindings must
agree with bootstrap.owner and each other. The new projection is paused/unready
with verification_pending and two unverified bindings (credential_revision=0,
binding_revision=1); the empty initial sealed ruleset has revision=0. The input
cannot supply an already-verified account, mapping, cursor or restored instance.

Before any DDL, require no open transaction, application_id=0, user_version=0
and no application tables/indexes/views/triggers in sqlite_schema. Verify the
writer connection settings under the already acquired owner; this is an explicit
creation path, never a skip-schema flag on `_attach_writer`. One transaction
creates trusted v0001/schema ledger/projection/two binding history and current
rows/empty ruleset/checkpoint(cursor=NULL,coverage=NULL,revision=0). It returns
only after commit and the same exact schema/identity validation used by ordinary
attach. The returned WriterSession owns that same connection; the raw handle is
not given to repositories. On failure/ambiguous commit it closes/invalidate the
connection without deleting, repairing or emptying the database.

If a matching M1-03 bootstrap journal survives a crash, its owner first inspects
the existing DB: an exact committed expected v1 instance uses ordinary attach and
resumes only journal finalization; a rolled-back pristine schema may re-enter this
initializer only for that same journal request; partial/unrelated/mismatching
schema refuses with maintenance_required/consistency_failure. Merely discovering
an empty file without the actual journal does not authorize initialization.
Tests use explicitly test-owned new connections/context; no production fixture
factory or caller boolean certifies locks. This lifecycle is the only exception
to the normal repository projection_id/uow argument convention.

Private M1-02 integration functions are `_attach_writer(connection,
info:OwnerSessionInfo) -> WriterSession` and `_attach_view(connection,
expected_instance:LocalId) -> ReadSession`. They accept already-open sqlite3
connections, never paths. Only M1-03's owner/view adapter imports them in production;
there is no CLI registration or automatic discovery. M1-02 tests import a clearly
test-owned factory that supplies their temporary connection. Python visibility
is not a security boundary: actual lock ownership proof belongs to the M1-03
integration tests, and missing integration cannot be called runtime-ready.

WriterSession records creating thread, connection identity, owner info and an
active/closed flag; every operation rejects a different thread, closed session,
wrong projection instance or lost lifecycle. It exposes `transaction() -> UnitOfWork`
and `close()`, not its raw connection. UnitOfWork is a context manager with no
public commit override: enters BEGIN IMMEDIATE; on success runs relational guards
then COMMIT; on failure ROLLBACK and propagates a fixed StorageFailure. Nesting is
refused. A transaction object is single-use and cannot survive its session close.
ReadSession exposes only fixed repository reads and close; a short read transaction
ends before the caller releases view.lock. No arbitrary callbacks run inside UoW.

Per writer connection settings: autocommit=True with explicit SQL BEGIN/COMMIT/
ROLLBACK; foreign_keys=ON; journal_mode=WAL; synchronous=FULL; busy_timeout=5000;
trusted_schema=OFF; wal_autocheckpoint=1000 pages. These values are verified, not
assumed from previous connection defaults. Readers do not set journal mode, run
checkpoint, change schema or create sidecars. Reader query_only=ON is connection
local defense, not a substitute for read-only open or filesystem/lock ownership.
ReadSession verifies expected schema/instance and existing readable state first.
Five-second BUSY is a controlled database_unavailable outcome, never an unbounded
loop or permission to retry an uncertain remote effect.

Only the writer connection performs checkpoints, outside a write transaction and
without holding a provider network wait. Read methods cap 500 rows and release
their transaction after materializing a closed bounded result; no cursor escapes.
An internal maintenance checkpoint may return controlled busy/partial progress,
but is not needed to justify backup correctness. Only M1-03 owns periodic timing.
M1-02 does not start a checkpoint thread or multiple independent writer handles.

SQLite write/commit errors are not mapped by exposing exception text. Classify
numeric SQLite result code into database_unavailable, persistence_failure or
consistency_failure. If rollback itself fails, commit outcome is ambiguous, or
connection state cannot be proven, invalidate the session and refuse further
mutation. Caller receives no success receipt/cursor promise; next real owner
inspects persistent state using schema/identity and effect keys. Preserve actual
remote facts for later owner recovery; never respond with a fabricated empty DB.

The DB library performs no network, token, terminal, sleep or worker scheduling.
M2 transport-entry callback tests assert connection.in_transaction is false
after mark_dispatch commits and before provider invocation. M1-02's own probe
only proves its transaction lifecycle; it cannot prove future runtime ordering.

## Atomic transitions and replay ownership

| Transaction | Required checks and durable group | Failure and forbidden continuation |
| --- | --- | --- |
| Initialization | `_initialize_database` on supplied pristine owner connection and actual matching journal; schema identity + one projection + two pending bindings + empty ruleset/checkpoint | Existing unknown/partial/unrelated DB is refusal, never replace or import spike |
| Rule publication | Expected current revision, registered normalized inputs; immutable revisions/snapshot + current pointers + audit | Same caller operation replay is handled by M1-03 receipt in same UoW; no new effective_at on replay |
| Admission/re-track | Exact AdmissionRef relationships, policy/preview gate supplied by owning feature, expected untracked/current generation; admission/history + tracked state + initial jobs + audit | Existing mapping blocks recopy; remove allow/blacklist does not re-track; rejected scope writes nothing |
| Stop/blacklist | Exact selected thread/current generation; optional exact-sender rule change + increment/inactive + cancel unstarted jobs/prepared intents + audit | No fanout to all threads/domain; dispatched work still records results; no deletion |
| History page chunks | Same poll/page digest/sequence; events + page membership + pending resolve jobs or selected work | Any failed chunk keeps page incomplete; no cursor movement; replay same immutable identities |
| History origin | checkpoint/initial-H0/approved-recovery-H1 relation, actual checkpoint CAS and one active poll | Starting/abandoning never fabricates coverage or writes H0/H1 into checkpoint; no generic reset |
| Final poll | All page-complete records chained; final cursor/coverage + poll completion + checkpoint revision | No update on missing/failed page; empty success still updates reliable coverage |
| Expansion snapshot | Exact expand_thread job/generation/current run; membership+derived jobs; final count/digest+completion | gen1 proof cannot complete gen3; interrupted >500-message snapshot resumes/restarts with retained work |
| Epoch start | Valid frozen decision/window; H0/H1 committed + partition rows + epoch | No scan before commit; unknown gap without approval cannot create work |
| Claim/prepare | Eligible job/current owner, binding/restore/pause/generation; claim then immutable prepared attempt | No second prepared attempt, no raw in DB, no permission from elapsed claim time |
| Dispatch entry | Same running claim/actor admission, fresh guards; state/certainty/timestamp marker | Failed DB commit means no provider invocation; marker is not proof bytes reached Google |
| Result recording | Original immutable attempt/source/claim; result facts + attempt state/error/recovery job | Post-stop result retained without reactivation; unknown is never ordinary queued insert |
| Mapping verification | Correct target ownership and reviewed direct/fidelity evidence; verified attempt + mapping/history/target set + completed job | Positive insert alone not success; failures preserve effect; search candidates need later reviewed extension |
| Action execution | Exact activation tuple and executed marker; rule/tracking/jobs/audit in same UoW | Repeat marker returns prior effect, cleanup cannot repeat business work; legacy observation cannot enter this API |
| Restore fence | Real maintenance provider; retained validated instance, new namespace/owner + verification_pending + revalidation_required + preserved paused/stopped/job/attempt facts | Missing post-backup rows are not evidence of absence; no write readiness until separate recovery policy |

Structural action replay in DB-07 tests calls the actual action repository and
same-UoW business changes twice: the second reads executed state and performs no
mutation. It does not invent a M1-03 command receipt. Direct CLI rules/stop/init
effects instead require M1-03 to check/store its actual stable request receipt
around these methods in the same UoW; tests of that protocol remain M1-03 gates.
Standalone stop_thread deliberately requires expected_generation and cannot
silently turn a repeated invocation into another increment. Its replaying command
returns its original receipt rather than resubmitting with a newer generation.

## Initialization, schema verification and migration backup

Database application_id is the fixed hexadecimal integer `0x46414354` (ASCII
FACT); user_version is 1 for initial production schema. Both must agree with
schema_metadata and the ordered migration ledger. A coincidental application ID
alone is insufficient: inspect exact tables/columns/indexes/checksums against the
trusted manifest. No arbitrary tables/triggers/views are accepted as Facet state.
Manifest digest is computed from a fixed canonical list of trusted migration
identifiers/checksums; the database cannot supply its own validator.

Initial production registry contains only v0001. There is no supported production
v0 imported from spike or inferred from an empty user_version. The initialize API
requires a pristine newly-created test/owner connection and explicit bootstrap
instance. Transactionally creates schema/metadata, commits, and then the M1-03
bootstrap journal decides when its full root/config/namespace operation is done.
An existing partial bootstrap must follow the exact initialization/attach/refusal
branches above and match that journal; initialization errors never
unlink the existing database, lower user_version or start a new empty instance.

Future migrations are fixed trusted registry steps with exact from/to versions,
source checksum, atomic DDL/data statements and a tested compatibility statement.
No user SQL, runtime downloaded migration, executescript implicit transaction or
arbitrary Python callback. Tests register a clearly test-only predecessor in an
isolated engine fixture; that registration is not available through production
initialization/migrate CLI. No downgrade is supported by schema v1.

Before any existing-state migration, require a real complete coordinated bundle
backup receipt, not a boolean callback or main-DB file copy. The M1-02 interface
is storage-local `MigrationBackupReceipt(bundle_id:LocalId, manifest_digest:Sha256Hex,
state_instance_id:LocalId, request_namespace:LocalId, schema_version:SchemaVersion,
config_revision:Revision, source_credential_revision:Revision,
target_credential_revision:Revision)`, all required. It is supplied only by the
M1-03/M6 maintenance provider after validating durable private manifest/files under
owner/view/credential locks. The DB compares all expected metadata revisions;
the provider proves filesystem completion. No general caller can enable production
migration merely by constructing this dataclass. Until that provider is integrated,
existing-state migration is maintenance_required; initial creation is separate.

M1-02 exports an internal DB snapshot primitive `snapshot_database(source_session,
destination_connection) -> DatabaseSnapshotInfo(schema_version:SchemaVersion,
state_instance_id:LocalId, request_namespace:LocalId, integrity_ok:Literal[True])`.
Connections already belong to the test/maintenance owner; no path argument or
overwrite behavior is exposed. Uses SQLite backup API, not file copy, and verifies
integrity_check plus foreign_key_check on the closed snapshot. A failure yields
no receipt. The provider exclusively creates the 0600 destination and owns file/
directory sync and manifest publication. No credentials enter this helper.

Apply each supported migration's schema/data/version/ledger changes in one explicit
transaction. Failure before commit leaves the previous schema. Uncertain commit
requires session invalidation and reopen inspection of trusted versions, not
blind rerun. No VACUUM, file replacement or config/token write participates in a
claimed SQL-atomic transaction. Those operations use the separately reviewed M6
staged-bundle journal. Rollback is old compatible image plus complete validated
backup when reverse migration is unavailable, never only a live main DB copy.

Restore's DB metadata operation is `fence_restored_instance(uow,
expected_instance:LocalId, old_namespace:LocalId, new_namespace:LocalId,
new_owner_run:LocalId)`; expected instance and old namespace are its exact lineage
CAS, not an invented projection revision. The verified bundle's state_instance_id
is retained as persistent instance identity; request namespace and owner run
rotate. New namespace differs from old/historical receipt namespaces. The owner
run is the actual newly locked maintenance owner, not a fabricated authorization.
It preserves all jobs, mappings,
unknown attempts, paused/stopped fields, while replacing owner/clearing claims only
through intent-aware recovery and setting binding verification pending plus the
independent restore fence. Actual bundle install/rollback belongs to M6, not this
method. Operations after backup may have no row: no negative query reauthorizes
their remote effect. New owner dispatch remains blocked until the applicable
M2-04/M6 recovery decision resolves that broader uncertainty.

This representation is coordinated with M1-04's immutable credential envelopes:
validated bundle instance/binding/credential revisions remain compatible without
rewriting secrets solely to rotate request keys. Preserving instance ID is not
evidence that post-backup operations did not occur. Mixed envelope/DB revisions,
unsupported schema or incomplete bundle still refuse; absent old receipts return
lineage mismatch and never authorize resubmission under a new key. Actual live
profile readiness and restore-effect readiness are separate gates. This follows
frozen writer v1's fresh namespace/owner rule without changing core contracts.

## Privacy, artifact and bounded evidence requirements

No raw mail enters database parameters, temporary files, error/audit records or
backup. The only BLOB is explicitly versioned KeyBytes; arbitrary provider objects
are not accepted. Private rule/account metadata stays in its designated tables,
never duplicated per-message From/To/Subject. No SQL trace callback, row dump or
unfiltered sqlite exception is logged, including DEBUG and failed assertions.

Sentinel tests scan actual logical cells and active DB/WAL/rollback-journal/temp
files before checkpoint/close, plus failure-path logs/outputs and snapshots.
Positive controls retain allowed IDs/rules/bindings; content/credential markers
must be rejected before insertion, not written then deleted. Negative controls
prove each scanner detects leaks in its claimed encoding. ReadPage and CountsSnapshot
are internal typed metadata, not a public export API. No DB, WAL, backup, runtime
or real fixture is uploaded in CI artifacts, images, documentation or PRs.

Use per-test temporary local roots and bounded child PIDs/timeouts. DB-18 kills a
real child only after a named durable boundary is reached, then reopens a real
database independently. Python exceptions are separate fault cases; neither is
a power-loss/physical fsync guarantee. Concurrency tests use separate real read
connections but one legitimate writer owner, plus explicit violating competitors
for rejection tests. No second checkpointing connection is introduced as a
production design. Record linked SQLite 3.53.1 and compile options when tests
actually run; the existing memory SELECT is not storage acceptance.

## Acceptance mapping and counterexamples

All rows are future tests against actual SQLite/repository implementations, not
claims this documentation executed them. P1-02 fixtures are reused only after its
complete compatibility gate is independently reviewed and merged.

| Plan case | Exact proposal subject and required negative control |
| --- | --- |
| DB-01 | Actual interpreter/library compile options, STRICT/FK/WAL/FULL settings; incompatible library refuses, memory SELECT alone insufficient |
| DB-02 | Complete manifest/schema_metadata/migration ledger; add unexpected trigger/table or alter a CHECK and opening rejects |
| DB-03 | `_initialize_database` supplied-connection lifecycle; committed matching bootstrap attaches, rolled-back pristine same journal resumes, partial/mismatched/no-journal refuses without skip flag/second opener |
| DB-04 | Every storage row/union codec and SQL scalar template; wrong tag, surplus fields, invalid nullness, bool-as-count or content-bearing payload rejects with sealed error |
| DB-05 | Projection-aware FKs, nullable groups, immutable rule snapshots; foreign projection references and changed sealed snapshot fail even after current pointer moves |
| DB-06 | All 11 job indexes and stable codec; replay one identity, conflicting thread/read-kind rejected, distinct authorized repair preserved |
| DB-07 | Actual action tuple/marker plus typed same-UoW effects twice; no duplicate changes/audit; explicit separate M1-03 request/IPC consumer pending |
| DB-08 | stop_thread/publish_rules/admit_thread; gen1 expansion complete then stop/retrack gen3 in same epoch cannot reuse run; selected generation increments once, other threads unaffected, removed rule does not re-track |
| DB-09 | claim and exact session run/revision; competing CAS yields one winner, elapsed time cannot steal live ownership |
| DB-10 | prepare/mark_dispatch/stop both orderings; unsent intent cancelled, dispatched factual result retained without scheduling revival |
| DB-11 | Attempt axis CHECKs/unique blockers/result recovery; response loss cannot become queued insert; known response+failed readback not verified |
| DB-12 | verify_mapping/target_ownership/history/thread_targets; mappings and success basis atomic, conflicting target ownership blocked, Spam/Trash distinct |
| DB-13 | Null checkpoint initial H0 poll, ordinary checkpoint poll and expired-cursor recovery H1 poll each succeed only through own relation; interrupted/replayed/empty/multipage cases preserve truthful cursor/coverage and exact CAS; caller-supplied or other-epoch catchup ID cannot complete an epoch |
| DB-14 | Epoch fence before scans and generation-bound expansion runs; 501-item chunk crash/re-fetch changed-set retains prior work; wrong epoch/job/gen proof and partial snapshot cannot complete |
| DB-15 | Known-gap coverage minus persisted 300000000us overlap/effective_at; min Timestamp clamp/future-time refusal; unknown approved range only; expired initial H0/null checkpoint followed by new initial H0 still refuses while gap unresolved; only latest matching approved recovery lineage proceeds |
| DB-16 | Immutable rule_revisions/rulesets, original effective_at; replay and clock rollback do not widen old authorization |
| DB-17 | Real sqlite busy and injected storage failures at execute/commit/rollback; invalid session and no false success/cursor, reopen inspection required |
| DB-18 | Child process kill around transaction commits with actual files; reopened rows distinguish committed/uncommitted, not a claimed physical power-loss simulation |
| DB-19 | snapshot_database plus coordinated receipt revision checks; committed WAL included, bad/incomplete receipt blocks existing-state migration |
| DB-20 | Trusted registry transaction and deliberate test-only predecessor; injected DDL/version failure preserves old schema, future versions refuse downgrade |
| DB-21 | Clean stopped and active readable WAL views; missing sidecars/recovery-needed state refuses without filesystem creation, no immutable-live shortcut |
| DB-22 | Initializer returns same-connection validated WriterSession only after commit; attach rejects pristine/partial, initialization failure closes/invalidate without delete; no fallback opener/skip-schema/lock boolean |
| DB-23 | Restore preserves valid bundle instance/envelope identities but rotates namespace/owner; mixed envelope revisions refuse, absent old receipt and missing post-backup attempt never mean no effect; pause/stop/unknown fences persist |
| DB-24 | Typed input/SQL/error/audit/backup sentinels; inspect actual active files and rollback journals with positive metadata and deliberate leak controls |
| DB-25 | CountsSnapshot unique mappings/exclusive job states/unknown totals; multiple attempts or repaired historical rows do not inflate current unique success |
| DB-26 | UoW lifetime probe at controlled simulated transport entry; later actual M2/M1-03 callbacks must repeat, future network proof not claimed here |
| DB-27 | PageLimit/keyset/index plan/short read transactions/bounded BUSY; no query cursor or unconstrained record collection escapes |
| DB-28 | Actual accepted dependency SHAs, locked install/full tests/lint/format/safety/new exact-head CI plus separate independent implementation review |

## Review, integration and unresolved external gates

This proposal has no accepted design revision until another independent reviewer
approves its exact hash. A change request is normal design work, not user product
authority. The author must not approve this schema or its own later implementation.
The coordinator verified the real M1-01 merge/main CI and complete P1-02 CT merge,
and authorized the normal base carry recorded above. Schema-design acceptance,
final interface alignment and a separate implementation dispatch remain required;
fulfilled dependency gates do not permit the author to waive those reviews.

The version label becomes a frozen storage contract only after those applicable
design gates. M1-03, M1-04 and later feature owners consume the closed storage
surface; their command/credential/policy extensions require their own independent
review. No deferred registry is accepted via a placeholder object or weak bool.
Real provider calls, OAuth, source mail, host deployment and image/release actions
remain outside this documentation-only dispatch. There is no commit, push or PR
authority in the current design step.

Primary SQLite/Python facts and their current WAL advisory are linked in the
approved plan's environment section. This proposal's single writer/checkpoint
design does not claim all library builds safe or replace runtime/version checks.
No actual storage, crash, Gmail, deployment, complete CLI or milestone evidence
is produced by writing this ADR.

### Revision r2 response to independent design review

The r1 hash `2bb3f02beffe12e7f24729a6d35cb156fe31575c3cfdaf93016b3144c45f1abf`
received changes_requested. R2 closes proposed design gaps rather than claiming
tested fixes: R1 adds the three PollOrigin branches and constrained H0/H1 CAS;
R2 persists a fixed recovery overlap and guarded time arithmetic without changing
rule effective_at; R3 adds exact generation-bound expansion runs/items and finite
chunk APIs; R4 defines the sole pristine initialization entry/lifecycle. DB cases
above contain their negative controls. Restore instance representation is aligned
with the credential proposal and frozen writer, subject to both independent
reviews; neither author's unreviewed document overrides the other contract.

Revision r3 makes two r2 review-edge guards explicit: unresolved gap blocks both
ordinary and initial origins, and catch-up identity is derived only by completion
of the same epoch's actual poll. No new table, authority or implementation scope.
